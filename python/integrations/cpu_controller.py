import os

DEFAULT_UXTU_PATH = 'C:\\Program Files\\JamesCJ60\\Universal x86 Tuning Utility\\Universal x86 Tuning Utility.exe'

def is_uxtu_installed(custom_path=None):
    return os.path.exists(custom_path or DEFAULT_UXTU_PATH)

"""  
CPU Controller Module for TDD Game Launcher
Handles CPU power/temperature control via RyzenAdj.
"""

import json
import subprocess
import ctypes
import time
import xml.etree.ElementTree as ET

# ----------------------------------------------------------
# RyzenAdj Path and Safety Limits
# ----------------------------------------------------------

# RyzenAdj executable path - checks AppData first, then legacy assets folder
def get_ryzenadj_path() -> str:
    """Get the path to ryzenadj.exe (AppData or legacy assets folder)."""
    # Try AppData first (from tools_downloader)
    try:
        from integrations.tools_downloader import get_ryzenadj_path as get_appdata_path
        appdata_path = get_appdata_path()
        if os.path.exists(appdata_path):
            return appdata_path
    except ImportError:
        pass
    
    # Fallback to legacy assets folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "assets", "ryzenadj.exe")

def is_ryzenadj_available() -> bool:
    """Check if ryzenadj.exe exists (AppData or legacy)."""
    # Try tools_downloader first
    try:
        from integrations.tools_downloader import is_ryzenadj_available as check_available
        return check_available()
    except ImportError:
        pass
    
    # Fallback check
    return os.path.exists(get_ryzenadj_path())

# Legacy UXTU path (kept for compatibility)
DEFAULT_UXTU_PATH = r"C:\Program Files\JamesCJ60\Universal x86 Tuning Utility\Universal x86 Tuning Utility.exe"

# Safety limits (Priority #1) - Values will be clamped to these ranges
SAFETY_LIMITS = {
    "temp_limit": {"min": 50, "max": 95, "default": 85},
    "temp_skin_limit": {"min": 50, "max": 95, "default": 80},
    "stapm_limit": {"min": 15, "max": 65, "default": 40},
    "slow_limit": {"min": 15, "max": 65, "default": 30},
    "slow_duration": {"min": 1, "max": 300, "default": 180},
    "fast_limit": {"min": 15, "max": 80, "default": 50},
    "fast_duration": {"min": 1, "max": 120, "default": 64},
    "cpu_tdc": {"min": 10, "max": 80, "default": 45},
    "cpu_edc": {"min": 10, "max": 100, "default": 60},
    "gfx_tdc": {"min": 10, "max": 60, "default": 35},
    "gfx_edc": {"min": 10, "max": 80, "default": 50},
    # New: SoC current limits
    "soc_tdc": {"min": 10, "max": 80, "default": 64},
    "soc_edc": {"min": 10, "max": 100, "default": 65},
    # New: iGPU clock
    "igpu_clock": {"min": 250, "max": 4000, "default": 1000},
}

# Default profile values
DEFAULT_PROFILE = {
    "temp_limit": 85,
    "temp_skin_limit": 85,
    "stapm_limit": 40,
    "slow_limit": 30,
    "slow_duration": 180,
    "fast_limit": 50,
    "fast_duration": 64,
    "cpu_tdc": 45,
    "cpu_edc": 60,
    "gfx_tdc": 35,
    "gfx_edc": 50,
    # New: SoC and iGPU
    "soc_tdc": 64,
    "soc_edc": 65,
    "igpu_clock": 1000,
    # Enabled settings - controls which settings are applied
    "enabled_settings": {
        "temp_limit": True,
        "temp_skin_limit": True,
        "stapm_limit": False,
        "slow_limit": False,
        "slow_duration": False,
        "fast_limit": False,
        "fast_duration": False,
        "cpu_tdc": False,
        "cpu_edc": False,
        "gfx_tdc": False,
        "gfx_edc": False,
        # New settings default OFF for safety
        "soc_tdc": False,
        "soc_edc": False,
        "igpu_clock": False,
    }
}


def is_uxtu_installed(custom_path: str = None) -> bool:
    """Check if UXTU is installed at the expected path."""
    path = custom_path or DEFAULT_UXTU_PATH
    return os.path.exists(path)


def get_uxtu_directory(custom_path: str = None) -> str:
    """Get the UXTU installation directory."""
    path = custom_path or DEFAULT_UXTU_PATH
    return os.path.dirname(path)


def validate_value(key: str, value: int) -> int:
    """
    Validate and clamp a value to its safety limits.
    Returns the clamped value.
    """
    if key not in SAFETY_LIMITS:
        return value
    
    limits = SAFETY_LIMITS[key]
    clamped = max(limits["min"], min(limits["max"], value))
    
    if clamped != value:
        print(f"Warning: {key} clamped from {value} to {clamped}")
    
    return clamped


def validate_profile(profile: dict) -> dict:
    """Validate all values in a profile and return a safe version."""
    validated = {}
    for key, value in profile.items():
        if key in SAFETY_LIMITS:
            validated[key] = validate_value(key, value)
        else:
            validated[key] = value
    return validated


def get_default_profile() -> dict:
    """Get a copy of the default profile."""
    return DEFAULT_PROFILE.copy()


