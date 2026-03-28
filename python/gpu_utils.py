"""
GPU Detection and Selection Utilities

Provides cross-vendor GPU detection and selection for video playback.
Supports NVIDIA Optimus, AMD Switchable, and Intel hybrid graphics.

This module uses Windows DXGI to enumerate available GPUs and select
the best one for video decoding (discrete GPU with most VRAM).

Must be imported and initialized BEFORE QApplication is created.
"""

import os
import sys
import ctypes
from ctypes import wintypes, c_void_p, c_size_t, c_longlong, POINTER, Structure, byref
from typing import Optional, List, NamedTuple
import logging

logger = logging.getLogger(__name__)


class GPUInfo(NamedTuple):
    """Information about a GPU adapter."""
    index: int
    name: str
    dedicated_video_memory: int  # bytes
    shared_system_memory: int
    vendor_id: int
    device_id: int
    is_integrated: bool
    is_discrete: bool
    is_software: bool


# DXGI Adapter Flags
DXGI_ADAPTER_FLAG_NONE = 0
DXGI_ADAPTER_FLAG_REMOTE = 1
DXGI_ADAPTER_FLAG_SOFTWARE = 2

# DXGI Error Codes
DXGI_ERROR_NOT_FOUND = 0x887A0002
DXGI_ERROR_UNSUPPORTED = 0x887A0004
S_OK = 0

# GPU Vendor IDs
VENDOR_NVIDIA = 0x10DE
VENDOR_AMD = 0x1002
VENDOR_INTEL = 0x8086


class DXGI_ADAPTER_DESC1(Structure):
    """DXGI_ADAPTER_DESC1 structure for adapter information."""
    _fields_ = [
        ("Description", wintypes.WCHAR * 128),
        ("VendorId", wintypes.UINT),
        ("DeviceId", wintypes.UINT),
        ("SubSysId", wintypes.UINT),
        ("Revision", wintypes.UINT),
        ("DedicatedVideoMemory", c_size_t),
        ("DedicatedSystemMemory", c_size_t),
        ("SharedSystemMemory", c_size_t),
        ("AdapterLuid", c_longlong),
        ("Flags", wintypes.UINT),
    ]


class IUnknown(Structure):
    """IUnknown interface base."""
    _fields_ = [
        ("lpVtbl", c_void_p),
    ]


class IDXGIAdapter1(Structure):
    """IDXGIAdapter1 interface."""
    _fields_ = [
        ("lpVtbl", c_void_p),
    ]


class IDXGIFactory1(Structure):
    """IDXGIFactory1 interface."""
    _fields_ = [
        ("lpVtbl", c_void_p),
    ]


def _call_com_method(obj, method_offset, *args):
    """Call a COM method via vtable."""
    vtable = ctypes.cast(obj.lpVtbl, POINTER(c_void_p))
    method = vtable[method_offset]
    func_type = ctypes.WINFUNCTYPE(wintypes.HRESULT, c_void_p, *args)
    func = func_type(method)
    return func(obj, *args)


class GUID(Structure):
    """Windows GUID structure."""
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


# IID_IDXGIFactory1: {770aae78-f26f-44db-a82c-827c0c5c8d27}
IID_IDXGIFactory1 = GUID()
IID_IDXGIFactory1.Data1 = 0x770AAE78
IID_IDXGIFactory1.Data2 = 0xF26F
IID_IDXGIFactory1.Data3 = 0x44DB
IID_IDXGIFactory1.Data4 = (wintypes.BYTE * 8)(0xA8, 0x2C, 0x82, 0x7C, 0x0C, 0x5C, 0x8D, 0x27)


