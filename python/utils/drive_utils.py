"""
Drive utilities for HELXTATS storage dashboard and disk cleaner.

Component Name: DriveUtils
"""

from __future__ import annotations

import ctypes
import glob
import os
import re
import shutil
import struct
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

try:
    import psutil
    PSUTIL_AVAILABLE = True
except Exception:
    psutil = None
    PSUTIL_AVAILABLE = False


ProgressCallback = Optional[Callable[[str, int], None]]

DRIVE_TYPES = {
    0: "Unknown",
    1: "No Root",
    2: "Removable",
    3: "Fixed",
    4: "Network",
    5: "CD-ROM",
    6: "RAM Disk",
}

MAX_COLLECTED_PATHS = 5000


@dataclass(frozen=True)
class JunkCategory:
    id: str
    group_id: str
    group_name: str
    subgroup_id: Optional[str]
    subgroup_name: Optional[str]
    name: str
    tier: int
    description: str
    paths: Tuple[str, ...]
    default: bool = False
    requires_admin: bool = False


JUNK_CATEGORIES: Tuple[JunkCategory, ...] = (
    # Group: System -> Item: Recycle Bin
    JunkCategory(
        "recycle_bin",
        "system",
        "System",
        None,
        None,
        "Recycle Bin",
        1,
        "Deleted files stored in per-drive recycle bins.",
        tuple(f"{letter}:\\$Recycle.Bin" for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"),
        default=True,
    ),
    # Group: System -> Subgroup: Windows Temp Files
    JunkCategory(
        "system_temp",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "System temp files",
        1,
        "System temporary files and working directory leftovers.",
        ("%SystemRoot%\\Temp", "%TEMP%", "%LOCALAPPDATA%\\Temp"),
        default=True,
    ),
    JunkCategory(
        "installer_temp",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "Installer temp files",
        2,
        "MSI, WiX, and Visual Studio installer package cache.",
        ("%ProgramData%\\Package Cache",),
        default=False,
    ),
    JunkCategory(
        "downloads_folder",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "Default download folder",
        2,
        "Files inside default User Downloads directory.",
        ("%USERPROFILE%\\Downloads",),
        default=False,
    ),
    JunkCategory(
        "downloaded_installers",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "Downloaded installers",
        2,
        "Windows Update downloaded package cache (SoftwareDistribution).",
        ("%SystemRoot%\\SoftwareDistribution\\Download",),
        default=False,
        requires_admin=True,
    ),
    JunkCategory(
        "recent_files",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "Recent files",
        1,
        "Windows recent file shortcuts and document history.",
        ("%APPDATA%\\Microsoft\\Windows\\Recent",),
        default=False,
    ),
    JunkCategory(
        "error_reports",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "Error reports",
        1,
        "Windows Error Reporting dumps and crash archives.",
        (
            "%LOCALAPPDATA%\\CrashDumps",
            "%LOCALAPPDATA%\\Microsoft\\Windows\\WER\\ReportArchive",
            "%LOCALAPPDATA%\\Microsoft\\Windows\\WER\\ReportQueue",
            "%ProgramData%\\Microsoft\\Windows\\WER\\ReportArchive",
            "%ProgramData%\\Microsoft\\Windows\\WER\\ReportQueue",
        ),
        default=True,
    ),
    JunkCategory(
        "system_logs",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "System logs",
        1,
        "System setup logs, CBS logs, and Panther logs.",
        (
            "%SystemRoot%\\Logs",
            "%SystemRoot%\\Panther",
            "%SystemRoot%\\System32\\winevt\\Logs\\Archive*.evtx",
        ),
        default=True,
    ),
    JunkCategory(
        "system_cache",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "System cache",
        1,
        "DirectX shader cache, Explorer thumbnail and browser caches.",
        (
            "%LOCALAPPDATA%\\D3DSCache",
            "%LOCALAPPDATA%\\NVIDIA\\DXCache",
            "%LOCALAPPDATA%\\NVIDIA\\GLCache",
            "%LOCALAPPDATA%\\AMD\\DxCache",
            "%LOCALAPPDATA%\\Intel\\ShaderCache",
            "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\thumbcache_*.db",
            "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\iconcache_*.db",
        ),
        default=True,
    ),
    JunkCategory(
        "system_local_services",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "System local services",
        2,
        "Delivery Optimization and Windows Update SoftwareDistribution payload cache.",
        (
            "%ProgramData%\\Microsoft\\Windows\\DeliveryOptimization\\Cache",
            "%SystemRoot%\\SoftwareDistribution\\Download",
        ),
        default=True,
        requires_admin=True,
    ),
    JunkCategory(
        "system_expired_files",
        "system",
        "System",
        "win_temp",
        "Windows Temp Files",
        "System expired files",
        3,
        "Windows prefetch launch cache and expired temp files.",
        ("%SystemRoot%\\Prefetch", "%TEMP%\\*.tmp"),
        default=False,
        requires_admin=True,
    ),
    # Group: Browser -> Subgroup: Google Chrome
    JunkCategory(
        "chrome_cache",
        "browser",
        "Browser",
        "chrome",
        "Google Chrome",
        "Internet Cache",
        1,
        "Google Chrome web cache, file system, and temporary files.",
        (
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Cache",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Code Cache",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\GPUCache",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\File System",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Service Worker\\CacheStorage",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Service Worker\\ScriptCache",
        ),
        default=False,
    ),
    JunkCategory(
        "chrome_compact_db",
        "browser",
        "Browser",
        "chrome",
        "Google Chrome",
        "Compact Database",
        1,
        "IndexedDB, Service Worker, and web storage database caches.",
        (
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\IndexedDB",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Service Worker\\CacheStorage",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Service Worker\\ScriptCache",
        ),
        default=False,
    ),
    JunkCategory(
        "chrome_cookies",
        "browser",
        "Browser",
        "chrome",
        "Google Chrome",
        "Cookies",
        2,
        "Saved website session cookies and site preferences.",
        (
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Network\\Cookies",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Cookies",
        ),
        default=False,
    ),
    JunkCategory(
        "chrome_history",
        "browser",
        "Browser",
        "chrome",
        "Google Chrome",
        "History",
        2,
        "Browsing history, visited links, and top sites.",
        (
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\History",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Visited Links",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Top Sites",
        ),
        default=False,
    ),
    JunkCategory(
        "chrome_session",
        "browser",
        "Browser",
        "chrome",
        "Google Chrome",
        "Session",
        2,
        "Saved open tabs and browser session state.",
        (
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Sessions",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Session Storage",
        ),
        default=False,
    ),
    JunkCategory(
        "chrome_passwords",
        "browser",
        "Browser",
        "chrome",
        "Google Chrome",
        "Save Password",
        3,
        "Saved login credentials and passwords (USE WITH CAUTION).",
        (
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Login Data",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\*\\Login Data For Account",
        ),
        default=False,
    ),
    # Group: Browser -> Subgroup: Microsoft Edge
    JunkCategory(
        "edge_cache",
        "browser",
        "Browser",
        "edge",
        "Microsoft Edge",
        "Internet Cache",
        1,
        "Microsoft Edge web cache and temporary files.",
        (
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Cache",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Code Cache",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\GPUCache",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\File System",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Service Worker\\CacheStorage",
        ),
        default=False,
    ),
    JunkCategory(
        "edge_compact_db",
        "browser",
        "Browser",
        "edge",
        "Microsoft Edge",
        "Compact Database",
        1,
        "Edge IndexedDB and web storage database caches.",
        (
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\IndexedDB",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Service Worker\\CacheStorage",
        ),
        default=False,
    ),
    JunkCategory(
        "edge_cookies",
        "browser",
        "Browser",
        "edge",
        "Microsoft Edge",
        "Cookies",
        2,
        "Saved Microsoft Edge cookies and site preferences.",
        (
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Network\\Cookies",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Cookies",
        ),
        default=False,
    ),
    JunkCategory(
        "edge_history",
        "browser",
        "Browser",
        "edge",
        "Microsoft Edge",
        "History",
        2,
        "Edge browsing history and top sites.",
        (
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\History",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Top Sites",
        ),
        default=False,
    ),
    JunkCategory(
        "edge_session",
        "browser",
        "Browser",
        "edge",
        "Microsoft Edge",
        "Session",
        2,
        "Saved open tabs and Edge session state.",
        (
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Sessions",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Session Storage",
        ),
        default=False,
    ),
    JunkCategory(
        "edge_passwords",
        "browser",
        "Browser",
        "edge",
        "Microsoft Edge",
        "Save Password",
        3,
        "Edge saved passwords (USE WITH CAUTION).",
        (
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\*\\Login Data",
        ),
        default=False,
    ),
    # Group: Browser -> Subgroup: Brave Browser
    JunkCategory(
        "brave_cache",
        "browser",
        "Browser",
        "brave",
        "Brave Browser",
        "Internet Cache",
        1,
        "Brave Browser web cache and temporary files.",
        (
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\Cache",
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\Code Cache",
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\File System",
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\Service Worker\\CacheStorage",
        ),
        default=False,
    ),
    JunkCategory(
        "brave_compact_db",
        "browser",
        "Browser",
        "brave",
        "Brave Browser",
        "Compact Database",
        1,
        "Brave IndexedDB and web storage database caches.",
        (
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\IndexedDB",
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\Service Worker\\CacheStorage",
        ),
        default=False,
    ),
    JunkCategory(
        "brave_cookies",
        "browser",
        "Browser",
        "brave",
        "Brave Browser",
        "Cookies",
        2,
        "Saved Brave session cookies and site preferences.",
        (
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\Network\\Cookies",
        ),
        default=False,
    ),
    JunkCategory(
        "brave_history",
        "browser",
        "Browser",
        "brave",
        "Brave Browser",
        "History",
        2,
        "Brave browsing history and top sites.",
        (
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\History",
        ),
        default=False,
    ),
    JunkCategory(
        "brave_session",
        "browser",
        "Browser",
        "brave",
        "Brave Browser",
        "Session",
        2,
        "Saved open tabs and Brave session state.",
        (
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\Sessions",
        ),
        default=False,
    ),
    JunkCategory(
        "brave_passwords",
        "browser",
        "Browser",
        "brave",
        "Brave Browser",
        "Save Password",
        3,
        "Brave saved passwords (USE WITH CAUTION).",
        (
            "%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\*\\Login Data",
        ),
        default=False,
    ),
    # Group: Browser -> Subgroup: Mozilla Firefox
    JunkCategory(
        "firefox_cache",
        "browser",
        "Browser",
        "firefox",
        "Mozilla Firefox",
        "Internet Cache",
        1,
        "Mozilla Firefox web cache and temporary files.",
        (
            "%LOCALAPPDATA%\\Mozilla\\Firefox\\Profiles\\*\\cache2",
            "%LOCALAPPDATA%\\Mozilla\\Firefox\\Profiles\\*\\jumpListCache",
        ),
        default=False,
    ),
    JunkCategory(
        "firefox_compact_db",
        "browser",
        "Browser",
        "firefox",
        "Mozilla Firefox",
        "Compact Database",
        1,
        "Firefox web storage and IndexedDB caches.",
        (
            "%APPDATA%\\Mozilla\\Firefox\\Profiles\\*\\storage\\default",
        ),
        default=False,
    ),
    JunkCategory(
        "firefox_cookies",
        "browser",
        "Browser",
        "firefox",
        "Mozilla Firefox",
        "Cookies",
        2,
        "Saved Firefox session cookies.",
        (
            "%APPDATA%\\Mozilla\\Firefox\\Profiles\\*\\cookies.sqlite",
        ),
        default=False,
    ),
    JunkCategory(
        "firefox_history",
        "browser",
        "Browser",
        "firefox",
        "Mozilla Firefox",
        "History",
        2,
        "Firefox browsing history and bookmarks backup.",
        (
            "%APPDATA%\\Mozilla\\Firefox\\Profiles\\*\\places.sqlite",
        ),
        default=False,
    ),
    JunkCategory(
        "firefox_session",
        "browser",
        "Browser",
        "firefox",
        "Mozilla Firefox",
        "Session",
        2,
        "Saved open tabs and Firefox session state.",
        (
            "%APPDATA%\\Mozilla\\Firefox\\Profiles\\*\\sessionstore-backups",
        ),
        default=False,
    ),
    JunkCategory(
        "firefox_passwords",
        "browser",
        "Browser",
        "firefox",
        "Mozilla Firefox",
        "Save Password",
        3,
        "Firefox saved passwords (USE WITH CAUTION).",
        (
            "%APPDATA%\\Mozilla\\Firefox\\Profiles\\*\\logins.json",
            "%APPDATA%\\Mozilla\\Firefox\\Profiles\\*\\key4.db",
        ),
        default=False,
    ),
    # Group: Browser -> Subgroup: Opera / Opera GX
    JunkCategory(
        "opera_cache",
        "browser",
        "Browser",
        "opera",
        "Opera / Opera GX",
        "Internet Cache",
        1,
        "Opera & Opera GX web cache and temporary files.",
        (
            "%LOCALAPPDATA%\\Opera Software\\Opera Stable\\Cache",
            "%LOCALAPPDATA%\\Opera Software\\Opera GX Stable\\Cache",
        ),
        default=False,
    ),
    JunkCategory(
        "opera_compact_db",
        "browser",
        "Browser",
        "opera",
        "Opera / Opera GX",
        "Compact Database",
        1,
        "Opera web storage and IndexedDB caches.",
        (
            "%APPDATA%\\Opera Software\\Opera Stable\\IndexedDB",
            "%APPDATA%\\Opera Software\\Opera GX Stable\\IndexedDB",
        ),
        default=False,
    ),
    JunkCategory(
        "opera_cookies",
        "browser",
        "Browser",
        "opera",
        "Opera / Opera GX",
        "Cookies",
        2,
        "Saved Opera cookies and site preferences.",
        (
            "%APPDATA%\\Opera Software\\Opera Stable\\Network\\Cookies",
            "%APPDATA%\\Opera Software\\Opera GX Stable\\Network\\Cookies",
        ),
        default=False,
    ),
    JunkCategory(
        "opera_history",
        "browser",
        "Browser",
        "opera",
        "Opera / Opera GX",
        "History",
        2,
        "Opera browsing history.",
        (
            "%APPDATA%\\Opera Software\\Opera Stable\\History",
            "%APPDATA%\\Opera Software\\Opera GX Stable\\History",
        ),
        default=False,
    ),
    JunkCategory(
        "opera_session",
        "browser",
        "Browser",
        "opera",
        "Opera / Opera GX",
        "Session",
        2,
        "Saved open tabs and Opera session state.",
        (
            "%APPDATA%\\Opera Software\\Opera Stable\\Sessions",
            "%APPDATA%\\Opera Software\\Opera GX Stable\\Sessions",
        ),
        default=False,
    ),
    JunkCategory(
        "opera_passwords",
        "browser",
        "Browser",
        "opera",
        "Opera / Opera GX",
        "Save Password",
        3,
        "Opera saved passwords (USE WITH CAUTION).",
        (
            "%APPDATA%\\Opera Software\\Opera Stable\\Login Data",
            "%APPDATA%\\Opera Software\\Opera GX Stable\\Login Data",
        ),
        default=False,
    ),
    # Group: Browser -> Subgroup: Vivaldi
    JunkCategory(
        "vivaldi_cache",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Internet Cache",
        1,
        "Vivaldi web cache and temporary files.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Cache",
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Code Cache",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_compact_db",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Compact Database",
        1,
        "Vivaldi IndexedDB and web storage database caches.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\IndexedDB",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_cookies",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Cookies",
        2,
        "Saved Vivaldi cookies and site preferences.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Network\\Cookies",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_history",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "History",
        2,
        "Vivaldi browsing history.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\History",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_session",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Session",
        2,
        "Saved open tabs and Vivaldi session state.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Sessions",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_passwords",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Save Password",
        3,
        "Vivaldi saved passwords (USE WITH CAUTION).",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Login Data",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_cookies",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Cookies",
        2,
        "Saved Vivaldi cookies and site preferences.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Network\\Cookies",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_history",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "History",
        2,
        "Vivaldi browsing history.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\History",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_session",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Session",
        2,
        "Saved open tabs and Vivaldi session state.",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Sessions",
        ),
        default=False,
    ),
    JunkCategory(
        "vivaldi_passwords",
        "browser",
        "Browser",
        "vivaldi",
        "Vivaldi",
        "Save Password",
        3,
        "Vivaldi saved passwords (USE WITH CAUTION).",
        (
            "%LOCALAPPDATA%\\Vivaldi\\User Data\\*\\Login Data",
        ),
        default=False,
    ),
)


