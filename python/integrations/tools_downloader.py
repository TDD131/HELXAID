"""
Tools Downloader Module for HELXAID Game Launcher
Handles auto-download of RyzenAdj, FFmpeg, and LibreHardwareMonitor to AppData.
"""

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QGraphicsDropShadowEffect, QToolButton, QMenu, QFileDialog, QScrollArea
)
from PySide6.QtCore import Qt, QPoint, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QIcon
import os
import sys
import urllib.request
import zipfile
import tempfile
import shutil
import uuid
from typing import Optional, Tuple, Callable, List, Dict, Any, Union

# AppData tools directory (Hard fallback to Roaming to prevent PermissionErrors)
DEFAULT_APPDATA = os.path.expanduser("~\\AppData\\Roaming")
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", DEFAULT_APPDATA), "HELXAID")
TOOLS_DIR = os.path.join(APPDATA_DIR, "tools")

# Tool subdirectories
RYZENADJ_DIR = os.path.join(TOOLS_DIR, "ryzenadj")
FFMPEG_DIR = os.path.join(TOOLS_DIR, "ffmpeg")
LIBREHWMON_DIR = os.path.join(TOOLS_DIR, "librehardwaremonitor")
HWINFO_DIR = os.path.join(TOOLS_DIR, "hwinfo")
AHK_DIR = os.path.join(TOOLS_DIR, "ahk")

# Download URLs
RYZENADJ_URL = "https://github.com/FlyGoat/RyzenAdj/releases/latest/download/ryzenadj-win64.zip"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
LIBREHWMON_URL = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.4/LibreHardwareMonitor-net472.zip"
AHK_URL = "https://www.autohotkey.com/download/ahk.zip"
# HWiNFO Portable (~5MB, latest stable version)
HWINFO_URL = "https://www.hwinfo.com/files/hwi_848.zip"  # v8.48 portable

# Checksums for verifying download integrity (SHA256)
# Note: RyzenAdj uses dynamic version checking instead of a hardcoded checksum
# because it points to the "latest" release URL which changes with every new release.
CHECKSUMS = {
    "ffmpeg": "bd0a32dc485304724a7ba55bd5dd74b0ed6df3432770cd43ec0cb666d9f78310",  # ffmpeg-release-essentials.zip
    "librehwmon": "d2e397cc4d33d65c6493dff83b9335bc341a3af31caafceef83f717fdab37448", # v0.9.4 net472
    "ahk": "d1a6d71b8be8fa5ab62f8cb20dffdf7c05b8ef84cfef9262cfb30cd7119ffbb7"    # ahk.zip v1.1.37.02
}


def calculate_checksum(file_path: str, algorithm: str = "sha256") -> str:
    """
    Calculate checksum of a file.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (sha256 or md5)
    
    Returns:
        Hex digest string
    """
    import hashlib
    
    hash_func = hashlib.sha256() if algorithm == "sha256" else hashlib.md5()
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def get_ryzenadj_path() -> str:
    """Get path to ryzenadj.exe in AppData."""
    return os.path.join(RYZENADJ_DIR, "ryzenadj.exe")


def get_ffmpeg_path() -> str:
    """Get path to ffmpeg.exe in AppData."""
    return os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")


def get_ahk_path() -> str:
    """Get path to AutoHotkey.exe in AppData tools or fallback plugins directory."""
    appdata_ahk = os.path.join(AHK_DIR, "AutoHotkey.exe")
    if os.path.exists(appdata_ahk):
        return appdata_ahk
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    plugin_ahk = os.path.join(base_dir, "plugins", "ahk", "AutoHotkey.exe")
    if os.path.exists(plugin_ahk):
        return plugin_ahk
    return appdata_ahk


def is_ahk_installed() -> bool:
    """Check if AutoHotkey.exe exists in AppData tools or plugins."""
    return os.path.exists(get_ahk_path())


def download_ahk(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, str]:
    """
    Downloads AutoHotkey v1.1 portable zip, extracts AutoHotkeyU64.exe,
    and places it in %APPDATA%/HELXAID/tools/ahk/AutoHotkey.exe using CRC-32 structural validation.
    """
    import os, shutil, tempfile, uuid
    
    target_dir = AHK_DIR
    os.makedirs(target_dir, exist_ok=True)
    target_exe = os.path.join(target_dir, "AutoHotkey.exe")
    
    if os.path.exists(target_exe):
        return True, target_exe

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, f"ahk-{uuid.uuid4().hex}.zip")
    
    try:
        success, error = download_file(
            AHK_URL,
            zip_path,
            progress_callback,
            expected_checksum=None
        )
        if not success:
            return False, f"Failed to download AHK: {error}"

        # Extract with CRC-32 integrity validation
        extract_target = os.path.join(temp_dir, "extracted")
        success, error = extract_zip(zip_path, extract_target)
        if not success:
            return False, f"Failed to extract AHK: {error}"

        ahk_u64 = os.path.join(extract_target, "AutoHotkeyU64.exe")
        if not os.path.exists(ahk_u64):
            ahk_u64 = os.path.join(extract_target, "AutoHotkey.exe")
        
        if os.path.exists(ahk_u64) and os.path.getsize(ahk_u64) > 0:
            shutil.copy2(ahk_u64, target_exe)
        else:
            return False, "AutoHotkey binary not found inside archive."

        print(f"[ToolsDownloader] Downloaded AutoHotkey to: {target_exe}")
        return True, target_exe
    except Exception as e:
        print(f"[ToolsDownloader] Failed to download AHK: {e}")
        return False, f"Failed to download AHK: {e}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)



def get_ryzenadj_installed_version() -> Optional[str]:
    """
    Get the version of the currently installed RyzenAdj exe WITHOUT running it.

    RyzenAdj needs AMD hardware access (SMU/kernel driver), so running it
    without admin rights or on non-AMD hardware hangs indefinitely. Instead
    we read the Windows file version resource embedded in the PE header using
    the win32api module (available on Windows), which is purely a file read.

    Fallback chain:
      1. win32api.GetFileVersionInfo  - fast, no process spawn
      2. Return None                  - safe no-op if pywin32 not installed

    Returns:
        Version string like "v0.14.0", or None if not installed / unreadable.
    """
    exe = get_ryzenadj_path()
    if not os.path.exists(exe):
        return None
    try:
        # pywin32 is typically available in the HELXAID venv.
        # Reading file version info does NOT spawn a process.
        import win32api  # type: ignore
        info = win32api.GetFileVersionInfo(exe, "\\")
        ms = info["FileVersionMS"]
        ls = info["FileVersionLS"]
        major = (ms >> 16) & 0xFFFF
        minor = ms & 0xFFFF
        patch = (ls >> 16) & 0xFFFF
        return f"v{major}.{minor}.{patch}"
    except Exception:
        # pywin32 not installed, or file has no version resource - that's fine.
        return None


def get_ryzenadj_latest_version() -> Optional[str]:
    """
    Query the GitHub API for the latest RyzenAdj release tag.

    Uses the public GitHub releases API endpoint (no auth required for public
    repos at normal request rates).

    Returns:
        Tag name string like "v0.14.0", or None on network error.
    """
    import urllib.request
    import json
    api_url = "https://api.github.com/repos/FlyGoat/RyzenAdj/releases/latest"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "HELXAID-Launcher", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("tag_name")  # e.g. "v0.14.0"
    except Exception:
        return None