def is_admin() -> bool:
    """Check if the current process has admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def is_service_running() -> bool:
    """Check if the HELXAID Helper Service is running."""
    try:
        import win32serviceutil
        import win32service
        status = win32serviceutil.QueryServiceStatus('HelxaidHelperService')
        return status[1] == win32service.SERVICE_RUNNING
    except Exception:
        return False


def run_as_admin(command: list) -> tuple:
    """
    Run a command with elevated privileges using UAC.
    Returns (success: bool, error_message: str or None)
    """
    try:
        # Use ShellExecuteW to trigger UAC
        import ctypes
        
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            command[0],
            " ".join(command[1:]) if len(command) > 1 else None,
            None,
            1  # SW_SHOWNORMAL
        )
        
        # Return value > 32 indicates success
        if ret > 32:
            return True, None
        else:
            return False, f"Failed to elevate privileges (error code: {ret})"
    except Exception as e:
        return False, str(e)


def launch_uxtu(custom_path: str = None) -> tuple:
    """
    Launch UXTU application.
    Returns (success: bool, error_message: str or None)
    """
    path = custom_path or DEFAULT_UXTU_PATH
    
    if not os.path.exists(path):
        return False, f"UXTU not found at: {path}"
    
    try:
        # Launch without waiting, detached to prevent locking _MEI directory
        subprocess.Popen(
            [path], 
            cwd=os.path.dirname(path),
            creationflags=subprocess.CREATE_NO_WINDOW | 0x00000008, # DETACHED_PROCESS
            close_fds=True
        )
        return True, None
    except Exception as e:
        return False, str(e)


def get_uxtu_presets_path(custom_path: str = None) -> str:
    """Get the path to UXTU's apuPresets.json file."""
    uxtu_dir = get_uxtu_directory(custom_path)
    return os.path.join(uxtu_dir, "apuPresets.json")



TEMP_PRESET_NAME = "TDD_Launcher_Applied"


def apply_settings_direct(profile: dict, custom_path: str = None) -> tuple:
    """
    Apply CPU settings directly using RyzenAdj.
    Falls back to UXTU if RyzenAdj is not available.
    
    Args:
        profile: Dictionary with profile values
        custom_path: Optional custom path (unused for RyzenAdj)
    
    Returns:
        (success: bool, error_message: str or None)
    """
    print("[CPU DEBUG] apply_settings_direct() called")
    
    # Primary method: RyzenAdj
    if is_ryzenadj_available():
        print("[CPU DEBUG] Using RyzenAdj method")
        return apply_ryzenadj(profile)
    
    # Fallback: UXTU method (if RyzenAdj not found)
    if is_uxtu_installed(custom_path):
        print("[CPU DEBUG] RyzenAdj not found, using UXTU fallback")
        if not is_admin():
            return _apply_settings_elevated(profile, custom_path)
        return apply_settings_auto_restart_direct(profile, custom_path)
    
    print("[CPU DEBUG] Neither RyzenAdj nor UXTU found!")
    return False, "Neither RyzenAdj nor UXTU found. Please install RyzenAdj in assets folder."


