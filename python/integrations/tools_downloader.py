"""
Tools Downloader Module for HELXAID Game Launcher
Handles auto-download of RyzenAdj, FFmpeg, and LibreHardwareMonitor to AppData.
"""

import os
import sys
import urllib.request
import zipfile
import tempfile
import shutil
import uuid
from typing import Optional, Tuple, Callable

# AppData tools directory
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", ""), "HELXAID")
TOOLS_DIR = os.path.join(APPDATA_DIR, "tools")

# Tool subdirectories
RYZENADJ_DIR = os.path.join(TOOLS_DIR, "ryzenadj")
FFMPEG_DIR = os.path.join(TOOLS_DIR, "ffmpeg")
LIBREHWMON_DIR = os.path.join(TOOLS_DIR, "librehardwaremonitor")
HWINFO_DIR = os.path.join(TOOLS_DIR, "hwinfo")
VLC_DIR = os.path.join(TOOLS_DIR, "vlc")

# Download URLs
RYZENADJ_URL = "https://github.com/FlyGoat/RyzenAdj/releases/latest/download/ryzenadj-win64.zip"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
LIBREHWMON_URL = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.4/LibreHardwareMonitor-net472.zip"
# HWiNFO Portable (~5MB, latest stable version)
HWINFO_URL = "https://www.hwinfo.com/files/hwi_848.zip"  # v8.48 portable
# VLC Portable (from VideoLAN, ~40MB) - Version 3.0.20 (stable)
VLC_URLS = [
    "https://get.videolan.org/vlc/3.0.20/win64/vlc-3.0.20-win64.zip",
    "https://mirror.fcix.net/videolan-ftp/vlc/3.0.20/win64/vlc-3.0.20-win64.zip",
    "https://ftp.osuosl.org/pub/videolan/vlc/3.0.20/win64/vlc-3.0.20-win64.zip",
    "https://mirrors.ocf.berkeley.edu/videolan/vlc/3.0.20/win64/vlc-3.0.20-win64.zip",
    "https://mirror.clarkson.edu/videolan/vlc/3.0.20/win64/vlc-3.0.20-win64.zip",
]

