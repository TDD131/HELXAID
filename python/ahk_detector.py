"""
AutoHotkey (AHK) User Detection Engine for HELXAID.
Component Name: AHKDetector
Page Domain: HELXAIRO (Macro Setting) & Core System

Features:
- Exhaustive system-wide AutoHotkey detection:
  * Running process detection (AutoHotkey.exe, AutoHotkeyU64.exe, etc.)
  * Windows Registry (HKLM / HKCU / Shell association)
  * System PATH environment
  * Standard installation folders (Program Files, LocalAppData, AppData)
  * HELXAID managed tools (%APPDATA%/HELXAID/tools/ahk)
  * Bundled plugin folder (plugins/ahk)
- Version probing (v1.1 vs v2.x, 32-bit vs 64-bit)
- Active script detection (detects running .ahk scripts and PIDs)
- High-performance caching to prevent repeated disk/registry lookups
"""

import os
import sys
import shutil
import re
from typing import Dict, Any, List, Optional, Tuple

# Cached detection result for zero-latency lookups
_CACHED_AHK_INFO: Optional[Dict[str, Any]] = None


def _get_registry_ahk_paths() -> List[Tuple[str, str]]:
    """Query Windows Registry for AutoHotkey install locations and file associations."""
    if not sys.platform.startswith("win"):
        return []

    found = []
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return []

    # 1. HKLM & HKCU Software\AutoHotkey InstallDir
    roots = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\AutoHotkey"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\AutoHotkey"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\AutoHotkey"),
    ]
    candidate_exes = [
        "AutoHotkeyU64.exe",
        "AutoHotkey.exe",
        "AutoHotkey64.exe",
        "AutoHotkeyU32.exe",
        "AutoHotkeyA32.exe",
        "AutoHotkey32.exe",
        os.path.join("v2", "AutoHotkey64.exe"),
        os.path.join("v2", "AutoHotkey.exe"),
        os.path.join("v1.1", "AutoHotkeyU64.exe"),
        os.path.join("v1.1", "AutoHotkey.exe"),
    ]

    for root_key, sub_key in roots:
        try:
            with winreg.OpenKey(root_key, sub_key) as key:
                val, _ = winreg.QueryValueEx(key, "InstallDir")
                if val and os.path.isdir(val):
                    for exe_rel in candidate_exes:
                        full_path = os.path.join(val, exe_rel)
                        if os.path.exists(full_path):
                            found.append((os.path.abspath(full_path), "registry"))
        except Exception:
            pass

    # 2. Shell Association: HKCR\AutoHotkeyScript\Shell\Open\Command
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"AutoHotkeyScript\Shell\Open\Command") as key:
            val, _ = winreg.QueryValue(key, "")
            if val:
                m = re.search(r'"([^"]+AutoHotkey[^"]*)"', val, re.IGNORECASE)
                if m:
                    extracted_path = m.group(1)
                    if os.path.exists(extracted_path):
                        found.append((os.path.abspath(extracted_path), "registry_shell_assoc"))
    except Exception:
        pass

    return found