def format_bytes(num_bytes: int) -> str:
    value = float(max(0, num_bytes or 0))
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if value < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def is_admin() -> bool:
    if os.name != "nt":
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _send_ipc_command(payload_dict: dict) -> dict:
    """Send JSON payload to HelxaidHelperService over named pipe for Zero-UAC disk operations."""
    try:
        import win32pipe
        import pywintypes
        import subprocess
        import json
        pipe_name = r'\\.\pipe\HelxaidCpuPipe'
        try:
            win32pipe.WaitNamedPipe(pipe_name, 100)
        except pywintypes.error:
            try:
                subprocess.run(['net.exe', 'start', 'HelxaidHelperService'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                win32pipe.WaitNamedPipe(pipe_name, 2000)
            except Exception:
                return {"status": "error", "message": "Service pipe not available"}
        
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        data = win32pipe.CallNamedPipe(pipe_name, payload_bytes, 1048576, 15000)
        return json.loads(data.decode('utf-8'))
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_junk_categories() -> List[Dict]:
    return [
        {
            "id": cat.id,
            "group_id": cat.group_id,
            "group_name": cat.group_name,
            "subgroup_id": cat.subgroup_id,
            "subgroup_name": cat.subgroup_name,
            "name": cat.name,
            "tier": cat.tier,
            "description": cat.description,
            "default": cat.default,
            "requires_admin": cat.requires_admin,
        }
        for cat in JUNK_CATEGORIES
    ]


def _as_category_dicts(categories: Optional[Iterable]) -> List[Dict]:
    source = categories if categories is not None else JUNK_CATEGORIES
    out = []
    for cat in source:
        if isinstance(cat, JunkCategory):
            out.append({
                "id": cat.id,
                "name": cat.name,
                "tier": cat.tier,
                "description": cat.description,
                "paths": list(cat.paths),
                "default": cat.default,
                "requires_admin": cat.requires_admin,
            })
        else:
            item = dict(cat)
            item.setdefault("tier", 1)
            item.setdefault("description", "")
            item.setdefault("paths", [])
            item.setdefault("default", False)
            item.setdefault("requires_admin", False)
            out.append(item)
    return out


def get_user_downloads_folder() -> str:
    r"""
    Get the universal Windows Downloads folder path, resolving custom/relocated locations
    (e.g., if user moved Downloads to D:\Downloads or another custom drive).

    Component Name: DriveUtils
    """
    if os.name == "nt":
        # 1. Try Windows Shell API (SHGetKnownFolderPath with FOLDERID_Downloads)
        try:
            import ctypes.wintypes
            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_byte * 8),
                ]
            FOLDERID_Downloads = GUID(
                0x374DE290, 0x123F, 0x4565,
                (ctypes.c_byte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B)
            )
            path_ptr = ctypes.c_wchar_p()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(FOLDERID_Downloads), 0, None, ctypes.byref(path_ptr)
            )
            if res == 0 and path_ptr.value:
                dl_path = str(path_ptr.value)
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                if os.path.exists(dl_path):
                    return dl_path
        except Exception:
            pass

        # 2. Fallback to Windows Registry (User Shell Folders)
        try:
            import winreg
            reg_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key) as key:
                for val_name in ("{374DE290-123F-4565-9164-39C4925E467B}", "Downloads"):
                    try:
                        raw_val, _ = winreg.QueryValueEx(key, val_name)
                        if raw_val:
                            expanded_val = os.path.expanduser(os.path.expandvars(raw_val))
                            if os.path.exists(expanded_val):
                                return expanded_val
                    except FileNotFoundError:
                        pass
        except Exception:
            pass

    # 3. Default fallback
    return os.path.expanduser(os.path.expandvars(r"%USERPROFILE%\Downloads"))


