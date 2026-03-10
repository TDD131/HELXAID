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
from typing import Optional, Tuple, Callable

# AppData tools directory
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", ""), "HELXAID")
TOOLS_DIR = os.path.join(APPDATA_DIR, "tools")

# Tool subdirectories
RYZENADJ_DIR = os.path.join(TOOLS_DIR, "ryzenadj")
FFMPEG_DIR = os.path.join(TOOLS_DIR, "ffmpeg")
LIBREHWMON_DIR = os.path.join(TOOLS_DIR, "librehardwaremonitor")
HWINFO_DIR = os.path.join(TOOLS_DIR, "hwinfo")

# Download URLs
RYZENADJ_URL = "https://github.com/FlyGoat/RyzenAdj/releases/latest/download/ryzenadj-win64.zip"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
LIBREHWMON_URL = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.4/LibreHardwareMonitor-net472.zip"
# HWiNFO Portable (~5MB, latest stable version)
HWINFO_URL = "https://www.hwinfo.com/files/hwi_834.zip"  # v8.34 portable


def get_ryzenadj_path() -> str:
    """Get path to ryzenadj.exe in AppData."""
    return os.path.join(RYZENADJ_DIR, "ryzenadj.exe")


def get_ffmpeg_path() -> str:
    """Get path to ffmpeg.exe in AppData."""
    return os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")


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
    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        return result.returncode == 0
    except:
        return False


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


def download_file(url: str, dest_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download a file from URL to destination path.
    
    Args:
        url: Download URL
        dest_path: Destination file path
        progress_callback: Optional callback(downloaded_bytes, total_bytes)
    
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


def download_ryzenadj(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install RyzenAdj to AppData.
    
    Returns:
        (success, error_message)
    """
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, "ryzenadj-win64.zip")
        
        # Download
        print(f"[Tools] Downloading RyzenAdj from {RYZENADJ_URL}...")
        success, error = download_file(RYZENADJ_URL, zip_path, progress_callback)
        if not success:
            return False, f"Download failed: {error}"
        
        # Clean existing installation
        if os.path.exists(RYZENADJ_DIR):
            shutil.rmtree(RYZENADJ_DIR)
        
        # Extract (flatten to get ryzenadj.exe directly)
        print(f"[Tools] Extracting to {RYZENADJ_DIR}...")
        success, error = extract_zip(zip_path, RYZENADJ_DIR, flatten=True)
        if not success:
            return False, f"Extract failed: {error}"
        
        # Cleanup temp file
        try:
            os.remove(zip_path)
        except:
            pass
        
        # Verify installation
        if os.path.exists(get_ryzenadj_path()):
            print("[Tools] RyzenAdj installed successfully!")
            return True, None
        else:
            return False, "RyzenAdj.exe not found after extraction"
        
    except Exception as e:
        return False, str(e)


def download_ffmpeg(progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, Optional[str]]:
    """
    Download and install FFmpeg to AppData.
    
    Returns:
        (success, error_message)
    """
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, "ffmpeg-essentials.zip")
        
        # Download
        print(f"[Tools] Downloading FFmpeg from {FFMPEG_URL}...")
        success, error = download_file(FFMPEG_URL, zip_path, progress_callback)
        if not success:
            return False, f"Download failed: {error}"
        
        # Clean existing installation
        if os.path.exists(FFMPEG_DIR):
            shutil.rmtree(FFMPEG_DIR)
        
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
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, "LibreHardwareMonitor.zip")
        
        # Download
        print(f"[Tools] Downloading LibreHardwareMonitor from {LIBREHWMON_URL}...")
        success, error = download_file(LIBREHWMON_URL, zip_path, progress_callback)
        if not success:
            return False, f"Download failed: {error}"
        
        # Clean existing installation
        if os.path.exists(LIBREHWMON_DIR):
            shutil.rmtree(LIBREHWMON_DIR)
        
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
    try:
        # Create temp file for download
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, "hwinfo_portable.zip")
        
        # Download
        print(f"[Tools] Downloading HWiNFO from {HWINFO_URL}...")
        success, error = download_file(HWINFO_URL, zip_path, progress_callback)
        if not success:
            return False, f"Download failed: {error}"
        
        # Clean existing installation
        if os.path.exists(HWINFO_DIR):
            shutil.rmtree(HWINFO_DIR)
        
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
            if state["cancelled"]:
                return
            success, error = download_func(on_progress)
            state["success"] = success
            state["error"] = error or ""
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
        
        # Poll for completion with processEvents to keep UI responsive
        from PySide6.QtWidgets import QApplication
        
        while not state["done"]:
            # Process events to keep UI alive
            QApplication.processEvents()
            
            # Check for cancel
            if progress.wasCanceled():
                state["cancelled"] = True
                break
            
            # Update progress display
            if state["total"] > 0:
                percent = int((state["downloaded"] / state["total"]) * 100)
                progress.setValue(percent)
                progress.setLabelText(
                    f"Downloading {tool_name}... {state['downloaded'] // 1024} KB / {state['total'] // 1024} KB"
                )
            
            # Small sleep to avoid CPU spin
            import time
            time.sleep(0.05)
        
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
        True if RyzenAdj is available
    """
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