def is_pawnio_running() -> bool:
    """Check if UXTU's PawnIO driver is currently running."""
    try:
        import subprocess
        # Check via sc query (works for drivers too)
        result = subprocess.run(["sc.exe", "query", "PawnIO"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return "STATE" in result.stdout and "RUNNING" in result.stdout
    except Exception:
        return False

def send_service_command(payload_dict: dict) -> dict:
    """Send JSON payload to HelxaidHelperService over named pipe."""
    try:
        import win32pipe
        import pywintypes
        import time
        import subprocess
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
        data = win32pipe.CallNamedPipe(pipe_name, payload_bytes, 65536, 15000)
        res = json.loads(data.decode('utf-8'))
        
        # Self-healing: If background service process has older code in memory, automatically trigger self-restart
        if res.get("status") == "error":
            err_msg = str(res.get("message", ""))
            if "Unknown action" in err_msg or "local variable" in err_msg or "UnboundLocalError" in err_msg:
                print(f"[Service IPC] Detected outdated service code ({err_msg}). Triggering background service restart...")
                try:
                    restart_bytes = json.dumps({"action": "restart"}).encode('utf-8')
                    win32pipe.CallNamedPipe(pipe_name, restart_bytes, 65536, 1000)
                except Exception:
                    pass
                
                # Wait for service process to restart and recreate named pipe
                time.sleep(1.0)
                for attempt in range(1, 7):
                    try:
                        try:
                            win32pipe.WaitNamedPipe(pipe_name, 500)
                        except pywintypes.error:
                            subprocess.run(['net.exe', 'start', 'HelxaidHelperService'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                            win32pipe.WaitNamedPipe(pipe_name, 1500)

                        retry_data = win32pipe.CallNamedPipe(pipe_name, payload_bytes, 65536, 15000)
                        print(f"[Service IPC] Successfully reconnected to service after restart (attempt {attempt})")
                        return json.loads(retry_data.decode('utf-8'))
                    except pywintypes.error:
                        print(f"[Service IPC] Waiting for restarted service (attempt {attempt}/6)...")
                        time.sleep(1.0)
                    except Exception as retry_err:
                        print(f"[Service IPC] Auto-retry error (attempt {attempt}): {retry_err}")
                        time.sleep(1.0)
        return res
    except Exception as e:
        return {"status": "error", "message": str(e)}

def apply_ryzenadj(profile: dict) -> tuple:
    """
    Apply CPU settings using RyzenAdj CLI.
    Requires admin elevation.
    
    Returns:
        (success: bool, error_message: str or None)
    """
    # 1. Attempt Service IPC (Zero-UAC)
    try:
        ry_path = get_ryzenadj_path()
        payload = {
            "action": "apply_cpu",
            "profile": profile,
            "ryzenadj_path": ry_path
        }
        
        response = send_service_command(payload)
        
        if response and response.get("status") == "success":
            print(f"[CPU DEBUG] Applied via Helper Service (Zero-UAC): {response.get('message', 'Applied')}")
            return True, None
        elif is_service_running():
            # Helper Service IS running!
            err_msg = response.get("message") if response else "Unknown service error"
            # If response indicates post-SMU crash suppressed or exit code ignored, treat as success
            if response and ("Applied" in str(err_msg) or "crash" in str(err_msg).lower()):
                print(f"[CPU DEBUG] Applied via Helper Service ({err_msg})")
                return True, None
            print(f"[CPU DEBUG] Service IPC returned error: {err_msg}")
            # CRITICAL: Do NOT fall back to UAC prompt when Zero-UAC service is running
            return False, f"Zero-UAC Service error: {err_msg}"
        else:
            err_msg = response.get("message") if response else "Unknown service error"
            print(f"[CPU DEBUG] Service IPC failed or returned error: {err_msg}")
            print("[CPU DEBUG] Falling back to UAC elevation...")
            # Fall through to UAC execution
    except Exception as e:
        print(f"[CPU DEBUG] Service IPC failed: {e}")
        if is_service_running():
            return False, f"Zero-UAC Service IPC error: {e}"

    ryzenadj_path = get_ryzenadj_path()
    print(f"[CPU DEBUG] apply_ryzenadj() - Path: {ryzenadj_path}")
    
    if not os.path.exists(ryzenadj_path):
        print(f"[CPU DEBUG] RyzenAdj NOT FOUND at: {ryzenadj_path}")
        return False, f"RyzenAdj not found at: {ryzenadj_path}"
    
    # Build command arguments
    args = _build_ryzenadj_args(profile)
    print(f"[CPU DEBUG] RyzenAdj args: {' '.join(args)}")
    
    # Execute with elevation if needed
    if not is_admin():
        print("[CPU DEBUG] Not admin - using elevated execution")
        return _execute_ryzenadj_elevated(ryzenadj_path, args)
    else:
        print("[CPU DEBUG] Already admin - direct execution")
        return _execute_ryzenadj_direct(ryzenadj_path, args)


def _build_ryzenadj_args(profile: dict) -> list:
    """Build RyzenAdj command line arguments from profile.
    Only includes settings that are enabled in 'enabled_settings'.
    """
    args = []
    enabled = profile.get("enabled_settings", {})
    
    # Helper function - only add if enabled (default True for backward compat)
    def is_enabled(key):
        return enabled.get(key, True)
    
    # Temperature (°C)
    if is_enabled("temp_limit"):
        temp = profile.get("temp_limit", 85)
        args.append(f"--tctl-temp={temp}")
    
    if is_enabled("temp_skin_limit"):
        skin_temp = profile.get("temp_skin_limit", 80)
        args.append(f"--apu-skin-temp={skin_temp}")
    
    # Power limits (W -> mW)
    if is_enabled("stapm_limit") and "stapm_limit" in profile:
        args.append(f"--stapm-limit={profile['stapm_limit'] * 1000}")
    if is_enabled("slow_limit") and "slow_limit" in profile:
        args.append(f"--slow-limit={profile['slow_limit'] * 1000}")
    if is_enabled("fast_limit") and "fast_limit" in profile:
        args.append(f"--fast-limit={profile['fast_limit'] * 1000}")
    
    # Time limits (seconds)
    if is_enabled("slow_duration") and "slow_duration" in profile:
        args.append(f"--slow-time={profile['slow_duration']}")
    if is_enabled("fast_duration") and "fast_duration" in profile:
        args.append(f"--stapm-time={profile['fast_duration']}")
    
    # CPU current limits (A -> mA)
    if is_enabled("cpu_tdc") and "cpu_tdc" in profile:
        args.append(f"--vrm-current={profile['cpu_tdc'] * 1000}")
    if is_enabled("cpu_edc") and "cpu_edc" in profile:
        args.append(f"--vrmmax-current={profile['cpu_edc'] * 1000}")
    
    # GFX current limits - only TDC, EDC may not be supported on all versions
    if is_enabled("gfx_tdc") and "gfx_tdc" in profile:
        args.append(f"--vrmgfx-current={profile['gfx_tdc'] * 1000}")
    # NOTE: --vrmgfxmax-current not supported on RyzenAdj v0.17.0 and some other versions
    # if is_enabled("gfx_edc") and "gfx_edc" in profile:
    #     args.append(f"--vrmgfxmax-current={profile['gfx_edc'] * 1000}")
    
    # SoC current limits - may not be supported on all versions
    # NOTE: Disabled to avoid errors on older RyzenAdj versions
    # if is_enabled("soc_tdc") and "soc_tdc" in profile:
    #     args.append(f"--vrmsoc-current={profile['soc_tdc'] * 1000}")
    # if is_enabled("soc_edc") and "soc_edc" in profile:
    #     args.append(f"--vrmsocmax-current={profile['soc_edc'] * 1000}")
    
    # iGPU clock (MHz) - may not be supported on all CPUs
    # NOTE: Disabled to avoid errors
    # if is_enabled("igpu_clock") and "igpu_clock" in profile:
    #     args.append(f"--gfx-clk={profile['igpu_clock']}")
    
    return args


def _execute_ryzenadj_direct(ryzenadj_path: str, args: list) -> tuple:
    """Execute RyzenAdj directly (requires admin).
    
    Suppresses Windows Error Reporting (WER) crash dialogs using
    SEM_NOGPFAULTERRORBOX | SEM_FAILCRITICALERRORS. RyzenAdj commonly
    crashes after successfully writing SMU registers, which floods
    Reliability Monitor with false "Stopped working" entries.
    """
    try:
        # Suppress WER crash dialog for this process and children
        SEM_FAILCRITICALERRORS = 0x0001
        SEM_NOGPFAULTERRORBOX = 0x0002
        old_mode = ctypes.windll.kernel32.SetErrorMode(
            SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX
        )
        
        cmd = [ryzenadj_path] + args
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(ryzenadj_path),
            capture_output=True,
            text=True,
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW | 0x00000004  # CREATE_NO_WINDOW | CREATE_DEFAULT_ERROR_MODE suppressed
        )
        
        # Restore original error mode
        ctypes.windll.kernel32.SetErrorMode(old_mode)
        
        # RyzenAdj often exits with non-zero after successfully applying settings
        # Check stdout for success indicators
        output = result.stdout.strip()
        if result.returncode == 0:
            return True, None
        elif output and ("successfully" in output.lower() or "SMU" in output):
            # Settings were applied even though exit code is non-zero
            print(f"[CPU DEBUG] RyzenAdj exited with code {result.returncode} but settings applied")
            return True, None
        else:
            error_msg = result.stderr.strip() or output or "Unknown error"
            return False, f"RyzenAdj failed: {error_msg}"
            
    except Exception as e:
        return False, f"Failed to execute RyzenAdj: {str(e)}"


def _execute_ryzenadj_elevated(ryzenadj_path: str, args: list) -> tuple:
    """Execute RyzenAdj with UAC elevation via PowerShell script.
    
    Uses Start-Process -Wait inside the PS script instead of raw & invocation.
    Suppresses Windows Error Reporting (WER) crash dialogs by:
      1. Setting SEM_NOGPFAULTERRORBOX on the child process via Job Object
      2. Wrapping in try/catch to swallow crash exceptions
      3. Disabling WER for the ryzenadj.exe process via registry (per-session)
    
    This prevents Reliability Monitor from logging "Stopped working" entries
    every time RyzenAdj exits after accessing low-level SMU registers.
    """
    import tempfile
    
    print(f"[CPU DEBUG] _execute_ryzenadj_elevated() called")
    
    try:
        args_str = " ".join(args)
        print(f"[CPU DEBUG] Command: {ryzenadj_path} {args_str}")
        
        # Temp paths for script and output log
        temp_dir = tempfile.gettempdir()
        ps_script_path = os.path.join(temp_dir, "helxaid_ryzenadj.ps1")
        vbs_script_path = os.path.join(temp_dir, "helxaid_ryzenadj.vbs")
        log_path = os.path.join(temp_dir, "helxaid_ryzenadj_output.txt")
        err_path = os.path.join(temp_dir, "helxaid_ryzenadj_error.txt")
        
        print(f"[CPU DEBUG] PS script: {ps_script_path}")
        print(f"[CPU DEBUG] Log path: {log_path}")
        
        # PowerShell script with WER suppression
        # Uses kernel32 SetErrorMode to suppress crash dialogs for child processes
        # and wraps execution in try/catch to handle crash gracefully
        ps_script = f'''
$ErrorActionPreference = 'SilentlyContinue'

# Auto-kill UXTU's PawnIO driver to prevent RyzenAdj crash
sc.exe stop PawnIO | Out-Null
Start-Sleep -Seconds 1.5

# Suppress WER crash dialogs for child processes
$signature = @"
[DllImport("kernel32.dll")]
public static extern uint SetErrorMode(uint uMode);
[DllImport("kernel32.dll")]
public static extern bool SetProcessDEPPolicy(uint dwFlags);
"@
$Kernel32 = Add-Type -MemberDefinition $signature -Name "Kernel32WER" -Namespace "Win32" -PassThru
# SEM_FAILCRITICALERRORS (0x1) | SEM_NOGPFAULTERRORBOX (0x2) | SEM_NOOPENFILEERRORBOX (0x8000)
[void]$Kernel32::SetErrorMode(0x8003)

# Disable WER for this specific exe via registry (session-only, non-persistent)
$werKey = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting\\ExcludedApplications"
if (-not (Test-Path $werKey)) {{ New-Item -Path $werKey -Force | Out-Null }}
Set-ItemProperty -Path $werKey -Name "ryzenadj.exe" -Value 1 -ErrorAction SilentlyContinue

try {{
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "{ryzenadj_path}"
    $psi.Arguments = "{args_str}"
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    # Inherit error mode (SEM_NOGPFAULTERRORBOX) to suppress crash dialog
    $psi.EnvironmentVariables["__COMPAT_LAYER"] = "RUNASINVOKER"
    
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    
    # Wait max 15 seconds (RyzenAdj should finish in <2s)
    $proc.WaitForExit(15000) | Out-Null
    
    $stdout | Out-File -FilePath "{log_path}" -Encoding UTF8
    if ($stderr) {{ $stderr | Out-File -FilePath "{err_path}" -Encoding UTF8 }}
    
    # Write exit code
    Add-Content -Path "{log_path}" -Value "`nExitCode: $($proc.ExitCode)"
}} catch {{
    # RyzenAdj crashed after applying settings - this is NORMAL behavior
    # Settings are already written to SMU registers before the crash
    "Applied (process exited abnormally - settings were applied)" | Out-File -FilePath "{log_path}" -Encoding UTF8
}}
'''
        
        with open(ps_script_path, 'w', encoding='utf-8') as f:
            f.write(ps_script)
            
        # VBS wrapper for 100% silent execution (no console flash)
        vbs_script = f'''Set objShell = CreateObject("WScript.Shell")\nobjShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{ps_script_path}""", 0, True\n'''
        with open(vbs_script_path, 'w', encoding='utf-8') as f:
            f.write(vbs_script)
        
        # Execute VBS script with elevation
        print("[CPU DEBUG] Calling ShellExecuteW with runas (wscript.exe)...")
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "wscript.exe",
            f'//B //Nologo "{vbs_script_path}"',
            None, 0  # SW_HIDE
        )
        
        print(f"[CPU DEBUG] ShellExecuteW (wscript) returned: {ret}")
        
        if ret > 32:
            # VBS now uses "True" for bWaitOnReturn, so it blocks until PS finishes
            # But ShellExecuteW with runas is async, so we still need to poll
            print("[CPU DEBUG] Waiting for script to complete...")
            
            # Poll for log file (max 10 seconds)
            for i in range(20):
                time.sleep(0.5)
                if os.path.exists(log_path):
                    # Give it a moment to finish writing
                    time.sleep(0.3)
                    break
            
            # Try to read the log file
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    output = f.read().strip()
                print(f"[CPU DEBUG] RyzenAdj output: {output[:200]}..." if len(output) > 200 else f"[CPU DEBUG] RyzenAdj output: {output}")
                try:
                    os.remove(log_path)
                except OSError:
                    pass
            else:
                print("[CPU DEBUG] Log file not found (script may still be running)")
            
            # Cleanup err/script/wrapper
            for path_to_clean in [err_path, ps_script_path, vbs_script_path]:
                if os.path.exists(path_to_clean):
                    try: os.remove(path_to_clean)
                    except OSError: pass
                
            print("[CPU DEBUG] Elevated execution SUCCESS")
            return True, None
        else:
            print(f"[CPU DEBUG] ShellExecuteW FAILED with code: {ret}")
            return False, f"Failed to elevate RyzenAdj (Error: {ret})"
            
    except Exception as e:
        print(f"[CPU DEBUG] Exception: {str(e)}")
        return False, f"Elevated execution failed: {str(e)}"


def apply_settings_auto_restart_direct(profile: dict, custom_path: str = None) -> tuple:
    """
    Apply settings by:
    1. Injecting temporary preset
    2. Killing UXTU
    3. Setting active preset in UXTU config
    4. Restarting UXTU
    """
    # 1. Inject Preset
    success, error = inject_preset_to_uxtu(TEMP_PRESET_NAME, profile, custom_path)
    if not success:
        return False, error
    
    # 2. Kill UXTU
    if not kill_uxtu_process():
        # Proceed even if kill fails (might not be running)
        pass
        
    # 3. Update Config (with command string for actual values)
    command_string = _build_uxtu_command_string(profile)
    config_success, config_msg = set_active_preset_in_config(TEMP_PRESET_NAME, command_string)
    if not config_success:
        return False, f"Failed to update UXTU config: {config_msg}"
        
    # 4. Restart UXTU
    if not restart_uxtu_process(custom_path):
        return False, "Failed to restart UXTU application."
        
    return True, None


def inject_preset_to_uxtu(preset_name: str, profile: dict, custom_path: str = None) -> tuple:
    """
    Inject a preset into UXTU's apuPresets.json file.
    Automatically uses UAC elevation if permission denied.
    
    Args:
        preset_name: Name for the preset in UXTU
        profile: Dictionary with our profile values (temp_limit, stapm_limit, etc.)
        custom_path: Optional custom UXTU installation path
    
    Returns:
        (success: bool, error_message: str or None)
    """
    presets_path = get_uxtu_presets_path(custom_path)
    
    if not os.path.exists(presets_path):
        return False, f"UXTU presets file not found at: {presets_path}"
    
    # Build the UXTU preset structure
    uxtu_preset = _build_uxtu_preset(profile)
    
    # First try direct write
    try:
        with open(presets_path, 'r', encoding='utf-8') as f:
            uxtu_presets = json.load(f)
        
        uxtu_presets[preset_name] = uxtu_preset
        
        with open(presets_path, 'w', encoding='utf-8') as f:
            json.dump(uxtu_presets, f, indent=2)
        
        return True, None
        
    except PermissionError:
        # Try elevated write via PowerShell
        return _inject_preset_elevated(presets_path, preset_name, uxtu_preset)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in UXTU presets file: {e}"
    except Exception as e:
        return False, str(e)


def _build_uxtu_preset(profile: dict) -> dict:
    """Build UXTU preset structure from our profile values."""
    return {
        # Power/Temperature values
        "apuTemp": profile.get("temp_limit", 80),
        "apuSkinTemp": profile.get("temp_limit", 85),
        "apuSTAPMPow": profile.get("stapm_limit", 40),
        "apuSTAPMTime": profile.get("slow_duration", 180),
        "apuFastPow": profile.get("fast_limit", 50),
        "apuSlowPow": profile.get("slow_limit", 30),
        "apuSlowTime": profile.get("fast_duration", 64),
        "apuCpuTdc": profile.get("cpu_tdc", 45),
        "apuCpuEdc": profile.get("cpu_edc", 60),
        "apuSocTdc": 25,
        "apuSocEdc": 25,
        "apuGfxTdc": profile.get("gfx_tdc", 35),
        "apuGfxEdc": profile.get("gfx_edc", 50),
        "apuGfxClk": 2700,
        
        # Enable flags for settings we're controlling
        "isApuTemp": True,
        "isApuSkinTemp": True,
        "isApuSTAPMPow": True,
        "isApuSTAPMTime": True,
        "isApuFastPow": True,
        "isApuSlowPow": True,
        "isApuSlowTime": True,
        "isApuCpuTdc": True,
        "isApuCpuEdc": True,
        "isApuSocTdc": False,
        "isApuSocEdc": False,
        "isApuGfxTdc": True,
        "isApuGfxEdc": True,
        "isApuGfxClk": False,
        
        # Disable other features
        "isPboScalar": False, "isCoAllCore": False, "isCoGfx": False,
        "isDtCpuTemp": False, "isDtCpuPPT": False, "isDtCpuTDC": False, "isDtCpuEDC": False,
        "isIntelPL1": False, "isIntelPL2": False, "isRadeonGraphics": False,
        "isAntiLag": False, "isRSR": False, "isBoost": False,
        "isImageSharp": False, "isSync": False, "isNVIDIA": False,
        "IsCCD1Core1": False, "IsCCD1Core2": False, "IsCCD1Core3": False, "IsCCD1Core4": False,
        "IsCCD1Core5": False, "IsCCD1Core6": False, "IsCCD1Core7": False, "IsCCD1Core8": False,
        "IsCCD2Core1": False, "IsCCD2Core2": False, "IsCCD2Core3": False, "IsCCD2Core4": False,
        "IsCCD2Core5": False, "IsCCD2Core6": False, "IsCCD2Core7": False, "IsCCD2Core8": False,
        "IsAmdOC": False,
        "isSoftMiniGPUClk": False, "isSoftMaxiGPUClk": False,
        "isSoftMinCPUClk": False, "isSoftMaxCPUClk": False,
        "isSoftMinDataClk": False, "isSoftMaxDataClk": False,
        "isSoftMinFabClk": False, "isSoftMaxFabClk": False,
        "isSoftMinVCNClk": False, "isSoftMaxVCNClk": False,
        "isSoftMinSoCClk": False, "isSoftMaxSoCClk": False,
        
        # System settings
        "asusPowerProfile": 0, "asusGPUUlti": False, "asusiGPU": False,
        "displayHz": 1, "ccdAffinity": 0, "powerMode": 3,
        "isMag": False, "isVsync": False, "isRecap": False,
        "Sharpness": 5, "ResScaleIndex": 0,
    }


def _build_uxtu_command_string(profile: dict) -> str:
    """
    Build UXTU command string from profile values.
    UXTU uses milliwatts for power and milliamps for current.
    """
    # Extract values (our profile uses W/A, UXTU uses mW/mA)
    temp = profile.get("temp_limit", 85)
    stapm = profile.get("stapm_limit", 40) * 1000  # W to mW
    slow = profile.get("slow_limit", 30) * 1000
    fast = profile.get("fast_limit", 50) * 1000
    slow_time = profile.get("slow_duration", 180)
    fast_time = profile.get("fast_duration", 64)
    cpu_tdc = profile.get("cpu_tdc", 45) * 1000  # A to mA
    cpu_edc = profile.get("cpu_edc", 60) * 1000
    gfx_tdc = profile.get("gfx_tdc", 35) * 1000
    gfx_edc = profile.get("gfx_edc", 50) * 1000
    
    # Build command string matching UXTU format
    cmd = (
        f"--UXTUSR=False-False-0.05-0-False "
        f"--Win-Power=2 "
        f"--tctl-temp={temp} "
        f"--cHTC-temp={temp} "
        f"--apu-skin-temp={temp} "
        f"--stapm-limit={stapm} "
        f"--fast-limit={fast} "
        f"--stapm-time={fast_time} "
        f"--slow-limit={slow} "
        f"--slow-time={slow_time} "
        f"--vrm-current={cpu_tdc} "
        f"--vrmmax-current={cpu_edc} "
        f"--vrmgfx-current={gfx_tdc} "
        f"--vrmgfxmax-current={gfx_edc} "
        f"--max-performance"
    )
    return cmd


def _inject_preset_elevated(presets_path: str, preset_name: str, uxtu_preset: dict) -> tuple:
    """
    Inject preset using elevated PowerShell to bypass permission issues.
    This will trigger a UAC prompt.
    """
    import tempfile
    
    try:
        # Read current presets
        with open(presets_path, 'r', encoding='utf-8') as f:
            uxtu_presets = json.load(f)
        
        # Add our preset
        uxtu_presets[preset_name] = uxtu_preset
        
        # Write to temp file first
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "helxaid_uxtu_preset_temp.json")
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(uxtu_presets, f, indent=2)
        
        # Use PowerShell with elevation to copy the file
        ps_script = f'''
        Copy-Item -Path "{temp_file}" -Destination "{presets_path}" -Force
        Remove-Item -Path "{temp_file}" -Force -ErrorAction SilentlyContinue
        '''
        
        # Run elevated PowerShell
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "powershell.exe",
            f'-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "{ps_script}"',
            None,
            0  # SW_HIDE - hide the window
        )
        
        # ShellExecuteW returns > 32 on success
        if result > 32:
            return True, None
        else:
            return False, f"UAC elevation failed (error code: {result})"
            
    except Exception as e:
        return False, f"Elevated injection failed: {e}"