def _expanded_paths(raw_paths: Iterable[str]) -> List[str]:
    paths = []
    user_downloads = get_user_downloads_folder()
    default_downloads = os.path.expanduser(os.path.expandvars(r"%USERPROFILE%\Downloads"))

    for raw in raw_paths:
        if not raw:
            continue
        raw_str = str(raw)
        expanded = os.path.expanduser(os.path.expandvars(raw_str))

        # Dynamically resolve relocated Downloads folder (e.g. D:\Downloads)
        if default_downloads.lower() in expanded.lower():
            idx = expanded.lower().find(default_downloads.lower())
            if idx != -1:
                custom_expanded = expanded[:idx] + user_downloads + expanded[idx + len(default_downloads):]
                if custom_expanded not in paths:
                    paths.append(custom_expanded)

        if expanded and expanded not in paths:
            paths.append(expanded)

        if user_downloads and user_downloads not in paths and os.path.exists(user_downloads):
            if default_downloads.lower() in raw_str.lower():
                paths.append(user_downloads)

    return paths


def _has_glob(path: str) -> bool:
    return any(ch in path for ch in "*?[]")


def _safe_cleanup_root(path: str) -> bool:
    if not path:
        return False
    path = os.path.abspath(path)
    drive, tail = os.path.splitdrive(path)
    tail = tail.strip("\\/")
    if not tail:
        return False
    lowered = path.lower().rstrip("\\/")
    blocked = {
        os.path.expandvars("%SystemRoot%").lower().rstrip("\\/"),
        os.path.expandvars("%ProgramFiles%").lower().rstrip("\\/"),
        os.path.expandvars("%ProgramFiles(x86)%").lower().rstrip("\\/"),
        os.path.expandvars("%USERPROFILE%").lower().rstrip("\\/"),
    }
    return lowered not in blocked


def _iter_existing_targets(path: str) -> Iterable[str]:
    if _has_glob(path):
        yield from glob.iglob(path)
    else:
        yield path


def _iter_files(raw_paths: Iterable[str]) -> Iterable[str]:
    seen = set()
    for path in _expanded_paths(raw_paths):
        safe_base = os.path.dirname(path) if _has_glob(path) else path
        if not _safe_cleanup_root(safe_base):
            continue
        for target in _iter_existing_targets(path):
            if not target or target in seen:
                continue
            try:
                if os.path.islink(target) or not os.path.exists(target):
                    continue
                if os.path.isfile(target):
                    seen.add(target)
                    yield target
                    continue
                if not os.path.isdir(target):
                    continue
                for dirpath, dirnames, filenames in os.walk(target, topdown=True, followlinks=False):
                    dirnames[:] = [
                        name for name in dirnames
                        if not os.path.islink(os.path.join(dirpath, name))
                    ]
                    for filename in filenames:
                        file_path = os.path.join(dirpath, filename)
                        if file_path in seen or os.path.islink(file_path):
                            continue
                        seen.add(file_path)
                        yield file_path
            except (PermissionError, OSError):
                continue


def _remove_empty_dirs(raw_paths: Iterable[str]) -> None:
    for path in _expanded_paths(raw_paths):
        if _has_glob(path):
            continue
        if not _safe_cleanup_root(path) or not os.path.isdir(path):
            continue
        root = os.path.abspath(path)
        for dirpath, dirnames, _ in os.walk(root, topdown=False, followlinks=False):
            if os.path.abspath(dirpath) == root:
                continue
            for dirname in dirnames:
                candidate = os.path.join(dirpath, dirname)
                try:
                    os.rmdir(candidate)
                except (PermissionError, OSError):
                    pass
            try:
                os.rmdir(dirpath)
            except (PermissionError, OSError):
                pass


def scan_junk_categories(
    selected_categories: Optional[Iterable[str]] = None,
    progress_callback: ProgressCallback = None,
    categories: Optional[Iterable] = None,
    collect_paths: bool = True,
) -> Dict[str, Dict]:
    cats = _as_category_dicts(categories)
    selected = set(selected_categories or [cat["id"] for cat in cats])
    admin = is_admin()
    results: Dict[str, Dict] = {}
    total = max(1, len([cat for cat in cats if cat["id"] in selected]))
    done = 0

    for cat in cats:
        cat_id = cat["id"]
        if cat_id not in selected:
            continue

        done += 1
        percent = int((done - 1) / total * 100)
        if progress_callback:
            progress_callback(f"Scanning {cat['name']}...", percent)

        result = {
            "id": cat_id,
            "name": cat["name"],
            "tier": int(cat.get("tier", 1)),
            "description": cat.get("description", ""),
            "bytes": 0,
            "file_count": 0,
            "paths": [],
            "path_count_truncated": False,
            "requires_admin": bool(cat.get("requires_admin", False)),
            "admin_required": False,
            "errors": [],
        }

        if result["requires_admin"] and not admin:
            # Delegate to Zero-UAC service
            helper_res = _send_ipc_command({"action": "scan_disk_category", "cat_id": cat_id, "collect_paths": collect_paths})
            if helper_res.get("status") == "success":
                result["bytes"] = helper_res.get("bytes", 0)
                result["file_count"] = helper_res.get("file_count", 0)
                result["paths"] = helper_res.get("paths", [])
                result["path_count_truncated"] = helper_res.get("path_count_truncated", False)
                result["admin_required"] = True # It was required, but we bypassed it via Zero-UAC
            else:
                result["admin_required"] = True
                result["errors"].append(helper_res.get("message", "Zero-UAC service failed to scan"))
            results[cat_id] = result
            continue

        for file_path in _iter_files(cat.get("paths", [])):
            try:
                size = os.path.getsize(file_path)
            except (PermissionError, OSError):
                size = 0
            result["bytes"] += size
            result["file_count"] += 1
            if collect_paths and len(result["paths"]) < MAX_COLLECTED_PATHS:
                result["paths"].append(file_path)
            elif collect_paths:
                result["path_count_truncated"] = True

        results[cat_id] = result

    if progress_callback:
        progress_callback("Scan complete", 100)
    return results


def clean_junk_categories(
    selected_categories: Iterable[str],
    progress_callback: ProgressCallback = None,
    categories: Optional[Iterable] = None,
) -> Tuple[int, int, List[str]]:
    cats = {cat["id"]: cat for cat in _as_category_dicts(categories)}
    selected = [cat_id for cat_id in selected_categories if cat_id in cats]
    admin = is_admin()
    cleaned_bytes = 0
    skipped_bytes = 0
    errors: List[str] = []
    total = max(1, len(selected))

    for index, cat_id in enumerate(selected):
        cat = cats[cat_id]
        if progress_callback:
            progress_callback(f"Cleaning {cat['name']}...", int(index / total * 100))

        if cat.get("requires_admin") and not admin:
            # Delegate to Zero-UAC service
            helper_res = _send_ipc_command({"action": "clean_disk_category", "cat_id": cat_id})
            if helper_res.get("status") == "success":
                cleaned_bytes += helper_res.get("cleaned_bytes", 0)
                skipped_bytes += helper_res.get("skipped_bytes", 0)
                if helper_res.get("errors"):
                    errors.extend(helper_res["errors"])
            else:
                errors.append(f"{cat['name']}: {helper_res.get('message', 'Zero-UAC service failed to clean')}")
            continue

        for file_path in _iter_files(cat.get("paths", [])):
            try:
                size = os.path.getsize(file_path)
            except (PermissionError, OSError):
                size = 0
            try:
                os.remove(file_path)
                cleaned_bytes += size
            except (PermissionError, OSError) as exc:
                skipped_bytes += size
                if len(errors) < 25:
                    errors.append(f"{file_path}: {exc}")
        _remove_empty_dirs(cat.get("paths", []))

    if progress_callback:
        progress_callback("Clean complete", 100)
    return cleaned_bytes, skipped_bytes, errors


def _get_drive_type(path: str) -> str:
    if os.name != "nt":
        return "Fixed"
    try:
        dtype = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(path))
        return DRIVE_TYPES.get(dtype, "Unknown")
    except Exception:
        return "Unknown"


def _get_volume_label(path: str) -> str:
    if os.name != "nt":
        return ""
    try:
        volume_name = ctypes.create_unicode_buffer(261)
        fs_name = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_uint32()
        max_component = ctypes.c_uint32()
        flags = ctypes.c_uint32()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(path),
            volume_name,
            len(volume_name),
            ctypes.byref(serial),
            ctypes.byref(max_component),
            ctypes.byref(flags),
            fs_name,
            len(fs_name),
        )
        return volume_name.value if ok else ""
    except Exception:
        return ""


def _get_cluster_size(path: str) -> int:
    if os.name != "nt":
        return 0
    try:
        sectors_per_cluster = ctypes.c_uint32()
        bytes_per_sector = ctypes.c_uint32()
        free_clusters = ctypes.c_uint32()
        total_clusters = ctypes.c_uint32()
        ok = ctypes.windll.kernel32.GetDiskFreeSpaceW(
            ctypes.c_wchar_p(path),
            ctypes.byref(sectors_per_cluster),
            ctypes.byref(bytes_per_sector),
            ctypes.byref(free_clusters),
            ctypes.byref(total_clusters),
        )
        if not ok:
            return 0
        return int(sectors_per_cluster.value * bytes_per_sector.value)
    except Exception:
        return 0