def is_ryzenadj_available() -> bool:
    """Check if RyzenAdj is available (AppData or legacy assets)."""
    # Check AppData first
    if os.path.exists(get_ryzenadj_path()):
        return True
    
    # Fallback: check legacy assets folder (for development)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        legacy_path = os.path.join(script_dir, "assets", "ryzenadj.exe")
        return os.path.exists(legacy_path)
    except:
        return False


def get_ffprobe_path() -> str:
    """Get path to ffprobe.exe in AppData."""
    return os.path.join(FFMPEG_DIR, "bin", "ffprobe.exe")


def is_ffmpeg_available() -> bool:
    """Check if FFmpeg is available in AppData tools path."""
    return os.path.exists(get_ffmpeg_path()) or os.path.exists(os.path.join(FFMPEG_DIR, "ffmpeg.exe"))


def get_librehwmon_path() -> str:
    """Get path to LibreHardwareMonitor.exe in AppData."""
    return os.path.join(LIBREHWMON_DIR, "LibreHardwareMonitor.exe")


def get_librehwmon_dll_path() -> str:
    """Get path to LibreHardwareMonitorLib.dll for Python integration."""
    return os.path.join(LIBREHWMON_DIR, "LibreHardwareMonitorLib.dll")


def is_librehwmon_available() -> bool:
    """Check if LibreHardwareMonitor is available."""
    return os.path.exists(get_librehwmon_path())


def get_hwinfo_path() -> str:
    """Get path to HWiNFO64.exe in AppData."""
    return os.path.join(HWINFO_DIR, "HWiNFO64.exe")


def get_hwinfo32_path() -> str:
    """Get path to HWiNFO32.exe in AppData (for 32-bit systems)."""
    return os.path.join(HWINFO_DIR, "HWiNFO32.exe")


def is_hwinfo_available() -> bool:
    """Check if HWiNFO is available."""
    return os.path.exists(get_hwinfo_path()) or os.path.exists(get_hwinfo32_path())


# Aliases for backward compatibility and intuitive naming
is_ffmpeg_installed = is_ffmpeg_available
is_ryzenadj_installed = is_ryzenadj_available
is_lhm_installed = is_librehwmon_available
is_librehwmon_installed = is_librehwmon_available





def download_file(url: str, dest_path: str, progress_callback: Optional[Callable[[int, int], None]] = None, expected_checksum: Optional[str] = None, checksum_algorithm: str = "sha256") -> Tuple[bool, Optional[str]]:
    """
    Download a file from URL to destination path.
    
    Args:
        url: Download URL
        dest_path: Destination file path
        progress_callback: Optional callback(downloaded_bytes, total_bytes)
        expected_checksum: Optional expected checksum for verification
        checksum_algorithm: Hash algorithm (sha256 or md5)
    
    Returns:
        (success, error_message)
    """
    try:
        # Ensure destination directory exists
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Create request with browser-like headers to avoid 403 blocks
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        
        with urllib.request.urlopen(request, timeout=60) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 8192
            
            with open(dest_path, "wb") as f:
                while True:
                    block = response.read(block_size)
                    if not block:
                        break
                    f.write(block)
                    downloaded += len(block)
                    
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)
        
        # Verify checksum if provided
        if expected_checksum:
            print(f"[Tools] Verifying checksum ({checksum_algorithm})...")
            actual_checksum = calculate_checksum(dest_path, checksum_algorithm)
            if actual_checksum.lower() != expected_checksum.lower():
                print(f"[Tools] Checksum mismatch!")
                print(f"[Tools] Expected: {expected_checksum}")
                print(f"[Tools] Actual:   {actual_checksum}")
                try:
                    os.remove(dest_path)
                except:
                    pass
                return False, f"Checksum verification failed: file corrupted or wrong version"
            print(f"[Tools] Checksum verified successfully")
        
        return True, None
        
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"URL Error: {e.reason}"