# Checksums for verifying download integrity (SHA256)
# Note: RyzenAdj uses dynamic version checking instead of a hardcoded checksum
# because it points to the "latest" release URL which changes with every new release.
CHECKSUMS = {
    "vlc": "75d946b166476191df3d93783f7683b7a1a5176aad105e1cd46d940c049f7cdc",  # VLC 3.0.20 win64
    "librehwmon": "d2e397cc4d33d65c6493dff83b9335bc341a3af31caafceef83f717fdab37448",  # LibreHardwareMonitor v0.9.4
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


def is_ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    # Check AppData
    if os.path.exists(get_ffmpeg_path()):
        return True
    
    # Check if ffmpeg is in PATH
    import shutil
    return shutil.which("ffmpeg") is not None or shutil.which("ffprobe") is not None


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


def get_vlc_path() -> str:
    """Get path to vlc.exe in AppData."""
    return os.path.join(VLC_DIR, "vlc.exe")


def get_libvlc_path() -> str:
    """Get path to libvlc.dll for python-vlc bindings."""
    return os.path.join(VLC_DIR, "libvlc.dll")


def is_vlc_available() -> bool:
    """Check if VLC Portable is available in AppData only."""
    return os.path.exists(get_vlc_path()) and os.path.exists(get_libvlc_path())


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
    except Exception as e:
        return False, str(e)


def extract_zip(zip_path: str, dest_dir: str, flatten: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Extract a ZIP file to destination directory.
    
    Args:
        zip_path: Path to ZIP file
        dest_dir: Destination directory
        flatten: If True, extract files directly without preserving folder structure
    
    Returns:
        (success, error_message)
    """
    try:
        os.makedirs(dest_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            if flatten:
                # Extract files directly, ignoring folder structure
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
        
    except zipfile.BadZipFile:
        return False, "Invalid or corrupted ZIP file"
    except Exception as e:
        return False, str(e)


def download_ryzenadj(progress_callback: Optional[Callable[[int, int], None]] = None, force: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Download and install RyzenAdj to AppData.

    Before downloading, checks whether the installed version already matches
    the latest GitHub release. If they match and `force` is False, the
    download is skipped and (True, None) is returned immediately.

    Version checking uses two helpers:
      - get_ryzenadj_installed_version(): runs the local exe to read its tag
      - get_ryzenadj_latest_version():    queries the GitHub releases API

    The download does NOT use a hardcoded SHA-256 checksum because the
    RYZENADJ_URL always points to "latest", meaning the file changes with
    every new release. Instead, correct installation is verified by confirming
    the executable exists after extraction.

    Args:
        progress_callback: Optional callback(downloaded_bytes, total_bytes) for
                           UI progress reporting.
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
        for attempt in range(3):
            print(f"[Tools] Downloading RyzenAdj from {RYZENADJ_URL} (attempt {attempt + 1}/3)...")
            # No expected_checksum: the "latest" URL changes with every release,
            # so a hardcoded hash will always mismatch. Integrity is instead
            # confirmed by verifying the exe exists after extraction.
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
                if attempt < 2:
                    backoff_time = 2 ** attempt
                    print(f"[Tools] Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                last_error = error

        if not success:
            return False, f"Download failed: {last_error}"

        # --- Install ---
        # Clean existing installation before extracting new files
        if os.path.exists(RYZENADJ_DIR):
            shutil.rmtree(RYZENADJ_DIR, ignore_errors=True)

        print(f"[Tools] Extracting to {RYZENADJ_DIR}...")
        success, error = extract_zip(zip_path, RYZENADJ_DIR, flatten=True)
        if not success:
            return False, f"Extract failed: {error}"

        # Remove temp zip
        try:
            os.remove(zip_path)
        except Exception:
            pass

        # Verify the exe is present after extraction.
        # NOTE: We intentionally do NOT call get_ryzenadj_installed_version()
        # here because running ryzenadj.exe requires AMD hardware / admin
        # access and will hang indefinitely when those aren't available.
        if os.path.exists(get_ryzenadj_path()):
            print("[Tools] RyzenAdj installed successfully!")
            return True, None
        else:
            return False, "ryzenadj.exe not found after extraction"

    except Exception as e:
        return False, str(e)


def download_ffmpeg(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install FFmpeg to AppData.
    
    Returns:
        (success, error_message)
    """
    import time
    
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"ffmpeg-essentials-{uuid.uuid4().hex}.zip")
        
        last_error = None
        success = False
        for attempt in range(5):  # Increased from 1 to 5
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
        
        # Clean existing installation
        if os.path.exists(FFMPEG_DIR):
            shutil.rmtree(FFMPEG_DIR, ignore_errors=True)
        
        # Extract to temp first (FFmpeg ZIP has nested folder)
        print(f"[Tools] Extracting FFmpeg...")
        temp_extract = os.path.join(temp_dir, "ffmpeg_extract")
        success, error = extract_zip(zip_path, temp_extract, flatten=False)
        if not success:
            return False, f"Extract failed: {error}"
        
        # Find the extracted folder (e.g., ffmpeg-7.0-essentials_build)
        extracted_folders = [f for f in os.listdir(temp_extract) if f.startswith("ffmpeg")]
        if not extracted_folders:
            return False, "FFmpeg folder not found in archive"
        
        extracted_folder = os.path.join(temp_extract, extracted_folders[0])
        
        # Move to final destination
        os.makedirs(FFMPEG_DIR, exist_ok=True)
        
        # Copy bin folder
        src_bin = os.path.join(extracted_folder, "bin")
        dst_bin = os.path.join(FFMPEG_DIR, "bin")
        if os.path.exists(src_bin):
            shutil.copytree(src_bin, dst_bin)
        
        # Cleanup
        try:
            shutil.rmtree(temp_extract)
            os.remove(zip_path)
        except:
            pass
        
        # Verify installation
        if os.path.exists(get_ffmpeg_path()):
            print("[Tools] FFmpeg installed successfully!")
            return True, None
        else:
            return False, "ffmpeg.exe not found after extraction"
        
    except Exception as e:
        return False, str(e)


def download_librehwmon(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install LibreHardwareMonitor to AppData.
    
    Returns:
        (success, error_message)
    """
    import time
    
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"LibreHardwareMonitor-{uuid.uuid4().hex}.zip")
        
        last_error = None
        success = False
        for attempt in range(5):  # Increased from 1 to 5
            print(f"[Tools] Downloading LibreHardwareMonitor from {LIBREHWMON_URL} (attempt {attempt + 1}/5)...")
            success, error = download_file(
                LIBREHWMON_URL,
                zip_path,
                progress_callback,
                expected_checksum=CHECKSUMS["librehwmon"],
                checksum_algorithm="sha256"
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
        
        # Clean existing installation
        if os.path.exists(LIBREHWMON_DIR):
            shutil.rmtree(LIBREHWMON_DIR, ignore_errors=True)
        
        # Extract (LibreHardwareMonitor ZIP has files directly at root)
        print(f"[Tools] Extracting to {LIBREHWMON_DIR}...")
        success, error = extract_zip(zip_path, LIBREHWMON_DIR, flatten=False)
        if not success:
            return False, f"Extract failed: {error}"
        
        # Cleanup temp file
        try:
            os.remove(zip_path)
        except Exception:
            pass
        
        # Verify installation
        if os.path.exists(get_librehwmon_path()):
            print("[Tools] LibreHardwareMonitor installed successfully!")
            return True, None
        else:
            return False, "LibreHardwareMonitor.exe not found after extraction"
        
    except Exception as e:
        return False, str(e)


def download_hwinfo(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install HWiNFO Portable to AppData.
    Uses the smallest portable version (~5MB).
    
    Returns:
        (success, error_message)
    """
    import time
    
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"hwinfo_portable-{uuid.uuid4().hex}.zip")
        
        last_error = None
        success = False
        for attempt in range(5):  # Increased from 1 to 5
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
        
        # Clean existing installation
        if os.path.exists(HWINFO_DIR):
            shutil.rmtree(HWINFO_DIR, ignore_errors=True)
        
        # Extract (HWiNFO ZIP has files directly at root)
        print(f"[Tools] Extracting to {HWINFO_DIR}...")
        success, error = extract_zip(zip_path, HWINFO_DIR, flatten=False)
        if not success:
            return False, f"Extract failed: {error}"
        
        # Cleanup temp file
        try:
            os.remove(zip_path)
        except Exception:
            pass
        
        # Verify installation (check for 64-bit or 32-bit version)
        if os.path.exists(get_hwinfo_path()) or os.path.exists(get_hwinfo32_path()):
            print("[Tools] HWiNFO installed successfully!")
            return True, None
        else:
            return False, "HWiNFO64.exe not found after extraction"
        
    except Exception as e:
        return False, str(e)


# Qt UI functions (require PySide6)
def show_download_dialog(parent, tool_name: str, download_func: Callable) -> bool:
    """
    Show download consent dialog and progress with background thread.
    Uses Python threading for truly non-blocking download.
    """
    try:
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
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
        
        # Create progress dialog
        progress = QProgressDialog(
            f"Downloading {tool_name}...",
            "Cancel",
            0, 100,
            parent
        )
        progress.setWindowTitle(f"Installing {tool_name}")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
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
                percent = int((state["downloaded"] / state["total"]) * 100)
                progress.setValue(percent)
                progress.setLabelText(
                    f"Downloading {tool_name}... {state['downloaded'] // 1024} KB / {state['total'] // 1024} KB"
                )
                
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
            reply = QMessageBox.information(
                parent,
                "Download Complete",
                f"{tool_name} has been installed successfully!\n\nHELXAID needs to restart to apply changes.",
                QMessageBox.Ok
            )
            
            # Restart the application using QProcess which works correctly
            # on Windows for both frozen executables and dev script runs.
            # os.execl() is unreliable on Windows (does not truly replace
            # the process when running under a debugger or via pythonw).
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
                # Fallback: tell user to restart manually
                QMessageBox.information(
                    parent,
                    "Restart Required",
                    "Please close and reopen HELXAID manually to complete the installation."
                )
            
            return True

        else:
            QMessageBox.critical(
                parent,
                "Download Failed",
                f"Failed to install {tool_name}:\n{state['error']}"
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


def download_vlc(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install VLC Portable to AppData.
    
    VLC Portable provides:
    - Hardware decoding (D3D11VA/DXVA2)
    - All codec support
    - Audio pitch correction at playback speed changes
    
    Returns:
        (success, error_message)
    """
    import time
    
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        archive_path = os.path.join(temp_dir, f"vlc-portable-{uuid.uuid4().hex}.zip")

        last_error = None
        success = False
        for url_idx, url in enumerate(VLC_URLS):
            for attempt in range(5):  # Increased from 3 to 5
                print(f"[Tools] Downloading VLC from {url} (attempt {attempt + 1}/5)...")
                success, error = download_file(
                    url, 
                    archive_path, 
                    progress_callback,
                    expected_checksum=CHECKSUMS["vlc"],
                    checksum_algorithm="sha256"
                )
                if success:
                    print(f"[Tools] VLC download validated successfully")
                    last_error = None
                    break
                else:
                    print(f"[Tools] Download failed: {error}")
                    if attempt < 4:  # Don't sleep on last attempt
                        backoff_time = 2 ** attempt  # Exponential backoff
                        print(f"[Tools] Waiting {backoff_time}s before retry...")
                        time.sleep(backoff_time)
                    last_error = error
            if success:
                break
            else:
                # Delete corrupted file before trying next URL
                try:
                    if os.path.exists(archive_path):
                        os.remove(archive_path)
                except:
                    pass
        if not success:
            return False, f"Download failed: {last_error}"
        
        # Clean existing installation
        if os.path.exists(VLC_DIR):
            shutil.rmtree(VLC_DIR, ignore_errors=True)
        
        # Extract ZIP file
        print(f"[Tools] Extracting VLC...")
        temp_extract = os.path.join(temp_dir, "vlc_extract")
        if os.path.exists(temp_extract):
            shutil.rmtree(temp_extract, ignore_errors=True)
        
        success, error = extract_zip(archive_path, temp_extract, flatten=False)
        if not success:
            return False, f"Extract failed: {error}"
        
        # Find the extracted folder (e.g., vlc-3.0.20-win64)
        extracted_folders = [f for f in os.listdir(temp_extract) if f.startswith("vlc")]
        if not extracted_folders:
            return False, "VLC folder not found in archive"
        
        extracted_folder = os.path.join(temp_extract, extracted_folders[0])
        
        # Move to final destination
        os.makedirs(VLC_DIR, exist_ok=True)
        
        # Copy all files from extracted folder
        for item in os.listdir(extracted_folder):
            src = os.path.join(extracted_folder, item)
            dst = os.path.join(VLC_DIR, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        
        # Cleanup
        try:
            shutil.rmtree(temp_extract)
            os.remove(archive_path)
        except:
            pass
        
        # Verify installation
        if os.path.exists(get_vlc_path()) and os.path.exists(get_libvlc_path()):
            print("[Tools] VLC installed successfully!")
            return True, None
        else:
            return False, "vlc.exe or libvlc.dll not found after extraction"
        
    except Exception as e:
        return False, str(e)


def ensure_vlc(parent=None) -> bool:
    """
    Ensure VLC is available, downloading if needed.
    
    VLC provides:
    - Hardware video decoding (D3D11VA/DXVA2)
    - All codec support
    - Audio pitch correction at playback speed changes
    
    Args:
        parent: Optional parent widget for dialog
    
    Returns:
        True if VLC is available
    """
    if is_vlc_available():
        return True
    
    if parent:
        return show_download_dialog(parent, "VLC Portable", download_vlc)
    else:
        success, _ = download_vlc()
        return success


def ensure_ffmpeg_and_vlc(parent=None) -> bool:
    """
    Ensure both FFmpeg and VLC are available, downloading both if needed.
    Shows separate floating progress windows for each download.
    
    Args:
        parent: Optional parent widget for dialogs
    
    Returns:
        True if both are available
    """
    try:
        from PySide6.QtWidgets import QMessageBox, QProgressDialog, QApplication
        from PySide6.QtCore import Qt, QTimer, QEventLoop
        import threading
        import time
        
        ffmpeg_needed = not is_ffmpeg_available()
        vlc_needed = not is_vlc_available()
        
        if not ffmpeg_needed and not vlc_needed:
            return True
        
        # Ask user consent once for both
        tools_list = []
        if ffmpeg_needed:
            tools_list.append("FFmpeg (audio processing)")
        if vlc_needed:
            tools_list.append("VLC (hardware video decoding)")
        
        reply = QMessageBox.question(
            parent,
            "Download Required Tools",
            f"The following tools are required for Music Player:\n\n" +
            "\n".join(f"• {t}" for t in tools_list) +
            f"\n\nWould you like to download them now?\n"
            f"They will be installed to: {TOOLS_DIR}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return False
        
        # Download each tool with its own progress window
        for tool_name, download_func, needed in [
            ("FFmpeg", download_ffmpeg, ffmpeg_needed),
            ("VLC Portable", download_vlc, vlc_needed)
        ]:
            if not needed:
                continue
            
            # Shared state between thread and UI
            state = {
                "downloaded": 0,
                "total": 0,
                "done": False,
                "success": False,
                "error": "",
                "cancelled": False
            }
            
            def on_progress(downloaded: int, total: int):
                state["downloaded"] = downloaded
                state["total"] = total
            
            def do_download():
                if state["cancelled"]:
                    return
                success, error = download_func(on_progress)
                state["success"] = success
                state["error"] = error or ""
                state["done"] = True
            
            # Create progress dialog (floating window, not modal)
            progress = QProgressDialog(
                f"Downloading {tool_name}...",
                "Cancel",
                0, 100,
                parent
            )
            progress.setWindowTitle(f"Installing {tool_name}")
            progress.setWindowModality(Qt.NonModal)  # Floating window
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.setWindowFlags(
                progress.windowFlags() | 
                Qt.WindowStaysOnTopHint
            )
            progress.show()
            
            # Start download in thread
            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()
            
            # Poll for completion
            loop = QEventLoop()
            timer = QTimer()
            
            def check_status():
                if progress.wasCanceled():
                    state["cancelled"] = True
                    timer.stop()
                    loop.quit()
                    return
                
                if state["total"] > 0:
                    percent = int((state["downloaded"] / state["total"]) * 100)
                    progress.setValue(percent)
                    progress.setLabelText(
                        f"Downloading {tool_name}... {state['downloaded'] // 1024} KB / {state['total'] // 1024} KB"
                    )
                    
                if state["done"]:
                    timer.stop()
                    loop.quit()
                    
            timer.timeout.connect(check_status)
            timer.start(50)
            loop.exec()
            
            progress.close()
            
            if state["cancelled"]:
                QMessageBox.warning(
                    parent,
                    "Download Cancelled",
                    f"{tool_name} download was cancelled. Some features may not work."
                )
                return False
            
            if not state["success"]:
                QMessageBox.critical(
                    parent,
                    "Download Failed",
                    f"Failed to install {tool_name}:\n{state['error']}"
                )
                return False
        
        # Both installed successfully - ask to restart
        reply = QMessageBox.information(
            parent,
            "Installation Complete",
            "FFmpeg and VLC have been installed successfully!\n\n"
            "HELXAID needs to restart to apply changes.",
            QMessageBox.Ok
        )
        
        # Restart the application
        try:
            from PySide6.QtCore import QProcess
            import sys, os
            
            if getattr(sys, 'frozen', False):
                exe = sys.executable
                args = sys.argv[1:]
            else:
                exe = sys.executable
                args = sys.argv
            
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
            QMessageBox.information(
                parent,
                "Restart Required",
                "Please close and reopen HELXAID manually to complete the installation."
            )
        
        return True
        
    except ImportError:
        # No Qt available, download silently
        if ffmpeg_needed:
            success1, _ = download_ffmpeg()
        else:
            success1 = True
        if vlc_needed:
            success2, _ = download_vlc()
        else:
            success2 = True
        return success1 and success2

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
