"""
HWiNFO Shared Memory Reader - Read sensor data from HWiNFO64/32

HWiNFO exposes sensor data through shared memory when "Shared Memory Support" is enabled.
This module reads that shared memory to get real-time hardware data.

Requirements:
- HWiNFO64/32 must be running
- "Shared Memory Support" must be enabled in HWiNFO settings

Component Name: HWiNFOReader
"""

import ctypes
from ctypes import wintypes
from typing import Dict, List, Optional
import struct

# Windows constants
SYNCHRONIZE = 0x00100000
FILE_MAP_READ = 0x0004
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF

# HWiNFO shared memory names
HWINFO_SHARED_MEM_NAME = "Global\\HWiNFO_SENS_SM2"
HWINFO_MUTEX_NAME = "Global\\HWiNFO_SM2_MUTEX"

# HWiNFO sensor types
SENSOR_TYPE_NONE = 0
SENSOR_TYPE_TEMP = 1
SENSOR_TYPE_VOLT = 2
SENSOR_TYPE_FAN = 3
SENSOR_TYPE_CURRENT = 4
SENSOR_TYPE_POWER = 5
SENSOR_TYPE_CLOCK = 6
SENSOR_TYPE_USAGE = 7
SENSOR_TYPE_OTHER = 8


class HWiNFOHeader(ctypes.Structure):
    """Header structure for HWiNFO shared memory."""
    _pack_ = 1
    _fields_ = [
        ("dwSignature", wintypes.DWORD),      # 'HWiS' signature
        ("dwVersion", wintypes.DWORD),        # Version
        ("dwRevision", wintypes.DWORD),       # Revision
        ("poll_time", ctypes.c_longlong),     # Poll time (FILETIME)
        ("dwOffsetSensorSection", wintypes.DWORD),
        ("dwSizeSensorElement", wintypes.DWORD),
        ("dwNumSensorElements", wintypes.DWORD),
        ("dwOffsetReadingSection", wintypes.DWORD),
        ("dwSizeReadingElement", wintypes.DWORD),
        ("dwNumReadingElements", wintypes.DWORD),
    ]


class HWiNFOSensor(ctypes.Structure):
    """Sensor element structure."""
    _pack_ = 1
    _fields_ = [
        ("dwSensorId", wintypes.DWORD),
        ("dwSensorInst", wintypes.DWORD),
        ("szSensorNameOrig", ctypes.c_char * 128),
        ("szSensorNameUser", ctypes.c_char * 128),
    ]


class HWiNFOReading(ctypes.Structure):
    """Reading element structure."""
    _pack_ = 1
    _fields_ = [
        ("tReading", wintypes.DWORD),         # Sensor type
        ("dwSensorIndex", wintypes.DWORD),
        ("dwReadingId", wintypes.DWORD),
        ("szLabelOrig", ctypes.c_char * 128),
        ("szLabelUser", ctypes.c_char * 128),
        ("szUnit", ctypes.c_char * 16),
        ("Value", ctypes.c_double),
        ("ValueMin", ctypes.c_double),
        ("ValueMax", ctypes.c_double),
        ("ValueAvg", ctypes.c_double),
    ]


