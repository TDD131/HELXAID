"""
Hardware Wrapper - Python bindings for hardware monitoring

Tries to use C++ hardware_utils module, falls back to psutil.
Provides unified API for Hardware Panel.

Component Name: HardwareWrapper
"""

import os
import subprocess
import time
from typing import Dict, List, Optional

# Try to import C++ module, fallback to psutil
try:
    import hardware_utils as _hw
    NATIVE_AVAILABLE = True
    print("[Hardware] C++ hardware_utils loaded")
except ImportError:
    NATIVE_AVAILABLE = False
    print("[Hardware] C++ not available, using psutil fallback")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[Hardware] psutil not available")

# Try to import HWiNFO reader for real-time sensor data
try:
    from hwinfo_reader import get_hwinfo_reader, is_hwinfo_available
    HWINFO_AVAILABLE = True
except ImportError:
    HWINFO_AVAILABLE = False
    print("[Hardware] HWiNFO reader not available")

def _query_wmi_fast(namespace: str, query: str) -> list:
    """
    Query WMI directly using pywin32 COM interface without spawning powershell.exe processes.
    Sub-millisecond execution, 0% CPU process creation overhead.
    """
    if os.name != 'nt':
        return []
    try:
        import win32com.client
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
            
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        services = locator.ConnectServer(".", f"root\\{namespace}")
        results = services.ExecQuery(query)
        items = []
        for obj in results:
            item = {}
            for prop in obj.Properties_:
                item[prop.Name] = prop.Value
            items.append(item)
        return items
    except Exception:
        return []

_pdh_query_handle = None
_pdh_counter_handle = None

def _get_pdh_cpu_freq_ghz() -> float:
    """Read dynamic real-time CPU frequency using Windows PDH Processor Performance counter."""
    if os.name != 'nt':
        return 0.0
    global _pdh_query_handle, _pdh_counter_handle
    try:
        import ctypes
        import struct
        pdh = ctypes.windll.pdh
        if _pdh_query_handle is None:
            hq = ctypes.c_void_p()
            hc = ctypes.c_void_p()
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(hq)) == 0:
                if pdh.PdhAddEnglishCounterW(hq, r'\Processor Information(_Total)\% Processor Performance', 0, ctypes.byref(hc)) == 0:
                    _pdh_query_handle = hq
                    _pdh_counter_handle = hc
                    pdh.PdhCollectQueryData(_pdh_query_handle)
                    return 0.0
        if _pdh_query_handle and _pdh_counter_handle:
            pdh.PdhCollectQueryData(_pdh_query_handle)
            buf = (ctypes.c_uint8 * 16)()
            if pdh.PdhGetFormattedCounterValue(_pdh_counter_handle, 0x200, None, buf) == 0:
                perf_pct = struct.unpack('d', bytes(buf)[8:16])[0]
                if perf_pct > 0:
                    base_mhz = 2635.0
                    if PSUTIL_AVAILABLE:
                        try:
                            freq = psutil.cpu_freq()
                            if freq and freq.current > 0:
                                base_mhz = freq.current
                        except Exception:
                            pass
                    return round(base_mhz * (perf_pct / 100.0) / 1000.0, 2)
    except Exception:
        pass
    return 0.0