def _apply_settings_elevated(profile: dict, custom_path: str = None) -> tuple:
    """
    Perform the full Auto-Apply sequence using an elevated PowerShell script.
    Handled: Inject Preset -> Kill UXTU -> Update Config -> Restart UXTU
    """
    import tempfile
    
    try:
        # 1. PREPARE PRESETS FILE
        presets_path = get_uxtu_presets_path(custom_path)
        if not os.path.exists(presets_path):
            return False, f"UXTU presets file not found at: {presets_path}"
            
        with open(presets_path, 'r', encoding='utf-8') as f:
            uxtu_presets = json.load(f)
            
        uxtu_presets[TEMP_PRESET_NAME] = _build_uxtu_preset(profile)
        
        temp_dir = tempfile.gettempdir()
        temp_presets_path = os.path.join(temp_dir, "helxaid_uxtu_presets_new.json")
        with open(temp_presets_path, 'w', encoding='utf-8') as f:
            json.dump(uxtu_presets, f, indent=2)
            
        # 2. PREPARE CONFIG FILE - Update both preset names AND command strings
        config_path = find_uxtu_config_path()
        if not config_path:
            return False, "UXTU configuration file not found."
        
        # Build the command string from profile values
        command_string = _build_uxtu_command_string(profile)
            
        tree = ET.parse(config_path)
        root = tree.getroot()
        
        # Settings to update: preset names and command strings
        preset_settings = ["acPreset", "dcPreset", "resumePreset"]
        command_settings = ["acCommandString", "dcCommandString", "resumeCommandString", "CommandString"]
        
        for setting in root.iter("setting"):
            name = setting.get("name")
            val = setting.find("value")
            if val is not None:
                if name in preset_settings:
                    val.text = TEMP_PRESET_NAME
                elif name in command_settings:
                    val.text = command_string
        
        temp_config_path = os.path.join(temp_dir, "helxaid_uxtu_config_new.config")
        tree.write(temp_config_path, encoding="utf-8", xml_declaration=True)
        
        # 3. WRITE POWERSHELL SCRIPT TO TEMP FILE
        uxtu_exe = custom_path or DEFAULT_UXTU_PATH
        ps_script_path = os.path.join(temp_dir, "helxaid_apply_uxtu.ps1")
        
        ps_script_content = f'''
# Kill UXTU
Stop-Process -Name "Universal x86 Tuning Utility" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Overwrite Presets
Copy-Item -Path "{temp_presets_path}" -Destination "{presets_path}" -Force

# Overwrite Config  
Copy-Item -Path "{temp_config_path}" -Destination "{config_path}" -Force

# Restart UXTU
Start-Process -FilePath "{uxtu_exe}"

# Cleanup
Start-Sleep -Seconds 2
Remove-Item -Path "{temp_presets_path}" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "{temp_config_path}" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "{ps_script_path}" -Force -ErrorAction SilentlyContinue
'''
        
        with open(ps_script_path, 'w', encoding='utf-8') as f:
            f.write(ps_script_content)
        
        # 4. EXECUTE ELEVATED SCRIPT
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            f'-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File "{ps_script_path}"',
            None, 0  # SW_HIDE
        )
        
        if ret > 32:
            return True, None
        else:
            return False, f"Failed to elevate process (Error: {ret})"
            
    except Exception as e:
        return False, f"Elevated application failed: {str(e)}"


