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
        
        # Start background temperature thread
        self._start_temp_thread()
        
        # Initialize CPU counter if native available
        if NATIVE_AVAILABLE:
            try:
                _hw.init_cpu_counter()
            except Exception:
                pass
    
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
        
        # Priority 2: Try LHM/OHM via WMI if HWiNFO didn't provide data
        if status == "unavailable":
            for namespace in ['LibreHardwareMonitor', 'OpenHardwareMonitor']:
                if cpu_temp > 0:
                    break
                try:
                    ps_script = f'''
$sensors = Get-WmiObject -Namespace root/{namespace} -Class Sensor -ErrorAction SilentlyContinue | Select-Object Name, SensorType, Value
if ($sensors) {{
    $result = @{{
        cpu_temp = ($sensors | Where-Object {{$_.SensorType -eq 'Temperature' -and ($_.Name -like '*CPU*' -or $_.Name -like 'Core*' -or $_.Name -like '*Package*')}} | Select-Object -First 1).Value
        gpu_temp = ($sensors | Where-Object {{$_.SensorType -eq 'Temperature' -and $_.Name -like '*GPU*'}} | Select-Object -First 1).Value
        cpu_load = ($sensors | Where-Object {{$_.SensorType -eq 'Load' -and ($_.Name -like '*CPU*' -or $_.Name -like '*Total*')}} | Select-Object -First 1).Value
        gpu_load = ($sensors | Where-Object {{$_.SensorType -eq 'Load' -and $_.Name -like '*GPU*'}} | Select-Object -First 1).Value
        fans = @($sensors | Where-Object {{$_.SensorType -eq 'Fan'}} | Select-Object Name, Value)
        power = ($sensors | Where-Object {{$_.SensorType -eq 'Power' -and $_.Name -like '*Package*'}} | Select-Object -First 1).Value
        cpu_clock = ($sensors | Where-Object {{$_.SensorType -eq 'Clock' -and ($_.Name -like '*Core*' -or $_.Name -like '*CPU*')}} | Measure-Object -Property Value -Average).Average
    }}
    $result | ConvertTo-Json -Compress
}}
'''
                    result = subprocess.run(
                        ['powershell', '-NoProfile', '-Command', ps_script],
                        capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    
                    if result.returncode == 0 and result.stdout.strip():
                        try:
                            data = json.loads(result.stdout.strip())
                            cpu_temp = float(data.get('cpu_temp') or 0)
                            gpu_temp = float(data.get('gpu_temp') or 0)
                            cpu_load = float(data.get('cpu_load') or 0)
                            gpu_load = float(data.get('gpu_load') or 0)
                            power = float(data.get('power') or 0)
                            cpu_clock = float(data.get('cpu_clock') or 0)
                            
                            fans_data = data.get('fans', [])
                            if isinstance(fans_data, list):
                                for f in fans_data:
                                    fname = str(f.get('Name', '')).lower()
                                    fval = float(f.get('Value', 0))
                                    if "cpu" in fname:
                                        cpu_fan_speed = max(cpu_fan_speed, fval)
                                    elif "gpu" in fname:
                                        if gpu_fan_speed == 0:  # Only override if pynvml failed
                                            gpu_fan_speed = max(gpu_fan_speed, fval)
                                    else:
                                        sys_fan_speed = max(sys_fan_speed, fval)
                                        
                            fan_speed = cpu_fan_speed or sys_fan_speed or gpu_fan_speed

                            if cpu_temp > 0 or gpu_temp > 0:
                                status = "lhm"
                        except (json.JSONDecodeError, ValueError, TypeError):
                            pass
                            
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
        Get Physical Disk S.M.A.R.T info (Health, Temperature) via LibreHardwareMonitor.
        """
        smart_disks = []
        if os.name != 'nt':
            return smart_disks
        
        try:
            ps_script = '''
$result = @()
$lhm_hw = Get-WmiObject -Namespace root/LibreHardwareMonitor -Class Hardware -ErrorAction SilentlyContinue | Where-Object HardwareType -eq 'Storage'
if ($lhm_hw) {
    try {
        $sensors = Get-WmiObject -Namespace root/LibreHardwareMonitor -Class Sensor -ErrorAction SilentlyContinue
        foreach ($hw in $lhm_hw) {
            $id = $hw.Identifier
            $hw_sensors = $sensors | Where-Object { $_.Identifier -like "$id*" }
            
            $temp_val = 0
            $health_pct = 100
            
            # Find temperature
            $temp_sensor = $hw_sensors | Where-Object { $_.SensorType -eq 'Temperature' } | Select-Object -First 1
            if ($temp_sensor -ne $null) { $temp_val = $temp_sensor.Value }
            
            # Find health
            $pct_used = $hw_sensors | Where-Object { $_.Name -match 'Percentage Used|Degradation' } | Select-Object -First 1
            $rem_life = $hw_sensors | Where-Object { $_.Name -match 'Remaining Life|Available Spare' } | Select-Object -First 1
            
            if ($pct_used -ne $null) {
                # Wear level is 'Percentage Used', health is 100 - wear
                $health_pct = 100 - $pct_used.Value
            } elseif ($rem_life -ne $null) {
                $health_pct = $rem_life.Value
            }
            
            if ($health_pct -lt 0) { $health_pct = 0 }
            if ($health_pct -gt 100) { $health_pct = 100 }
            
            $model_name = $hw.Name
            $is_ssd = ($model_name -match "NVMe|SSD|M\.2|WD.*|Samsung.*EVO|KINGSTON|Crucial")
            
            $status = "OK"
            if ($health_pct -lt 20) { $status = "Warning" }
            if ($health_pct -lt 5) { $status = "Critical" }
            
            $result += @{
                model = $model_name
                temp = [math]::Round($temp_val, 0)
                health_percent = [math]::Round($health_pct, 0)
                status = $status
                type = if ($is_ssd) { "SSD" } else { "HDD" }
            }
        }
    } catch {}
} else {
    try {
        $phys = Get-PhysicalDisk -ErrorAction SilentlyContinue
        foreach ($p in $phys) {
            $health = 100
            if ($p.HealthStatus -ne "Healthy") { $health = 50 }
            $result += @{
                model = $p.FriendlyName
                temp = 0
                health_percent = $health
                status = $p.HealthStatus
                type = if ($p.MediaType -match "SSD") { "SSD" } else { "HDD" }
            }
        }
    } catch {}
}
$result | ConvertTo-Json -Compress
'''
            res = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_script],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            if res.returncode == 0 and res.stdout.strip():
                import json
                data = json.loads(res.stdout.strip())
                if isinstance(data, dict):
                    data = [data]
                if isinstance(data, list):
                    for item in data:
                        smart_disks.append({
                            'model': item.get('model', 'Unknown'),
                            'temp': float(item.get('temp', 0)),
                            'health_percent': float(item.get('health_percent', 100)),
                            'status': item.get('status', 'OK'),
                            'type': str(item.get('type', 'HDD')).upper()
                        })
        except Exception as e:
            print(f"[Hardware] SMART disks error: {e}")
        
        return smart_disks

    def get_disk_details(self) -> Dict[str, Dict]:
        """
        Get detailed disk info (model, type, serial) via WMI.
        
        Returns:
            Dict mapping drive letter to disk details
        """
        details = {}
        
        if os.name != 'nt':
            return details
        
        try:
            # Simple PowerShell script to get disk info
            ps_script = '''
$result = @{}
$physicalDisks = Get-WmiObject Win32_DiskDrive
$physicalDisk = $physicalDisks | Select-Object -First 1
$model = if ($physicalDisk) { $physicalDisk.Model } else { "Unknown" }
$isNVMe = $model -match "NVMe|SSD|M\.2|WD_BLACK|Samsung.*EVO|KINGSTON|Crucial"

# Get all logical disks
Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    $result[$_.DeviceID] = @{
        model = $model
        type = if ($isNVMe) { "SSD" } else { "HDD" }
        size = [math]::Round($_.Size / 1GB, 0)
        free = [math]::Round($_.FreeSpace / 1GB, 0)
    }
}
$result | ConvertTo-Json -Compress
'''
            
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_script],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                data = json.loads(result.stdout.strip())
                if isinstance(data, dict):
                    for drive, info in data.items():
                        if isinstance(info, dict):
                            details[drive + '\\'] = {
                                'model': info.get('model', 'Unknown'),
                                'type': info.get('type', 'HDD'),
                                'size': info.get('size', 0),
                                'free': info.get('free', 0)
                            }
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
