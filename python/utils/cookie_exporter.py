"""
Chrome Cookie Lock Bypass - Cookie Exporter Module

Exports cookies from Chromium-based browsers (Chrome, Edge, Brave) to a temporary
Netscape-format file that yt-dlp can consume. Handles locked cookie databases by
using Windows Backup Semantics to read files even when Chrome holds an exclusive lock.

Key Features:
- Bypasses Chrome 114+ exclusive database lock using FILE_FLAG_BACKUP_SEMANTICS
- Decrypts DPAPI-encrypted cookie values on Windows
- Exports to Netscape format (yt-dlp compatible)
- Automatic cleanup of temporary cookie files
- Supports Chrome, Edge, and Brave browsers

Security & Privacy:
- Temp cookies stored in %TEMP%\helxaid_cookies\ with random filename
- Deleted immediately after yt-dlp uses them
- No cookie values logged in debug output

Component Name: CookieExporter
"""

import os
import sys
import sqlite3
import tempfile
import uuid
import shutil
import ctypes
import ctypes.wintypes
import time
from typing import Optional, List, Tuple, Dict
from pathlib import Path
from dataclasses import dataclass
from contextlib import contextmanager


# Windows API constants for file access
FILE_READ_ATTRIBUTES = 0x0080
FILE_READ_DATA = 0x0001
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
GENERIC_READ = 0x80000000

# DPAPI constants for cookie decryption
CRYPTPROTECT_UI_FORBIDDEN = 0x01


@dataclass
class CookieEntry:
    """
    Represents a single cookie entry for export.
    
    Attributes:
        domain: Cookie domain (e.g., ".youtube.com")
        path: Cookie path (usually "/")
        secure: Whether cookie requires HTTPS
        expires: Unix timestamp of expiration (0 = session cookie)
        name: Cookie name
        value: Decrypted cookie value
    """
    domain: str
    path: str
    secure: bool
    expires: int
    name: str
    value: str


class CookieExporterError(Exception):
    """Base exception for cookie export failures."""
    pass


class DatabaseLockedError(CookieExporterError):
    """Raised when the cookie database is locked and cannot be accessed."""
    pass


class DecryptionError(CookieExporterError):
    """Raised when cookie value decryption fails."""
    pass


class BrowserNotFoundError(CookieExporterError):
    """Raised when the specified browser is not installed or has no profile."""
    pass