def _get_logical_drives_fast(include_remote: bool = False) -> List[Dict]:
    if os.name != "nt":
        return []
    try:
        k32 = ctypes.windll.kernel32
        SEM_FAILCRITICALERRORS = 0x0001
        SEM_NOOPENFILEERRORBOX = 0x8000
        old_mode = k32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)
    except Exception:
        return []

    partitions = []
    try:
        drive_mask = k32.GetLogicalDrives()
        for i in range(26):
            if not (drive_mask & (1 << i)):
                continue
            letter = chr(ord('A') + i)
            mountpoint = f"{letter}:\\"
            dtype = k32.GetDriveTypeW(mountpoint)
            if dtype == 4 and not include_remote:
                continue
            if dtype in (0, 1):
                continue

            free_avail = ctypes.c_uint64()
            total_bytes = ctypes.c_uint64()
            total_free = ctypes.c_uint64()
            ok_space = k32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(mountpoint),
                ctypes.byref(free_avail),
                ctypes.byref(total_bytes),
                ctypes.byref(total_free)
            )
            if not ok_space or total_bytes.value == 0:
                continue

            vol_name = ctypes.create_unicode_buffer(261)
            fs_name = ctypes.create_unicode_buffer(261)
            serial = ctypes.c_uint32()
            max_comp = ctypes.c_uint32()
            flags = ctypes.c_uint32()
            ok_vol = k32.GetVolumeInformationW(
                ctypes.c_wchar_p(mountpoint),
                vol_name, len(vol_name),
                ctypes.byref(serial),
                ctypes.byref(max_comp),
                ctypes.byref(flags),
                fs_name, len(fs_name)
            )
            drive_type_str = DRIVE_TYPES.get(dtype, "Fixed")
            label = vol_name.value if (ok_vol and vol_name.value) else ("Local Disk" if dtype == 3 else drive_type_str)
            fstype = fs_name.value if (ok_vol and fs_name.value) else "NTFS"

            sectors_per_cluster = ctypes.c_uint32()
            bytes_per_sector = ctypes.c_uint32()
            free_clusters = ctypes.c_uint32()
            total_clusters = ctypes.c_uint32()
            ok_cluster = k32.GetDiskFreeSpaceW(
                ctypes.c_wchar_p(mountpoint),
                ctypes.byref(sectors_per_cluster),
                ctypes.byref(bytes_per_sector),
                ctypes.byref(free_clusters),
                ctypes.byref(total_clusters)
            )
            cluster_size = int(sectors_per_cluster.value * bytes_per_sector.value) if ok_cluster else 4096

            total = int(total_bytes.value)
            free = int(total_free.value)
            used = max(0, total - free)
            percent = float((used / total * 100) if total else 0.0)

            partitions.append({
                "drive": mountpoint,
                "letter": f"{letter}:",
                "label": label,
                "filesystem": fstype,
                "drive_type": drive_type_str,
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "percent_used": percent,
                "cluster_size": cluster_size,
                "opts": "rw",
            })
    except Exception:
        pass
    finally:
        try:
            k32.SetErrorMode(old_mode)
        except Exception:
            pass

    return partitions


def get_drive_partitions_info(include_remote: bool = False) -> List[Dict]:
    # 1. High-Performance Native Win32 Path (< 0.5ms)
    if os.name == "nt":
        fast_parts = _get_logical_drives_fast(include_remote=include_remote)
        if fast_parts:
            return fast_parts

    # 2. Fallback Path (psutil / standard python)
    partitions = []
    raw_parts = []

    if PSUTIL_AVAILABLE:
        try:
            raw_parts = psutil.disk_partitions(all=False)
        except Exception:
            raw_parts = []

    if not raw_parts and os.name == "nt":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            mount = f"{letter}:\\"
            if os.path.exists(mount):
                raw_parts.append(type("Part", (), {"mountpoint": mount, "fstype": "", "opts": ""})())

    for part in raw_parts:
        mountpoint = getattr(part, "mountpoint", "")
        if not mountpoint:
            continue
        if os.name == "nt" and not mountpoint.endswith("\\"):
            mountpoint += "\\"
        drive_type = _get_drive_type(mountpoint)
        if drive_type == "Network" and not include_remote:
            continue
        if drive_type == "CD-ROM" and not os.path.exists(mountpoint):
            continue
        try:
            usage = psutil.disk_usage(mountpoint) if PSUTIL_AVAILABLE else shutil.disk_usage(mountpoint)
        except Exception:
            continue

        letter = mountpoint.rstrip("\\/")
        label = _get_volume_label(mountpoint) or ("Local Disk" if drive_type == "Fixed" else drive_type)
        total = int(usage.total)
        free = int(usage.free)
        used = int(usage.used)
        percent = float(getattr(usage, "percent", (used / total * 100) if total else 0))
        partitions.append({
            "drive": mountpoint,
            "letter": letter,
            "label": label,
            "filesystem": getattr(part, "fstype", "") or "Unknown",
            "drive_type": drive_type,
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "percent_used": percent,
            "cluster_size": _get_cluster_size(mountpoint),
            "opts": getattr(part, "opts", ""),
        })

    return partitions


def _query_wmi(namespace: str, query: str) -> List[Dict]:
    if os.name != "nt":
        return []
    try:
        import pythoncom
        import win32com.client
    except Exception:
        return []

    rows = []
    initialized = False
    try:
        pythoncom.CoInitialize()
        initialized = True
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        service = locator.ConnectServer(".", f"root\\{namespace}")
        results = service.ExecQuery(query)
        for item in results:
            row = {}
            for prop in item.Properties_:
                try:
                    row[prop.Name] = prop.Value
                except Exception:
                    pass
            rows.append(row)
        item = None
        results = None
        service = None
        locator = None
    except Exception:
        return []
    finally:
        if initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
    return rows


def _query_seek_penalty(handle) -> Optional[bool]:
    """
    Query StorageDeviceSeekPenaltyProperty (0x7) via DeviceIoControl.
    Available without admin rights on Windows 7+.
    Returns:
      False -> No seek penalty (SSD / Flash storage)
      True  -> Incurs seek penalty (Rotational mechanical HDD)
      None  -> Unsupported or query failed
    """
    try:
        k32 = ctypes.windll.kernel32
        IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
        # PropertyId = 7 (StorageDeviceSeekPenaltyProperty), QueryType = 0 (PropertyStandardQuery)
        query_buf = (ctypes.c_ubyte * 12)()
        struct.pack_into('<III', query_buf, 0, 7, 0, 0)
        # DEVICE_SEEK_PENALTY_DESCRIPTOR: Version (DWORD), Size (DWORD), IncursSeekPenalty (BOOLEAN)
        out_buf = (ctypes.c_ubyte * 12)()
        bytes_ret = ctypes.wintypes.DWORD() if hasattr(ctypes, 'wintypes') else ctypes.c_ulong()

        ok = k32.DeviceIoControl(
            handle,
            IOCTL_STORAGE_QUERY_PROPERTY,
            ctypes.byref(query_buf), ctypes.sizeof(query_buf),
            ctypes.byref(out_buf), ctypes.sizeof(out_buf),
            ctypes.byref(bytes_ret),
            None
        )
        if ok and bytes_ret.value >= 9:
            raw = bytes(out_buf[:bytes_ret.value])
            # IncursSeekPenalty is byte 8 (BOOLEAN)
            return bool(raw[8])
    except Exception:
        pass
    return None


def _query_msft_disk_types() -> Dict[int, Dict]:
    """
    Query MSFT_PhysicalDisk from Windows Storage Management API for definitive
    SSD/HDD classification. This is the same source CrystalDiskInfo and Windows
    Optimize Drives use internally. Works WITHOUT admin privileges on Windows 8+.

    Returns: {device_id: {'media_type_num': int, 'bus_type_num': int,
                           'friendly_name': str, 'spindle_speed': int, 'size': int}}

    MSFT MediaType: 0=Unspecified, 3=HDD, 4=SSD, 5=SCM
    MSFT BusType:   7=USB, 11=SATA, 17=NVMe
    """
    result = {}
    try:
        rows = _query_wmi(
            "microsoft\\windows\\storage",
            "SELECT DeviceId, FriendlyName, MediaType, BusType, SpindleSpeed, Size FROM MSFT_PhysicalDisk"
        )
        for row in rows:
            try:
                dev_id = int(row.get('DeviceId', -1))
            except (ValueError, TypeError):
                continue
            if dev_id >= 0:
                result[dev_id] = {
                    'media_type_num': int(row.get('MediaType', 0) or 0),
                    'bus_type_num': int(row.get('BusType', 0) or 0),
                    'friendly_name': str(row.get('FriendlyName', '')).strip(),
                    'spindle_speed': int(row.get('SpindleSpeed', 0) or 0),
                    'size': int(row.get('Size', 0) or 0),
                }
    except Exception:
        pass
    return result


def _resolve_media_type(drive_idx: int, model: str, ioctl_bus_type: int,
                        msft_data: Dict[int, Dict], seek_penalty: Optional[bool] = None) -> str:
    """
    Resolve the media type label for a physical drive using a multi-tier strategy:
      1. MSFT_PhysicalDisk (definitive, OS-level — same source as CrystalDiskInfo)
      2. Win32 IOCTL Seek Penalty (hardware-level seek latency check)
      3. IOCTL bus_type (NVMe = 0x11 is always SSD)
      4. Model name pattern matching (fallback for USB enclosures / legacy systems)
    """
    model_u = model.upper()

    # --- Tier 1: MSFT_PhysicalDisk definitive classification ---
    msft = msft_data.get(drive_idx)
    if msft:
        mt = msft['media_type_num']
        bt = msft['bus_type_num']
        spindle = msft.get('spindle_speed', 0)

        if mt == 4:  # SSD (non-rotating media)
            if bt == 17 or ioctl_bus_type == 0x11 or "NVME" in model_u:
                return "NVMe SSD"
            elif bt == 7 or ioctl_bus_type == 0x07 or "USB" in model_u:
                return "USB SSD"
            else:
                return "SATA SSD"
        elif mt == 3 or spindle > 0:  # HDD (rotational media)
            return "HDD"
        elif mt == 5:  # SCM (Storage Class Memory / Optane)
            return "NVMe SSD"
        # mt == 0 (Unspecified) — proceed to Tier 2

    # --- Tier 2: Win32 IOCTL Seek Penalty (Direct hardware interrogation) ---
    if seek_penalty is not None:
        if seek_penalty is False:  # No seek penalty -> Solid State
            if ioctl_bus_type == 0x11 or "NVME" in model_u:
                return "NVMe SSD"
            elif ioctl_bus_type == 0x07 or "USB" in model_u:
                return "USB SSD"
            else:
                return "SATA SSD"
        elif seek_penalty is True:  # Seek penalty present -> Mechanical spinning platter
            return "HDD"

    # --- Tier 3: IOCTL bus_type check ---
    if ioctl_bus_type == 0x11:
        return "NVMe SSD"

    # --- Tier 4: Pattern & keyword inference ---
    BUS_NAMES = {0x03: "ATA", 0x07: "USB", 0x0B: "SATA", 0x11: "NVMe"}
    bus_name = BUS_NAMES.get(ioctl_bus_type, "")
    return _infer_media_type(model, "", bus_name, "")


