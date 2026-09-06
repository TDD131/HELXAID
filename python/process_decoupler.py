"""
Process Decoupler Module for HELXAID
=====================================
Ensures child processes (games, launchers, tools) are fully decoupled from
the HELXAID process tree and any parent Windows Job Objects (e.g., debugpy,
VS Code, Windows Terminal).

Tiered Execution Strategy:
- Tier 1: Out-of-Process Explorer COM Desktop Dispatch (PPID = explorer.exe)
- Tier 2: Win32 CreateProcessW with CREATE_BREAKAWAY_FROM_JOB
- Tier 3: WMI Win32_Process.Create (PPID = wmiprvse.exe)
- Tier 4: Native ctypes ShellExecuteW (Fail-safe direct execution with runas fallback)
"""

import os
import sys
import ctypes
from ctypes import wintypes
from typing import Tuple, Optional

# Win32 Constants
SW_HIDE = 0
SW_SHOWNORMAL = 1
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
SWC_DESKTOP = 8
SWFO_NEEDDISPATCH = 1


def launch_decoupled_process(
    target_path: str,
    args: str = "",
    working_dir: str = "",
    verb: str = "open",
    hidden: bool = False
) -> Tuple[bool, str, Optional[str]]:
    """
    Launch a process detached from the current process tree and Job Object.

    Args:
        target_path: Full path to executable, shortcut (.lnk), or target string.
        args: Command line arguments string.
        working_dir: Working directory (defaults to target's directory).
        verb: Shell execution verb ("open", "runas").
        hidden: If True, spawns process completely hidden with no terminal/console window.

    Returns:
        Tuple of (success: bool, tier_used: str, error_msg: Optional[str])
    """
    clean_target = target_path.strip().strip('"\'').strip()
    if not clean_target:
        return False, "validation", "Empty target path"

    clean_dir = working_dir.strip().strip('"\'').strip() if working_dir else os.path.dirname(clean_target)
    if not clean_dir or not os.path.exists(clean_dir):
        clean_dir = os.path.dirname(clean_target) if os.path.exists(clean_target) else ""

    clean_args = args or ""

    # Automatically suppress console window for scripts, batch files, background commands, or if explicitly requested
    is_script = clean_target.lower().endswith(('.bat', '.cmd', '.vbs', '.ps1'))
    is_console_exec = os.path.basename(clean_target.lower()) in ('cmd.exe', 'powershell.exe', 'pwsh.exe') and any(
        f in (clean_args or "").lower() for f in ('/c', '-c', '-command', '/k')
    )
    is_hidden = hidden or is_script or is_console_exec
    show_mode = SW_HIDE if is_hidden else SW_SHOWNORMAL

    tier1_error = None
    tier2_error = None
    tier3_error = None
    tier4_error = None

    cmd_line = f'"{clean_target}" {clean_args}'.strip() if clean_args else f'"{clean_target}"'

    # =========================================================================
    # TIER 1: WMI Win32_Process.Create (PPID = WmiPrvSE.exe)
    # =========================================================================
    # Spawns outside the caller/IDE process tree under WmiPrvSE.exe in Session 1.
    # Provides absolute immunity against debugpy/IDE restart process-tree kill.
    # =========================================================================
    try:
        import pythoncom
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")
        proc_class = wmi.Get("Win32_Process")
        
        startup_class = wmi.Get("Win32_ProcessStartup")
        startup = startup_class.SpawnInstance_()
        startup.ShowWindow = show_mode

        in_params = proc_class.Methods_("Create").InParameters.SpawnInstance_()
        in_params.CommandLine = cmd_line
        if clean_dir and os.path.exists(clean_dir):
            in_params.CurrentDirectory = clean_dir
        in_params.ProcessStartupInformation = startup

        out_params = proc_class.ExecMethod_("Create", in_params)
        if out_params and out_params.ReturnValue == 0:
            return True, "wmi_provider", None
        else:
            tier1_error = f"WMI ReturnValue {getattr(out_params, 'ReturnValue', 'unknown')}"
    except Exception as e:
        tier1_error = str(e)

    # =========================================================================
    # TIER 2: Out-of-Process Explorer COM Desktop Dispatch (PPID = explorer.exe)
    # =========================================================================
    try:
        import pythoncom
        import win32com.client
        
        shell_app = win32com.client.Dispatch("Shell.Application")
        windows = shell_app.Windows()
        
        # Query desktop window hosted by explorer.exe using pythoncom.VT_I4
        desktop = windows.FindWindowSW(
            win32com.client.VARIANT(pythoncom.VT_I4, 0),
            win32com.client.VARIANT(pythoncom.VT_EMPTY, None),
            SWC_DESKTOP, 0, SWFO_NEEDDISPATCH
        )
        
        if desktop and hasattr(desktop, "Document") and hasattr(desktop.Document, "Application"):
            explorer_dispatch = desktop.Document.Application
            explorer_dispatch.ShellExecute(
                clean_target,
                clean_args,
                clean_dir,
                verb,
                show_mode
            )
            return True, "explorer_com", None
        else:
            tier2_error = "Desktop view dispatch object not found in Explorer"
    except Exception as e:
        tier2_error = str(e)

    # =========================================================================
    # TIER 3: Zero-UAC Helper Service Dispatch (PPID = HelxaidHelperService)
    # =========================================================================
    try:
        from integrations.cpu_controller import is_service_running, send_service_command
        if is_service_running():
            res = send_service_command({
                "action": "launch_process",
                "target": clean_target,
                "args": clean_args,
                "dir": clean_dir
            })
            if isinstance(res, dict) and res.get("status") == "success":
                return True, "zero_uac_service", None
            tier3_error = f"Service response: {res}"
    except Exception as e:
        tier3_error = str(e)

    # =========================================================================
    # TIER 4: Native CreateProcessW with CREATE_BREAKAWAY_FROM_JOB
    # =========================================================================
    try:
        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        si.dwFlags = 0x00000001  # STARTF_USESHOWWINDOW
        si.wShowWindow = show_mode

        pi = PROCESS_INFORMATION()

        flags = CREATE_BREAKAWAY_FROM_JOB | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        if is_hidden:
            flags |= CREATE_NO_WINDOW

        create_ok = ctypes.windll.kernel32.CreateProcessW(
            clean_target if os.path.exists(clean_target) and clean_target.lower().endswith(('.exe', '.bat', '.cmd')) else None,
            cmd_line,
            None,
            None,
            False,
            flags,
            None,
            clean_dir if clean_dir else None,
            ctypes.byref(si),
            ctypes.byref(pi)
        )

        if create_ok:
            ctypes.windll.kernel32.CloseHandle(pi.hThread)
            ctypes.windll.kernel32.CloseHandle(pi.hProcess)
            return True, "createprocess_breakaway", None
        else:
            tier4_error = f"Win32 error {ctypes.windll.kernel32.GetLastError()}"
    except Exception as e:
        tier4_error = str(e)

    # =========================================================================
    # TIER 5: Fail-Safe Direct ShellExecuteW
    # =========================================================================
    try:
        ctypes.windll.shell32.ShellExecuteW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int
        ]
        res = ctypes.windll.shell32.ShellExecuteW(
            None, verb, clean_target, clean_args if clean_args else None, clean_dir or None, show_mode
        )
        if res > 32:
            return True, "shellexecute_direct", None
        
        # If error 5 (Access Denied / UAC elevation needed), escalate to runas
        if res == 5 and verb != "runas":
            res2 = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", clean_target, clean_args if clean_args else None, clean_dir or None, show_mode
            )
            if res2 > 32:
                return True, "shellexecute_runas", None
            return False, "shellexecute_fallback", f"Elevation error {res2}"
            
        return False, "shellexecute_fallback", f"ShellExecute error {res}"
    except Exception as e:
        return False, "failed_all_tiers", f"Tier 1: {tier1_error}, Tier 2: {tier2_error}, Tier 3: {tier3_error}, Tier 4: {tier4_error}, Tier 5: {e}"