class HWiNFOReader:
    """
    Reader for HWiNFO shared memory sensor data.
    
    Component Name: HWiNFOReader
    """
    
    def __init__(self):
        self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self._map_handle = None
        self._view = None
        self._mutex = None
        self._available = False
        
        # Cache for sensor data
        self._sensors: List[Dict] = []
        self._readings: List[Dict] = []
        
    def is_available(self) -> bool:
        """Check if HWiNFO shared memory is available."""
        try:
            handle = self._kernel32.OpenFileMappingW(
                FILE_MAP_READ,
                False,
                HWINFO_SHARED_MEM_NAME
            )
            if handle:
                self._kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    
    def connect(self) -> bool:
        """Connect to HWiNFO shared memory."""
        try:
            # Open mutex for synchronization
            self._mutex = self._kernel32.OpenMutexW(
                SYNCHRONIZE,
                False,
                HWINFO_MUTEX_NAME
            )
            
            # Open file mapping
            self._map_handle = self._kernel32.OpenFileMappingW(
                FILE_MAP_READ,
                False,
                HWINFO_SHARED_MEM_NAME
            )
            
            if not self._map_handle:
                return False
            
            # Map view of file
            self._view = self._kernel32.MapViewOfFile(
                self._map_handle,
                FILE_MAP_READ,
                0, 0, 0
            )
            
            if not self._view:
                self._kernel32.CloseHandle(self._map_handle)
                self._map_handle = None
                return False
            
            self._available = True
            return True
            
        except Exception as e:
            print(f"[HWiNFO] Connect error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from HWiNFO shared memory."""
        try:
            if self._view:
                self._kernel32.UnmapViewOfFile(self._view)
                self._view = None
            if self._map_handle:
                self._kernel32.CloseHandle(self._map_handle)
                self._map_handle = None
            if self._mutex:
                self._kernel32.CloseHandle(self._mutex)
                self._mutex = None
            self._available = False
        except Exception:
            pass
    
    def _acquire_mutex(self, timeout_ms: int = 100) -> bool:
        """Acquire mutex for safe reading."""
        if not self._mutex:
            return True  # No mutex, proceed anyway
        
        result = self._kernel32.WaitForSingleObject(self._mutex, timeout_ms)
        return result == WAIT_OBJECT_0
    
    def _release_mutex(self):
        """Release mutex after reading."""
        if self._mutex:
            self._kernel32.ReleaseMutex(self._mutex)
    
    def read_sensors(self) -> Dict:
        """
        Read all sensor data from HWiNFO shared memory.
        
        Returns:
            Dict with cpu_clock, cpu_temp, gpu_temp, gpu_clock, fan_speed, etc.
        """
        result = {
            "cpu_clock": 0.0,
            "cpu_temp": 0.0,
            "cpu_load": 0.0,
            "gpu_clock": 0.0,
            "gpu_temp": 0.0,
            "gpu_load": 0.0,
            "fan_speed": 0.0,      # Primary/first fan
            "cpu_fan": 0.0,        # CPU fan RPM
            "gpu_fan": 0.0,        # GPU fan RPM
            "sys_fan": 0.0,        # System/case fan RPM
            "power": 0.0,
            "gpu_power": 0.0,      # GPU power consumption
            "available": False
        }
        
        if not self._available:
            if not self.connect():
                return result
        
        try:
            if not self._acquire_mutex():
                return result
            
            # Read header
            header = HWiNFOHeader.from_address(self._view)
            
            # Verify signature 'HWiS' = 0x53695748
            if header.dwSignature != 0x53695748:
                self._release_mutex()
                return result
            
            result["available"] = True
            
            # Read all readings
            reading_base = self._view + header.dwOffsetReadingSection
            reading_size = header.dwSizeReadingElement
            
            for i in range(header.dwNumReadingElements):
                reading_addr = reading_base + (i * reading_size)
                reading = HWiNFOReading.from_address(reading_addr)
                
                label = reading.szLabelOrig.decode('utf-8', errors='ignore').strip('\x00')
                value = reading.Value
                sensor_type = reading.tReading
                
                # CPU Clock (average of core clocks)
                if sensor_type == SENSOR_TYPE_CLOCK:
                    if 'Core' in label and 'CPU' not in label.upper():
                        # Individual core clock
                        if result["cpu_clock"] == 0:
                            result["cpu_clock"] = value
                        else:
                            result["cpu_clock"] = (result["cpu_clock"] + value) / 2
                    elif 'CPU' in label.upper() and 'Clock' in label:
                        result["cpu_clock"] = value
                    elif 'GPU' in label.upper():
                        result["gpu_clock"] = value
                
                # CPU Temperature
                elif sensor_type == SENSOR_TYPE_TEMP:
                    if 'CPU' in label.upper() and ('Package' in label or 'Core' in label):
                        if result["cpu_temp"] == 0:
                            result["cpu_temp"] = value
                    elif 'GPU' in label.upper():
                        if result["gpu_temp"] == 0:
                            result["gpu_temp"] = value
                
                # Fan Speed - categorize by fan type
                elif sensor_type == SENSOR_TYPE_FAN:
                    label_upper = label.upper()
                    if 'CPU' in label_upper:
                        if result["cpu_fan"] == 0:
                            result["cpu_fan"] = value
                    elif 'GPU' in label_upper:
                        if result["gpu_fan"] == 0:
                            result["gpu_fan"] = value
                    elif 'SYS' in label_upper or 'CASE' in label_upper or 'CHASSIS' in label_upper:
                        if result["sys_fan"] == 0:
                            result["sys_fan"] = value
                    else:
                        # First fan found as fallback
                        if result["fan_speed"] == 0:
                            result["fan_speed"] = value
                
                # Power - CPU and GPU
                elif sensor_type == SENSOR_TYPE_POWER:
                    label_upper = label.upper()
                    if 'CPU' in label_upper and 'Package' in label:
                        result["power"] = value
                    elif 'GPU' in label_upper:
                        if result["gpu_power"] == 0:
                            result["gpu_power"] = value
                
                # Usage/Load
                elif sensor_type == SENSOR_TYPE_USAGE:
                    if 'CPU' in label.upper() and 'Total' in label:
                        result["cpu_load"] = value
                    elif 'GPU' in label.upper():
                        if result["gpu_load"] == 0:
                            result["gpu_load"] = value
            
            # Set primary fan_speed to first non-zero categorized fan
            if result["fan_speed"] == 0:
                result["fan_speed"] = result["cpu_fan"] or result["gpu_fan"] or result["sys_fan"]
            
            self._release_mutex()
            return result
            
        except Exception as e:
            print(f"[HWiNFO] Read error: {e}")
            self._release_mutex()
            return result
    
    def get_cpu_clock(self) -> float:
        """Get current CPU clock in MHz."""
        data = self.read_sensors()
        return data.get("cpu_clock", 0.0)
    
    def get_all_readings(self) -> List[Dict]:
        """Get all sensor readings as a list of dicts."""
        readings = []
        
        if not self._available:
            if not self.connect():
                return readings
        
        try:
            if not self._acquire_mutex():
                return readings
            
            header = HWiNFOHeader.from_address(self._view)
            
            if header.dwSignature != 0x53695748:
                self._release_mutex()
                return readings
            
            reading_base = self._view + header.dwOffsetReadingSection
            reading_size = header.dwSizeReadingElement
            
            for i in range(header.dwNumReadingElements):
                reading_addr = reading_base + (i * reading_size)
                reading = HWiNFOReading.from_address(reading_addr)
                
                readings.append({
                    "label": reading.szLabelOrig.decode('utf-8', errors='ignore').strip('\x00'),
                    "type": reading.tReading,
                    "value": reading.Value,
                    "unit": reading.szUnit.decode('utf-8', errors='ignore').strip('\x00'),
                    "min": reading.ValueMin,
                    "max": reading.ValueMax,
                    "avg": reading.ValueAvg
                })
            
            self._release_mutex()
            return readings
            
        except Exception as e:
            print(f"[HWiNFO] Error: {e}")
            self._release_mutex()
            return readings


# Singleton instance
_hwinfo_reader: Optional[HWiNFOReader] = None

def get_hwinfo_reader() -> HWiNFOReader:
    """Get or create HWiNFO reader singleton."""
    global _hwinfo_reader
    if _hwinfo_reader is None:
        _hwinfo_reader = HWiNFOReader()
    return _hwinfo_reader


def is_hwinfo_available() -> bool:
    """Check if HWiNFO is running with shared memory enabled."""
    return get_hwinfo_reader().is_available()


def get_hwinfo_sensors() -> Dict:
    """Get sensor data from HWiNFO."""
    return get_hwinfo_reader().read_sensors()