class CookieExporter:
    """
    Exports cookies from Chromium-based browsers to Netscape format files.
    
    This class handles the Chrome 114+ exclusive database lock problem by using
    Windows Backup Semantics to read the SQLite database file even when Chrome
    holds an exclusive lock on it.
    
    Usage:
        exporter = CookieExporter()
        cookie_file = exporter.export_cookies('chrome', domains=['.youtube.com'])
        # Pass cookie_file to yt-dlp via --cookies parameter
        exporter.cleanup()  # Delete temp file when done
    
    The exported file is in Netscape format, compatible with yt-dlp's --cookies option.
    """
    
    # Browser profile paths relative to LOCALAPPDATA
    BROWSER_PATHS = {
        'chrome': {
            'base': os.path.join('Google', 'Chrome', 'User Data'),
            'default_profile': 'Default',
            'alt_profiles': ['Profile 1', 'Profile 2', 'Profile 3'],
        },
        'edge': {
            'base': os.path.join('Microsoft', 'Edge', 'User Data'),
            'default_profile': 'Default',
            'alt_profiles': ['Profile 1', 'Profile 2', 'Profile 3'],
        },
        'brave': {
            'base': os.path.join('BraveSoftware', 'Brave-Browser', 'User Data'),
            'default_profile': 'Default',
            'alt_profiles': ['Profile 1', 'Profile 2', 'Profile 3'],
        },
    }
    
    # Temp directory for cookie files (created on demand)
    TEMP_COOKIE_DIR = 'helxaid_cookies'
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        """
        Initialize the cookie exporter.
        
        Args:
            max_retries: Maximum number of retry attempts for locked database
            retry_delay: Base delay in seconds between retries (exponential backoff)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._temp_file_path: Optional[str] = None
        self._temp_dir: Optional[str] = None
        
    @property
    def temp_file_path(self) -> Optional[str]:
        """Returns the path to the temporary cookie file, if created."""
        return self._temp_file_path
    
    def _get_temp_dir(self) -> str:
        """
        Get or create the temporary directory for cookie files.
        
        Returns:
            Absolute path to the temp directory.
        """
        if self._temp_dir is None:
            temp_base = os.environ.get('TEMP', tempfile.gettempdir())
            self._temp_dir = os.path.join(temp_base, self.TEMP_COOKIE_DIR)
            os.makedirs(self._temp_dir, exist_ok=True)
        return self._temp_dir
    
    def _get_cookie_db_path(self, browser: str) -> Optional[str]:
        """
        Find the path to the browser's cookie database.
        
        Checks both the legacy 'Cookies' file and the newer 'Network/Cookies' location.
        Also checks alternate profiles if the default profile doesn't have cookies.
        
        Args:
            browser: Browser name ('chrome', 'edge', 'brave')
            
        Returns:
            Absolute path to the cookie database file, or None if not found.
        """
        if browser not in self.BROWSER_PATHS:
            return None
            
        localappdata = os.environ.get('LOCALAPPDATA', '')
        if not localappdata:
            return None
            
        browser_info = self.BROWSER_PATHS[browser]
        base_path = os.path.join(localappdata, browser_info['base'])
        
        # List of profiles to check (default first, then alternates)
        profiles = [browser_info['default_profile']] + browser_info['alt_profiles']
        
        for profile in profiles:
            profile_path = os.path.join(base_path, profile)
            if not os.path.isdir(profile_path):
                continue
                
            # Check both legacy and new cookie locations
            cookie_paths = [
                os.path.join(profile_path, 'Network', 'Cookies'),  # Chrome 114+ new location
                os.path.join(profile_path, 'Cookies'),             # Legacy location
            ]
            
            for cookie_path in cookie_paths:
                if os.path.isfile(cookie_path):
                    return cookie_path
                    
        return None
    
    def _copy_locked_file_with_backup_semantics(self, src_path: str, dst_path: str) -> bool:
        """
        Copy a file that may be locked by another process using Windows Backup Semantics.
        
        This uses the FILE_FLAG_BACKUP_SEMANTICS flag which allows reading files even
        when they're opened exclusively by another process (like Chrome's cookie database).
        This requires the SeBackupPrivilege, but on Windows 10+ this is typically available
        to the current user for their own files.
        
        Args:
            src_path: Path to the source (possibly locked) file
            dst_path: Path where the copy should be created
            
        Returns:
            True if copy succeeded, False otherwise.
        """
        kernel32 = ctypes.windll.kernel32
        
        # Convert paths to wide strings for Windows API
        src_wide = ctypes.create_unicode_buffer(src_path)
        dst_wide = ctypes.create_unicode_buffer(dst_path)
        
        # Open source file with Backup Semantics
        # This allows reading even when the file is exclusively locked
        src_handle = kernel32.CreateFileW(
            src_wide,
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,  # Security attributes
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_SEQUENTIAL_SCAN,
            None   # Template file
        )
        
        if src_handle == -1:  # INVALID_HANDLE_VALUE
            return False
            
        try:
            # Create destination file
            dst_handle = kernel32.CreateFileW(
                dst_wide,
                0x40000000,  # GENERIC_WRITE
                0,           # No sharing
                None,
                1,           # CREATE_ALWAYS
                0x80,        # FILE_ATTRIBUTE_NORMAL
                None
            )
            
            if dst_handle == -1:
                return False
                
            try:
                # Read and copy in chunks
                buffer_size = 65536  # 64KB chunks
                buffer = ctypes.create_string_buffer(buffer_size)
                bytes_read = ctypes.wintypes.DWORD()
                bytes_written = ctypes.wintypes.DWORD()
                
                while True:
                    success = kernel32.ReadFile(
                        src_handle,
                        buffer,
                        buffer_size,
                        ctypes.byref(bytes_read),
                        None
                    )
                    
                    if not success or bytes_read.value == 0:
                        break
                        
                    success = kernel32.WriteFile(
                        dst_handle,
                        buffer,
                        bytes_read.value,
                        ctypes.byref(bytes_written),
                        None
                    )
                    
                    if not success or bytes_written.value != bytes_read.value:
                        return False
                        
                return True
            finally:
                kernel32.CloseHandle(dst_handle)
        finally:
            kernel32.CloseHandle(src_handle)
            
        return False
    
    def _copy_cookie_db(self, db_path: str) -> Optional[str]:
        """
        Copy the cookie database to a temporary location.
        
        First tries a normal copy (fast), then falls back to Backup Semantics
        if the file is locked.
        
        Args:
            db_path: Path to the original cookie database
            
        Returns:
            Path to the temporary copy, or None if copy failed.
        """
        temp_dir = self._get_temp_dir()
        temp_db_name = f"cookies_{uuid.uuid4().hex[:12]}.db"
        temp_db_path = os.path.join(temp_dir, temp_db_name)
        
        # First try normal copy (works if browser is closed)
        try:
            shutil.copy2(db_path, temp_db_path)
            return temp_db_path
        except (PermissionError, OSError):
            # File is locked, try Backup Semantics
            pass
            
        # Try Backup Semantics for locked file
        if self._copy_locked_file_with_backup_semantics(db_path, temp_db_path):
            return temp_db_path
            
        return None
    
    def _decrypt_dpapi_value(self, encrypted_value: bytes) -> str:
        """
        Decrypt a DPAPI-encrypted cookie value.
        
        Chromium browsers on Windows encrypt cookie values using DPAPI
        (Data Protection API) with the current user's credentials.
        
        Args:
            encrypted_value: The encrypted cookie value bytes
            
        Returns:
            Decrypted cookie value as a string.
            
        Raises:
            DecryptionError: If decryption fails.
        """
        if not encrypted_value:
            return ""
            
        # Check if this is actually encrypted (Chromium prefix)
        # Chromium cookies start with a version prefix: v10 (0x76 0x31 0x30)
        # or v11 (0x76 0x31 0x31) for encrypted values
        if len(encrypted_value) >= 3:
            prefix = encrypted_value[:3]
            if prefix == b'v10' or prefix == b'v11':
                # This is a Chromium-encrypted value, strip the prefix
                encrypted_value = encrypted_value[3:]
        
        # If the value is empty or just plaintext, return as-is
        if not encrypted_value:
            return ""
            
        # Try to decode as UTF-8 first (might be unencrypted)
        try:
            decoded = encrypted_value.decode('utf-8')
            if all(ord(c) < 128 or ord(c) > 31 for c in decoded):
                return decoded
        except UnicodeDecodeError:
            pass
            
        # Use DPAPI to decrypt
        crypt32 = ctypes.windll.crypt32
        
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ('cbData', ctypes.wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.wintypes.BYTE))
            ]
            
        # Prepare input blob
        input_blob = DATA_BLOB()
        input_blob.cbData = len(encrypted_value)
        input_blob.pbData = (ctypes.wintypes.BYTE * len(encrypted_value))(*encrypted_value)
        
        # Prepare output blob
        output_blob = DATA_BLOB()
        
        # Decrypt
        success = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,  # Description (optional)
            None,  # Entropy (optional)
            None,  # Reserved
            None,  # Prompt structure
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob)
        )
        
        if not success:
            raise DecryptionError("DPAPI decryption failed")
            
        # Extract decrypted data
        try:
            decrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
            return decrypted.decode('utf-8', errors='replace')
        finally:
            # Free the output buffer
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)
    
    def _read_cookies_from_db(
        self, 
        db_path: str, 
        domains: Optional[List[str]] = None
    ) -> List[CookieEntry]:
        """
        Read cookies from a SQLite cookie database.
        
        Args:
            db_path: Path to the cookie database file
            domains: Optional list of domain filters (e.g., ['.youtube.com'])
                     If None, all cookies are returned.
        
        Returns:
            List of CookieEntry objects.
            
        Raises:
            sqlite3.Error: If database query fails.
        """
        cookies = []
        
        # Connect to the database in read-only mode
        # URI mode allows us to specify ?mode=ro for read-only
        db_uri = f"file:{db_path}?mode=ro"
        
        try:
            conn = sqlite3.connect(db_uri, uri=True)
        except sqlite3.OperationalError:
            # Fall back to normal connection if URI mode fails
            conn = sqlite3.connect(db_path)
            
        try:
            cursor = conn.cursor()
            
            # Build query with optional domain filter
            if domains:
                # Create LIKE patterns for each domain
                # Match both exact domain and subdomain patterns
                domain_conditions = []
                params = []
                for domain in domains:
                    # Clean domain for matching
                    clean_domain = domain.lstrip('.')
                    domain_conditions.append(
                        "(host_key = ? OR host_key LIKE ? OR host_key = ?)"
                    )
                    params.extend([
                        clean_domain,
                        f"%.{clean_domain}",
                        f".{clean_domain}"
                    ])
                    
                query = f"""
                    SELECT host_key, path, is_secure, expires_utc, name, encrypted_value
                    FROM cookies
                    WHERE {' OR '.join(domain_conditions)}
                """
                cursor.execute(query, params)
            else:
                query = """
                    SELECT host_key, path, is_secure, expires_utc, name, encrypted_value
                    FROM cookies
                """
                cursor.execute(query)
            
            for row in cursor.fetchall():
                host_key, path, is_secure, expires_utc, name, encrypted_value = row
                
                try:
                    # Decrypt the cookie value
                    value = self._decrypt_dpapi_value(encrypted_value)
                except DecryptionError:
                    # Skip cookies we can't decrypt
                    continue
                    
                # Convert Chrome timestamp to Unix timestamp
                # Chrome uses Windows FILETIME (100-nanosecond intervals since Jan 1, 1601)
                # FILETIME epoch: 11644473600 seconds before Unix epoch
                if expires_utc and expires_utc > 0:
                    # Chrome stores timestamps in microseconds since 1601
                    # Convert to Unix timestamp
                    try:
                        unix_timestamp = int((expires_utc / 1000000) - 11644473600)
                    except (ValueError, TypeError):
                        unix_timestamp = 0
                else:
                    unix_timestamp = 0
                    
                cookies.append(CookieEntry(
                    domain=host_key,
                    path=path or '/',
                    secure=bool(is_secure),
                    expires=unix_timestamp,
                    name=name,
                    value=value
                ))
                
        finally:
            conn.close()
            
        return cookies
    
    def _write_netscape_format(self, cookies: List[CookieEntry], output_path: str) -> None:
        """
        Write cookies to a file in Netscape format.
        
        This format is compatible with yt-dlp's --cookies option.
        
        Format:
        # Netscape HTTP Cookie File
        # https://curl.haxx.se/rfc/cookie_spec.html
        # This is a generated file! Do not edit.
        
        domain	FLAG	path	secure	expiry	name	value
        
        Args:
            cookies: List of CookieEntry objects to write
            output_path: Path to the output file
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
            f.write("# This file was generated by HELXAID Cookie Exporter\n")
            f.write("# Do not edit this file manually.\n\n")
            
            # Write each cookie
            for cookie in cookies:
                # Format: domain	FLAG	path	secure	expiry	name	value
                # FLAG is TRUE if domain starts with '.', FALSE otherwise
                flag = "TRUE" if cookie.domain.startswith('.') else "FALSE"
                secure = "TRUE" if cookie.secure else "FALSE"
                
                # Escape special characters in value (tab, newline, backslash)
                value = cookie.value.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n')
                
                f.write(f"{cookie.domain}\t{flag}\t{cookie.path}\t{secure}\t{cookie.expires}\t{cookie.name}\t{value}\n")
    
    def export_cookies(
        self, 
        browser: str, 
        domains: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None
    ) -> Optional[str]:
        """
        Export cookies from the specified browser to a temporary file.
        
        This is the main entry point for cookie export. It handles:
        1. Finding the browser's cookie database
        2. Copying the database (with lock bypass if needed)
        3. Reading and decrypting cookies
        4. Writing to Netscape format file
        
        Args:
            browser: Browser name ('chrome', 'edge', 'brave')
            domains: Optional list of domains to filter (e.g., ['.youtube.com'])
                     If None, exports all cookies (not recommended for privacy)
            progress_callback: Optional callback for progress updates
                               Signature: callback(message: str)
        
        Returns:
            Path to the temporary cookie file, or None if export failed.
            The caller is responsible for calling cleanup() when done.
            
        Raises:
            BrowserNotFoundError: If browser is not installed or has no profile
            DatabaseLockedError: If database is locked and all retries failed
            CookieExporterError: For other export failures
        """
        if progress_callback:
            progress_callback(f"Finding {browser} profile...")
            
        # Find cookie database
        db_path = self._get_cookie_db_path(browser)
        if not db_path:
            raise BrowserNotFoundError(
                f"Browser '{browser}' not found or has no profile. "
                f"Try selecting a different browser."
            )
            
        if progress_callback:
            progress_callback("Preparing cookie database...")
            
        # Copy database with retries
        temp_db_path = None
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                temp_db_path = self._copy_cookie_db(db_path)
                if temp_db_path:
                    break
            except Exception as e:
                last_error = e
                
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                if progress_callback:
                    progress_callback(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
                
        if not temp_db_path:
            raise DatabaseLockedError(
                f"Could not access {browser} cookie database. "
                f"The database may be locked. Try closing {browser} completely "
                f"(check System Tray) or select a different browser."
            )
            
        try:
            if progress_callback:
                progress_callback("Reading cookies...")
                
            # Read cookies from the copied database
            cookies = self._read_cookies_from_db(temp_db_path, domains)
            
            if not cookies:
                # No cookies found - might be wrong domain or empty profile
                return None
                
            if progress_callback:
                progress_callback(f"Exported {len(cookies)} cookies")
                
            # Create output file
            temp_dir = self._get_temp_dir()
            self._temp_file_path = os.path.join(
                temp_dir, 
                f"yt_cookies_{uuid.uuid4().hex[:12]}.txt"
            )
            
            # Write in Netscape format
            self._write_netscape_format(cookies, self._temp_file_path)
            
            return self._temp_file_path
            
        finally:
            # Clean up the temporary database copy
            if temp_db_path and os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except OSError:
                    pass
                    
    def cleanup(self) -> None:
        """
        Remove the temporary cookie file if it exists.
        
        This should be called after yt-dlp has finished using the cookies.
        For security, always call this when done with the exported cookies.
        """
        if self._temp_file_path and os.path.exists(self._temp_file_path):
            try:
                os.remove(self._temp_file_path)
            except OSError:
                pass
            self._temp_file_path = None
            
    def __del__(self):
        """Ensure cleanup on garbage collection."""
        self.cleanup()


@contextmanager
def exported_cookies(
    browser: str, 
    domains: Optional[List[str]] = None,
    progress_callback: Optional[callable] = None
):
    """
    Context manager for cookie export with automatic cleanup.
    
    Usage:
        with exported_cookies('chrome', ['.youtube.com']) as cookie_file:
            if cookie_file:
                # Pass cookie_file to yt-dlp via --cookies
                cmd.extend(['--cookies', cookie_file])
            else:
                # Fall back to --cookies-from-browser
                pass
        # Cookie file is automatically cleaned up when exiting context
    
    Args:
        browser: Browser name ('chrome', 'edge', 'brave')
        domains: Optional list of domains to filter
        progress_callback: Optional callback for progress updates
    
    Yields:
        Path to the temporary cookie file, or None if export failed.
    """
    exporter = CookieExporter()
    cookie_file = None
    
    try:
        cookie_file = exporter.export_cookies(browser, domains, progress_callback)
        yield cookie_file
    finally:
        exporter.cleanup()


def get_available_browsers() -> List[str]:
    """
    Get a list of browsers with cookie databases available on this system.
    
    Returns:
        List of browser names that have cookie databases present.
    """
    available = []
    
    for browser in CookieExporter.BROWSER_PATHS.keys():
        db_path = CookieExporter()._get_cookie_db_path(browser)
        if db_path:
            available.append(browser)
            
    return available


# YouTube-related domains for cookie filtering
YOUTUBE_DOMAINS = [
    '.youtube.com',
    'youtube.com',
    '.google.com',
    'google.com',
    '.accounts.google.com',
]