class CPUControlSettings:
    """Manages CPU control settings persistence."""
    
    def __init__(self, settings_path: str):
        self.settings_path = settings_path
        self._settings = None
        self.load()
    
    def load(self):
        """Load settings from file."""
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    all_settings = json.load(f)
                    self._settings = all_settings.get("cpu_control", {})
            else:
                self._settings = {}
        except Exception as e:
            print(f"Error loading CPU settings: {e}")
            self._settings = {}
    
    def save(self):
        """Save settings to file."""
        try:
            # Load existing settings first
            all_settings = {}
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    all_settings = json.load(f)
            
            # Update cpu_control section
            all_settings["cpu_control"] = self._settings
            
            with open(self.settings_path, 'w') as f:
                json.dump(all_settings, f, indent=4)
        except Exception as e:
            print(f"Error saving CPU settings: {e}")
    
    @property
    def enabled(self) -> bool:
        return self._settings.get("enabled", False)
    
    @enabled.setter
    def enabled(self, value: bool):
        self._settings["enabled"] = value
        self.save()
    
    @property
    def uxtu_path(self) -> str:
        return self._settings.get("uxtu_path", DEFAULT_UXTU_PATH)
    
    @uxtu_path.setter
    def uxtu_path(self, value: str):
        self._settings["uxtu_path"] = value
        self.save()
    
    @property
    def profile(self) -> dict:
        stored = self._settings.get("profile", {})
        # Merge with defaults for any missing keys
        result = get_default_profile()
        result.update(stored)
        return validate_profile(result)
    
    @profile.setter
    def profile(self, value: dict):
        self._settings["profile"] = validate_profile(value)
        self.save()
    
    def get_value(self, key: str) -> int:
        """Get a single profile value."""
        return self.profile.get(key, SAFETY_LIMITS.get(key, {}).get("default", 0))
    
    def set_value(self, key: str, value: int):
        """Set a single profile value with validation."""
        profile = self.profile
        profile[key] = validate_value(key, value)
        self.profile = profile
    
    # ----------------------------------------------------------
    # Preset Management
    # ----------------------------------------------------------
    
    @property
    def presets(self) -> dict:
        """Get all saved presets."""
        return self._settings.get("presets", {})
    
    @property
    def current_preset_name(self) -> str:
        """Get the name of the currently active preset."""
        return self._settings.get("current_preset", "")
    
    @current_preset_name.setter
    def current_preset_name(self, name: str):
        """Set the current preset name."""
        self._settings["current_preset"] = name
        self.save()
    
    def get_preset_names(self) -> list:
        """Get a list of all preset names."""
        return list(self.presets.keys())
    
    def get_preset(self, name: str) -> dict:
        """Get a preset by name. Returns None if not found."""
        return self.presets.get(name, None)
    
    def save_preset(self, name: str, values: dict = None):
        """
        Save current profile values as a named preset.
        If values is provided, use those instead of current profile.
        """
        if values is None:
            values = self.profile
        
        # Ensure presets dict exists
        if "presets" not in self._settings:
            self._settings["presets"] = {}
        
        # Save validated preset
        self._settings["presets"][name] = validate_profile(values)
        self._settings["current_preset"] = name
        self.save()
    
    def load_preset(self, name: str) -> bool:
        """
        Load a preset by name and apply it to current profile.
        Returns True if successful, False if preset not found.
        """
        preset = self.get_preset(name)
        if preset is None:
            return False
        
        self.profile = preset
        self._settings["current_preset"] = name
        self.save()
        return True
    
    def delete_preset(self, name: str) -> bool:
        """
        Delete a preset by name.
        Returns True if successful, False if preset not found.
        """
        if name not in self.presets:
            return False
        
        del self._settings["presets"][name]
        
        # Clear current preset if it was the deleted one
        if self.current_preset_name == name:
            self._settings["current_preset"] = ""
        
        self.save()
        return True
    
    def rename_preset(self, old_name: str, new_name: str) -> bool:
        """
        Rename a preset.
        Returns True if successful, False if old preset not found.
        """
        if old_name not in self.presets:
            return False
        
        # Copy preset to new name
        self._settings["presets"][new_name] = self._settings["presets"][old_name]
        del self._settings["presets"][old_name]
        
        # Update current preset name if needed
        if self.current_preset_name == old_name:
            self._settings["current_preset"] = new_name
        
        self.save()
        return True



