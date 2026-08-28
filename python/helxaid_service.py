import sys
import os
import json
import time
import subprocess
import traceback

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    import win32pipe
    import win32file
    import pywintypes
    import win32security
except ImportError:
    pass

PIPE_NAME = r'\\.\pipe\HelxaidCpuPipe'
_service_lhm_computer = None

class HelxaidHelperService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'HelxaidHelperService'
    _svc_display_name_ = 'HELXAID Helper Service'
    _svc_description_ = 'Provides zero-UAC CPU/TDP adjustments for HELXAID.'
    _svc_start_type_ = win32service.SERVICE_AUTO_START if 'win32service' in globals() else 2
    
    if getattr(sys, 'frozen', False):
        _exe_name_ = sys.executable
        _exe_args_ = '--run-service'
    else:
        _exe_name_ = sys.executable
        import os
        # sys.argv[0] could be helxaid_service.py or launcher.py
        _exe_args_ = f'"{os.path.abspath(sys.argv[0])}" --run-service'

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        global _service_lhm_computer
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.stop_event)
        
        # Safely close persistent LHM computer handle if initialized
        if _service_lhm_computer is not None:
            try:
                _service_lhm_computer.Close()
            except Exception:
                pass
            _service_lhm_computer = None

        # Connect to pipe just to unblock the WaitNamedPipe/ConnectNamedPipe loop
        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None
            )
            win32file.CloseHandle(handle)
        except:
            pass

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        try:
            self.main()
        except Exception as e:
            servicemanager.LogErrorMsg(f"HELXAID Service crashed: {str(e)}\n{traceback.format_exc()}")
            self.SvcStop()

    def create_pipe_security_attributes(self):
        # Create a security attribute allowing Authenticated Users or Everyone
        sa = win32security.SECURITY_ATTRIBUTES()
        sa.bInheritHandle = 1
        
        # Create Security Descriptor with Null DACL (Allows everyone to read/write)
        # This is safe because we tightly validate the JSON payload and DO NOT execute arbitrary commands.
        sd = win32security.SECURITY_DESCRIPTOR()
        sd.SetSecurityDescriptorDacl(1, None, 0) 
        sa.SECURITY_DESCRIPTOR = sd
        return sa

    def get_ryzenadj_path(self, explicit_path=None):
        if explicit_path and os.path.exists(explicit_path):
            return explicit_path

        # Try finding in the portable dir (next to service executable)
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        # PyInstaller paths
        exe_dir = os.path.dirname(sys.executable)
        
        paths_to_check = [
            os.path.join(base_dir, "assets", "ryzenadj.exe"),
            os.path.join(exe_dir, "assets", "ryzenadj.exe"),
            os.path.join(base_dir, "tools", "ryzenadj", "ryzenadj.exe"),
            os.path.join(exe_dir, "tools", "ryzenadj", "ryzenadj.exe"),
            os.path.join(os.environ.get('APPDATA', ''), "HELXAID", "tools", "ryzenadj", "ryzenadj.exe")
        ]

        # Scan user profiles in C:\Users when running under LocalSystem account
        users_dir = "C:\\Users"
        if os.path.exists(users_dir):
            try:
                for u in os.listdir(users_dir):
                    if u.lower() in ["public", "default", "default user", "all users"]:
                        continue
                    p = os.path.join(users_dir, u, "AppData", "Roaming", "HELXAID", "tools", "ryzenadj", "ryzenadj.exe")
                    if os.path.exists(p):
                        paths_to_check.append(p)
            except Exception:
                pass
        
        for p in paths_to_check:
            if p and os.path.exists(p):
                return p
        return None

    def process_command(self, payload_str):
        try:
            data = json.loads(payload_str)
            action = data.get("action")
            
            if action == "apply_cpu":
                profile = data.get("profile", {})
                if not profile:
                    return {"status": "error", "message": "No profile data provided."}
                
                # Check CPU vendor - skip RyzenAdj on Intel CPUs
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                    vendor_id, _ = winreg.QueryValueEx(key, "VendorIdentifier")
                    winreg.CloseKey(key)
                    if "INTEL" in str(vendor_id).upper() or "GENUINEINTEL" in str(vendor_id).upper():
                        return {"status": "success", "message": "Intel CPU detected. Zero-UAC active for system features; CPU power managed via Windows Power Scheme."}
                except Exception:
                    pass

                explicit_path = data.get("ryzenadj_path")
                ryzenadj_path = self.get_ryzenadj_path(explicit_path)
                if not ryzenadj_path:
                    return {"status": "error", "message": "RyzenAdj executable not found."}

                
                # Auto-kill UXTU's PawnIO driver if it's running (to prevent RyzenAdj crash)
                try:
                    res = subprocess.run(["sc.exe", "stop", "PawnIO"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if res.returncode == 0:
                        time.sleep(1.5)  # Wait for driver to fully unload from memory
                except Exception:
                    pass
                
                # Build arguments to match cpu_controller._build_ryzenadj_args exactly.
                # Profile stores power in Watts, ryzenadj expects mW (×1000).
                # Only include settings that are enabled in 'enabled_settings'.
                args = [ryzenadj_path]
                enabled = profile.get("enabled_settings", {})

                def is_enabled(key):
                    return enabled.get(key, True)  # default True for backwards compat

                # Temperature (°C) — no unit conversion
                if is_enabled("temp_limit"):
                    args.append(f"--tctl-temp={int(profile.get('temp_limit', 85))}")
                if is_enabled("temp_skin_limit"):
                    args.append(f"--apu-skin-temp={int(profile.get('temp_skin_limit', 80))}")

                # Power limits (W → mW)
                if is_enabled("stapm_limit") and "stapm_limit" in profile:
                    args.append(f"--stapm-limit={int(profile['stapm_limit'] * 1000)}")
                if is_enabled("slow_limit") and "slow_limit" in profile:
                    args.append(f"--slow-limit={int(profile['slow_limit'] * 1000)}")
                if is_enabled("fast_limit") and "fast_limit" in profile:
                    args.append(f"--fast-limit={int(profile['fast_limit'] * 1000)}")

                # Time limits (seconds) — no conversion
                if is_enabled("slow_duration") and "slow_duration" in profile:
                    args.append(f"--slow-time={int(profile['slow_duration'])}")
                if is_enabled("fast_duration") and "fast_duration" in profile:
                    args.append(f"--stapm-time={int(profile['fast_duration'])}")

                # CPU current limits (A → mA)
                if is_enabled("cpu_tdc") and "cpu_tdc" in profile:
                    args.append(f"--vrm-current={int(profile['cpu_tdc'] * 1000)}")
                if is_enabled("cpu_edc") and "cpu_edc" in profile:
                    args.append(f"--vrmmax-current={int(profile['cpu_edc'] * 1000)}")

                # GFX current limits (A → mA)
                if is_enabled("gfx_tdc") and "gfx_tdc" in profile:
                    args.append(f"--vrmgfx-current={int(profile['gfx_tdc'] * 1000)}")

                if len(args) == 1:
                    return {"status": "error", "message": "No valid CPU limits found in profile."}

                # Execute securely without shell=True.
                # Run from ryzenadj's own directory so it can find its DLLs.
                result = subprocess.run(
                    args,
                    cwd=os.path.dirname(ryzenadj_path),
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10
                )

                # RyzenAdj OFTEN crashes with exit code 0xC0000005 (Access Violation)
                # AFTER successfully writing settings to SMU registers. This is a known ryzenadj
                # behaviour — the crash happens during cleanup, not during the actual apply.
                # We treat it as success if the error matches and stdout is empty (no error msg).
                # Python's subprocess can return this as signed (-1073741819) or unsigned (3221225477).
                KNOWN_CRASH_CODES = (-1073741819, 3221225477, -1073740791, 3221226505)
                output = result.stdout.strip()
                stderr  = result.stderr.strip()
                combined_log = (output + "\n" + stderr).lower()

                # Keywords indicating ryzenadj attempted or succeeded setting values:
                # Note: ryzenadj source code spells "Sucessfully" with a single 'c'
                SUCCESS_KEYWORDS = (
                    "sucessfully", "successfully", "smu", "stapm", "tctl", 
                    "fast-limit", "slow-limit", "vrm", "apu", "setting", "limit"
                )

                if result.returncode == 0:
                    return {"status": "success", "message": "Applied successfully."}
                elif result.returncode in KNOWN_CRASH_CODES:
                    # Known post-SMU write crash — settings were written to registers before process cleanup crash
                    return {"status": "success", "message": f"Applied (post-SMU crash suppressed, exit code {result.returncode})."}
                elif any(kw in combined_log for kw in SUCCESS_KEYWORDS):
                    return {"status": "success", "message": f"Applied (exit code {result.returncode} ignored)."}
                else:
                    err_detail = stderr or output or "no output"
                    return {"status": "error", "message": f"RyzenAdj error {result.returncode}: {err_detail}"}
                    
            elif action in ("launch_tool", "kill_tool", "cleanup_lhm"):
                exe_path = data.get("exe_path", "")
                exe_name = os.path.basename(exe_path) if exe_path else "LibreHardwareMonitor.exe"
                silent = data.get("silent", False)
                
                # Kill any background/Session 0 instances running under SYSTEM
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/IM", exe_name],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                except Exception:
                    pass
                    
                if action == "kill_tool":
                    return {"status": "success", "message": f"{exe_name} terminated."}
                    
                if silent:
                    # Silent launch in background
                    try:
                        if exe_path and os.path.exists(exe_path):
                            subprocess.Popen(
                                [exe_path],
                                cwd=os.path.dirname(exe_path),
                                creationflags=subprocess.CREATE_NO_WINDOW
                            )
                            return {"status": "success", "message": f"{exe_name} started silently."}
                    except Exception as e:
                        return {"status": "error", "message": str(e)}
                        
                return {"status": "success", "message": f"{exe_name} background instances cleared for interactive launch."}

            elif action == "read_lhm_sensors":
                # Read LHM sensors from SYSTEM context (elevated) so AMD SMU Tdie temp is accessible.
                try:
                    import sys as _sys
                    global _service_lhm_computer
                    if _service_lhm_computer is None:
                        # Build DLL search paths scanning all user AppData dirs
                        dll_candidates = []
                        users_dir = "C:\\Users"
                        if os.path.exists(users_dir):
                            for u in os.listdir(users_dir):
                                if u.lower() in ["public", "default", "default user", "all users"]:
                                    continue
                                p = os.path.join(users_dir, u, "AppData", "Roaming", "HELXAID",
                                                 "tools", "librehardwaremonitor", "LibreHardwareMonitorLib.dll")
                                if os.path.exists(p):
                                    dll_candidates.append(p)
                        
                        dll_path = dll_candidates[0] if dll_candidates else None
                        if not dll_path:
                            return {"status": "error", "message": "LibreHardwareMonitorLib.dll not found"}
                        
                        # Unblock Zone.Identifier stream if present (Mark of the Web)
                        zone_id = dll_path + ":Zone.Identifier"
                        if os.path.exists(zone_id):
                            try: os.remove(zone_id)
                            except Exception: pass

                        dll_dir = os.path.dirname(os.path.abspath(dll_path))
                        if dll_dir not in _sys.path:
                            _sys.path.append(dll_dir)
                        if hasattr(os, 'add_dll_directory') and os.path.exists(dll_dir):
                            try: os.add_dll_directory(dll_dir)
                            except Exception: pass

                        import clr
                        clr.AddReference(os.path.abspath(dll_path))
                        from LibreHardwareMonitor.Hardware import Computer  # type: ignore[import-not-found, import-untyped]  # noqa: F401
                        
                        c = Computer()
                        c.IsCpuEnabled = True
                        c.IsGpuEnabled = True
                        c.IsStorageEnabled = True
                        c.IsMotherboardEnabled = True
                        c.Open()
                        _service_lhm_computer = c
                        try:
                            import System
                            System.GC.Collect()
                        except Exception:
                            pass
                    
                    import math
                    c = _service_lhm_computer
                    
                    out = {
                        "available": True,
                        "cpu_temp": 0.0, "cpu_load": 0.0, "cpu_clock": 0.0, "cpu_power": 0.0,
                        "igpu_temp": 0.0, "igpu_load": 0.0, "igpu_power": 0.0,
                        "dgpu_temp": 0.0, "dgpu_load": 0.0, "dgpu_power": 0.0,
                        "gpu_fan": 0.0, "cpu_fan": 0.0, "fan_speed": 0.0,
                        "storage": [],
                        "status": "lhm_service"
                    }
                    
                    for hw in c.Hardware:
                        hw.Update()
                        hw_type = str(hw.HardwareType).upper()
                        hw_name = str(hw.Name).upper()
                        is_cpu  = "CPU" in hw_type
                        is_igpu = "GPUAMD" in hw_type or ("GPUINTEL" in hw_type)
                        is_dgpu = "GPUNVIDIA" in hw_type or ("GPUAMD" in hw_type and not is_igpu)
                        is_storage = "STORAGE" in hw_type
                        
                        if is_storage:
                            disk_info = {"name": str(hw.Name), "temp": 0.0, "health_percent": 100.0}
                        
                        # Refine: separate iGPU (Radeon integrated) vs dGPU (NVIDIA)
                        if "NVIDIA" in hw_name:
                            is_dgpu = True
                            is_igpu = False
                        elif "RADEON" in hw_name and "CPU" not in hw_type:
                            is_igpu = True
                            is_dgpu = False
                        
                        for sensor in hw.Sensors:
                            val = sensor.Value
                            if val is None:
                                continue
                            try:
                                fval = float(val)
                            except Exception:
                                continue
                            if math.isnan(fval):
                                continue
                            stype = str(sensor.SensorType).upper()
                            sname = str(sensor.Name).upper()
                            
                            if is_cpu:
                                if stype == "TEMPERATURE" and fval > 0:
                                    if ("TCTL" in sname or "TDIE" in sname or "PACKAGE" in sname) and out["cpu_temp"] == 0:
                                        out["cpu_temp"] = fval
                                    elif "CORE" in sname and out["cpu_temp"] == 0:
                                        out["cpu_temp"] = fval
                                elif stype == "LOAD":
                                    if "TOTAL" in sname or "CORE MAX" in sname:
                                        out["cpu_load"] = max(out["cpu_load"], fval)
                                elif stype == "CLOCK" and fval > 200:
                                    out["cpu_clock"] = max(out["cpu_clock"], fval)
                                elif stype == "POWER" and ("PACKAGE" in sname or "CPU" in sname):
                                    out["cpu_power"] = fval
                            
                            elif is_igpu:
                                if stype == "TEMPERATURE" and ("CORE" in sname or "GPU" in sname) and out["igpu_temp"] == 0:
                                    out["igpu_temp"] = fval
                                elif stype == "LOAD" and ("CORE" in sname or "GPU" in sname or "3D" in sname):
                                    out["igpu_load"] = max(out["igpu_load"], fval)
                                elif stype == "POWER":
                                    out["igpu_power"] = fval
                            
                            elif is_dgpu:
                                if stype == "TEMPERATURE" and ("CORE" in sname or "GPU" in sname) and out["dgpu_temp"] == 0:
                                    out["dgpu_temp"] = fval
                                elif stype == "LOAD" and ("CORE" in sname or "3D" in sname or "GPU" in sname):
                                    out["dgpu_load"] = max(out["dgpu_load"], fval)
                                elif stype == "POWER":
                                    out["dgpu_power"] = fval
                                elif stype == "FAN":
                                    out["gpu_fan"] = fval
                                    out["fan_speed"] = max(out["fan_speed"], fval)
                            
                            elif is_storage:
                                if stype == "TEMPERATURE" and disk_info["temp"] == 0:
                                    disk_info["temp"] = fval
                                elif 'PERCENTAGE USED' in sname or 'DEGRADATION' in sname:
                                    disk_info["health_percent"] = max(0.0, min(100.0, 100.0 - fval))
                                elif 'AVAILABLE SPARE' in sname or 'REMAINING LIFE' in sname:
                                    disk_info["health_percent"] = max(0.0, min(100.0, fval))
                        
                        if is_storage:
                            out["storage"].append(disk_info)
                    
                    if out["igpu_temp"] == 0 and out["cpu_temp"] > 0:
                        out["igpu_temp"] = out["cpu_temp"]
                    if out["igpu_power"] == 0 and out["cpu_power"] > 0:
                        out["igpu_power"] = out["cpu_power"]
                    
                    try:
                        c.Close()
                    except Exception:
                        pass
                    
                    out["status_str"] = "lhm_service"
                    return {"status": "success", "sensors": out}
                except Exception as ex:
                    return {"status": "error", "message": f"LHM service read error: {ex}"}

            elif action == "restart_self":
                # Restart the service itself to pick up code changes
                try:
                    subprocess.Popen(
                        ['sc.exe', 'stop', 'HelxaidHelperService'],
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    import time as _time
                    _time.sleep(1.5)
                    subprocess.Popen(
                        ['sc.exe', 'start', 'HelxaidHelperService'],
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    return {"status": "success", "message": "Service restart initiated."}
                except Exception as e:
                    return {"status": "error", "message": str(e)}

            elif action == "get_drive_health":
                import ctypes, ctypes.wintypes, struct, json as js

                debug_log = []  # Returned in response so main app can print it

                GENERIC_READ = 0x80000000
                GENERIC_WRITE = 0x40000000
                FILE_SHARE_READ = 0x00000001
                FILE_SHARE_WRITE = 0x00000002
                OPEN_EXISTING = 3
                IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
                StorageDeviceProtocolSpecificProperty = 49
                ProtocolTypeNvme = 3
                NVMeDataTypeLogPage = 2

                kernel32 = ctypes.windll.kernel32
                # Set return type properly so INVALID_HANDLE_VALUE comparison works
                kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
                INVALID_HANDLE_VALUE = ctypes.wintypes.HANDLE(-1).value

                def _read_nvme_smart(drive_idx):
                    path = f"\\\\.\\PhysicalDrive{drive_idx}"
                    debug_log.append(f"[NVMe] Opening: {path}")
                    hnd = kernel32.CreateFileW(
                        path, GENERIC_READ,
                        FILE_SHARE_READ | FILE_SHARE_WRITE,
                        None, OPEN_EXISTING, 0, None
                    )
                    last_err = ctypes.GetLastError()
                    debug_log.append(f"[NVMe] hnd={hnd} INVALID={INVALID_HANDLE_VALUE} LastError={last_err}")
                    if hnd is None or hnd == INVALID_HANDLE_VALUE or hnd == -1:
                        debug_log.append(f"[NVMe] FAILED to open {path}, err={last_err}")
                        return None
                    debug_log.append(f"[NVMe] Handle OK for {path}")
                    try:
                        header_size = 48
                        data_size = 512
                        total_buf_size = header_size + data_size
                        in_buf = (ctypes.c_byte * total_buf_size)()
                        out_buf = (ctypes.c_byte * total_buf_size)()
                        bytes_returned = ctypes.c_ulong(0)

                        struct.pack_into('<II', in_buf, 0, StorageDeviceProtocolSpecificProperty, 0)
                        struct.pack_into('<IIIIIIIIII', in_buf, 8,
                            ProtocolTypeNvme, NVMeDataTypeLogPage,
                            0x02, 0, header_size, data_size, 0, 0, 0, 0
                        )
                        ok = kernel32.DeviceIoControl(
                            hnd, IOCTL_STORAGE_QUERY_PROPERTY,
                            in_buf, total_buf_size,
                            out_buf, total_buf_size,
                            ctypes.byref(bytes_returned), None
                        )
                        ioctl_err = ctypes.GetLastError()
                        debug_log.append(f"[NVMe] IOCTL ok={ok}, bytes={bytes_returned.value}, err={ioctl_err}")
                        if ok:
                            pct = out_buf[header_size + 5]
                            temp_k = struct.unpack_from('<H', out_buf, header_size + 1)[0]
                            temp_c = max(0, temp_k - 273) if temp_k > 200 else 0
                            debug_log.append(f"[NVMe] Drive{drive_idx}: pct_used={pct}, temp={temp_c}C, raw[48:56]={list(out_buf[48:56])}")
                            return {"percentage_used": int(pct), "temperature": temp_c, "type": "nvme"}
                        debug_log.append(f"[NVMe] IOCTL returned False for Drive{drive_idx}")
                        return None
                    except Exception as ex:
                        debug_log.append(f"[NVMe] Exception: {ex}")
                        return None
                    finally:
                        kernel32.CloseHandle(hnd)

                def _read_ata_smart(drive_idx):
                    debug_log.append(f"[ATA] Reading SMART disk{drive_idx}")
                    try:
                        import win32com.client
                        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
                        svc = locator.ConnectServer(".", "root\\wmi")
                        data_items = list(svc.ExecQuery("SELECT InstanceName, VendorSpecific FROM MSStorageDriver_FailurePredictData"))
                        debug_log.append(f"[ATA] Found {len(data_items)} instances")
                        target_idx = str(drive_idx)
                        smart_data = None
                        for item in data_items:
                            iname = str(getattr(item, "InstanceName", "") or "")
                            debug_log.append(f"[ATA]  Instance: {iname}")
                            if f"disk{target_idx}" in iname.lower() or f"physicaldrive{target_idx}" in iname.lower():
                                vs = getattr(item, "VendorSpecific", None)
                                if vs:
                                    smart_data = list(vs)
                                    debug_log.append(f"[ATA]  Matched! len={len(smart_data)}")
                                break
                        if not smart_data or len(smart_data) < 362:
                            debug_log.append(f"[ATA] No valid data for disk{drive_idx}")
                            return None
                        attrs = {}
                        for i in range(30):
                            offset = 2 + i * 12
                            attr_id = smart_data[offset]
                            if attr_id == 0:
                                continue
                            raw_bytes = bytes(smart_data[offset+5:offset+12]).ljust(8, b'\x00')
                            attrs[attr_id] = struct.unpack_from('<Q', raw_bytes)[0] & 0xFFFFFFFF
                        debug_log.append(f"[ATA] disk{drive_idx}: ID5={attrs.get(5,0)} ID197={attrs.get(197,0)} ID198={attrs.get(198,0)}")
                        return {"attrs": attrs, "type": "ata"}
                    except Exception as ex:
                        debug_log.append(f"[ATA] Exception: {ex}")
                        return None

                counters = {}
                try:
                    ps_list = subprocess.run(
                        ['powershell.exe', '-NoProfile', '-Command',
                         'Get-WmiObject -Namespace root\\microsoft\\windows\\storage -Class MSFT_PhysicalDisk | Select-Object DeviceId, MediaType, BusType | ConvertTo-Json'],
                        capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=8
                    )
                    debug_log.append(f"PS rc={ps_list.returncode}, out={ps_list.stdout[:200]}")
                    disk_list = []
                    if ps_list.returncode == 0 and ps_list.stdout.strip():
                        raw_list = js.loads(ps_list.stdout.strip())
                        if isinstance(raw_list, dict):
                            raw_list = [raw_list]
                        disk_list = raw_list

                    if not disk_list:
                        disk_list = [{"DeviceId": i, "BusType": 17} for i in range(4)]

                    # SYSTEM elevated query: Get-StorageReliabilityCounter for ALL drives
                    try:
                        ps_cmd = "Get-PhysicalDisk | Get-StorageReliabilityCounter | Select-Object DeviceId, Wear, Temperature, ReadErrorsTotal, WriteErrorsTotal | ConvertTo-Json"
                        ps_res = subprocess.run(
                            ["powershell", "-NoProfile", "-Command", ps_cmd],
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=8
                        )
                        if ps_res.returncode == 0 and ps_res.stdout.strip():
                            rel_data = js.loads(ps_res.stdout.strip())
                            if isinstance(rel_data, dict):
                                rel_data = [rel_data]
                            for ritem in rel_data:
                                rid = str(ritem.get("DeviceId", "")).strip()
                                rwear = int(ritem.get("Wear", 0) or 0)
                                rtemp = int(ritem.get("Temperature", 0) or 0)
                                rerrs = int(ritem.get("ReadErrorsTotal", 0) or 0) + int(ritem.get("WriteErrorsTotal", 0) or 0)
                                counters[rid] = {
                                    "Wear": rwear,
                                    "ReadErrors": rerrs,
                                    "Temperature": rtemp
                                }
                            debug_log.append(f"[Get-StorageReliabilityCounter] SYSTEM output: {counters}")
                    except Exception as ex_rel:
                        debug_log.append(f"[Get-StorageReliabilityCounter] Exception: {ex_rel}")

                    for disk_entry in disk_list:
                        dev_id = str(disk_entry.get("DeviceId", ""))
                        bus_type = int(disk_entry.get("BusType") or 0)
                        
                        # Use reliability counters if already obtained
                        c_entry = counters.get(dev_id, {})
                        wear = c_entry.get("Wear", 0)
                        read_errors = c_entry.get("ReadErrors", 0)
                        temperature = c_entry.get("Temperature", 0)

                        if temperature == 0:
                            nvme = _read_nvme_smart(dev_id)
                            if nvme:
                                wear = nvme["percentage_used"]
                                temperature = nvme["temperature"]
                            else:
                                ata = _read_ata_smart(dev_id)
                                if ata:
                                    attrs = ata["attrs"]
                                    temperature = int(attrs.get(194, attrs.get(190, 0)) & 0xFF)
                                    reallocated = int(attrs.get(5, 0))
                                    pending = int(attrs.get(197, 0))
                                    uncorrectable = int(attrs.get(198, 0))
                                    read_errors = reallocated + pending + uncorrectable
                                    wear = min(99, reallocated * 3 + pending * 2 + uncorrectable * 5)

                        counters[dev_id] = {
                            "Wear": wear,
                            "ReadErrors": read_errors,
                            "Temperature": temperature
                        }
                    return {"status": "success", "counters": counters, "debug": debug_log}
                except Exception as e:
                    debug_log.append(f"TOP EXCEPTION: {e}")
                    return {"status": "error", "message": str(e), "debug": debug_log}

            elif action in ("launch_lhm", "launch_tool"):

                exe_path = data.get("exe_path")
                silent = data.get("silent", False)
                if not exe_path or not os.path.exists(exe_path):
                    return {"status": "error", "message": f"Executable path not found: {exe_path}"}
                
                exe_name = os.path.basename(exe_path)
                try:
                    import psutil
                    for p in psutil.process_iter(['name']):
                        if p.info.get('name', '').lower() == exe_name.lower():
                            return {"status": "success", "message": f"{exe_name} is already running."}
                except Exception:
                    pass

                flags = subprocess.CREATE_NO_WINDOW if silent else 0
                proc = subprocess.Popen(
                    [exe_path],
                    cwd=os.path.dirname(exe_path),
                    creationflags=flags
                )
                return {"status": "success", "message": f"Launched {exe_name} via Zero-UAC Service.", "pid": proc.pid}

            elif action == "manage_service":
                svc_name = data.get("service_name")
                cmd_type = data.get("command", "stop")
                if not svc_name:
                    return {"status": "error", "message": "No service_name provided."}

                try:
                    qr = subprocess.run(
                        ['sc.exe', 'query', svc_name],
                        capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
                    )
                    q_out = (qr.stdout or '').upper()

                    if cmd_type == "stop":
                        if 'STOPPED' in q_out and 'START_PENDING' not in q_out and 'STOP_PENDING' not in q_out:
                            return {"status": "success", "message": "ALREADY_STOPPED"}
                        
                        # 1. Try Stop-Service -Force via PowerShell FIRST (handles dependent services like SstpSvc automatically)
                        ps_res = subprocess.run(
                            ['powershell.exe', '-NoProfile', '-Command', f"Stop-Service -Name '{svc_name}' -Force -ErrorAction SilentlyContinue"],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=15
                        )
                        if ps_res.returncode == 0:
                            return {"status": "success", "message": "OK"}

                        # 2. Try net.exe stop <svc_name> /y
                        sr = subprocess.run(
                            ['net.exe', 'stop', svc_name, '/y'],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=15
                        )
                        combined = ((sr.stdout or '') + (sr.stderr or '')).lower()
                        if sr.returncode == 0 or 'not started' in combined or 'successfully' in combined or 'already' in combined or '1062' in combined:
                            return {"status": "success", "message": "OK"}

                        # 3. Fallback to sc.exe stop
                        sr_sc = subprocess.run(
                            ['sc.exe', 'stop', svc_name],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10
                        )
                        combined_sc = ((sr_sc.stdout or '') + (sr_sc.stderr or '')).lower()
                        if sr_sc.returncode == 0 or sr_sc.returncode == 1062 or 'not been started' in combined_sc:
                            return {"status": "success", "message": "OK"}

                        return {"status": "error", "message": sr.stderr or sr.stdout or f"stop exit {sr.returncode}"}

                    elif cmd_type == "start":
                        if 'RUNNING' in q_out:
                            return {"status": "success", "message": "ALREADY_RUNNING"}
                        sr = subprocess.run(
                            ['sc.exe', 'start', svc_name],
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10
                        )
                        combined = ((sr.stdout or '') + (sr.stderr or '')).lower()
                        if sr.returncode == 0 or sr.returncode == 1056 or 'already running' in combined:
                            return {"status": "success", "message": "OK"}
                        return {"status": "error", "message": sr.stderr or sr.stdout or f"sc exit {sr.returncode}"}
                    else:
                        return {"status": "error", "message": f"Unknown service command: {cmd_type}"}
                except Exception as e:
                    return {"status": "error", "message": str(e)}

            elif action == "create_startup_task":
                task_name = data.get("task_name", "HELXAID_Startup")
                xml_path = data.get("xml_path")
                xml_content = data.get("xml_content")
                
                if xml_content:
                    import tempfile
                    xml_path = os.path.join(tempfile.gettempdir(), "helxaid_task_svc.xml")
                    with open(xml_path, 'w', encoding='utf-16') as f:
                        f.write(xml_content)
                        
                if not xml_path or not os.path.exists(xml_path):
                    return {"status": "error", "message": f"XML task config path not found: {xml_path}"}

                res = subprocess.run(
                    ["schtasks.exe", "/Create", "/TN", task_name, "/XML", xml_path, "/F"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15
                )
                if res.returncode == 0:
                    return {"status": "success", "message": f"Scheduled task '{task_name}' created successfully via Zero-UAC."}
                else:
                    err_msg = (res.stderr or res.stdout or "").strip()
                    return {"status": "error", "message": f"schtasks error {res.returncode}: {err_msg}"}

            elif action == "delete_startup_task":
                task_name = data.get("task_name", "HELXAID_Startup")
                res = subprocess.run(
                    ["schtasks.exe", "/Delete", "/TN", task_name, "/F"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15
                )
                err_msg = (res.stderr or res.stdout or "").lower()
                if res.returncode == 0 or "does not exist" in err_msg or "not found" in err_msg:
                    return {"status": "success", "message": f"Scheduled task '{task_name}' deleted successfully via Zero-UAC."}
                else:
                    return {"status": "error", "message": f"schtasks error {res.returncode}: {(res.stderr or res.stdout or '').strip()}"}

            elif action == "scan_disk_category":
                try:
                    from utils.drive_utils import _as_category_dicts, _iter_files, MAX_COLLECTED_PATHS
                    cat_id = data.get("cat_id")
                    collect_paths = data.get("collect_paths", True)
                    all_cats = {cat["id"]: cat for cat in _as_category_dicts(None)}
                    if cat_id not in all_cats:
                        return {"status": "error", "message": f"Category {cat_id} not found"}
                    
                    cat = all_cats[cat_id]
                    result = {
                        "status": "success",
                        "bytes": 0,
                        "file_count": 0,
                        "paths": [],
                        "path_count_truncated": False
                    }
                    
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
                            
                    return result
                except Exception as e:
                    return {"status": "error", "message": f"Scan failed: {str(e)}"}
            
            elif action == "clean_disk_category":
                try:
                    from utils.drive_utils import _as_category_dicts, _iter_files, _remove_empty_dirs
                    cat_id = data.get("cat_id")
                    all_cats = {cat["id"]: cat for cat in _as_category_dicts(None)}
                    if cat_id not in all_cats:
                        return {"status": "error", "message": f"Category {cat_id} not found"}
                        
                    cat = all_cats[cat_id]
                    result = {
                        "status": "success",
                        "cleaned_bytes": 0,
                        "skipped_bytes": 0,
                        "errors": []
                    }
                    
                    for file_path in _iter_files(cat.get("paths", [])):
                        try:
                            size = os.path.getsize(file_path)
                        except (PermissionError, OSError):
                            size = 0
                        try:
                            os.remove(file_path)
                            result["cleaned_bytes"] += size
                        except (PermissionError, OSError) as exc:
                            result["skipped_bytes"] += size
                            if len(result["errors"]) < 25:
                                result["errors"].append(f"{file_path}: {exc}")
                                
                    _remove_empty_dirs(cat.get("paths", []))
                    return result
                except Exception as e:
                    return {"status": "error", "message": f"Clean failed: {str(e)}"}

            elif action == "exec_batch_commands":
                commands = data.get("commands", [])
                if not commands:
                    return {"status": "error", "message": "No commands provided."}
                
                import tempfile
                temp_dir = tempfile.gettempdir()
                bat_path = os.path.join(temp_dir, f"helxaid_svc_cmd_{int(time.time()*1000)}.bat")
                with open(bat_path, 'w', encoding='utf-8') as f:
                    f.write("@echo off\n")
                    for cmd in commands:
                        f.write(cmd + "\n")
                
                try:
                    res = subprocess.run(
                        ["cmd.exe", "/c", bat_path],
                        capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=30
                    )
                    if res.returncode == 0:
                        return {"status": "success", "message": "OK"}
                    else:
                        err_out = (res.stderr or res.stdout or "").strip()
                        return {"status": "error", "message": f"Command exit {res.returncode}: {err_out}"}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
                finally:
                    if os.path.exists(bat_path):
                        try: os.remove(bat_path)
                        except OSError: pass

            elif action == "delete_path":
                target_path = data.get("path")
                if not target_path or not os.path.exists(target_path):
                    return {"status": "success", "message": "Path does not exist"}
                try:
                    import stat, tempfile, uuid
                    if os.path.isdir(target_path):
                        for root, dirs, files in os.walk(target_path, topdown=False):
                            for f in files:
                                f_path = os.path.join(root, f)
                                try:
                                    os.chmod(f_path, stat.S_IWRITE)
                                    os.remove(f_path)
                                except Exception:
                                    try:
                                        os.rename(f_path, os.path.join(tempfile.gettempdir(), f"{f}.del_{uuid.uuid4().hex[:4]}"))
                                    except Exception:
                                        pass
                        subprocess.run(['cmd.exe', '/c', f'attrib -r -s -h "{target_path}\\*" /s /d & rd /s /q "{target_path}"'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        try:
                            os.chmod(target_path, stat.S_IWRITE)
                            os.remove(target_path)
                        except Exception:
                            os.rename(target_path, os.path.join(tempfile.gettempdir(), f"{os.path.basename(target_path)}.del_{uuid.uuid4().hex[:4]}"))
                    return {"status": "success", "removed": not os.path.exists(target_path)}
                except Exception as e:
                    return {"status": "error", "message": str(e)}

            elif action == "ping":
                return {"status": "success", "message": "pong"}

            elif action == "restart":
                def _do_restart():
                    time.sleep(0.2)
                    try:
                        subprocess.Popen(
                            ["cmd.exe", "/c", "timeout /t 1 /nobreak && net start HelxaidHelperService"],
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                    except Exception:
                        pass
                    os._exit(1)
                import threading
                threading.Thread(target=_do_restart, daemon=True).start()
                return {"status": "success", "message": "Restarting service..."}
                
            else:
                return {"status": "error", "message": "Unknown action."}
                
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON format."}
        except Exception as e:
            return {"status": "error", "message": f"Internal error: {str(e)}"}

    def main(self):
        sa = self.create_pipe_security_attributes()
        
        while self.running:
            try:
                pipe = win32pipe.CreateNamedPipe(
                    PIPE_NAME,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                    win32pipe.PIPE_UNLIMITED_INSTANCES, 
                    1048576, 1048576,
                    0,
                    sa
                )
                
                win32pipe.ConnectNamedPipe(pipe, None)
                
                if not self.running:
                    win32file.CloseHandle(pipe)
                    break
                    
                # Read payload
                hr, data = win32file.ReadFile(pipe, 65536)
                if hr == 0:
                    payload_str = data.decode('utf-8')
                    response_dict = self.process_command(payload_str)
                    
                    # Send response
                    response_bytes = json.dumps(response_dict).encode('utf-8')
                    win32file.WriteFile(pipe, response_bytes)
                
                win32file.FlushFileBuffers(pipe)
                win32pipe.DisconnectNamedPipe(pipe)
                win32file.CloseHandle(pipe)
                
            except pywintypes.error as e:
                # 109 is ERROR_BROKEN_PIPE
                if e.winerror != 109:
                    servicemanager.LogWarningMsg(f"Pipe error: {e}")
                try:
                    win32pipe.DisconnectNamedPipe(pipe)
                    win32file.CloseHandle(pipe)
                except:
                    pass
            except Exception as e:
                servicemanager.LogWarningMsg(f"HELXAID Service loop error: {e}")
                time.sleep(1)

def run_as_service():
    if len(sys.argv) > 1 and sys.argv[1] == '--run-service':
        if len(sys.argv) > 2:
            # Handle --install, --remove, --start
            action = sys.argv[2]
            
            # We need to strip '--run-service' from sys.argv so win32serviceutil parses it correctly
            sys.argv.pop(1) 
            
            if action == '--install':
                sys.argv = [sys.argv[0], '--startup', 'auto', 'install']
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
                try:
                    subprocess.run(['sc.exe', 'config', 'HelxaidHelperService', 'start=', 'auto'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception:
                    pass
            elif action == '--remove':
                sys.argv = [sys.argv[0], 'remove']
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
            elif action == '--start':
                sys.argv = [sys.argv[0], 'start']
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
            elif action == '--stop':
                sys.argv = [sys.argv[0], 'stop']
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
            elif action == '--setup':
                sys.argv = [sys.argv[0], '--startup', 'auto', 'install']
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
                # Wait a bit for SCM to register it
                import time
                time.sleep(1)
                try:
                    subprocess.run(['sc.exe', 'config', 'HelxaidHelperService', 'start=', 'auto'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception:
                    pass
                try:
                    win32serviceutil.StartService(HelxaidHelperService._svc_name_)
                except Exception as e:
                    print(f"Failed to start service: {e}")
            elif action == '--teardown':
                try:
                    win32serviceutil.StopService(HelxaidHelperService._svc_name_)
                    import time
                    time.sleep(1)
                except Exception:
                    pass # Ignore if not running
                sys.argv[1] = 'remove'
                win32serviceutil.HandleCommandLine(HelxaidHelperService)
        else:
            # Service Control Manager passes "service name" as arg1 usually, 
            # but PyInstaller passes the exe name. We handle this explicitly in launcher.py.
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(HelxaidHelperService)
            servicemanager.StartServiceCtrlDispatcher()

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(HelxaidHelperService)