def _get_gpus_via_wmi() -> List['GPUInfoWMI']:
    """
    Enumerate GPUs using WMI (Windows Management Instrumentation).
    
    This is the most reliable method from Python without dealing with
    complex COM interfaces.
    
    Returns:
        List of GPUInfoWMI objects sorted by preference (dGPU first).
    """
    gpus = []
    
    if os.name != 'nt':
        return gpus
    
    try:
        # Use WMI via subprocess to avoid dependency on wmi package
        import subprocess
        result = subprocess.run(
            ['wmic', 'path', 'win32_VideoController', 'get', 
             'name,AdapterRAM,DriverVersion', '/format:csv'],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode != 0:
            logger.warning(f"WMI query failed: {result.stderr}")
            return gpus
        
        # Parse CSV output
        lines = result.stdout.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Node'):
                continue
            
            parts = line.split(',')
            if len(parts) >= 4:
                # Format: Node,AdapterRAM,DriverVersion,Name
                adapter_ram = parts[1].strip() if parts[1].strip() else '0'
                driver_version = parts[2].strip()
                name = parts[3].strip()
                
                if not name:
                    continue
                
                # Parse adapter RAM (in bytes)
                try:
                    ram_bytes = int(adapter_ram)
                    ram_mb = ram_bytes // (1024 * 1024)
                except ValueError:
                    ram_mb = 0
                
                # Detect vendor
                name_lower = name.lower()
                if 'nvidia' in name_lower or 'geforce' in name_lower or 'rtx' in name_lower or 'gtx' in name_lower:
                    vendor = 'NVIDIA'
                elif 'amd' in name_lower or 'radeon' in name_lower:
                    vendor = 'AMD'
                elif 'intel' in name_lower:
                    vendor = 'Intel'
                else:
                    vendor = 'Unknown'
                
                # Detect iGPU vs dGPU
                # iGPU typically has < 256MB dedicated RAM
                # Also check for common iGPU naming patterns
                is_integrated = (
                    ram_mb < 256 or
                    ('intel' in name_lower and 'uhd' in name_lower) or
                    ('intel' in name_lower and 'iris' in name_lower and ram_mb < 512) or
                    'amd' in name_lower and 'integrated' in name_lower
                )
                is_discrete = not is_integrated and ram_mb >= 64
                
                gpu = GPUInfo(
                    index=len(gpus),
                    name=name,
                    dedicated_video_memory=ram_mb * 1024 * 1024,  # Convert back to bytes
                    shared_system_memory=0,
                    vendor_id=VENDOR_NVIDIA if vendor == 'NVIDIA' else (VENDOR_AMD if vendor == 'AMD' else (VENDOR_INTEL if vendor == 'Intel' else 0)),
                    device_id=0,
                    is_integrated=is_integrated,
                    is_discrete=is_discrete,
                    is_software=False
                )
                gpus.append(gpu)
                
    except subprocess.TimeoutExpired:
        logger.warning("WMI query timed out")
    except FileNotFoundError:
        logger.warning("wmic not found - not running on Windows")
    except Exception as e:
        logger.error(f"WMI enumeration failed: {e}")
    
    # Sort: dGPU first (by RAM descending), then iGPU
    gpus.sort(key=lambda g: (
        not g.is_discrete,
        -g.dedicated_video_memory
    ))
    
    return gpus


def enumerate_dxgi_adapters() -> List[GPUInfo]:
    """
    Enumerate all GPUs and return GPU information.
    
    Uses WMI for reliable detection on Windows.
    
    Returns:
        List of GPUInfo objects for each adapter, sorted by preference
        (dGPU with most VRAM first, then iGPU, then software).
    """
    gpus = _get_gpus_via_wmi()
    
    # Ensure correct sorting (dGPU first, by VRAM descending)
    gpus.sort(key=lambda g: (
        not g.is_discrete,  # dGPU first
        -g.dedicated_video_memory,  # More VRAM = higher priority
        g.is_software  # Software last
    ))
    
    return gpus


def get_preferred_gpu() -> Optional[GPUInfo]:
    """
    Get the best GPU for video decoding.
    
    Priority:
    1. Discrete GPU with most dedicated VRAM
    2. Any GPU with dedicated VRAM
    3. Integrated GPU (fallback)
    
    Returns:
        GPUInfo of the preferred GPU, or None if detection fails.
    """
    gpus = enumerate_dxgi_adapters()
    
    if not gpus:
        return None
    
    # Return first GPU (already sorted by preference)
    return gpus[0]


def set_windows_gpu_preference_high_performance(exe_path: str = None) -> bool:
    """
    Set Windows Graphics Performance preference to High Performance.
    
    This is the most reliable method to force dGPU usage on Windows 10/11.
    The preference is stored in registry and persists across runs.
    
    Registry path: HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences
    Value name: Full path to executable
    Value data: "GpuPreference=2" (2 = High Performance)
    
    Args:
        exe_path: Path to executable. If None, uses current process.
    
    Returns:
        True if successful, False otherwise.
    """
    if exe_path is None:
        exe_path = sys.executable
    
    try:
        import winreg
        
        key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
        
        # Open or create key
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WRITE
        )
        
        # Set GpuPreference=2 (High Performance)
        # GpuPreference values: 0=Unspecified, 1=Minimum Power, 2=High Performance
        winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, "GpuPreference=2")
        winreg.CloseKey(key)
        
        logger.info(f"Set GPU preference for {exe_path} to High Performance")
        return True
        
    except Exception as e:
        logger.error(f"Failed to set GPU preference: {e}")
        return False


