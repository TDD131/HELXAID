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
            time.sleep(2)  # Update every 2 seconds
    
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
        
        # Priority 1: Try HWiNFO (fast, direct shared memory access)
        if HWINFO_AVAILABLE:
            try:
                hwinfo = get_hwinfo_reader()
                if hwinfo.is_available():
                    sensors = hwinfo.read_sensors()
                    if sensors.get("available"):
                        cpu_temp = sensors.get("cpu_temp", 0)
                        gpu_temp = sensors.get("gpu_temp", 0)
                        cpu_load = sensors.get("cpu_load", 0)
                        gpu_load = sensors.get("gpu_load", 0)
                        fan_speed = sensors.get("fan_speed", 0)
                        power = sensors.get("power", 0)
                        cpu_clock = sensors.get("cpu_clock", 0)
                        cpu_fan_speed = fan_speed  # HWiNFO default mapping
                        sys_fan_speed = sensors.get("sys_fan", 0)
                        gpu_fan_speed = sensors.get("gpu_fan", 0)
                        if cpu_temp > 0 or gpu_temp > 0:
                            status = "hwinfo"
                            # Print once when first successful
                            if not getattr(self, '_hwinfo_logged', False):
                                print(f"[Hardware] Using HWiNFO for sensor data")
                                self._hwinfo_logged = True
            except Exception:
                pass  # Silently fall back to LHM
                
        # Try getting NVIDIA GPU info directly via pynvml (most reliable for NVIDIA)
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            try: gpu_fan_speed = float(pynvml.nvmlDeviceGetFanSpeed(handle))
            except Exception: pass
            
            try: dgpu_temp = float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
            except Exception: pass
            
            try: dgpu_load = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            except Exception: pass
            
            try: dgpu_power = float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0
            except Exception: pass
        except Exception:
            pass
        
        # Priority 2: Try LHM/OHM via fast COM WMI (zero powershell processes)
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
                            sval = float(s.get('Value') or 0)
                            sname_u = sname.upper()
                            
                            if stype == 'Temperature':
                                # Exclude GPU sensors from CPU matching
                                if 'GPU' in sname_u:
                                    if gpu_temp == 0 or 'CORE' in sname_u:
                                        gpu_temp = sval
                                else:
                                    # CPU Temperature Priority: Tctl/Tdie/Package > CPU > Core
                                    if ('TCTL' in sname_u or 'TDIE' in sname_u or 'PACKAGE' in sname_u) and cpu_prio < 3:
                                        cpu_temp = sval
                                        cpu_prio = 3
                                    elif 'CPU' in sname_u and cpu_prio < 2:
                                        cpu_temp = sval
                                        cpu_prio = 2
                                    elif 'CORE' in sname_u and cpu_prio < 1:
                                        cpu_temp = sval
                                        cpu_prio = 1

                            elif stype == 'Load':
                                if 'GPU' in sname_u:
                                    if gpu_load == 0 or 'CORE' in sname_u:
                                        gpu_load = sval
                                else:
                                    if ('CPU' in sname_u or 'TOTAL' in sname_u) and cpu_load == 0:
                                        cpu_load = sval

                            elif stype == 'Power':
                                if 'GPU' in sname_u:
                                    gpu_power = sval
                                elif ('CPU' in sname_u or 'PACKAGE' in sname_u) and power == 0:
                                    power = sval

                            elif stype == 'Clock':
                                if 'GPU' in sname_u:
                                    pass
                                elif 'CORE' in sname_u or 'CPU' in sname_u:
                                    if cpu_clock == 0:
                                        cpu_clock = sval
                                    else:
                                        cpu_clock = (cpu_clock + sval) / 2.0

                            elif stype == 'Fan':
                                fname = sname.lower()
                                if 'cpu' in fname:
                                    cpu_fan_speed = max(cpu_fan_speed, sval)
                                elif 'gpu' in fname:
                                    if gpu_fan_speed == 0:
                                        gpu_fan_speed = max(gpu_fan_speed, sval)
                                else:
                                    sys_fan_speed = max(sys_fan_speed, sval)
                        
                        fan_speed = cpu_fan_speed or sys_fan_speed or gpu_fan_speed
                        if cpu_temp > 0 or gpu_temp > 0:
                            status = "lhm_com"
                except Exception:
                    pass

        
        # Helper: Map generic gpu to igpu or duplicate
        if dgpu_temp > 0 and abs(gpu_temp - dgpu_temp) < 2 and abs(gpu_load - dgpu_load) < 5:
            # The generic GPU temp picked up by HWiNFO/LHM is likely the dGPU. So no iGPU.
            igpu_temp = 0
            igpu_load = 0
            igpu_power = 0
        else:
            igpu_temp = gpu_temp
            igpu_load = gpu_load
            igpu_power = gpu_power

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
        
        Priority: HWiNFO > LHM > psutil
        
        Returns:
            Dict with freq_ghz, cores, and threads
        """
        if NATIVE_AVAILABLE:
            try:
                return _hw.get_cpu_freq()
            except Exception:
                pass
        
        freq_ghz = 0.0
        cores = 0
        threads = 0
        
        # Get cores/threads from psutil
        if PSUTIL_AVAILABLE:
            cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
            threads = psutil.cpu_count(logical=True) or psutil.cpu_count()
        
        # Priority 1: Try HWiNFO (most accurate real-time boost clock)
        if HWINFO_AVAILABLE:
            try:
                hwinfo = get_hwinfo_reader()
                if hwinfo.is_available():
                    sensors = hwinfo.read_sensors()
                    if sensors.get("available") and sensors.get("cpu_clock", 0) > 0:
                        freq_ghz = sensors["cpu_clock"] / 1000  # MHz to GHz
                        return {"freq_ghz": freq_ghz, "cores": cores, "threads": threads}
            except Exception:
                pass
        
        # Priority 2: Try LHM cached clock
        lhm_clock = self._temp_cache.get("cpu_clock", 0)
        if lhm_clock > 0:
            freq_ghz = lhm_clock / 1000  # MHz to GHz
            return {"freq_ghz": freq_ghz, "cores": cores, "threads": threads}
        
        # Priority 3: Fallback to psutil (usually base clock only)
        if PSUTIL_AVAILABLE:
            try:
                per_cpu = psutil.cpu_freq(percpu=True)
                if per_cpu:
                    current_freq = max(cpu.current for cpu in per_cpu)
                else:
                    freq = psutil.cpu_freq()
                    current_freq = freq.current if freq else 0
            except Exception:
                freq = psutil.cpu_freq()
                current_freq = freq.current if freq else 0
            freq_ghz = current_freq / 1000 if current_freq else 0
        
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
        Get Physical Disk S.M.A.R.T info (Health, Temperature) via COM WMI / WinAPI without spawning powershell.
        """
        smart_disks = []
        if os.name != 'nt':
            return smart_disks

        # 1. Try LHM via COM WMI
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

        # 2. Fallback: Standard Win32_DiskDrive COM query if empty
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
        Works best with LibreHardwareMonitor running in background.
        
        Returns:
            Dict with cpu_temp, gpu_temp, cpu_load, gpu_load, fan_speed, power, status
        """
        if NATIVE_AVAILABLE:
            try:
                return _hw.get_temperatures()
            except Exception:
                pass
        
        # Return cached data (updated by background thread)
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