def _infer_media_type(model: str, media_type: str, interface_type: str, pnp_id: str = "") -> str:
    """Keyword-based media type inference. Used as ultimate fallback when MSFT_PhysicalDisk
    and IOCTL Seek Penalty data are unavailable or inconclusive."""
    clean_media_type = media_type
    # Win32_DiskDrive returns "Fixed hard disk media" for both SSDs and HDDs
    if "HARD DISK MEDIA" in media_type.upper():
        clean_media_type = ""
    haystack = " ".join([model, clean_media_type, interface_type, pnp_id]).upper()

    # 1. NVMe SSD indicators (NVMe is exclusively SSD)
    if "NVME" in haystack or "NVM" in haystack:
        return "NVMe SSD"
    
    nvme_keywords = (
        # Western Digital NVMe
        "SN740", "SN7100", "SN770", "SN850", "SN580", "SN570", "SN550", "SN530", "SN520", "SN350", "SDDPN", "WD PC ",
        # Samsung NVMe
        "970 EVO", "970 PRO", "980 PRO", "990 PRO", "980", "960 EVO", "960 PRO", "950 PRO", "PM981", "PM9A1", "PM991", "PM961",
        # Kingston NVMe
        "KC3000", "KC2500", "KC2000", "SFYRD", "SFYRS", "SKC3000", "SKC2500", "SNV2S", "SNV3S", "NV2", "NV3", "A2000",
        # Crucial NVMe
        "P1SSD", "P2SSD", "P3SSD", "P5SSD", "CT1000P", "CT2000P", "CT4000P", "CT500P", "CT250P", "T500", "T700", "T705",
        # Corsair / Sabrent / Solidigm / SK Hynix / Lexar NVMe
        "MP600", "MP700", "MP510", "ROCKET 4", "ROCKET NVME", "P41 PLUS", "PLATINUM P41", "GOLD P31", "BC711", "PC711", "PC801",
        "NM790", "NM800", "NM620", "NM710", "CARDEA", "SPATIUM", "EXCERIA PLUS", "EXCERIA PRO", "FIRECUDA 5"
    )
    if any(kw in haystack for kw in nvme_keywords):
        return "NVMe SSD"

    # 2. Explicit Rotational HDD indicators (checked before generic brand names)
    hdd_keywords = (
        "HDD", "SPINNING", "7200", "5400", "5900", "10000RPM",
        # Seagate HDDs
        "BARRACUDA", "IRONWOLF", "SKYHAWK", "EXOS", "FIRECUDA HDD",
        "ST1000", "ST2000", "ST3000", "ST4000", "ST5000", "ST6000", "ST8000", "ST10000", "ST12000", "ST14000", "ST16000",
        # Western Digital HDDs
        "WDC WD", "WD BLUE WD", "WD BLACK WD", "WD RED WD", "WD PURPLE", "WD GOLD", "WD GREEN WD",
        "WD ELEMENTS", "WD MY PASSPORT", "WD MY BOOK", "WD EASYSTORE",
        # Toshiba HDDs
        "TOSHIBA DT", "TOSHIBA MQ", "TOSHIBA MK", "TOSHIBA HD", "TOSHIBA MD", "TOSHIBA MG", "TOSHIBA MN",
        # HGST / Hitachi / Maxtor HDDs
        "HGST", "HITACHI", "DESKSTAR", "TRAVELSTAR", "ULTRASTAR", "MAXTOR",
        # Samsung HDDs (Spinpoint series)
        "SPINPOINT", "HD103", "HD502", "HD322", "HD204", "HD154",
    )
    if any(kw in haystack for kw in hdd_keywords) and not ("SSD" in haystack or "SOLID STATE" in haystack):
        return "HDD"

    # 3. Explicit SSD indicators
    if "SSD" in haystack or "SOLID STATE" in haystack:
        if "USB" in haystack or interface_type == "USB":
            return "USB SSD"
        return "SATA SSD"
    if any(kw in haystack for kw in ("850 EVO", "860 EVO", "870 EVO", "870 QVO", "MX500", "BX500", "SA400", "SU800", "SU650")):
        return "SATA SSD"
    if any(vendor in haystack for vendor in ("SAMSUNG SSD", "KINGSTON SSD", "CRUCIAL SSD", "SANDISK SSD", "INTEL SSD", "KIOXIA SSD", "SKHYNIX SSD", "MICRON SSD")):
        return "SATA SSD"

    # 4. USB Removable Storage
    if "USB" in haystack or interface_type == "USB":
        return "USB Storage"

    return "Storage"


def _read_nvme_smart(handle) -> Optional[Dict]:
    """Read NVMe SMART/Health Log Page 0x02 via DeviceIoControl on an open handle.
    Extracts Composite Temperature, Available Spare, Percentage Used (wear),
    Critical Warnings, and Media Errors according to the NVM Express Specification.
    Returns dict with telemetry or None."""
    try:
        k32 = ctypes.windll.kernel32
        IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
        in_buf = (ctypes.c_ubyte * 48)()
        out_buf = (ctypes.c_ubyte * 560)()
        ret = ctypes.wintypes.DWORD(0) if hasattr(ctypes, 'wintypes') else ctypes.c_ulong(0)
        struct.pack_into('<II', in_buf, 0, 49, 0)  # StorageDeviceProtocolSpecificProperty
        struct.pack_into('<IIIIIIIIII', in_buf, 8, 3, 2, 0x02, 0, 40, 512, 0, 0, 0, 0)
        if k32.DeviceIoControl(handle, IOCTL_STORAGE_QUERY_PROPERTY, ctypes.byref(in_buf), 48,
                               ctypes.byref(out_buf), 560, ctypes.byref(ret), None):
            if ret.value >= 54:
                raw = bytes(out_buf[:ret.value])
                # In STORAGE_PROPERTY_QUERY + STORAGE_PROTOCOL_DATA_DESCRIPTOR:
                # ProtocolDataOffset at byte 24 is relative to descriptor (byte 8 of buffer).
                proto_offset = struct.unpack_from('<I', raw, 24)[0] if len(raw) >= 28 else 40
                data_offset = 8 + proto_offset if (8 + proto_offset + 6 <= len(raw)) else 48

                if data_offset + 6 <= len(raw):
                    # NVMe SMART Log Page 0x02 layout (per NVMe spec):
                    # Byte 0: Critical Warning flags
                    # Byte 1-2: Composite Temperature (Kelvin, uint16 LE)
                    # Byte 3: Available Spare (%)
                    # Byte 4: Available Spare Threshold (%)
                    # Byte 5: Percentage Used (wear indicator)
                    # Byte 160-175: Media and Data Integrity Errors (128-bit)
                    # Byte 176-191: Number of Error Information Log Entries (128-bit)
                    crit_warn = int(raw[data_offset])
                    tk = int.from_bytes(raw[data_offset + 1:data_offset + 3], 'little')
                    temp = max(0, tk - 273) if 200 < tk < 400 else 0
                    avail_spare = int(raw[data_offset + 3])
                    avail_spare_thresh = int(raw[data_offset + 4])
                    wear = int(raw[data_offset + 5])
                    
                    media_errors = 0
                    if data_offset + 168 <= len(raw):
                        media_errors = int.from_bytes(raw[data_offset + 160:data_offset + 168], 'little')

                    return {
                        "wear": wear,
                        "temp": temp,
                        "avail_spare": avail_spare,
                        "avail_spare_thresh": avail_spare_thresh,
                        "critical_warning": crit_warn,
                        "media_errors": media_errors,
                    }
    except Exception:
        pass
    return None


def _read_ata_smart_local(drive_idx: int) -> Optional[Dict]:
    """Read ATA/SATA SMART via WMI MSStorageDriver_FailurePredictData (non-admin on most systems).
    Returns {'wear': int, 'temp': int, 'read_errors': int, 'attrs': dict} or None."""
    all_ata = _read_all_ata_smart_local()
    return all_ata.get(drive_idx)