def detect_gpu_vendor() -> str:
    """
    Detect primary GPU vendor.
    
    Returns:
        'nvidia', 'amd', 'intel', or 'unknown'
    """
    gpus = enumerate_dxgi_adapters()
    
    if not gpus:
        return 'unknown'
    
    # Check preferred GPU vendor
    preferred = gpus[0]
    
    if preferred.vendor_id == VENDOR_NVIDIA:
        return 'nvidia'
    elif preferred.vendor_id == VENDOR_AMD:
        return 'amd'
    elif preferred.vendor_id == VENDOR_INTEL:
        return 'intel'
    
    return 'unknown'


def init_dgpu_for_video() -> bool:
    """
    Initialize discrete GPU for video playback.
    
    This is the main entry point that should be called BEFORE QApplication.
    
    Performs:
    1. Registry GPU preference setting (persists across runs)
    2. Environment variable setup (for current process)
    3. DXGI adapter detection and logging
    
    Returns:
        True if dGPU was successfully initialized or available,
        False if using iGPU or detection failed.
    """
    if os.name != 'nt':
        logger.info("GPU selection only available on Windows")
        return False
    
    # Step 1: Set registry preference (persists across runs)
    registry_ok = set_windows_gpu_preference_high_performance()
    
    # Step 2: Set environment variables (for current process)
    # These are hints that may or may not work depending on driver version
    os.environ["NvOptimusEnablement"] = "1"
    os.environ["AmdPowerXpressRequestHighPerformance"] = "1"
    
    # Step 3: Detect available GPUs
    gpus = enumerate_dxgi_adapters()
    
    if not gpus:
        logger.warning("No GPUs detected via DXGI")
        print("[GPU] No GPUs detected via DXGI enumeration")
        return False
    
    # Log detected GPUs
    print(f"[GPU] Detected {len(gpus)} GPU adapter(s):")
    for gpu in gpus:
        gpu_type = "dGPU" if gpu.is_discrete else "iGPU" if gpu.is_integrated else "Software"
        vram_mb = gpu.dedicated_video_memory // (1024 * 1024)
        
        # Mark the preferred GPU
        marker = " <-- PREFERRED" if gpu == gpus[0] else ""
        print(f"  [{gpu.index}] {gpu.name} ({gpu_type}, {vram_mb}MB VRAM){marker}")
    
    # Step 4: Check if we have a dGPU
    dgpu = next((g for g in gpus if g.is_discrete), None)
    
    if dgpu:
        vram_mb = dgpu.dedicated_video_memory // (1024 * 1024)
        print(f"[GPU] Discrete GPU selected: {dgpu.name} ({vram_mb}MB VRAM)")
        return True
    else:
        igpu = next((g for g in gpus if g.is_integrated), None)
        if igpu:
            print(f"[GPU] No discrete GPU found, using integrated: {igpu.name}")
        return False


def get_gpu_info_string() -> str:
    """
    Get a formatted string with GPU information for display.
    
    Returns:
        Human-readable GPU information string.
    """
    gpus = enumerate_dxgi_adapters()
    
    if not gpus:
        return "No GPUs detected"
    
    lines = []
    for gpu in gpus:
        gpu_type = "Discrete" if gpu.is_discrete else "Integrated" if gpu.is_integrated else "Software"
        vram_mb = gpu.dedicated_video_memory // (1024 * 1024)
        vendor = "Unknown"
        
        if gpu.vendor_id == VENDOR_NVIDIA:
            vendor = "NVIDIA"
        elif gpu.vendor_id == VENDOR_AMD:
            vendor = "AMD"
        elif gpu.vendor_id == VENDOR_INTEL:
            vendor = "Intel"
        
        lines.append(f"{gpu.name} ({vendor} {gpu_type}, {vram_mb}MB)")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test GPU detection
    print("=" * 60)
    print("GPU Detection Test")
    print("=" * 60)
    
    result = init_dgpu_for_video()
    
    print()
    print("=" * 60)
    print(f"Result: {'dGPU available' if result else 'Using iGPU'}")
    print("=" * 60)