def _get_standard_ahk_paths() -> List[Tuple[str, str]]:
    """Check standard Windows installation paths for AutoHotkey."""
    candidates = []

    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    roaming_appdata = os.environ.get("APPDATA", "")

    # Program Files
    candidates.extend([
        (os.path.join(prog_files, "AutoHotkey", "AutoHotkeyU64.exe"), "program_files"),
        (os.path.join(prog_files, "AutoHotkey", "AutoHotkey.exe"), "program_files"),
        (os.path.join(prog_files, "AutoHotkey", "AutoHotkeyU32.exe"), "program_files"),
        (os.path.join(prog_files, "AutoHotkey", "v2", "AutoHotkey64.exe"), "program_files_v2"),
        (os.path.join(prog_files, "AutoHotkey", "v2", "AutoHotkey.exe"), "program_files_v2"),
        (os.path.join(prog_files, "AutoHotkey", "v1.1", "AutoHotkeyU64.exe"), "program_files_v1"),
        (os.path.join(prog_files_x86, "AutoHotkey", "AutoHotkey.exe"), "program_files_x86"),
        (os.path.join(prog_files_x86, "AutoHotkey", "AutoHotkeyU32.exe"), "program_files_x86"),
    ])

    # Local AppData
    if local_appdata:
        candidates.extend([
            (os.path.join(local_appdata, "Programs", "AutoHotkey", "AutoHotkey.exe"), "local_appdata"),
            (os.path.join(local_appdata, "Programs", "AutoHotkey", "AutoHotkeyU64.exe"), "local_appdata"),
            (os.path.join(local_appdata, "Programs", "AutoHotkey", "v2", "AutoHotkey64.exe"), "local_appdata_v2"),
            (os.path.join(local_appdata, "Programs", "AutoHotkey", "v2", "AutoHotkey.exe"), "local_appdata_v2"),
        ])

    # Roaming AppData
    if roaming_appdata:
        candidates.extend([
            (os.path.join(roaming_appdata, "AutoHotkey", "AutoHotkey.exe"), "roaming_appdata"),
            (os.path.join(roaming_appdata, "HELXAID", "tools", "ahk", "AutoHotkey.exe"), "helxaid_tools"),
            (os.path.join(roaming_appdata, "HELXAID", "tools", "ahk", "AutoHotkeyU64.exe"), "helxaid_tools"),
        ])

    # Root Drive Standard Fallbacks
    candidates.extend([
        (r"C:\AutoHotkey\AutoHotkey.exe", "root_path"),
        (r"C:\AutoHotkey\AutoHotkeyU64.exe", "root_path"),
        (r"D:\AutoHotkey\AutoHotkey.exe", "root_path"),
    ])

    # Workspace / App directory plugins (check both python/ and workspace root)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append((os.path.join(base_dir, "plugins", "ahk", "AutoHotkey.exe"), "plugin"))
    candidates.append((os.path.join(base_dir, "plugins", "ahk", "AutoHotkeyU64.exe"), "plugin"))
    root_dir = os.path.dirname(base_dir)
    candidates.append((os.path.join(root_dir, "plugins", "ahk", "AutoHotkey.exe"), "workspace_plugin"))
    candidates.append((os.path.join(root_dir, "plugins", "ahk", "AutoHotkeyU64.exe"), "workspace_plugin"))

    valid = []
    seen = set()
    for path, source in candidates:
        if path and path not in seen and os.path.exists(path):
            seen.add(path)
            valid.append((os.path.abspath(path), source))
    return valid


def _get_path_env_ahk() -> List[Tuple[str, str]]:
    """Check PATH environment variable for AutoHotkey executables."""
    found = []
    names = ["AutoHotkeyU64.exe", "AutoHotkey.exe", "AutoHotkey64.exe", "AutoHotkey"]
    for name in names:
        p = shutil.which(name)
        if p and os.path.exists(p):
            found.append((os.path.abspath(p), "system_path"))
    return found


def _check_running_ahk_processes() -> Dict[str, Any]:
    """
    Ultra-fast process scanner for active AutoHotkey instances.
    Only inspects process names first; queries full details exclusively for matching PIDs.
    """
    result = {
        "running": False,
        "pids": [],
        "paths": [],
        "scripts": []
    }
    ahk_names = {
        "autohotkey.exe",
        "autohotkeyu64.exe",
        "autohotkeyu32.exe",
        "autohotkeya32.exe",
        "autohotkey64.exe",
        "autohotkey32.exe"
    }

    try:
        from utils.drive_utils import psutil  # type: ignore[import-not-found]
    except ImportError:
        try:
            import psutil  # type: ignore[import-not-found]
        except ImportError:
            return result

    try:
        # Fast scan: only request 'name' to avoid querying memory/PEB on 300+ unrelated processes
        for proc in psutil.process_iter(['name']):
            try:
                pname = (proc.info.get('name') or '').lower()
                if pname in ahk_names:
                    result["running"] = True
                    pid = proc.pid
                    if pid and pid not in result["pids"]:
                        result["pids"].append(pid)

                    try:
                        exe = proc.exe()
                        if exe and os.path.exists(exe) and exe not in result["paths"]:
                            result["paths"].append(os.path.abspath(exe))
                    except Exception:
                        pass

                    try:
                        cmdline = proc.cmdline() or []
                        if len(cmdline) > 1:
                            for arg in cmdline[1:]:
                                if arg.lower().endswith(".ahk") and arg not in result["scripts"]:
                                    result["scripts"].append(arg)
                    except Exception:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception:
                pass
    except Exception:
        pass

    return result