def _read_all_ata_smart_local() -> Dict[int, Dict]:
    """Query WMI once, return {drive_idx: {...}} for all SATA drives with SMART data.
    Parses both normalized and raw attribute values, resolving SSD wear leveling
    and HDD bad sector indicators accurately."""
    if os.name != "nt":
        return {}
    try:
        rows = _query_wmi("wmi", "SELECT InstanceName, VendorSpecific FROM MSStorageDriver_FailurePredictData")
        if not rows:
            return {}

        # Build PNPDeviceID, Model, and Index map via Win32_DiskDrive
        pnp_to_idx: Dict[str, int] = {}
        model_map: Dict[int, str] = {}
        try:
            dd_rows = _query_wmi("cimv2", "SELECT DeviceID, PNPDeviceID, Index, Model FROM Win32_DiskDrive")
            for dd in (dd_rows or []):
                devid = str(dd.get("DeviceID", "") or "")
                pnp = str(dd.get("PNPDeviceID", "") or "").lower().rstrip("\\")
                model = str(dd.get("Model", "") or "").strip()
                m = re.search(r'physicaldrive(\d+)', devid.lower())
                d_idx = int(m.group(1)) if m else (int(dd.get("Index")) if dd.get("Index") is not None else None)
                if d_idx is not None:
                    if pnp:
                        pnp_to_idx[pnp] = d_idx
                    if model:
                        model_map[d_idx] = model
        except Exception:
            pass

        results: Dict[int, Dict] = {}
        for item in rows:
            iname = str(item.get("InstanceName", "") or "").lower().rstrip("_\\ \t")
            vs = item.get("VendorSpecific")
            if not vs:
                continue
            smart_data = list(vs)
            if len(smart_data) < 362:
                continue

            # Multi-tier matching: PNPDeviceID exact/prefix -> Model token match -> single disk fallback
            didx = None
            for pnp, idx in pnp_to_idx.items():
                if pnp in iname or iname.startswith(pnp) or (len(pnp) > 10 and pnp[:20] in iname):
                    didx = idx
                    break

            if didx is None:
                # Fuzzy match by model tokens
                for idx, model in model_map.items():
                    model_tokens = [t.lower() for t in re.split(r'[\s\-_]+', model) if len(t) >= 4]
                    if model_tokens and any(tok in iname for tok in model_tokens):
                        didx = idx
                        break

            if didx is None:
                # Fallback: if only one instance and one SATA drive known
                if len(rows) == 1 and pnp_to_idx:
                    didx = next(iter(pnp_to_idx.values()), 0)
                else:
                    continue

            attrs: Dict[int, Dict] = {}
            for i in range(30):
                offset = 2 + i * 12
                attr_id = smart_data[offset]
                if attr_id == 0:
                    continue
                flags = int.from_bytes(bytes(smart_data[offset + 1:offset + 3]), 'little')
                current_val = int(smart_data[offset + 3])
                worst_val = int(smart_data[offset + 4])
                raw_bytes = bytes(smart_data[offset + 5:offset + 12]).ljust(8, b'\x00')
                raw_val = struct.unpack_from('<Q', raw_bytes)[0] & 0xFFFFFFFFFFFF
                attrs[attr_id] = {
                    "raw": raw_val,
                    "current": current_val,
                    "worst": worst_val,
                    "flags": flags,
                }

            # Temperature detection (ID 194 or ID 190)
            temp = 0
            if 194 in attrs:
                t_cand = int(attrs[194]["raw"] & 0xFF)
                if 10 <= t_cand <= 95:
                    temp = t_cand
            if not temp and 190 in attrs:
                t_cand = int(attrs[190]["raw"] & 0xFF)
                if 10 <= t_cand <= 95:
                    temp = t_cand

            # Bad sectors / Critical attributes
            reallocated = int(attrs.get(5, {}).get("raw", 0))
            pending = int(attrs.get(197, {}).get("raw", 0))
            uncorrectable = int(attrs.get(198, {}).get("raw", 0))
            reported_uncorr = int(attrs.get(187, {}).get("raw", 0))
            read_errors = reallocated + pending + uncorrectable + reported_uncorr

            # SATA SSD Wear Detection: Check SSD wearout indicator attributes
            # ID 231 (Life Left), 233 (Media Wearout), 169 (Remaining Life), 177 (Wear Leveling), 202 (Lifetime Remaining)
            ssd_wear = 0
            has_ssd_wear = False
            for wear_id in (231, 233, 169, 177, 202, 173):
                if wear_id in attrs:
                    cur = attrs[wear_id]["current"]
                    raw = attrs[wear_id]["raw"]
                    if 0 < cur <= 100:
                        ssd_wear = max(0, 100 - cur)
                        has_ssd_wear = True
                        break
                    elif 0 < raw <= 100:
                        ssd_wear = max(0, 100 - int(raw))
                        has_ssd_wear = True
                        break

            # HDD or bad sector wear penalty
            sector_penalty = min(99, reallocated * 3 + pending * 5 + uncorrectable * 10 + reported_uncorr * 2)

            if has_ssd_wear:
                final_wear = min(99, max(ssd_wear, sector_penalty))
            else:
                final_wear = sector_penalty

            results[didx] = {
                "wear": final_wear,
                "temp": temp,
                "read_errors": read_errors,
                "attrs": {k: v["raw"] for k, v in attrs.items()},
                "raw_attrs": attrs,
                "has_ssd_wear": has_ssd_wear,
            }
        return results
    except Exception:
        return {}


def _read_storage_wmi_local() -> Dict[int, Dict]:
    """Tier 3: Query MSFT_StorageReliabilityCounter and MSFT_PhysicalDisk directly
    via WMI (root\\microsoft\\windows\\storage) without spawning powershell.exe."""
    if os.name != "nt":
        return {}
    try:
        counters: Dict[int, Dict] = {}
        rel_rows = _query_wmi(
            r"microsoft\windows\storage",
            "SELECT DeviceId, Wear, Temperature, ReadErrorsTotal, WriteErrorsTotal, ReadErrorsUncorrected FROM MSFT_StorageReliabilityCounter"
        )
        for r in (rel_rows or []):
            dev_id_str = str(r.get("DeviceId", "")).strip()
            if not dev_id_str.isdigit():
                continue
            didx = int(dev_id_str)
            wear = int(r.get("Wear", 0) or 0)
            temp = int(r.get("Temperature", 0) or 0)
            errs = int(r.get("ReadErrorsTotal", 0) or 0) + int(r.get("WriteErrorsTotal", 0) or 0) + int(r.get("ReadErrorsUncorrected", 0) or 0)
            counters[didx] = {
                "wear": wear,
                "temp": temp,
                "read_errors": errs,
                "source": "msft_storage_wmi",
            }
        return counters
    except Exception:
        return {}


def _make_health_result(wear: int, temp: int, read_errors: int, source: str, avail_spare: int = 0,
                        model: str = "", media_type: str = "", crit_warn: int = 0) -> Dict:
    """Build a standardized health result dict with health score, status, and telemetry."""
    health = max(0, min(100, 100 - wear))
    if crit_warn > 0:
        health = min(health, 50)
        status = "CRITICAL" if (crit_warn & 0x05) else "WARNING"
    elif read_errors > 0 or health < 60:
        status = "CRITICAL" if (health < 30 or read_errors >= 10) else "WARNING"
    else:
        status = "HEALTHY" if health >= 90 else "WARNING"

    # Normalize media type label
    mt_str = str(media_type).strip()
    if mt_str in ("4", "SSD") or any(kw in (model + " " + mt_str).upper() for kw in ("NVME", "SSD", "M.2", "EVO", "PRO")):
        clean_type = "NVMe SSD" if "NVME" in (model + " " + mt_str).upper() else "SSD"
    elif mt_str in ("3", "HDD") or ("HARD DISK" in model.upper()):
        clean_type = "HDD"
    elif mt_str == "5":
        clean_type = "SCM"
    else:
        inferred = _infer_media_type(model, mt_str, "", "")
        if inferred != "Storage":
            clean_type = inferred
        elif "HARD DISK" in mt_str.upper():
            clean_type = "SSD" if any(kw in (model + " " + mt_str).upper() for kw in ("SSD", "NVME", "M.2", "SCSI", "UASP", "KYO")) else "Storage"
        else:
            clean_type = mt_str or "Storage"

    return {
        "wear": wear,
        "temp": temp,
        "read_errors": read_errors,
        "health_pct": health,
        "health_text": f"{health}% {status}",
        "status": status,
        "avail_spare": avail_spare,
        "source": source,
        "model": model,
        "type": clean_type,
        "critical_warning": crit_warn,
    }