class HardwareMonitor:
    """
    Hardware monitoring class with customizable update interval.
    
    Component Name: HardwareMonitor
    """
    
    def __init__(self, update_interval_ms: int = 500):
        """
        Initialize hardware monitor.
        
        Args:
            update_interval_ms: Update interval in milliseconds (100-1000)
        """
        self.update_interval_ms = max(100, min(1000, update_interval_ms))
        self._last_net_bytes_recv = 0
        self._last_net_bytes_sent = 0
        self._last_net_time = 0
        
        # Cached temperature data (updated in background thread)
        self._temp_cache = {
            "cpu_temp": 0, "gpu_temp": 0,
            "cpu_load": 0, "gpu_load": 0,
            "fan_speed": 0, "power": 0,
            "cpu_fan_speed": 0, "gpu_fan_speed": 0, "sys_fan_speed": 0,
            "cpu_clock": 0,  # Real-time CPU clock in MHz from LHM
            "status": "unavailable"
        }
        self._temp_thread = None
        self._temp_thread_running = False
        self._temp_thread_started = False
        
        # Initialize CPU counter if native available
        if NATIVE_AVAILABLE:
            try:
                _hw.init_cpu_counter()
            except Exception:
                pass

    def start(self):
        """Start background monitoring threads.

        This is intentionally NOT called by __init__ to keep baseline memory
        lower when a HardwareMonitor instance is created but the monitoring
        UI is not actively used.
        """
        if self._temp_thread_started:
            return
        self._temp_thread_started = True
        self._start_temp_thread()

    def stop(self):
        """Stop background monitoring threads."""
        self._temp_thread_running = False
        try:
            t = self._temp_thread
        except Exception:
            t = None
        if t is not None:
            try:
                t.join(timeout=2.0)
            except Exception:
                pass
        self._temp_thread = None
        self._temp_thread_started = False
    
    def _start_temp_thread(self):
        """Start background thread for temperature monitoring."""
        import threading
        
        if self._temp_thread_running:
            return
        
        self._temp_thread_running = True
        self._temp_thread = threading.Thread(target=self._temp_monitor_loop, daemon=True)
        self._temp_thread.start()
    
    def _temp_monitor_loop(self):
        """Background loop for temperature monitoring."""
        import time
        
        while self._temp_thread_running:
            try:
                self._update_temp_cache()
            except Exception as e:
                print(f"[Hardware] Temp thread error: {e}")
            time.sleep(0.5)  # Update every 500ms for real-time hardware sensors
    
    def _update_temp_cache(self):
        """Update temperature cache (runs in background thread).
        
        Priority: HWiNFO (fast shared memory) > LHM WMI (slow PowerShell)
        """
        import subprocess
        import json
        
        cpu_temp = 0
        gpu_temp = 0
        cpu_load = 0
        gpu_load = 0
        fan_speed = 0
        cpu_fan_speed = 0
        gpu_fan_speed = 0
        sys_fan_speed = 0
        power = 0
        gpu_power = 0
        cpu_power = 0
        cpu_clock = 0
        status = "unavailable"
        
        igpu_temp = 0
        igpu_load = 0
        igpu_power = 0
        
        dgpu_temp = 0
        dgpu_load = 0
        dgpu_power = 0
        
        # Priority 1: Exclusive Embedded LibreHardwareMonitor Engine (100% Native, non-admin)
        # Gets: iGPU temp/load/power, GPU clock, fan speeds, CPU load/clock
        # Does NOT get: AMD CPU Tdie/Tctl (requires SMU / SYSTEM privileges)
        try:
            from core.lhm_wrapper import get_lhm_reader_instance
            lhm = get_lhm_reader_instance()
            if lhm.is_available():
                sensors = lhm.read_sensors()
                if sensors.get("available"):
                    # CPU - load and clock are OK even non-admin; temp may be 0 on AMD
                    cpu_load  = float(sensors.get("cpu_load")  or 0)
                    cpu_clock = float(sensors.get("cpu_clock") or 0)
                    cpu_power = float(sensors.get("cpu_power") or 0)
                    power     = cpu_power

                    # iGPU (AMD Radeon integrated) — available non-admin on AMD
                    igpu_temp  = float(sensors.get("igpu_temp")  or 0)
                    igpu_load  = float(sensors.get("igpu_load")  or 0)
                    igpu_power = float(sensors.get("igpu_power") or 0)

                    # dGPU from LHM (fallback; pynvml below overrides)
                    dgpu_temp  = float(sensors.get("dgpu_temp")  or 0)
                    dgpu_load  = float(sensors.get("dgpu_load")  or 0)
                    dgpu_power = float(sensors.get("dgpu_power") or 0)
                    gpu_temp   = float(sensors.get("gpu_temp")   or 0)
                    gpu_load   = float(sensors.get("gpu_load")   or 0)
                    gpu_power  = float(sensors.get("gpu_power")  or 0)

                    fan_speed     = float(sensors.get("fan_speed")  or 0)
                    cpu_fan_speed = float(sensors.get("cpu_fan")    or 0)
                    gpu_fan_speed = float(sensors.get("gpu_fan")    or 0)
                    sys_fan_speed = float(sensors.get("sys_fan")    or 0)

                    if cpu_load > 0 or igpu_load > 0 or dgpu_load > 0:
                        status = "lhm_embedded"
                        if not getattr(self, '_lhm_logged', False):
                            print("[Hardware] Using Exclusive LibreHardwareMonitor Engine")
                            self._lhm_logged = True
        except Exception:
            pass

        # Priority 2: NVIDIA GPU via pynvml — most accurate NVIDIA data, always overrides LHM dGPU values
        try:
            import pynvml
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            try:
                dgpu_temp = float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
                gpu_temp  = dgpu_temp
            except Exception: pass
            try:
                dgpu_load = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
                gpu_load  = dgpu_load
            except Exception: pass
            try:
                dgpu_power = float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0
                gpu_power  = dgpu_power
            except Exception: pass
            try:
                gpu_fan_speed = float(pynvml.nvmlDeviceGetFanSpeed(handle))
                fan_speed = max(fan_speed, gpu_fan_speed)
            except Exception: pass
            if dgpu_temp > 0 and status == "unavailable":
                status = "pynvml"
        except Exception:
            pass

        # Priority 3: AMD CPU Tdie via Zero-UAC service (SYSTEM context = SMU access)
        # Only needed when cpu_temp is still 0 (AMD Ryzen non-admin limitation)
        if cpu_temp == 0:
            try:
                from integrations.cpu_controller import send_service_command
                resp = send_service_command({"action": "read_lhm_sensors"})
                if resp and resp.get("status") == "success":
                    svc_sensors = resp.get("sensors", {})
                    svc_cpu = float(svc_sensors.get("cpu_temp") or 0)
                    if svc_cpu > 0:
                        cpu_temp = svc_cpu
                        if status == "unavailable":
                            status = "lhm_service"
                    # Also grab CPU clock and power from service if not yet set
                    if cpu_clock == 0:
                        cpu_clock = float(svc_sensors.get("cpu_clock") or 0)
                    if cpu_power == 0:
                        cpu_power = float(svc_sensors.get("cpu_power") or 0)
                        power = cpu_power
                    # iGPU from service if local LHM didn't get it
                    if igpu_temp == 0:
                        igpu_temp  = float(svc_sensors.get("igpu_temp")  or 0)
                        igpu_load  = float(svc_sensors.get("igpu_load")  or 0)
                        igpu_power = float(svc_sensors.get("igpu_power") or 0)
            except Exception:
                pass

        # Priority 4: Fast COM WMI (LHM/OHM WMI namespace) — only if still no data
        if status == "unavailable":
            for namespace in ['LibreHardwareMonitor', 'OpenHardwareMonitor']:
                if cpu_temp > 0:
                    break
                try:
                    sensors = _query_wmi_fast(namespace, "SELECT Name, SensorType, Value FROM Sensor")
                    if sensors:
                        cpu_prio = 0
                        for s in sensors:
                            stype = str(s.get('SensorType', ''))
                            sname = str(s.get('Name', ''))
                            sval  = float(s.get('Value') or 0)
                            sname_u = sname.upper()

                            if stype == 'Temperature':
                                if 'GPU' in sname_u:
                                    if gpu_temp == 0 or 'CORE' in sname_u:
                                        gpu_temp = sval
                                else:
                                    if ('TCTL' in sname_u or 'TDIE' in sname_u or 'PACKAGE' in sname_u) and cpu_prio < 3:
                                        cpu_temp = sval; cpu_prio = 3
                                    elif 'CPU' in sname_u and cpu_prio < 2:
                                        cpu_temp = sval; cpu_prio = 2
                                    elif 'CORE' in sname_u and cpu_prio < 1:
                                        cpu_temp = sval; cpu_prio = 1
                            elif stype == 'Load':
                                if 'GPU' in sname_u:
                                    if gpu_load == 0 or 'CORE' in sname_u: gpu_load = sval
                                elif ('CPU' in sname_u or 'TOTAL' in sname_u) and cpu_load == 0:
                                    cpu_load = sval
                            elif stype == 'Power':
                                if 'GPU' in sname_u: gpu_power = sval
                                elif ('CPU' in sname_u or 'PACKAGE' in sname_u) and power == 0: power = sval
                            elif stype == 'Fan':
                                fname = sname.lower()
                                if 'cpu' in fname: cpu_fan_speed = max(cpu_fan_speed, sval)
                                elif 'gpu' in fname: gpu_fan_speed = max(gpu_fan_speed, sval)
                                else: sys_fan_speed = max(sys_fan_speed, sval)

                        fan_speed = cpu_fan_speed or sys_fan_speed or gpu_fan_speed
                        if cpu_temp > 0 or gpu_temp > 0:
                            status = "lhm_com"
                except Exception:
                    pass

        # Update cache
        self._temp_cache = {
            "cpu_temp": cpu_temp, "gpu_temp": gpu_temp,
            "cpu_load": cpu_load, "gpu_load": gpu_load,
            "fan_speed": fan_speed, "power": power,
            "cpu_fan_speed": cpu_fan_speed, "gpu_fan_speed": gpu_fan_speed,
            "sys_fan_speed": sys_fan_speed,
            "cpu_clock": cpu_clock,
            "cpu_power": power,             # Store generic power as cpu_power
            "igpu_temp": igpu_temp, "igpu_load": igpu_load, "igpu_power": igpu_power,
            "dgpu_temp": dgpu_temp, "dgpu_load": dgpu_load, "dgpu_power": dgpu_power,
            "status": status
        }
    
    def _clean_ram_ctypes(self) -> Dict:
        """
        Clean RAM using Windows ctypes API (EmptyWorkingSet).
        
        This is an effective fallback when C++ module is not available.
        Empties working sets of processes, forcing pages to swap file.
        """
        import ctypes
        from ctypes import wintypes
        
        try:
            # Get RAM before
            if PSUTIL_AVAILABLE:
                mem_before = psutil.virtual_memory()
                used_before = mem_before.used
            else:
                used_before = 0
            
            # Windows API functions
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            
            # Constants
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_SET_QUOTA = 0x0100
            
            # Get process IDs
            process_ids = (wintypes.DWORD * 2048)()
            bytes_returned = wintypes.DWORD()
            
            if not psapi.EnumProcesses(
                ctypes.byref(process_ids),
                ctypes.sizeof(process_ids),
                ctypes.byref(bytes_returned)
            ):
                return {"processes_cleaned": 0, "memory_freed_mb": 0, "error": "EnumProcesses failed"}
            
            num_processes = bytes_returned.value // ctypes.sizeof(wintypes.DWORD)
            processes_cleaned = 0
            
            for i in range(num_processes):
                pid = process_ids[i]
                if pid == 0:  # Skip System Idle
                    continue
                
                # Open process
                h_process = kernel32.OpenProcess(
                    PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA,
                    False,
                    pid
                )
                
                if h_process:
                    # EmptyWorkingSet flushes working set to pagefile
                    if psapi.EmptyWorkingSet(h_process):
                        processes_cleaned += 1
                    kernel32.CloseHandle(h_process)
            
            # Get RAM after
            if PSUTIL_AVAILABLE:
                mem_after = psutil.virtual_memory()
                used_after = mem_after.used
                freed_bytes = max(0, used_before - used_after)
                freed_mb = freed_bytes / (1024 * 1024)
            else:
                freed_mb = 0
            
            return {
                "processes_cleaned": processes_cleaned,
                "memory_freed_mb": round(freed_mb, 2)
            }
            
        except Exception as e:
            return {"processes_cleaned": 0, "memory_freed_mb": 0, "error": str(e)}
    
    def set_update_interval(self, interval_ms: int):
        """Set update interval (100-1000ms)."""
        self.update_interval_ms = max(100, min(1000, interval_ms))
    
    # ============================================
    # RAM FUNCTIONS
    # ============================================
    
    def get_ram_info(self) -> Dict:
        """
        Get RAM usage information.
        
        Returns:
            Dict with total, used, free (in GB), and percent
        """
        if NATIVE_AVAILABLE:
            try:
                return _hw.get_ram_info()
            except Exception:
                pass
        
        if PSUTIL_AVAILABLE:
            mem = psutil.virtual_memory()
            return {
                "total": mem.total / (1024**3),
                "used": mem.used / (1024**3),
                "free": mem.available / (1024**3),
                "percent": mem.percent
            }
        
        return {"total": 0, "used": 0, "free": 0, "percent": 0}
    
    def clean_ram(self) -> Dict:
        """
        Clean RAM by emptying working sets.
        
        Returns:
            Dict with processes_cleaned and memory_freed_mb
        """
        if NATIVE_AVAILABLE:
            try:
                return _hw.clean_ram()
            except Exception as e:
                return {"processes_cleaned": 0, "memory_freed_mb": 0, "error": str(e)}
        
        # ctypes-based fallback using Windows API
        return self._clean_ram_ctypes()
    
    # ============================================
    # CPU FUNCTIONS
    # ============================================
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        if NATIVE_AVAILABLE:
            try:
                return _hw.get_cpu_usage()
            except Exception:
                pass
        
        if PSUTIL_AVAILABLE:
            return psutil.cpu_percent(interval=0)
        
        return 0.0

    def get_cpu_freq(self) -> Dict:
        """
        Get CPU frequency and core count.
        
        Priority for Frequency: LHM (MSR/SMU hardware clock) > Windows PDH (real-time dynamic clock) > psutil > HWiNFO > Native C++
        Cores & Threads: Always from psutil (Physical Cores & Logical Threads)
        
        Returns:
            Dict with freq_ghz, cores, and threads
        """
        cores = 0
        threads = 0
        
        # Get accurate physical cores and logical threads from psutil
        if PSUTIL_AVAILABLE:
            cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
            threads = psutil.cpu_count(logical=True) or psutil.cpu_count() or 0
        
        freq_ghz = 0.0
        
        # Priority 1: Try LHM real-time hardware clock (SMU / MSR max core boost clock)
        lhm_clock = self._temp_cache.get("cpu_clock", 0) if hasattr(self, '_temp_cache') else 0
        if lhm_clock > 0:
            freq_ghz = round(lhm_clock / 1000.0, 2)
            return {"freq_ghz": freq_ghz, "cores": cores, "threads": threads}
        
        # Priority 2: Try dynamic Windows PDH Processor Performance Counter (Ultra zero latency real-time GHz)
        pdh_freq = _get_pdh_cpu_freq_ghz()
        if pdh_freq > 0:
            return {"freq_ghz": pdh_freq, "cores": cores, "threads": threads}

        # Priority 3: Fallback to psutil
        if PSUTIL_AVAILABLE:
            try:
                freq = psutil.cpu_freq()
                if freq and freq.current > 0:
                    return {"freq_ghz": round(freq.current / 1000.0, 2), "cores": cores, "threads": threads}
            except Exception:
                pass

        # Priority 4: Try HWiNFO
        if HWINFO_AVAILABLE:
            try:
                hwinfo = get_hwinfo_reader()
                if hwinfo.is_available():
                    sensors = hwinfo.read_sensors()
                    if sensors.get("available") and sensors.get("cpu_clock", 0) > 0:
                        freq_ghz = round(sensors["cpu_clock"] / 1000.0, 2)
                        return {"freq_ghz": freq_ghz, "cores": cores, "threads": threads}
            except Exception:
                pass

        # Priority 5: Fallback to C++ Native extension
        if NATIVE_AVAILABLE:
            try:
                native_res = _hw.get_cpu_freq()
                if native_res and native_res.get("freq_ghz", 0) > 0:
                    freq_ghz = round(native_res.get("freq_ghz", 0.0), 2)
            except Exception:
                pass
        
        return {"freq_ghz": freq_ghz, "cores": cores, "threads": threads}
    
    # ============================================
    # DISK FUNCTIONS
    # ============================================
    
    def get_disk_info(self) -> List[Dict]:
        """
        Get disk usage for all drives.
        
        Returns:
            List of dicts with drive, total, used, free, percent
        """
        if NATIVE_AVAILABLE:
            try:
                return _hw.get_disk_info()
            except Exception:
                pass
        
        if PSUTIL_AVAILABLE:
            disks = []
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "drive": part.mountpoint,
                        "total": usage.total / (1024**3),
                        "used": usage.used / (1024**3),
                        "free": usage.free / (1024**3),
                        "percent": usage.percent,
                        "fstype": part.fstype or "Unknown"
                    })
                except Exception:
                    pass
            return disks
        
        return []
    
    def get_smart_disks(self) -> List[Dict]:
        """
        Get Physical Disk S.M.A.R.T info (Health, Temperature) via service, COM WMI, or WinAPI without spawning powershell.
        """
        smart_disks = []
        if os.name != 'nt':
            return smart_disks

        # 1. Try Zero-UAC Service (Fastest & most reliable for elevated SMART)
        try:
            from integrations.cpu_controller import send_service_command
            resp = send_service_command({"action": "read_lhm_sensors"})
            if resp and resp.get("status") == "success":
                svc_sensors = resp.get("sensors", {})
                for disk in svc_sensors.get("storage", []):
                    model_name = disk.get("name", "Unknown")
                    temp_val = float(disk.get("temp") or 0)
                    health_pct = float(disk.get("health_percent", 100))
                    
                    is_ssd = any(kw in model_name.upper() for kw in ["NVME", "SSD", "M.2", "WD", "SAMSUNG", "KINGSTON", "CRUCIAL"])
                    status_str = "OK"
                    if health_pct < 20: status_str = "Warning"
                    if health_pct < 5: status_str = "Critical"
                    
                    smart_disks.append({
                        'model': model_name,
                        'temp': round(temp_val, 0),
                        'health_percent': round(health_pct, 0),
                        'status': status_str,
                        'type': "SSD" if is_ssd else "HDD"
                    })
        except Exception:
            pass

        if smart_disks:
            return smart_disks

        # 2. Try LHM via COM WMI (Fallback if service is down)
        try:
            lhm_hw = _query_wmi_fast("LibreHardwareMonitor", "SELECT Identifier, Name FROM Hardware WHERE HardwareType='Storage'")
            if lhm_hw:
                sensors = _query_wmi_fast("LibreHardwareMonitor", "SELECT Identifier, Name, SensorType, Value FROM Sensor")
                for hw in lhm_hw:
                    hw_id = str(hw.get('Identifier', ''))
                    model_name = str(hw.get('Name', 'Unknown'))
                    hw_sensors = [s for s in sensors if str(s.get('Identifier', '')).startswith(hw_id)]
                    
                    temp_val = 0.0
                    health_pct = 100.0
                    
                    for s in hw_sensors:
                        stype = str(s.get('SensorType', ''))
                        sname = str(s.get('Name', ''))
                        sval = float(s.get('Value') or 0)
                        
                        if stype == 'Temperature' and temp_val == 0:
                            temp_val = sval
                        elif 'Percentage Used' in sname or 'Degradation' in sname:
                            health_pct = max(0.0, min(100.0, 100.0 - sval))
                        elif 'Remaining Life' in sname or 'Available Spare' in sname:
                            health_pct = max(0.0, min(100.0, sval))
                            
                    is_ssd = any(kw in model_name.upper() for kw in ["NVME", "SSD", "M.2", "WD", "SAMSUNG", "KINGSTON", "CRUCIAL"])
                    status_str = "OK"
                    if health_pct < 20: status_str = "Warning"
                    if health_pct < 5: status_str = "Critical"
                    
                    smart_disks.append({
                        'model': model_name,
                        'temp': round(temp_val, 0),
                        'health_percent': round(health_pct, 0),
                        'status': status_str,
                        'type': "SSD" if is_ssd else "HDD"
                    })
        except Exception:
            pass

        # 3. Fallback: Standard Win32_DiskDrive COM query if empty
        if not smart_disks:
            try:
                disks = _query_wmi_fast("cimv2", "SELECT Model, Status, MediaType FROM Win32_DiskDrive")
                failures = _query_wmi_fast("wmi", "SELECT Active, PredictFailure FROM MSStorageDriver_FailurePredictStatus")
                predict_failed = any(f.get('PredictFailure', False) for f in failures)
                
                for d in disks:
                    model_name = str(d.get('Model', 'Disk Drive'))
                    media_type = str(d.get('MediaType', '')).upper()
                    is_ssd = "SSD" in media_type or any(kw in model_name.upper() for kw in ["NVME", "SSD", "M.2", "WD", "SAMSUNG", "KINGSTON", "CRUCIAL"])
                    
                    health_pct = 50.0 if predict_failed else 100.0
                    status_str = "Warning" if predict_failed else "OK"
                    
                    smart_disks.append({
                        'model': model_name,
                        'temp': 0.0,
                        'health_percent': health_pct,
                        'status': status_str,
                        'type': "SSD" if is_ssd else "HDD"
                    })
            except Exception as e:
                print(f"[Hardware] SMART disks error: {e}")

        return smart_disks

    def get_disk_details(self) -> Dict[str, Dict]:
        """
        Get detailed disk info (model, type, size, free) via fast COM WMI or psutil.
        """
        details = {}
        if os.name != 'nt':
            return details

        try:
            physical_disks = _query_wmi_fast("cimv2", "SELECT Model FROM Win32_DiskDrive")
            model_name = str(physical_disks[0].get('Model', 'Unknown')) if physical_disks else "Unknown"
            is_nvme = any(kw in model_name.upper() for kw in ["NVME", "SSD", "M.2", "WD_BLACK", "SAMSUNG", "KINGSTON", "CRUCIAL"])
            disk_type = "SSD" if is_nvme else "HDD"

            if PSUTIL_AVAILABLE:
                for part in psutil.disk_partitions():
                    drive_letter = part.mountpoint
                    if 'fixed' in part.opts or part.fstype or (os.name == 'nt' and drive_letter.endswith(':\\')):
                        try:
                            usage = psutil.disk_usage(drive_letter)
                            details[drive_letter] = {
                                'model': model_name,
                                'type': disk_type,
                                'size': round(usage.total / (1024**3), 0),
                                'free': round(usage.free / (1024**3), 0)
                            }
                        except Exception:
                            pass
        except Exception as e:
            print(f"[Hardware] Disk details error: {e}")

        return details
    
    def get_disk_io_speed(self) -> Dict:
        """
        Get disk I/O speeds (read/write MB/s).
        
        Returns:
            Dict with read_mbps, write_mbps
        """
        if not hasattr(self, '_last_disk_io'):
            self._last_disk_io = None
            self._last_disk_io_time = 0
        
        if PSUTIL_AVAILABLE:
            try:
                io = psutil.disk_io_counters()
                current_time = time.time()
                
                read_speed = 0
                write_speed = 0
                
                if self._last_disk_io and self._last_disk_io_time > 0:
                    elapsed = current_time - self._last_disk_io_time
                    if elapsed > 0:
                        read_diff = io.read_bytes - self._last_disk_io.read_bytes
                        write_diff = io.write_bytes - self._last_disk_io.write_bytes
                        read_speed = (read_diff / elapsed) / (1024 * 1024)  # MB/s
                        write_speed = (write_diff / elapsed) / (1024 * 1024)  # MB/s
                
                self._last_disk_io = io
                self._last_disk_io_time = current_time
                
                return {
                    "read_mbps": read_speed,
                    "write_mbps": write_speed
                }
            except Exception:
                pass
        
        return {"read_mbps": 0, "write_mbps": 0}
    
    # ============================================
    # NETWORK FUNCTIONS
    # ============================================
    
    def get_network_stats(self) -> Dict:
        """
        Get network upload/download stats.
        
        Returns:
            Dict with download_mbps, upload_mbps, total bytes
        """
        if NATIVE_AVAILABLE:
            try:
                return _hw.get_network_stats()
            except Exception:
                pass
        
        if PSUTIL_AVAILABLE:
            net = psutil.net_io_counters()
            current_time = time.time()
            
            download_speed = 0
            upload_speed = 0
            
            if self._last_net_time > 0:
                elapsed = current_time - self._last_net_time
                if elapsed > 0:
                    bytes_recv_diff = net.bytes_recv - self._last_net_bytes_recv
                    bytes_sent_diff = net.bytes_sent - self._last_net_bytes_sent
                    download_speed = (bytes_recv_diff / elapsed) * 8 / (1024 * 1024)  # Mbps
                    upload_speed = (bytes_sent_diff / elapsed) * 8 / (1024 * 1024)  # Mbps
            
            self._last_net_bytes_recv = net.bytes_recv
            self._last_net_bytes_sent = net.bytes_sent
            self._last_net_time = current_time
            
            return {
                "download_mbps": download_speed,
                "upload_mbps": upload_speed,
                "total_received_bytes": net.bytes_recv,
                "total_sent_bytes": net.bytes_sent
            }
        
        return {"download_mbps": 0, "upload_mbps": 0, "total_received_bytes": 0, "total_sent_bytes": 0}
    
    # ============================================
    # TEMPERATURE FUNCTIONS
    # ============================================
    
    def get_temperatures(self) -> Dict:
        """
        Get CPU/GPU temperatures (non-blocking, uses cached data).
        
        Note: Data is updated in background thread every 2 seconds.
        Uses LHM embedded (iGPU/fans) + pynvml (NVIDIA dGPU) + service IPC (AMD CPU Tdie).
        
        Returns:
            Dict with cpu_temp, dgpu_temp, igpu_temp, gpu_temp, cpu_load, dgpu_load,
            igpu_load, gpu_load, fan_speed, cpu_power, dgpu_power, status
        """
        # Always use Python cache — LHM+pynvml+service IPC chain has AMD SMU, iGPU/dGPU split,
        # NVIDIA temp/power — far superior to C++ hardware_utils which lacks all of these.
        return self._temp_cache.copy()
    
    # ============================================
    # ALL-IN-ONE SNAPSHOT
    # ============================================
    
    def get_snapshot(self) -> Dict:
        """
        Get a complete snapshot of all hardware stats.
        
        Returns:
            Dict with ram, cpu, disk, network, temps
        """
        return {
            "ram": self.get_ram_info(),
            "cpu": {
                "usage": self.get_cpu_usage(),
                **self.get_cpu_freq()
            },
            "disk": self.get_disk_info(),
            "disk_io": self.get_disk_io_speed(),
            "network": self.get_network_stats(),
            "temps": self.get_temperatures(),
            "timestamp": time.time()
        }


# Singleton instance for easy access
_monitor: Optional[HardwareMonitor] = None

def get_monitor(update_interval_ms: int = 500) -> HardwareMonitor:
    """Get or create the hardware monitor singleton."""
    global _monitor
    if _monitor is None:
        _monitor = HardwareMonitor(update_interval_ms)
    return _monitor