def _probe_ahk_version(exe_path: str, allow_subprocess: bool = False) -> Tuple[str, bool]:
    """
    Determine AutoHotkey version (v1.1 vs v2.x).
    Uses fast static heuristics by default for zero startup latency.
    Subprocess probe is only executed if explicitly allowed.
    """
    if not exe_path or not os.path.exists(exe_path):
        return ("unknown", False)

    lower_path = exe_path.lower()
    is_v2_hint = (
        "\\v2\\" in lower_path or 
        "/v2/" in lower_path or 
        "autohotkey64.exe" in os.path.basename(lower_path)
    )

    if not allow_subprocess:
        return ("v2.x" if is_v2_hint else "v1.1", is_v2_hint)

    # Subprocess probe with tight 0.5s timeout if requested
    try:
        import subprocess
        res = subprocess.run(
            [exe_path, "/ErrorStdOut", "*"],
            input=b'FileAppend, %A_AhkVersion%, *',
            capture_output=True,
            timeout=0.5,
            creationflags=0x08000000
        )
        out = res.stdout.decode('utf-8', errors='ignore').strip()
        if out and out[0].isdigit():
            is_v2 = out.startswith("2.")
            return (f"v{out}", is_v2)
    except Exception:
        pass

    try:
        import subprocess
        res2 = subprocess.run(
            [exe_path, "/ErrorStdOut", "*"],
            input=b'FileAppend(A_AhkVersion, "*")',
            capture_output=True,
            timeout=0.5,
            creationflags=0x08000000
        )
        out2 = res2.stdout.decode('utf-8', errors='ignore').strip()
        if out2 and out2[0].isdigit():
            return (f"v{out2}", out2.startswith("2."))
    except Exception:
        pass

    return ("v2.x" if is_v2_hint else "v1.1", is_v2_hint)


def detect_user_ahk(force_refresh: bool = False, check_processes: bool = True, quick: bool = False, allow_subprocess: bool = False) -> Dict[str, Any]:
    """
    Comprehensive discovery of user's AutoHotkey engine across the system.
    Returns a dictionary with complete installation and running state metadata.
    """
    global _CACHED_AHK_INFO
    if quick:
        check_processes = False
        allow_subprocess = False
    if _CACHED_AHK_INFO is not None and not force_refresh:
        if check_processes:
            proc_info = _check_running_ahk_processes()
            _CACHED_AHK_INFO["running"] = proc_info["running"]
            _CACHED_AHK_INFO["running_pids"] = proc_info["pids"]
            _CACHED_AHK_INFO["running_scripts"] = proc_info["scripts"]
        return _CACHED_AHK_INFO

    candidates: List[Tuple[str, str]] = []

    # 1. Running process executables (highest priority if user is already actively using AHK)
    proc_info = _check_running_ahk_processes() if check_processes else {"running": False, "pids": [], "paths": [], "scripts": []}
    for p_exe in proc_info.get("paths", []):
        candidates.append((p_exe, "running_process"))

    # 2. HELXAID managed tools (%APPDATA%/HELXAID/tools/ahk)
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        helx_ahk = os.path.join(appdata, "HELXAID", "tools", "ahk", "AutoHotkey.exe")
        if os.path.exists(helx_ahk):
            candidates.append((os.path.abspath(helx_ahk), "helxaid_tools"))

    # 3. Windows Registry
    candidates.extend(_get_registry_ahk_paths())

    # 4. Standard installation paths
    candidates.extend(_get_standard_ahk_paths())

    # 5. System PATH
    candidates.extend(_get_path_env_ahk())

    # Deduplicate while preserving priority order
    seen_paths = set()
    unique_candidates: List[Tuple[str, str]] = []
    for path, source in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm not in seen_paths and os.path.exists(path):
            seen_paths.add(norm)
            unique_candidates.append((path, source))

    best_path: Optional[str] = None
    best_source = "none"

    if unique_candidates:
        preferred = [c for c in unique_candidates if "v2" not in c[0].lower() and ("u64" in c[0].lower() or "autohotkey.exe" in c[0].lower())]
        if preferred:
            best_path, best_source = preferred[0]
        else:
            best_path, best_source = unique_candidates[0]

    version_str = "none"
    is_v2 = False
    if best_path:
        version_str, is_v2 = _probe_ahk_version(best_path, allow_subprocess=allow_subprocess)

    result = {
        "installed": bool(best_path is not None and os.path.exists(best_path)),
        "path": best_path,
        "version": version_str,
        "source": best_source,
        "running": proc_info.get("running", False),
        "running_pids": proc_info.get("pids", []),
        "running_scripts": proc_info.get("scripts", []),
        "executable_name": os.path.basename(best_path) if best_path else "",
        "is_v2": is_v2,
        "all_found_paths": [c[0] for c in unique_candidates]
    }

    _CACHED_AHK_INFO = result
    return result


def get_user_ahk_path() -> Optional[str]:
    """Return the absolute path of the user's detected AutoHotkey executable."""
    info = detect_user_ahk()
    return info.get("path")


def is_user_ahk_installed() -> bool:
    """Return True if AutoHotkey was found anywhere on the user's system."""
    info = detect_user_ahk()
    return bool(info.get("installed", False))


def is_user_ahk_running() -> bool:
    """Return True if any AutoHotkey process is currently active."""
    info = detect_user_ahk()
    return bool(info.get("running", False))