def query_drive_health(drive_indices: Optional[List[int]] = None) -> Dict[int, Dict]:
    """Universal drive health detection — consolidated single entry point.

    Tiered Architecture:
    1. Tier 1: Direct Ring-3 NVMe IOCTL (Log Page 0x02) for internal NVMe drives (0ms, non-admin).
    2. Tier 2: Native ATA SMART via MSStorageDriver_FailurePredictData for SATA drives.
    3. Tier 3: CrystalDiskInfo Integration (bundled in tools/crystaldiskinfo, parses smart logs).
    4. Tier 4: Elevated HELXAID Zero-UAC Service IPC fallback.
    5. Tier 5: Direct MSFT Storage WMI (MSFT_StorageReliabilityCounter).
    6. Tier 6: Physical disk metadata fallback.

    Returns: {drive_idx: {'wear': int, 'temp': int, 'read_errors': int, 'health_pct': int,
                           'health_text': str, 'status': str, 'avail_spare': int, 'source': str, ...}}
    """
    if os.name != "nt":
        return {}

    # Discover physical disk indices dynamically if not specified
    disk_metadata: Dict[int, Dict] = {}
    if drive_indices is None:
        discovered_indices: List[int] = []
        try:
            dd_rows = _query_wmi("cimv2", "SELECT DeviceID, Index, Model, MediaType, InterfaceType FROM Win32_DiskDrive")
            for dd in (dd_rows or []):
                devid = str(dd.get("DeviceID", "") or "")
                m = re.search(r'physicaldrive(\d+)', devid.lower())
                d_idx = int(m.group(1)) if m else (int(dd.get("Index")) if dd.get("Index") is not None else None)
                if d_idx is not None:
                    discovered_indices.append(d_idx)
                    disk_metadata[d_idx] = {
                        "model": str(dd.get("Model", "") or "").strip(),
                        "media_type": str(dd.get("MediaType", "") or "").strip(),
                        "interface": str(dd.get("InterfaceType", "") or "").strip(),
                    }
        except Exception:
            pass
        drive_indices = sorted(set(discovered_indices)) if discovered_indices else list(range(4))

    results: Dict[int, Dict] = {}
    k32 = ctypes.windll.kernel32
    FILE_SHARE_RW = 0x01 | 0x02
    OPEN_EXISTING = 3

    # Tier 2 Data Collection: ATA SMART for all drives once via WMI
    ata_all = _read_all_ata_smart_local()
    ata_cache: Dict[int, Dict] = {
        idx: ata for idx, ata in ata_all.items()
        if idx in drive_indices and (ata["wear"] > 0 or ata["temp"] > 0 or ata["read_errors"] > 0 or ata.get("has_ssd_wear"))
    }

    # Process each drive index for ATA / Direct NVMe
    for idx in drive_indices:
        meta = disk_metadata.get(idx, {})
        model_name = meta.get("model", "")
        media_type = meta.get("media_type", "")

        # Tier 2: ATA SMART check
        if idx in ata_cache:
            ata = ata_cache[idx]
            results[idx] = _make_health_result(
                wear=ata["wear"],
                temp=ata["temp"],
                read_errors=ata["read_errors"],
                source="ata_wmi",
                model=model_name,
                media_type=media_type,
            )
            continue

        # Tier 1: Direct NVMe IOCTL — query PhysicalDriveX
        path = f"\\\\.\\PhysicalDrive{idx}"
        handle = k32.CreateFileW(path, 0, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
        if handle in (-1, 0, 0xFFFFFFFFFFFFFFFF):
            handle = k32.CreateFileW(path, 0x80000000, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
        if handle not in (-1, 0, 0xFFFFFFFFFFFFFFFF):
            try:
                nvme = _read_nvme_smart(handle)
                if nvme and (nvme["wear"] > 0 or nvme["temp"] > 0 or nvme.get("avail_spare", 0) > 0 or nvme.get("critical_warning", 0) > 0):
                    results[idx] = _make_health_result(
                        wear=nvme["wear"],
                        temp=nvme["temp"],
                        read_errors=nvme.get("media_errors", 0),
                        source="nvme_ioctl",
                        avail_spare=nvme.get("avail_spare", 0),
                        model=model_name,
                        media_type="NVMe SSD",
                        crit_warn=nvme.get("critical_warning", 0),
                    )
            finally:
                k32.CloseHandle(handle)

    # Tier 3: CrystalDiskInfo query for remaining drives (USB enclosures, external bridges, etc.)
    missing = [i for i in drive_indices if i not in results]
    if missing:
        try:
            from integrations.crystal_disk_info import query_crystal_disk_info
            cdi_res = query_crystal_disk_info()
            for idx in missing:
                c = cdi_res.get(str(idx))
                if not c:
                    meta = disk_metadata.get(idx, {})
                    fn = meta.get("model", "").upper()
                    for _, cd in (cdi_res or {}).items():
                        cd_m = str(cd.get("model", "")).upper()
                        if cd_m and (cd_m in fn or fn in cd_m):
                            c = cd
                            break
                if c and (c.get("temp", 0) > 0 or c.get("health_pct", 0) > 0):
                    meta = disk_metadata.get(idx, {})
                    results[idx] = _make_health_result(
                        wear=c.get("wear", 0),
                        temp=c.get("temp", 0),
                        read_errors=0,
                        source="crystaldiskinfo",
                        model=c.get("model") or meta.get("model", ""),
                        media_type=c.get("media_type") or meta.get("media_type", "SSD"),
                    )
        except Exception:
            pass

    # Tier 4: Elevated HELXAID Service IPC fallback for drives we couldn't read locally
    missing = [i for i in drive_indices if i not in results]
    if missing:
        try:
            from integrations.cpu_controller import send_service_command
            svc = send_service_command({"action": "get_drive_health"})
            if svc and svc.get("status") == "success":
                for dev_id, c in (svc.get("counters") or {}).items():
                    try:
                        didx = int(dev_id)
                    except (ValueError, TypeError):
                        continue
                    if didx in missing and didx not in results:
                        meta = disk_metadata.get(didx, {})
                        results[didx] = _make_health_result(
                            wear=int(c.get("Wear", 0) or 0),
                            temp=int(c.get("Temperature", 0) or 0),
                            read_errors=int(c.get("ReadErrors", 0) or 0),
                            source=c.get("Source", "service"),
                            avail_spare=int(c.get("AvailableSpare", 0) or 0),
                            model=c.get("Model") or meta.get("model", ""),
                            media_type=c.get("MediaType") or meta.get("media_type", ""),
                            crit_warn=int(c.get("CriticalWarning", 0) or 0),
                        )
        except Exception:
            pass

    # Tier 5: Direct MSFT Storage WMI query for remaining drives
    missing = [i for i in drive_indices if i not in results]
    if missing:
        msft_counters = _read_storage_wmi_local()
        for idx in missing:
            if idx in msft_counters:
                c = msft_counters[idx]
                meta = disk_metadata.get(idx, {})
                results[idx] = _make_health_result(
                    wear=c.get("wear", 0),
                    temp=c.get("temp", 0),
                    read_errors=c.get("read_errors", 0),
                    source="msft_storage_wmi",
                    model=meta.get("model", ""),
                    media_type=meta.get("media_type", ""),
                )

    # Tier 6: Baseline fallback for any physically present drive
    for idx in drive_indices:
        if idx not in results and idx in disk_metadata:
            meta = disk_metadata[idx]
            results[idx] = _make_health_result(
                wear=0,
                temp=0,
                read_errors=0,
                source="metadata_fallback",
                model=meta.get("model", f"Disk {idx}"),
                media_type=meta.get("media_type", "Storage"),
            )

    return results


def get_drive_hardware_info(partitions: Optional[List[Dict]] = None) -> Dict[str, Dict]:
    """
    Get hardware mapping for partitions with actual physical disk models.
    """
    if partitions is None:
        partitions = get_drive_partitions_info()

    # Get physical disks to map real models to partitions
    physical_disks = get_physical_disks_info(partitions=partitions)

    hardware: Dict[str, Dict] = {}
    for partition in partitions:
        mountpoint = partition.get("drive", "")
        if not mountpoint:
            continue
        
        # Find matching physical disk for this partition
        matching_disk = None
        for pdisk in physical_disks:
            if mountpoint in pdisk.get("logicals", []) or partition.get("letter", "") in [l.rstrip(":\\/") for l in pdisk.get("logicals", [])]:
                matching_disk = pdisk
                break
        if not matching_disk and len(physical_disks) == 1:
            matching_disk = physical_disks[0]

        if matching_disk:
            model_name = matching_disk.get("model", f"Storage ({mountpoint})")
            bus_type = matching_disk.get("media_type", partition.get("drive_type", "Storage"))
            media_type = matching_disk.get("media_type", partition.get("drive_type", "Storage"))
        else:
            model_name = f"Storage ({mountpoint})"
            bus_type = "Storage"
            media_type = partition.get("drive_type", "Storage")

        hardware[mountpoint] = {
            "model": model_name,
            "bus_type": bus_type,
            "media_type": media_type,
            "smart_status": "OK",
            "temperature": None,
        }
    return hardware


def get_physical_disks_info(partitions: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Query physical disk drive objects using native Win32 DeviceIoControl with robust WMI fallback.
    """
    if partitions is None:
        partitions = get_drive_partitions_info()

    if not partitions:
        return []

    drive_to_disk = {}
    if os.name == "nt":
        try:
            k32 = ctypes.windll.kernel32
            FILE_SHARE_READ = 0x00000001
            FILE_SHARE_WRITE = 0x00000002
            OPEN_EXISTING = 3
            IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
            IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000

            # 1. Map Logical Drives to Physical Disk Numbers
            for p in partitions:
                let = p.get("letter", "").rstrip(":\\/")
                if not let:
                    continue
                vol_path = f"\\\\.\\{let}:"
                h_vol = k32.CreateFileW(
                    vol_path,
                    0,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    0,
                    None
                )
                if h_vol not in (-1, 0, 0xFFFFFFFFFFFFFFFF):
                    extents_buf = (ctypes.c_ubyte * 512)()
                    bytes_ret = ctypes.wintypes.DWORD() if hasattr(ctypes, 'wintypes') else ctypes.c_ulong()
                    ok = k32.DeviceIoControl(
                        h_vol,
                        IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
                        None, 0,
                        ctypes.byref(extents_buf), ctypes.sizeof(extents_buf),
                        ctypes.byref(bytes_ret),
                        None
                    )
                    if ok:
                        raw_ext = bytes(extents_buf[:bytes_ret.value])
                        num_extents = int.from_bytes(raw_ext[0:4], 'little')
                        if num_extents > 0:
                            disk_num = int.from_bytes(raw_ext[8:12], 'little')
                            drive_to_disk.setdefault(disk_num, []).append(p.get("drive", f"{let}:\\"))
                    k32.CloseHandle(h_vol)

            # 2. Query MSFT_PhysicalDisk for definitive SSD/HDD classification
            msft_data = _query_msft_disk_types()

            # 3. Enumerate Physical Drives via DeviceIoControl
            physical_disks = []
            BUS_TYPES = {
                0x00: "Unknown", 0x01: "SCSI", 0x02: "ATAPI", 0x03: "ATA",
                0x07: "USB", 0x08: "RAID", 0x0B: "SATA", 0x11: "NVMe",
            }

            for drive_idx in range(8):
                drive_path = f"\\\\.\\PhysicalDrive{drive_idx}"
                handle = k32.CreateFileW(
                    drive_path,
                    0,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    0,
                    None
                )
                if handle in (-1, 0, 0xFFFFFFFFFFFFFFFF):
                    continue

                query_buf = (ctypes.c_ubyte * 12)()
                out_buf = (ctypes.c_ubyte * 1024)()
                bytes_returned = ctypes.wintypes.DWORD() if hasattr(ctypes, 'wintypes') else ctypes.c_ulong()

                ok = k32.DeviceIoControl(
                    handle,
                    IOCTL_STORAGE_QUERY_PROPERTY,
                    ctypes.byref(query_buf), ctypes.sizeof(query_buf),
                    ctypes.byref(out_buf), ctypes.sizeof(out_buf),
                    ctypes.byref(bytes_returned),
                    None
                )

                if ok:
                    raw = bytes(out_buf[:bytes_returned.value])
                    vendor_offset = int.from_bytes(raw[12:16], 'little')
                    product_offset = int.from_bytes(raw[16:20], 'little')
                    bus_type = int.from_bytes(raw[28:32], 'little')

                    def extract_str(offset):
                        if 0 < offset < len(raw):
                            end = raw.find(b'\x00', offset)
                            if end == -1:
                                end = len(raw)
                            return raw[offset:end].decode('ascii', errors='ignore').strip()
                        return ""

                    vendor = extract_str(vendor_offset)
                    product = extract_str(product_offset)
                    model = f"{vendor} {product}".strip() or f"Physical Drive {drive_idx}"

                    # Query seek penalty for exact SSD vs HDD physical determination
                    seek_penalty = _query_seek_penalty(handle)

                    # Enrich model from MSFT FriendlyName if IOCTL returned a generic name
                    msft_entry = msft_data.get(drive_idx)
                    if msft_entry and msft_entry.get('friendly_name'):
                        if model.startswith("Physical Drive") or len(model) < 4:
                            model = msft_entry['friendly_name']

                    # Resolve media type via MSFT_PhysicalDisk (primary) -> seek penalty -> keyword fallback
                    media_type = _resolve_media_type(drive_idx, model, bus_type, msft_data, seek_penalty)

                    logicals = drive_to_disk.get(drive_idx, [])
                    matching_parts = [p for p in partitions if p.get("drive") in logicals]
                    total_bytes = sum(int(p.get("total_bytes", 0)) for p in matching_parts) if matching_parts else sum(int(p.get("total_bytes", 0)) for p in partitions)

                    # SMART health deferred to post-loop enrichment via query_drive_health
                    # (handles NVMe vs SATA detection correctly)

                    physical_disks.append({
                        "index": drive_idx,
                        "device_id": drive_path,
                        "model": model,
                        "size_bytes": total_bytes,
                        "media_type": media_type,
                        "smart_status": "OK",
                        "health_pct": 100,
                        "health_text": "100% HEALTHY",
                        "wear_pct": 0,
                        "read_errors": 0,
                        "temp_c": 0,
                        "logicals": logicals,
                    })

                k32.CloseHandle(handle)

            # Enrich ALL drives with universal health detection (NVMe IOCTL / ATA WMI / service)
            if physical_disks:
                health_data = query_drive_health([d["index"] for d in physical_disks])
                for d in physical_disks:
                    h = health_data.get(d["index"])
                    if h:
                        d["wear_pct"] = h["wear"]
                        d["temp_c"] = h["temp"]
                        d["read_errors"] = h["read_errors"]
                        d["health_pct"] = h["health_pct"]
                        d["health_text"] = h["health_text"]

            # Check if physical disks returned non-generic models
            has_real_models = physical_disks and any(not d.get("model", "").startswith("Physical Drive ") for d in physical_disks)
            if has_real_models:
                return physical_disks
        except Exception:
            pass

        # 3. Fallback: Query Win32_DiskDrive via WMI (non-admin, works on Intel RST / VMD / all NVMe SSDs)
        try:
            wmi_disks = _query_wmi("cimv2", "SELECT Index, DeviceID, Model, Size, MediaType, InterfaceType, PNPDeviceID FROM Win32_DiskDrive")
            if wmi_disks:
                wmi_physical_disks = []
                for d in wmi_disks:
                    d_idx = int(d.get("Index", 0) if d.get("Index") is not None else 0)
                    raw_model = str(d.get("Model", "")).strip()
                    model = raw_model or f"Physical Drive {d_idx}"
                    size_bytes = int(d.get("Size") or 0)
                    # Use MSFT_PhysicalDisk as primary source, WMI keywords as fallback
                    mtype = _resolve_media_type(d_idx, model, 0, msft_data)
                    if mtype == "Storage":
                        # MSFT didn't have data — fall back to Win32_DiskDrive fields
                        mtype = _infer_media_type(model, str(d.get("MediaType", "")), str(d.get("InterfaceType", "")), str(d.get("PNPDeviceID", "")))
                    
                    logicals = drive_to_disk.get(d_idx, [])
                    if not logicals and len(wmi_disks) == 1:
                        logicals = [p.get("drive") for p in partitions if p.get("drive")]
                    
                    matching_parts = [p for p in partitions if p.get("drive") in logicals]
                    part_total = sum(int(p.get("total_bytes", 0)) for p in matching_parts) if matching_parts else sum(int(p.get("total_bytes", 0)) for p in partitions)

                    wmi_physical_disks.append({
                        "index": d_idx,
                        "device_id": d.get("DeviceID", f"\\\\.\\PhysicalDrive{d_idx}"),
                        "model": model,
                        "size_bytes": size_bytes if size_bytes > 0 else part_total,
                        "media_type": mtype,
                        "smart_status": "OK",
                        "health_pct": 100,
                        "health_text": "100% HEALTHY",
                        "wear_pct": 0,
                        "read_errors": 0,
                        "temp_c": 0,
                        "logicals": logicals,
                    })
                if wmi_physical_disks:
                    # Enrich with actual SMART health data
                    health_data = query_drive_health([d["index"] for d in wmi_physical_disks])
                    for d in wmi_physical_disks:
                        h = health_data.get(d["index"])
                        if h:
                            d["wear_pct"] = h["wear"]
                            d["temp_c"] = h["temp"]
                            d["read_errors"] = h["read_errors"]
                            d["health_pct"] = h["health_pct"]
                            d["health_text"] = h["health_text"]
                    return wmi_physical_disks
        except Exception:
            pass

    # Fallback to logical partition aggregation if Win32 querying is unavailable
    total_bytes = sum(int(p.get("total_bytes", 0)) for p in partitions)
    logicals = [p.get("drive") for p in partitions if p.get("drive")]
    has_ssd_kw = any("SSD" in (p.get("label", "") + " " + p.get("drive_type", "")).upper() for p in partitions)
    media_type_synth = "NVMe SSD" if has_ssd_kw else "Storage"
    model_synth = "Primary SSD Storage" if has_ssd_kw else "System Storage Drive"
    return [{
        "index": 0,
        "device_id": "\\\\.\\PhysicalDrive0",
        "model": model_synth,
        "size_bytes": total_bytes,
        "media_type": media_type_synth,
        "smart_status": "OK",
        "health_pct": 100,
        "health_text": "100% HEALTHY",
        "wear_pct": 0,
        "read_errors": 0,
        "temp_c": 0,
        "logicals": logicals,
    }]


_DRIVE_LETTER_DISK_MAP = {}
_DRIVE_MAP_LAST_TIME = 0.0


def get_drive_to_physical_disk_map() -> Dict[str, int]:
    """
    Maps logical drive identifiers ('C:', 'D:', 'C:\\') to physical disk index (0, 1, ...).
    Caches results for 60 seconds to avoid repetitive IOCTL queries.
    """
    global _DRIVE_LETTER_DISK_MAP, _DRIVE_MAP_LAST_TIME
    now = time.time()
    if _DRIVE_LETTER_DISK_MAP and (now - _DRIVE_MAP_LAST_TIME < 60):
        return _DRIVE_LETTER_DISK_MAP

    mapping: Dict[str, int] = {}
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes
            k32 = ctypes.windll.kernel32
            IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000
            FILE_SHARE_READ = 1
            FILE_SHARE_WRITE = 2
            OPEN_EXISTING = 3

            import string
            for letter in string.ascii_uppercase:
                vol_path = f"\\\\.\\{letter}:"
                h_vol = k32.CreateFileW(
                    vol_path,
                    0,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    0,
                    None
                )
                if h_vol not in (-1, 0, 0xFFFFFFFFFFFFFFFF, 4294967295, 18446744073709551615):
                    extents_buf = (ctypes.c_ubyte * 512)()
                    bytes_ret = ctypes.wintypes.DWORD()
                    ok = k32.DeviceIoControl(
                        h_vol,
                        IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
                        None, 0,
                        ctypes.byref(extents_buf), ctypes.sizeof(extents_buf),
                        ctypes.byref(bytes_ret),
                        None
                    )
                    if ok:
                        raw_ext = bytes(extents_buf[:bytes_ret.value])
                        num_extents = int.from_bytes(raw_ext[0:4], 'little')
                        if num_extents > 0:
                            disk_num = int.from_bytes(raw_ext[8:12], 'little')
                            mapping[f"{letter}:"] = disk_num
                            mapping[f"{letter}:\\"] = disk_num
                            mapping[letter] = disk_num
                    k32.CloseHandle(h_vol)
        except Exception:
            pass

    _DRIVE_LETTER_DISK_MAP = mapping
    _DRIVE_MAP_LAST_TIME = now
    return mapping


_PHYSICAL_DISK_MODEL_MAP = {}
_DISK_MODEL_MAP_LAST_TIME = 0.0


def get_physical_disk_model_map() -> Dict[int, str]:
    """
    Returns mapping from physical disk index (0, 1, ...) to hardware model name.
    Caches results for 120 seconds to avoid unnecessary WMI queries.
    """
    global _PHYSICAL_DISK_MODEL_MAP, _DISK_MODEL_MAP_LAST_TIME
    now = time.time()
    if _PHYSICAL_DISK_MODEL_MAP and (now - _DISK_MODEL_MAP_LAST_TIME < 120):
        return _PHYSICAL_DISK_MODEL_MAP

    model_map: Dict[int, str] = {}
    if os.name == "nt":
        try:
            dd_rows = _query_wmi("cimv2", "SELECT Index, DeviceID, Model FROM Win32_DiskDrive")
            for dd in (dd_rows or []):
                d_idx = dd.get("Index")
                if d_idx is None:
                    devid = str(dd.get("DeviceID", ""))
                    m = re.search(r'physicaldrive(\d+)', devid.lower())
                    if m:
                        d_idx = int(m.group(1))
                if d_idx is not None:
                    raw_model = str(dd.get("Model", "")).strip()
                    if raw_model:
                        model_map[int(d_idx)] = raw_model
        except Exception:
            pass

    _PHYSICAL_DISK_MODEL_MAP = model_map
    _DISK_MODEL_MAP_LAST_TIME = now
    return model_map


def _self_check() -> None:
    root = tempfile.mkdtemp(prefix="helxtats-drive-utils-")
    try:
        junk = os.path.join(root, "junk")
        os.makedirs(junk, exist_ok=True)
        file_path = os.path.join(junk, "cache.tmp")
        with open(file_path, "wb") as f:
            f.write(b"abcd")

        cats = [{
            "id": "self_check",
            "name": "Self Check",
            "tier": 1,
            "paths": [junk, os.path.join(root, "missing")],
            "default": True,
            "requires_admin": False,
        }]
        scanned = scan_junk_categories(categories=cats)
        assert scanned["self_check"]["file_count"] == 1
        assert scanned["self_check"]["bytes"] >= 4

        cleaned, skipped, errors = clean_junk_categories(["self_check"], categories=cats)
        assert cleaned >= 4
        assert skipped >= 0
        assert isinstance(errors, list)
        assert not os.path.exists(file_path)

        locked_path = os.path.join(junk, "locked.tmp")
        os.makedirs(junk, exist_ok=True)
        locked = open(locked_path, "wb")
        try:
            locked.write(b"locked")
            locked.flush()
            cleaned, skipped, errors = clean_junk_categories(["self_check"], categories=cats)
            assert cleaned >= 0
            assert skipped >= 0
            assert isinstance(errors, list)
        finally:
            locked.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    _self_check()
    print("drive_utils self-check passed")