def extract_zip(zip_path: str, dest_dir: str, flatten: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Safely extract a ZIP file to destination directory with pre-extraction CRC-32 integrity validation.
    
    Args:
        zip_path: Path to ZIP file
        dest_dir: Destination directory
        flatten: If True, extract files directly without preserving folder structure
    
    Returns:
        (success, error_message)
    """
    import zipfile, os, shutil
    
    if not zip_path or not os.path.exists(zip_path):
        return False, "ZIP file does not exist."
        
    if os.path.getsize(zip_path) == 0:
        return False, "Downloaded file is empty (0 bytes)."
        
    if not zipfile.is_zipfile(zip_path):
        return False, "Invalid or corrupted ZIP archive (not a valid zip format)."
        
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Full CRC-32 integrity pass across all archive members
            corrupted_file = zip_ref.testzip()
            if corrupted_file is not None:
                return False, f"ZIP CRC-32 verification failed on '{corrupted_file}'. Archive is corrupted."
                
            if flatten:
                for member in zip_ref.namelist():
                    filename = os.path.basename(member)
                    if filename:  # Skip directories
                        source = zip_ref.open(member)
                        target = open(os.path.join(dest_dir, filename), "wb")
                        with source, target:
                            shutil.copyfileobj(source, target)
            else:
                zip_ref.extractall(dest_dir)
        
        return True, None
        
    except zipfile.BadZipFile as e:
        return False, f"Bad ZIP archive: {e}"
    except Exception as e:
        return False, f"Extraction failed: {e}"


def atomic_install_tool_archive(
    zip_path: str,
    target_dir: str,
    required_binaries: List[str],
    nested_subfolder_prefix: Optional[str] = None,
    flatten: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Atomically validate, extract, and install a tool archive into target_dir.
    
    Handles Windows in-use files and locked DLLs gracefully via rename-swap and selective overwrite.
    
    Returns:
        (success, error_message)
    """
    import os, shutil, tempfile, uuid, stat
    
    staging_dir = os.path.join(tempfile.gettempdir(), f"helxaid_stage_{uuid.uuid4().hex}")
    
    try:
        # Step 1: Deep CRC-32 extraction to staging
        success, error = extract_zip(zip_path, staging_dir, flatten=flatten)
        if not success:
            return False, f"Archive extraction failed: {error}"
            
        source_root = staging_dir
        # Step 2: Handle nested folder structure if applicable
        if nested_subfolder_prefix:
            subfolders = [
                f for f in os.listdir(staging_dir) 
                if os.path.isdir(os.path.join(staging_dir, f)) and f.lower().startswith(nested_subfolder_prefix.lower())
            ]
            if subfolders:
                source_root = os.path.join(staging_dir, subfolders[0])
                
        # Step 3: Verify required binaries exist & non-empty in staging
        missing = []
        for req in required_binaries:
            req_path = os.path.join(source_root, req)
            if not os.path.exists(req_path) or os.path.getsize(req_path) == 0:
                alt_req_path = os.path.join(source_root, os.path.basename(req))
                if not os.path.exists(alt_req_path) or os.path.getsize(alt_req_path) == 0:
                    missing.append(req)
                    
        if missing:
            return False, f"Archive missing required binary: {', '.join(missing)}"
            
        # Step 4: Ensure target directory exists
        os.makedirs(target_dir, exist_ok=True)
        
        # Step 5: Smart In-Use File Replacement / Copy
        for root, dirs, files in os.walk(source_root):
            rel_path = os.path.relpath(root, source_root)
            dst_root = target_dir if rel_path == "." else os.path.join(target_dir, rel_path)
            os.makedirs(dst_root, exist_ok=True)
            
            for file in files:
                s_file = os.path.join(root, file)
                d_file = os.path.join(dst_root, file)
                
                try:
                    # Strip read-only attribute on destination if it exists
                    if os.path.exists(d_file):
                        try:
                            os.chmod(d_file, stat.S_IWRITE)
                        except Exception:
                            pass
                    shutil.copy2(s_file, d_file)
                except (PermissionError, OSError):
                    # File is in-use / locked by running app (WinError 32 / WinError 5)
                    # Attempt Windows rename-swap strategy
                    bak_file = f"{d_file}.old_{uuid.uuid4().hex[:6]}"
                    try:
                        os.rename(d_file, bak_file)
                        shutil.copy2(s_file, d_file)
                        try:
                            os.remove(bak_file)
                        except Exception:
                            pass  # Stale lock will be cleaned up on app exit
                    except Exception:
                        # If destination already exists and is non-empty, keep existing file gracefully
                        if os.path.exists(d_file) and os.path.getsize(d_file) > 0:
                            continue
                        else:
                            return False, f"Failed to replace in-use file '{file}'"
                            
        # Step 6: Final check on required binaries in target_dir
        for req in required_binaries:
            final_req_path = os.path.join(target_dir, req)
            if not os.path.exists(final_req_path):
                final_req_path = os.path.join(target_dir, os.path.basename(req))
            if not os.path.exists(final_req_path) or os.path.getsize(final_req_path) == 0:
                return False, f"Installation verification failed: {req} missing in {target_dir}"
                
        return True, None
        
    except Exception as e:
        return False, f"Atomic tool installation failed: {e}"
        
    finally:
        # Step 7: Cleanup staging and temp archive
        shutil.rmtree(staging_dir, ignore_errors=True)
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass


def download_ryzenadj(progress_callback: Optional[Callable[[int, int], None]] = None, force: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Download and install RyzenAdj to AppData.

    Before downloading, checks whether the installed version already matches
    the latest GitHub release. If they match and `force` is False, the
    download is skipped and (True, None) is returned immediately.

    Uses Structural Archive & Binary Integrity Validation (CRC-32 + binary checks).

    Args:
        progress_callback: Optional callback(downloaded_bytes, total_bytes) for UI progress reporting.
        force:             If True, skip the version check and always download.

    Returns:
        (success, error_message) - error_message is None on success.
    """
    import time

    try:
        # --- Version check: skip download if already up to date ---
        if not force:
            print("[Tools] Checking RyzenAdj version...")
            installed_ver = get_ryzenadj_installed_version()
            latest_ver = get_ryzenadj_latest_version()

            if installed_ver and latest_ver:
                print(f"[Tools] Installed: {installed_ver} | Latest: {latest_ver}")
                if installed_ver.lstrip('v') == latest_ver.lstrip('v'):
                    print("[Tools] RyzenAdj is already up to date. Skipping download.")
                    return True, None
                else:
                    print(f"[Tools] Update available: {installed_ver} -> {latest_ver}")
            elif installed_ver and not latest_ver:
                # Can't reach GitHub API - keep the existing install
                print("[Tools] Could not reach GitHub to check for updates. Using existing install.")
                return True, None
            else:
                print("[Tools] RyzenAdj not installed or version unreadable. Proceeding with download.")

        # --- Download ---
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"ryzenadj-win64-{uuid.uuid4().hex}.zip")

        last_error = None
        success = False
        for attempt in range(5):
            print(f"[Tools] Downloading RyzenAdj from {RYZENADJ_URL} (attempt {attempt + 1}/5)...")
            success, error = download_file(
                RYZENADJ_URL,
                zip_path,
                progress_callback,
                expected_checksum=None
            )
            if success:
                print("[Tools] RyzenAdj downloaded successfully.")
                last_error = None
                break
            else:
                print(f"[Tools] Download failed: {error}")
                if attempt < 4:
                    backoff_time = 2 ** attempt
                    print(f"[Tools] Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                last_error = error

        if not success:
            return False, f"Download failed: {last_error}"

        # --- Atomic Installation ---
        success, error = atomic_install_tool_archive(
            zip_path=zip_path,
            target_dir=RYZENADJ_DIR,
            required_binaries=["ryzenadj.exe"],
            flatten=True
        )
        if not success:
            return False, f"Install failed: {error}"

        if os.path.exists(get_ryzenadj_path()):
            print("[Tools] RyzenAdj installed successfully!")
            return True, None
        else:
            return False, "ryzenadj.exe not found after extraction"
            
    except Exception as e:
        return False, str(e)

def download_ffmpeg(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install FFmpeg to AppData using atomic structural validation.
    
    Returns:
        (success, error_message)
    """
    import time
    
    try:
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"ffmpeg-essentials-{uuid.uuid4().hex}.zip")
        
        last_error = None
        success = False
        for attempt in range(5):
            print(f"[Tools] Downloading FFmpeg from {FFMPEG_URL} (attempt {attempt + 1}/5)...")
            success, error = download_file(
                FFMPEG_URL,
                zip_path,
                progress_callback,
                expected_checksum=None
            )
            if success:
                print(f"[Tools] FFmpeg download validated successfully")
                last_error = None
                break
            else:
                print(f"[Tools] Download failed: {error}")
                if attempt < 4:
                    backoff_time = 2 ** attempt
                    print(f"[Tools] Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                last_error = error
        if not success:
            return False, f"Download failed: {last_error}"
        
        # Atomic Staging Installation
        success, error = atomic_install_tool_archive(
            zip_path=zip_path,
            target_dir=FFMPEG_DIR,
            required_binaries=["bin/ffmpeg.exe"],
            nested_subfolder_prefix="ffmpeg"
        )
        if not success:
            return False, f"Install failed: {error}"
            
        if os.path.exists(get_ffmpeg_path()):
            print("[Tools] FFmpeg installed successfully!")
            return True, None
        else:
            return False, "ffmpeg.exe not found after extraction"
    except Exception as e:
        return False, str(e)

def download_librehwmon(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install LibreHardwareMonitor to AppData using atomic structural validation.
    
    Returns:
        (success, error_message)
    """
    import time
    
    try:
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"LibreHardwareMonitor-{uuid.uuid4().hex}.zip")
        
        last_error = None
        success = False
        for attempt in range(5):
            print(f"[Tools] Downloading LibreHardwareMonitor from {LIBREHWMON_URL} (attempt {attempt + 1}/5)...")
            success, error = download_file(
                LIBREHWMON_URL,
                zip_path,
                progress_callback,
                expected_checksum=None
            )
            if success:
                print(f"[Tools] LibreHardwareMonitor download validated successfully")
                last_error = None
                break
            else:
                print(f"[Tools] Download failed: {error}")
                if attempt < 4:
                    backoff_time = 2 ** attempt
                    print(f"[Tools] Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                last_error = error
        if not success:
            return False, f"Download failed: {last_error}"
        
        # Atomic Staging Installation
        success, error = atomic_install_tool_archive(
            zip_path=zip_path,
            target_dir=LIBREHWMON_DIR,
            required_binaries=["LibreHardwareMonitor.exe", "LibreHardwareMonitorLib.dll"]
        )
        if not success:
            return False, f"Install failed: {error}"
            
        if os.path.exists(get_librehwmon_path()):
            print("[Tools] LibreHardwareMonitor installed successfully!")
            return True, None
        else:
            return False, "LibreHardwareMonitor.exe not found after extraction"
    except Exception as e:
        return False, str(e)

def download_hwinfo(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install HWiNFO Portable to AppData using atomic structural validation.
    
    Returns:
        (success, error_message)
    """
    import time
    
    try:
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"hwinfo_portable-{uuid.uuid4().hex}.zip")
        
        last_error = None
        success = False
        for attempt in range(5):
            print(f"[Tools] Downloading HWiNFO from {HWINFO_URL} (attempt {attempt + 1}/5)...")
            success, error = download_file(
                HWINFO_URL,
                zip_path,
                progress_callback,
                expected_checksum=None
            )
            if success:
                print(f"[Tools] HWiNFO download validated successfully")
                last_error = None
                break
            else:
                print(f"[Tools] Download failed: {error}")
                if attempt < 4:
                    backoff_time = 2 ** attempt
                    print(f"[Tools] Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                last_error = error
        if not success:
            return False, f"Download failed: {last_error}"
        
        # Atomic Staging Installation
        success, error = atomic_install_tool_archive(
            zip_path=zip_path,
            target_dir=HWINFO_DIR,
            required_binaries=["HWiNFO64.exe"]
        )
        if not success:
            return False, f"Install failed: {error}"
            
        if os.path.exists(get_hwinfo_path()) or os.path.exists(get_hwinfo32_path()):
            print("[Tools] HWiNFO installed successfully!")
            return True, None
        else:
            return False, "HWiNFO64.exe not found after extraction"
    except Exception as e:
        return False, str(e)

# Qt UI functions (require PySide6)
class HELXAIDProgressDialog:
    """
    Sleek, futuristic, Cyberpunk/Orbitron themed in-app Draggable Floating Panel for HELXAID.
    Frameless, rounded corners, glowing orange top accent line, custom progress bar.
    """
    def __new__(cls, *args, **kwargs):
        # We subclass QFrame dynamically to avoid importing Qt at module level
        from PySide6.QtWidgets import (
            QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
            QProgressBar, QWidget, QGraphicsDropShadowEffect
        )
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtGui import QColor, QFont

        class _CustomProgressDialog(QFrame):
            def __init__(self, title: str, cancel_text: str = "Cancel", min_val: int = 0, max_val: int = 100, parent=None):
                real_parent = parent.window() if parent and hasattr(parent, 'window') else parent
                super().__init__(real_parent)
                self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setObjectName("downloadFloatingPanel")
                self.setFixedSize(460, 200)
                self._is_canceled = False
                self._drag_pos = None
                self._last_time = None
                self._last_bytes = 0
                self._current_speed_str = ""

                layout = QVBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)

                # 1. Top Accent Line (Orange/Gold gradient bar)
                self.accent_line = QFrame(self)
                self.accent_line.setObjectName("dialogAccentLine")
                self.accent_line.setFixedHeight(3)
                self.accent_line.setStyleSheet("""
                    QFrame#dialogAccentLine {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                        border-radius: 0px;
                    }
                """)
                layout.addWidget(self.accent_line)

                # 2. Custom Title Bar
                self.title_bar = QWidget(self)
                self.title_bar.setObjectName("dialogTitleBar")
                self.title_bar.setStyleSheet("background: transparent;")
                title_layout = QHBoxLayout(self.title_bar)
                title_layout.setContentsMargins(20, 14, 20, 4)
                title_layout.setSpacing(10)
                title_layout.setAlignment(Qt.AlignVCenter)

                self.title_label = QLabel(title)
                self.title_label.setObjectName("dialogTitleLabel")
                self.title_label.setStyleSheet("""
                    font-family: 'Orbitron', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                    color: #FFFFFF;
                    letter-spacing: 0.5px;
                    background: transparent;
                """)
                title_layout.addWidget(self.title_label, alignment=Qt.AlignVCenter)
                title_layout.addStretch()
                layout.addWidget(self.title_bar)

                # 3. Content Body
                body_widget = QWidget(self)
                body_widget.setObjectName("dialogBodyWidget")
                body_widget.setStyleSheet("background: transparent;")
                body_layout = QVBoxLayout(body_widget)
                body_layout.setContentsMargins(20, 8, 20, 10)
                body_layout.setSpacing(10)

                # Status & Percentage Header Row
                status_row = QHBoxLayout()
                status_row.setSpacing(10)

                self.status_label = QLabel("Downloading...")
                self.status_label.setObjectName("dialogStatusLabel")
                self.status_label.setStyleSheet("""
                    font-family: 'Orbitron', sans-serif;
                    font-size: 12px;
                    color: #DDE6ED;
                    background: transparent;
                """)
                status_row.addWidget(self.status_label)
                status_row.addStretch()

                self.pct_label = QLabel("0%")
                self.pct_label.setObjectName("dialogPctLabel")
                self.pct_label.setStyleSheet("""
                    font-family: 'Orbitron', sans-serif;
                    font-size: 13px;
                    font-weight: bold;
                    color: #FDA903;
                    background: transparent;
                """)
                status_row.addWidget(self.pct_label)
                body_layout.addLayout(status_row)

                # Progress Bar
                self.progress_bar = QProgressBar()
                self.progress_bar.setObjectName("dialogProgressBar")
                self.progress_bar.setRange(min_val, max_val)
                self.progress_bar.setValue(min_val)
                self.progress_bar.setTextVisible(False)
                self.progress_bar.setFixedHeight(8)
                self.progress_bar.setStyleSheet("""
                    QProgressBar#dialogProgressBar {
                        background-color: rgba(255, 255, 255, 0.06);
                        border: none;
                        border-radius: 4px;
                    }
                    QProgressBar#dialogProgressBar::chunk {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903);
                        border-radius: 4px;
                    }
                """)
                body_layout.addWidget(self.progress_bar)

                # Bytes / Speed Info Row
                info_row = QHBoxLayout()
                self.bytes_label = QLabel("Preparing...")
                self.bytes_label.setObjectName("dialogBytesLabel")
                self.bytes_label.setStyleSheet("""
                    font-family: 'Orbitron', sans-serif;
                    font-size: 11px;
                    color: #6C757D;
                    background: transparent;
                """)
                info_row.addWidget(self.bytes_label)
                info_row.addStretch()

                self.speed_label = QLabel("")
                self.speed_label.setObjectName("dialogSpeedLabel")
                self.speed_label.setStyleSheet("""
                    font-family: 'Orbitron', sans-serif;
                    font-size: 11px;
                    font-weight: bold;
                    color: #9DB2BF;
                    background: transparent;
                """)
                info_row.addWidget(self.speed_label)
                body_layout.addLayout(info_row)

                layout.addWidget(body_widget)

                # 4. Actions Footer
                footer = QWidget(self)
                footer.setObjectName("dialogFooter")
                footer.setStyleSheet("background: transparent;")
                footer_layout = QHBoxLayout(footer)
                footer_layout.setContentsMargins(20, 2, 20, 16)
                footer_layout.addStretch()

                try:
                    from AnimatedButton import FadeHoverButton
                    self.cancel_btn = FadeHoverButton(cancel_text or "Cancel", is_secondary=True, border_radius=8.0)
                except Exception:
                    self.cancel_btn = QPushButton(cancel_text or "Cancel")
                    self.cancel_btn.setStyleSheet("""
                        QPushButton#dialogCancelBtn {
                            font-family: 'Orbitron', sans-serif;
                            font-size: 12px;
                            font-weight: bold;
                            color: #CCCCCC;
                            background-color: rgba(255, 255, 255, 0.05);
                            border: 1px solid rgba(255, 255, 255, 0.08);
                            border-radius: 8px;
                        }
                    """)

                self.cancel_btn.setObjectName("dialogCancelBtn")
                self.cancel_btn.setFixedSize(110, 32)
                self.cancel_btn.setCursor(Qt.PointingHandCursor)
                self.cancel_btn.clicked.connect(self.cancel)
                footer_layout.addWidget(self.cancel_btn)
                layout.addWidget(footer)

            def show(self):
                super().show()
                self.raise_()
                self._center_on_parent()

            def _center_on_parent(self):
                if self.parent():
                    rect = self.parent().rect()
                    self.move(
                        (rect.width() - self.width()) // 2,
                        (rect.height() - self.height()) // 2
                    )
                self.raise_()

            def paintEvent(self, event):
                from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor
                from PySide6.QtCore import QRectF
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
                path = QPainterPath()
                radius = 14.0
                path.moveTo(rect.left(), rect.top())
                path.lineTo(rect.right(), rect.top())
                path.lineTo(rect.right(), rect.bottom() - radius)
                path.arcTo(rect.right() - 2 * radius, rect.bottom() - 2 * radius, 2 * radius, 2 * radius, 0, -90)
                path.lineTo(rect.left() + radius, rect.bottom())
                path.arcTo(rect.left(), rect.bottom() - 2 * radius, 2 * radius, 2 * radius, 270, -90)
                path.closeSubpath()
                # 100% solid dark background
                painter.fillPath(path, QColor("#12141a"))
                # Subtle border outline
                pen = QPen(QColor(255, 255, 255, 26))
                pen.setWidthF(1.0)
                painter.setPen(pen)
                painter.drawPath(path)

            def mousePressEvent(self, event):
                from PySide6.QtCore import Qt
                if event.button() == Qt.LeftButton:
                    self._drag_pos = event.position().toPoint()
                    self.raise_()
                    event.accept()

            def mouseMoveEvent(self, event):
                from PySide6.QtCore import Qt
                if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
                    new_pos = self.mapToParent(event.position().toPoint() - self._drag_pos)
                    if self.parent():
                        p_rect = self.parent().rect()
                        x = max(0, min(new_pos.x(), p_rect.width() - self.width()))
                        y = max(0, min(new_pos.y(), p_rect.height() - self.height()))
                        self.move(x, y)
                    else:
                        self.move(new_pos)
                    event.accept()

            def mouseReleaseEvent(self, event):
                self._drag_pos = None

            def set_progress(self, downloaded: int, total: int):
                """Update progress bar, bytes label, download speed, and percentage label."""
                import time
                now = time.time()
                if self._last_time is not None:
                    dt = now - self._last_time
                    if dt >= 0.2:  # update speed calculation every 200ms for smoothness
                        d_bytes = downloaded - self._last_bytes
                        speed = d_bytes / dt if dt > 0 else 0
                        self._last_time = now
                        self._last_bytes = downloaded
                        if speed >= 1024 * 1024:
                            self._current_speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                        elif speed >= 1024:
                            self._current_speed_str = f"{speed / 1024:.1f} KB/s"
                        elif speed > 0:
                            self._current_speed_str = f"{int(speed)} B/s"
                        else:
                            self._current_speed_str = ""
                else:
                    self._last_time = now
                    self._last_bytes = downloaded

                if total > 0:
                    pct = int((downloaded / total) * 100)
                    self.progress_bar.setValue(pct)
                    self.pct_label.setText(f"{pct}%")
                    if total >= 1024 * 1024:
                        dl_mb = downloaded / (1024 * 1024)
                        tot_mb = total / (1024 * 1024)
                        self.bytes_label.setText(f"{dl_mb:.1f} MB / {tot_mb:.1f} MB")
                    else:
                        self.bytes_label.setText(f"{downloaded // 1024} KB / {total // 1024} KB")
                else:
                    self.bytes_label.setText(f"{downloaded // 1024} KB")

                if self._current_speed_str:
                    self.speed_label.setText(self._current_speed_str)

            def set_status(self, text: str):
                self.status_label.setText(text)

            def cancel(self):
                self._is_canceled = True
                self.close()

            def reject(self):
                self.cancel()

            def close(self):
                self.hide()
                self.deleteLater()

            def wasCanceled(self) -> bool:
                return self._is_canceled

            def setValue(self, val: int):
                self.progress_bar.setValue(val)
                self.pct_label.setText(f"{val}%")

            def setLabelText(self, text: str):
                self.status_label.setText(text)

            def setWindowTitle(self, title: str):
                self.title_label.setText(title)

            def setWindowModality(self, modality):
                pass

            def setMinimumDuration(self, ms: int):
                pass

            def setAutoClose(self, val: bool):
                pass

            def setAutoReset(self, val: bool):
                pass

        return _CustomProgressDialog(*args, **kwargs)


class HELXAIDMessagePanel:
    """
    Sleek, futuristic in-app floating message panel for notifications/alerts in HELXAID.
    Frameless, solid dark #12141a card, glowing top accent line, Orbitron typography,
    antialiased rounded corners, and FadeHoverButton OK action.
    """
    def __new__(cls, title: str, message: str, parent=None, on_ok=None, is_error: bool = False):
        from PySide6.QtWidgets import (
            QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
        )
        from PySide6.QtCore import Qt, QPoint, QRectF
        from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

        class _CustomMessagePanel(QFrame):
            def __init__(self):
                real_parent = parent.window() if parent and hasattr(parent, 'window') else parent
                super().__init__(real_parent)
                self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setObjectName("messageFloatingPanel")
                self.setFixedSize(460, 210)
                self._on_ok = on_ok
                self._drag_pos = None

                layout = QVBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)

                # 1. Top Accent Line
                accent_gradient = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B91C1C, stop:1 #FF3838)" if is_error else "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5B06, stop:1 #FDA903)"
                self.accent_line = QFrame(self)
                self.accent_line.setObjectName("msgAccentLine")
                self.accent_line.setFixedHeight(3)
                self.accent_line.setStyleSheet(f"""
                    QFrame#msgAccentLine {{
                        background: {accent_gradient};
                        border-radius: 0px;
                    }}
                """)
                layout.addWidget(self.accent_line)

                # 2. Title Bar
                self.title_bar = QWidget(self)
                self.title_bar.setObjectName("msgTitleBar")
                self.title_bar.setStyleSheet("background: transparent;")
                title_layout = QHBoxLayout(self.title_bar)
                title_layout.setContentsMargins(20, 14, 20, 4)
                title_layout.setSpacing(10)
                title_layout.setAlignment(Qt.AlignVCenter)

                title_color = "#FF4444" if is_error else "#FFFFFF"
                self.title_label = QLabel(title)
                self.title_label.setObjectName("msgTitleLabel")
                self.title_label.setStyleSheet(f"""
                    font-family: 'Orbitron', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                    color: {title_color};
                    letter-spacing: 0.5px;
                    background: transparent;
                """)
                title_layout.addWidget(self.title_label, alignment=Qt.AlignVCenter)
                title_layout.addStretch()
                layout.addWidget(self.title_bar)

                # 3. Message Body inside Scroll Area
                self.scroll_area = QScrollArea(self)
                self.scroll_area.setObjectName("msgScrollArea")
                self.scroll_area.setWidgetResizable(True)
                self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.scroll_area.setFrameShape(QFrame.NoFrame)

                scroll_handle_color = "rgba(255, 56, 56, 0.6)" if is_error else "rgba(255, 91, 6, 0.6)"
                scroll_hover_color = "rgba(255, 56, 56, 0.9)" if is_error else "rgba(255, 91, 6, 0.9)"
                self.scroll_area.setStyleSheet(f"""
                    QScrollArea#msgScrollArea {{
                        background: transparent;
                        border: none;
                    }}
                    QScrollBar:vertical {{
                        background: rgba(255, 255, 255, 0.04);
                        width: 6px;
                        border-radius: 3px;
                        margin: 0px 2px 0px 0px;
                    }}
                    QScrollBar::handle:vertical {{
                        background: {scroll_handle_color};
                        border-radius: 3px;
                        min-height: 20px;
                    }}
                    QScrollBar::handle:vertical:hover {{
                        background: {scroll_hover_color};
                    }}
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                        height: 0px;
                    }}
                    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                        background: transparent;
                    }}
                """)

                body_widget = QWidget()
                body_widget.setObjectName("msgBodyWidget")
                body_widget.setStyleSheet("background: transparent;")
                body_layout = QVBoxLayout(body_widget)
                body_layout.setContentsMargins(20, 6, 20, 6)
                body_layout.setSpacing(6)

                self.msg_label = QLabel(message)
                self.msg_label.setObjectName("msgLabel")
                self.msg_label.setWordWrap(True)
                self.msg_label.setStyleSheet("""
                    font-family: 'Orbitron', sans-serif;
                    font-size: 12px;
                    color: #DDE6ED;
                    background: transparent;
                    line-height: 1.4;
                """)
                body_layout.addWidget(self.msg_label)
                body_layout.addStretch()

                self.scroll_area.setWidget(body_widget)
                layout.addWidget(self.scroll_area, 1)

                # 4. Actions Footer
                footer = QWidget(self)
                footer.setObjectName("msgFooter")
                footer.setStyleSheet("background: transparent;")
                footer_layout = QHBoxLayout(footer)
                footer_layout.setContentsMargins(20, 0, 20, 16)
                footer_layout.addStretch()

                try:
                    from AnimatedButton import FadeHoverButton
                    self.ok_btn = FadeHoverButton("OK", is_secondary=True, border_radius=8.0)
                except Exception:
                    self.ok_btn = QPushButton("OK")
                    self.ok_btn.setStyleSheet("""
                        QPushButton {
                            font-family: 'Orbitron', sans-serif;
                            font-size: 12px;
                            font-weight: bold;
                            color: #CCCCCC;
                            background-color: rgba(255, 255, 255, 0.05);
                            border: 1px solid rgba(255, 255, 255, 0.08);
                            border-radius: 8px;
                        }
                    """)

                self.ok_btn.setObjectName("msgOkBtn")
                self.ok_btn.setFixedSize(90, 32)
                self.ok_btn.setCursor(Qt.PointingHandCursor)
                self.ok_btn.clicked.connect(self._handle_ok)
                footer_layout.addWidget(self.ok_btn)
                layout.addWidget(footer)

            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
                path = QPainterPath()
                radius = 14.0
                path.moveTo(rect.left(), rect.top())
                path.lineTo(rect.right(), rect.top())
                path.lineTo(rect.right(), rect.bottom() - radius)
                path.arcTo(rect.right() - 2 * radius, rect.bottom() - 2 * radius, 2 * radius, 2 * radius, 0, -90)
                path.lineTo(rect.left() + radius, rect.bottom())
                path.arcTo(rect.left(), rect.bottom() - 2 * radius, 2 * radius, 2 * radius, 270, -90)
                path.closeSubpath()
                painter.fillPath(path, QColor("#12141a"))
                pen = QPen(QColor(255, 255, 255, 26))
                pen.setWidthF(1.0)
                painter.setPen(pen)
                painter.drawPath(path)

            def show(self):
                super().show()
                self.raise_()
                self._center_on_parent()

            def _center_on_parent(self):
                if self.parent():
                    rect = self.parent().rect()
                    self.move(
                        (rect.width() - self.width()) // 2,
                        (rect.height() - self.height()) // 2
                    )
                self.raise_()

            def _handle_ok(self):
                self.hide()
                self.deleteLater()
                if callable(self._on_ok):
                    self._on_ok()

            def mousePressEvent(self, event):
                if event.button() == Qt.LeftButton:
                    self._drag_pos = event.position().toPoint()
                    self.raise_()
                    event.accept()

            def mouseMoveEvent(self, event):
                if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
                    new_pos = self.mapToParent(event.position().toPoint() - self._drag_pos)
                    if self.parent():
                        p_rect = self.parent().rect()
                        x = max(0, min(new_pos.x(), p_rect.width() - self.width()))
                        y = max(0, min(new_pos.y(), p_rect.height() - self.height()))
                        self.move(x, y)
                    else:
                        self.move(new_pos)
                    event.accept()

            def mouseReleaseEvent(self, event):
                self._drag_pos = None

        instance = _CustomMessagePanel()
        instance.show()
        return instance


def show_download_dialog(parent, tool_name: str, download_func: Callable) -> bool:
    """
    Show download consent dialog and progress with background thread.
    Uses Python threading for truly non-blocking download.
    """
    try:
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtCore import Qt, QTimer, QEventLoop
        import threading
        
        # Ask user consent
        reply = QMessageBox.question(
            parent,
            f"Download {tool_name}",
            f"{tool_name} is required but not installed.\n\n"
            f"Would you like to download it now?\n"
            f"It will be installed to: {TOOLS_DIR}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return False
        
        # Shared state between thread and UI
        state = {
            "downloaded": 0,
            "total": 0,
            "done": False,
            "success": False,
            "error": "",
            "cancelled": False
        }
        
        # Progress callback (called from download thread)
        def on_progress(downloaded: int, total: int):
            state["downloaded"] = downloaded
            state["total"] = total
        
        # Download function wrapper
        def do_download():
            try:
                if state["cancelled"]:
                    return
                success, error = download_func(on_progress)
                state["success"] = success
                state["error"] = error or ""
            except Exception as e:
                state["success"] = False
                state["error"] = str(e)
            finally:
                # Always mark as done so UI loop can exit
                state["done"] = True
        
        # Create sleek custom progress dialog
        progress = HELXAIDProgressDialog(
            f"Installing {tool_name}",
            "Cancel",
            0, 100,
            parent
        )
        progress.set_status(f"Downloading {tool_name}...")
        progress.show()
        
        # Start download in thread
        thread = threading.Thread(target=do_download, daemon=True)
        thread.start()
        
        # Poll for completion with QEventLoop to keep UI responsive
        loop = QEventLoop()
        timer = QTimer()
        
        def check_status():
            if progress.wasCanceled():
                state["cancelled"] = True
                # Ensure the loop exits even when cancelled
                state["done"] = True
                timer.stop()
                loop.quit()
                return
            
            if state["total"] > 0:
                progress.set_progress(state["downloaded"], state["total"])
                
            if state["done"]:
                timer.stop()
                loop.quit()
                
        timer.timeout.connect(check_status)
        timer.start(50)  # check every 50ms
        loop.exec()
        
        # Cleanup
        progress.close()
        
        # Don't block on thread.join - let it finish in background
        
        if state["cancelled"]:
            return False
        elif state["success"]:
            # Ask to restart app after successful install
            def do_restart():
                try:
                    from PySide6.QtCore import QProcess
                    from PySide6.QtWidgets import QApplication
                    import sys, os

                    if getattr(sys, 'frozen', False):
                        # Running as PyInstaller-built .exe — restart the exe directly
                        exe = sys.executable
                        args = sys.argv[1:]
                    else:
                        # Running as a plain Python script (development mode)
                        exe = sys.executable
                        args = sys.argv  # argv[0] is launcher.py

                    if parent:
                        try:
                            parent.window().confirm_on_exit = False
                        except AttributeError:
                            pass
                    
                    if "--force-restart" not in args:
                        args.append("--force-restart")
                            
                    QProcess.startDetached(exe, args)
                    QApplication.quit()
                except Exception as restart_err:
                    print(f"[Tools] Restart failed: {restart_err}")
                    HELXAIDMessagePanel(
                        "Restart Required",
                        "Please close and reopen HELXAID manually to complete the installation.",
                        parent
                    )

            HELXAIDMessagePanel(
                "Download Complete",
                f"{tool_name} has been installed successfully!\n\nHELXAID needs to restart to apply changes.",
                parent,
                on_ok=do_restart
            )
            return True

        else:
            HELXAIDMessagePanel(
                "Download Failed",
                f"Failed to install {tool_name}:\n{state['error']}",
                parent,
                is_error=True
            )
            return False
            
    except ImportError:
        # No Qt available, just download silently
        success, _ = download_func(None)
        return success


def ensure_ryzenadj(parent=None) -> bool:
    """
    Ensure RyzenAdj is available, downloading if needed.
    
    Args:
        parent: Optional parent widget for dialog
    
    Returns:
        True if RyzenAdj is available (or if Intel CPU where RyzenAdj is skipped)
    """
    try:
        from integrations.cpu_controller import is_intel_cpu
        if is_intel_cpu():
            print("[ToolsDownloader] Intel CPU detected. RyzenAdj is AMD-specific and will be skipped.")
            return True
    except Exception:
        pass

    if is_ryzenadj_available():
        return True
    
    if parent:
        return show_download_dialog(parent, "RyzenAdj", download_ryzenadj)
    else:
        success, _ = download_ryzenadj()
        return success



def ensure_ffmpeg(parent=None) -> bool:
    """
    Ensure FFmpeg is available, downloading if needed.
    
    Args:
        parent: Optional parent widget for dialog
    
    Returns:
        True if FFmpeg is available
    """
    if is_ffmpeg_available():
        return True
    
    if parent:
        return show_download_dialog(parent, "FFmpeg", download_ffmpeg)
    else:
        success, _ = download_ffmpeg()
        return success


def ensure_librehwmon(parent=None) -> bool:
    """
    Ensure LibreHardwareMonitor is available, downloading if needed.
    
    Args:
        parent: Optional parent widget for dialog
    
    Returns:
        True if LibreHardwareMonitor is available
    """
    if is_librehwmon_available():
        return True
    
    if parent:
        return show_download_dialog(parent, "LibreHardwareMonitor", download_librehwmon)
    else:
        success, _ = download_librehwmon()
        return success


def ensure_hwinfo(parent=None) -> bool:
    """
    Ensure HWiNFO is available, downloading if needed.
    
    Args:
        parent: Optional parent widget for dialog
    
    Returns:
        True if HWiNFO is available
    """
    if is_hwinfo_available():
        return True
    
    if parent:
        return show_download_dialog(parent, "HWiNFO Portable", download_hwinfo)
    else:
        success, _ = download_hwinfo()
        return success


def download_and_install_uxtu(progress_callback: Callable[[int, int], None] = None) -> Tuple[bool, str]:
    """Download and launch the UXTU installer (.msix) from GitHub."""
    import urllib.request
    import json
    import tempfile
    
    api_url = "https://api.github.com/repos/JamesCJ60/Universal-x86-Tuning-Utility/releases/latest"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "HELXAID-Launcher", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
            # Find MSIX asset
            msix_url = None
            msix_name = "Universal.x86.Tuning.Utility.msix"
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".msix") or asset.get("name", "").endswith(".msi"):
                    msix_url = asset.get("browser_download_url")
                    msix_name = asset.get("name")
                    break
            
            if not msix_url:
                return False, "Could not find UXTU installer in the latest release."
            
            temp_dir = tempfile.gettempdir()
            download_path = os.path.join(temp_dir, msix_name)
            
            # Download file
            def report_hook(block_num, block_size, total_size):
                if progress_callback:
                    downloaded = block_num * block_size
                    progress_callback(min(downloaded, total_size), total_size)
                    
            urllib.request.urlretrieve(msix_url, download_path, reporthook=report_hook)
            
            # Launch installer
            os.startfile(download_path)
            
            return True, "UXTU installer launched successfully."
            
    except Exception as e:
        return False, str(e)


def import_tool_from_path(target_dir: str, required_files: list, source_path: str) -> Tuple[bool, str]:
    """
    Import a tool from a user-selected archive (.zip, .7z, .tar, etc.) or directory, or single file.
    Extracts/copies into target_dir and verifies required_files exist.
    """
    import os, shutil, zipfile
    
    if not source_path or not os.path.exists(source_path):
        return False, "Selected file or folder does not exist."
        
    os.makedirs(target_dir, exist_ok=True)
    
    # Extensions that are relevant for tool binaries and libraries
    valid_exts = ('.exe', '.dll', '.sys', '.json', '.xml', '.config', '.pdb')
    
    try:
        # Case 1: Source is a zip file
        if os.path.isfile(source_path) and (source_path.lower().endswith('.zip') or zipfile.is_zipfile(source_path)):
            with zipfile.ZipFile(source_path, 'r') as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    filename = os.path.basename(member.filename)
                    if not filename:
                        continue
                    # Only extract binaries or files explicitly required
                    if filename.lower() in [r.lower() for r in required_files] or filename.lower().endswith(valid_exts):
                        target_file = os.path.join(target_dir, filename)
                        with zf.open(member) as src_handle, open(target_file, "wb") as dst_handle:
                            shutil.copyfileobj(src_handle, dst_handle)
                        
        # Case 2: Source is a directory
        elif os.path.isdir(source_path):
            found_reqs = set()
            for root, dirs, files in os.walk(source_path):
                for file in files:
                    file_lower = file.lower()
                    for req in required_files:
                        if file_lower == req.lower():
                            found_reqs.add(req)
                            # Copy the required binary
                            src_file = os.path.join(root, file)
                            dst_file = os.path.join(target_dir, file)
                            shutil.copy2(src_file, dst_file)
                            # Also copy sibling DLLs/dependencies in that specific folder
                            for sibling in files:
                                if sibling.lower().endswith(valid_exts):
                                    shutil.copy2(os.path.join(root, sibling), os.path.join(target_dir, sibling))
                                    
        # Case 3: Source is a single file
        elif os.path.isfile(source_path):
            filename = os.path.basename(source_path)
            shutil.copy2(source_path, os.path.join(target_dir, filename))
            src_dir = os.path.dirname(source_path)
            for req in required_files:
                companion = os.path.join(src_dir, req)
                if os.path.exists(companion) and companion != source_path:
                    shutil.copy2(companion, os.path.join(target_dir, req))
                    
        # Validate that all required files now exist in target_dir
        missing = []
        for req in required_files:
            if not os.path.exists(os.path.join(target_dir, req)):
                missing.append(req)
                
        if missing:
            return False, f"Missing required file(s): {', '.join(missing)}"
            
        return True, "Tool imported successfully!"
        
    except Exception as e:
        return False, str(e)


def import_ffmpeg_tool(source_path: str) -> Tuple[bool, str]:
    """Import FFmpeg archive or executable into FFMPEG_DIR."""
    success, msg = import_tool_from_path(FFMPEG_DIR, ["ffmpeg.exe"], source_path)
    if success and not is_ffmpeg_available():
        return False, "ffmpeg.exe was not found in the imported package."
    return success, msg


def import_ryzenadj_tool(source_path: str) -> Tuple[bool, str]:
    """Import RyzenAdj archive or executable into RYZENADJ_DIR."""
    success, msg = import_tool_from_path(RYZENADJ_DIR, ["ryzenadj.exe"], source_path)
    if success and not is_ryzenadj_available():
        return False, "ryzenadj.exe was not found in the imported package."
    return success, msg


def import_lhm_tool(source_path: str) -> Tuple[bool, str]:
    """Import LibreHardwareMonitor archive or dll into LIBREHWMON_DIR."""
    success, msg = import_tool_from_path(LIBREHWMON_DIR, ["LibreHardwareMonitorLib.dll"], source_path)
    if success and not is_librehwmon_available():
        return False, "LibreHardwareMonitorLib.dll was not found in the imported package."
    return success, msg


class SplitImportButton(QWidget):
    """
    Split dropdown button widget combining a main import action button and a dropdown mode switcher.
    Component Name: SplitImportButton
    """
    def __init__(self, tool_name: str, import_func: Callable, on_success_reload: Callable, parent=None):
        super().__init__(parent)
        self.tool_name = tool_name
        self.import_func = import_func
        self.on_success_reload = on_success_reload
        self.setObjectName(f"splitImportContainer_{tool_name}")

        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QToolButton, QMenu, QFileDialog
        from PySide6.QtCore import Qt, QSize
        from PySide6.QtGui import QIcon
        import os

        arrow_icon = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UI Icons", "down-arrow-triangle.svg").replace("\\", "/")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.btn_main = QPushButton(f"Import {tool_name} (.zip)", self)
        self.btn_main.setObjectName(f"splitImportMain_{tool_name}")
        self.btn_main.setCursor(Qt.PointingHandCursor)
        self.btn_main.setFixedHeight(36)

        self.btn_arrow = QToolButton(self)
        self.btn_arrow.setObjectName(f"splitImportArrow_{tool_name}")
        self.btn_arrow.setCursor(Qt.PointingHandCursor)
        self.btn_arrow.setPopupMode(QToolButton.InstantPopup)
        self.btn_arrow.setFixedSize(36, 36)

        if os.path.exists(arrow_icon):
            self.btn_arrow.setIcon(QIcon(arrow_icon))
            self.btn_arrow.setIconSize(QSize(12, 10))

        layout.addWidget(self.btn_main)
        layout.addWidget(self.btn_arrow)

        self.setStyleSheet("""
            QWidget[objectName^="splitImportContainer"] {
                background: transparent;
                border: none;
            }
            QPushButton[objectName^="splitImportMain"] {
                color: #FFFFFF;
                background-color: #1e2026;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top-left-radius: 8px;
                border-bottom-left-radius: 8px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 0px 16px;
                min-height: 36px;
                max-height: 36px;
                min-width: 184px;
                font-family: 'Orbitron', sans-serif;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton[objectName^="splitImportMain"]:hover {
                background-color: #2e323c;
                border-color: rgba(255, 255, 255, 0.22);
            }
            QPushButton[objectName^="splitImportMain"]:pressed {
                background-color: #16181d;
            }
            QToolButton[objectName^="splitImportArrow"] {
                background-color: #1e2026;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-left: 1px solid rgba(255, 255, 255, 0.15);
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                min-height: 36px;
                max-height: 36px;
            }
            QToolButton[objectName^="splitImportArrow"]:hover {
                background-color: #2e323c;
                border-color: rgba(255, 255, 255, 0.22);
            }
            QToolButton[objectName^="splitImportArrow"]:pressed {
                background-color: #16181d;
            }
            QToolButton[objectName^="splitImportArrow"]::menu-indicator {
                image: none;
                width: 0px;
            }
        """)

        # Menu Setup
        self.import_menu = QMenu(self)
        self.import_menu.setObjectName("splitImportMenu")
        self.import_menu.setStyleSheet("""
            QMenu#splitImportMenu {
                background-color: #1e2128;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #e0e0e0;
                font-family: 'Orbitron', sans-serif;
                font-size: 11px;
                font-weight: 500;
                padding: 4px;
            }
            QMenu#splitImportMenu::item {
                padding: 6px 14px;
                min-height: 26px;
                border-radius: 4px;
                background: transparent;
                color: #e0e0e0;
            }
            QMenu#splitImportMenu::item:selected, QMenu#splitImportMenu::item:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
        """)

        self.act_file = self.import_menu.addAction(f"Import {tool_name} Archive / File (.zip, .exe)")
        self.act_folder = self.import_menu.addAction(f"Import {tool_name} Folder / Directory")
        self.btn_arrow.setMenu(self.import_menu)

        self._active_mode = "file"  # "file" or "folder"

        # Signal connections
        self.btn_main.clicked.connect(self._on_main_clicked)
        self.act_file.triggered.connect(lambda: self._select_mode("file"))
        self.act_folder.triggered.connect(lambda: self._select_mode("folder"))

    def _select_mode(self, mode: str):
        self._active_mode = mode
        if mode == "file":
            self.btn_main.setText(f"Import {self.tool_name} (.zip)")
        else:
            self.btn_main.setText(f"Import {self.tool_name} Folder")

    def _on_main_clicked(self):
        self._open_file_dialog()

    def _open_file_dialog(self):
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtCore import QSettings
        import os

        settings = QSettings("TDD131", "HELXAID")
        last_dir = settings.value("Tools/last_import_dir", "", type=str)
        if last_dir and not os.path.exists(last_dir):
            last_dir = ""

        parent_window = self.window() if self.window() else self
        if self._active_mode == "file":
            path, _ = QFileDialog.getOpenFileName(
                parent_window,
                f"Select {self.tool_name} Archive or Binary",
                last_dir,
                "Supported Files (*.zip *.exe *.dll *.7z *.tar.gz *.tar.xz);;All Files (*.*)"
            )
        else:
            path = QFileDialog.getExistingDirectory(
                parent_window,
                f"Select {self.tool_name} Directory / Folder",
                last_dir
            )
            
        if not path:
            return

        # Save last selected directory to QSettings
        chosen_dir = path if os.path.isdir(path) else os.path.dirname(path)
        if chosen_dir and os.path.exists(chosen_dir):
            settings.setValue("Tools/last_import_dir", chosen_dir)

        success, msg = self.import_func(path)
        if success:
            HELXAIDMessagePanel(
                "Import Complete",
                f"{self.tool_name} has been imported successfully!\n\nClick OK to reload panel.",
                parent_window,
                on_ok=self.on_success_reload
            )
        else:
            HELXAIDMessagePanel(
                "Import Failed",
                f"Failed to import {self.tool_name}:\n{msg}",
                parent_window,
                is_error=True
            )


def handle_tool_import(parent, tool_name: str, import_func: Callable, on_success_reload: Callable):
    """
    Opens QFileDialog, runs import_func, and displays HELXAIDMessagePanel result.
    """
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtCore import QSettings
    import os

    settings = QSettings("TDD131", "HELXAID")
    last_dir = settings.value("Tools/last_import_dir", "", type=str)
    if last_dir and not os.path.exists(last_dir):
        last_dir = ""

    file_path, _ = QFileDialog.getOpenFileName(
        parent,
        f"Select {tool_name} Package or Binary",
        last_dir,
        "Supported Files (*.zip *.exe *.dll *.7z *.tar.gz *.tar.xz);;All Files (*.*)"
    )
    if not file_path:
        return
        
    chosen_dir = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
    if chosen_dir and os.path.exists(chosen_dir):
        settings.setValue("Tools/last_import_dir", chosen_dir)

    success, msg = import_func(file_path)
    if success:
        HELXAIDMessagePanel(
            "Import Complete",
            f"{tool_name} has been imported successfully!\n\nClick OK to reload panel.",
            parent,
            on_ok=on_success_reload
        )
    else:
        HELXAIDMessagePanel(
            "Import Failed",
            f"Failed to import {tool_name}:\n{msg}",
            parent,
            is_error=True
        )