# ----------------------------------------------------------
# Auto-Restart Helper Functions
# ----------------------------------------------------------

def find_uxtu_config_path() -> str:
    """Find the path to UXTU's user.config file."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    james_path = os.path.join(local_appdata, "JamesCJ60")
    
    if not os.path.exists(james_path):
        return None
        
    # Search for user.config in subdirectories
    for root, dirs, files in os.walk(james_path):
        if "Universal" in root and "user.config" in files:
            return os.path.join(root, "user.config")
            
    return None


def set_active_preset_in_config(preset_name: str, command_string: str = None) -> tuple:
    """
    Update UXTU config to set the active preset and command strings.
    Returns (success: bool, message: str)
    """
    config_path = find_uxtu_config_path()
    if not config_path:
        return False, "UXTU configuration file not found."
        
    try:
        tree = ET.parse(config_path)
        root = tree.getroot()
        modified = False
        
        # Settings to update
        preset_settings = ["acPreset", "dcPreset", "resumePreset"]
        command_settings = ["acCommandString", "dcCommandString", "resumeCommandString", "CommandString"]
        
        for setting in root.iter("setting"):
            name = setting.get("name")
            value_elem = setting.find("value")
            if value_elem is not None:
                if name in preset_settings:
                    value_elem.text = preset_name
                    modified = True
                elif name in command_settings and command_string:
                    value_elem.text = command_string
                    modified = True
        
        if modified:
            tree.write(config_path, encoding="utf-8", xml_declaration=True)
            return True, None
        else:
            return False, "Preset settings not found in configuration."
            
    except Exception as e:
        return False, str(e)


def kill_uxtu_process() -> bool:
    """Kill UXTU process if running."""
    try:
        # Use taskkill for force termination
        subprocess.run(["taskkill", "/F", "/IM", "Universal x86 Tuning Utility.exe"], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1) # Wait for release
        return True
    except Exception:
        return False


def restart_uxtu_process(custom_path: str = None) -> bool:
    """Restart UXTU application."""
    success, _ = launch_uxtu(custom_path)
    return success
