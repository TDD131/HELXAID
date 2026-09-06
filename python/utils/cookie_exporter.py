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
    
    def _get_cookie_db_paths(self, browser: str) -> List[str]:
        """
        Find all candidate cookie database paths across all browser profiles (Default, Profile 1..10, etc).
        
        Args:
            browser: Browser name ('chrome', 'edge', 'brave')
            
        Returns:
            List of absolute paths to existing cookie database files.
        """
        if browser not in self.BROWSER_PATHS:
            return []
            
        localappdata = os.environ.get('LOCALAPPDATA', '')
        if not localappdata:
            return []
            
        browser_info = self.BROWSER_PATHS[browser]
        base_path = os.path.join(localappdata, browser_info['base'])
        if not os.path.isdir(base_path):
            return []
            
        candidate_paths = []
        
        # Check standard default profile first
        for prof in [browser_info['default_profile']] + [f'Profile {i}' for i in range(1, 10)]:
            prof_dir = os.path.join(base_path, prof)
            if not os.path.isdir(prof_dir):
                continue
            for sub in [os.path.join('Network', 'Cookies'), 'Cookies']:
                c_path = os.path.join(prof_dir, sub)
                if os.path.isfile(c_path) and c_path not in candidate_paths:
                    candidate_paths.append(c_path)
                    
        return candidate_paths

    def _get_cookie_db_path(self, browser: str) -> Optional[str]:
        paths = self._get_cookie_db_paths(browser)
        return paths[0] if paths else None
    
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
    
    def _get_master_key(self, browser: str) -> Optional[bytes]:
        """
        Extract and decrypt the AES-256-GCM master key from Chromium's Local State file.
        """
        try:
            if browser not in self.BROWSER_PATHS:
                return None
            localappdata = os.environ.get('LOCALAPPDATA', '')
            if not localappdata:
                return None
            base_path = os.path.join(localappdata, self.BROWSER_PATHS[browser]['base'])
            local_state_path = os.path.join(base_path, 'Local State')
            if not os.path.isfile(local_state_path):
                return None
                
            import json, base64
            with open(local_state_path, 'r', encoding='utf-8') as f:
                local_state = json.load(f)
            encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
            if encrypted_key.startswith(b'DPAPI'):
                encrypted_key = encrypted_key[5:]
                
            try:
                import win32crypt
                unprotected = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
                if unprotected and len(unprotected) > 1:
                    return unprotected[1]
            except Exception:
                pass
                
            crypt32 = ctypes.WinDLL("crypt32.dll")
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [('cbData', ctypes.wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.wintypes.BYTE))]
            in_blob = DATA_BLOB()
            in_blob.cbData = len(encrypted_key)
            in_blob.pbData = (ctypes.wintypes.BYTE * len(encrypted_key))(*encrypted_key)
            out_blob = DATA_BLOB()
            crypt32.CryptUnprotectData.restype = ctypes.wintypes.BOOL
            success = crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob))
            if success and out_blob.pbData:
                key = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                ctypes.windll.kernel32.LocalFree(out_blob.pbData)
                return key
        except Exception as e:
            print(f"[CookieExporter] Failed to get master key for {browser}: {e}")
        return None

    def _decrypt_dpapi_value(self, encrypted_value: bytes, master_key: Optional[bytes] = None) -> str:
        """
        Decrypt a Chromium cookie value using AES-GCM (v10/v11) or legacy DPAPI.
        """
        if not encrypted_value:
            return ""
            
        # Modern Chromium (v10 / v11 AES-256-GCM)
        if len(encrypted_value) >= 31 and (encrypted_value.startswith(b'v10') or encrypted_value.startswith(b'v11')):
            if master_key:
                # 1. Cryptodome / Crypto (dynamic to avoid static IDE unresolved import warnings)
                try:
                    import importlib
                    AES = None
                    for _pkg in ("Cryptodome.Cipher.AES", "Crypto.Cipher.AES"):
                        try:
                            _mod = importlib.import_module(_pkg)
                            AES = getattr(_mod, "AES", _mod)
                            if AES is not None:
                                break
                        except Exception:
                            continue
                    if AES is not None:
                        nonce = encrypted_value[3:15]
                        ciphertext = encrypted_value[15:-16]
                        cipher = AES.new(master_key, AES.MODE_GCM, nonce)
                        return cipher.decrypt(ciphertext).decode('utf-8', errors='ignore')
                except Exception:
                    pass

                # 2. Windows native BCrypt CNG fallback (zero dependencies)
                try:
                    from YouTubeAccountEngine import _bcrypt_gcm_decrypt
                    nonce = encrypted_value[3:15]
                    ciphertext = encrypted_value[15:-16]
                    tag = encrypted_value[-16:]
                    dec_bytes = _bcrypt_gcm_decrypt(master_key, nonce, ciphertext, tag)
                    if dec_bytes:
                        return dec_bytes.decode('utf-8', errors='ignore')
                except Exception:
                    pass
            return ""

        # Try to decode as plaintext UTF-8
        try:
            decoded = encrypted_value.decode('utf-8')
            if all(ord(c) < 128 or ord(c) > 31 for c in decoded):
                return decoded
        except UnicodeDecodeError:
            pass
            
        # Legacy DPAPI decryption
        try:
            import win32crypt
            unprotected = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)
            if unprotected and len(unprotected) > 1 and unprotected[1]:
                return unprotected[1].decode('utf-8', errors='replace')
        except Exception:
            pass

        try:
            crypt32 = ctypes.WinDLL("crypt32.dll")
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [('cbData', ctypes.wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.wintypes.BYTE))]
            input_blob = DATA_BLOB()
            input_blob.cbData = len(encrypted_value)
            input_blob.pbData = (ctypes.wintypes.BYTE * len(encrypted_value))(*encrypted_value)
            output_blob = DATA_BLOB()
            crypt32.CryptUnprotectData.restype = ctypes.wintypes.BOOL
            success = crypt32.CryptUnprotectData(ctypes.byref(input_blob), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output_blob))
            if success and output_blob.pbData:
                decrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
                ctypes.windll.kernel32.LocalFree(output_blob.pbData)
                return decrypted.decode('utf-8', errors='replace')
        except Exception:
            pass
        return ""
    
    def _read_cookies_from_db(
        self, 
        db_path: str, 
        domains: Optional[List[str]] = None,
        master_key: Optional[bytes] = None
    ) -> List[CookieEntry]:
        """
        Read cookies from a SQLite cookie database.
        
        Args:
            db_path: Path to the cookie database file
            domains: Optional list of domain filters (e.g., ['.youtube.com'])
                     If None, all cookies are returned.
            master_key: Optional decrypted AES-256-GCM master key for modern Chromium
        
        Returns:
            List of CookieEntry objects.
        """
        cookies = []
        db_uri = f"file:{db_path}?mode=ro"
        
        try:
            conn = sqlite3.connect(db_uri, uri=True)
        except sqlite3.OperationalError:
            conn = sqlite3.connect(db_path)
            
        try:
            cursor = conn.cursor()
            if domains:
                domain_conditions = []
                params = []
                for domain in domains:
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
                    value = self._decrypt_dpapi_value(encrypted_value, master_key=master_key)
                except Exception:
                    continue
                    
                if not value:
                    continue
                    
                if expires_utc and expires_utc > 0:
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
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
            f.write("# This file was generated by HELXAID Cookie Exporter\n")
            f.write("# Do not edit this file manually.\n\n")
            for cookie in cookies:
                flag = "TRUE" if cookie.domain.startswith('.') else "FALSE"
                secure = "TRUE" if cookie.secure else "FALSE"
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
        """
        candidate_paths = self._get_cookie_db_paths(browser)
        if not candidate_paths:
            raise BrowserNotFoundError(
                f"Browser '{browser}' not found or has no profile. "
                f"Try selecting a different browser."
            )
            
        if progress_callback:
            progress_callback("Preparing cookie database...")
            
        master_key = self._get_master_key(browser)
        all_errors = []
        
        for db_path in candidate_paths:
            temp_db_path = self._copy_cookie_db(db_path)
            if not temp_db_path:
                continue
                
            try:
                if progress_callback:
                    progress_callback("Reading cookies...")
                    
                cookies = self._read_cookies_from_db(temp_db_path, domains, master_key=master_key)
                if cookies and len(cookies) > 0:
                    if progress_callback:
                        progress_callback(f"Exported {len(cookies)} cookies")
                        
                    temp_dir = self._get_temp_dir()
                    self._temp_file_path = os.path.join(
                        temp_dir, 
                        f"yt_cookies_{uuid.uuid4().hex[:12]}.txt"
                    )
                    self._write_netscape_format(cookies, self._temp_file_path)
                    return self._temp_file_path
            except Exception as e:
                all_errors.append(str(e))
            finally:
                if temp_db_path and os.path.exists(temp_db_path):
                    try:
                        os.remove(temp_db_path)
                    except OSError:
                        pass
                        
        raise DatabaseLockedError(
            f"Could not access {browser} cookie database. "
            f"The database may be locked. Try closing {browser} completely "
            f"(check System Tray) or select a different browser."
        )
        
    def get_cookies_dict(self, browser: str, domains: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Extract cookies directly as a key-value dictionary for in-memory session synchronization.
        """
        paths = self._get_cookie_db_paths(browser)
        master_key = self._get_master_key(browser)
        for db_path in paths:
            temp_db_path = self._copy_cookie_db(db_path)
            if not temp_db_path:
                continue
            try:
                cookies = self._read_cookies_from_db(temp_db_path, domains or YOUTUBE_DOMAINS, master_key=master_key)
                if cookies and len(cookies) > 0:
                    res = {}
                    for c in cookies:
                        res[c.name] = c.value
                    if 'SAPISID' in res or '__Secure-3PAPISID' in res or 'SID' in res:
                        return res
            except Exception:
                pass
            finally:
                if temp_db_path and os.path.exists(temp_db_path):
                    try:
                        os.remove(temp_db_path)
                    except OSError:
                        pass
        return {}

    def auto_import_youtube_cookies(self) -> Tuple[bool, str, Dict[str, str]]:
        """
        Automatically search Chrome, Edge, and Brave to extract active YouTube/Google session cookies.
        
        Returns:
            Tuple of (success: bool, browser_name: str, cookies_dict: Dict[str, str])
        """
        for b in ['chrome', 'edge', 'brave']:
            try:
                c_dict = self.get_cookies_dict(b, YOUTUBE_DOMAINS)
                if c_dict and ('SAPISID' in c_dict or '__Secure-3PAPISID' in c_dict or 'SID' in c_dict):
                    return True, b, c_dict
            except Exception:
                continue
        return False, "", {}

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
