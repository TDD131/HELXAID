"""
GPU Native Module - Python Wrapper

Provides a Python interface to the native C++ GPU detection module.
Automatically falls back to the Python WMI implementation if the native
module is not available.

Usage:
    from gpu_native import init_dgpu_for_video, enumerate_adapters
    
    # Initialize GPU for video playback
    init_dgpu_for_video()
    
    # Enumerate all adapters
    for gpu in enumerate_adapters():
        print(f"{gpu.name}: {gpu.dedicated_video_memory // (1024*1024)}MB")
"""

import os
import sys
from typing import List, Optional, Tuple

# Try to import native module
_native_available = False
_native_module = None

try:
    from . import gpu_native as _native_module
    _native_available = True
except ImportError:
    pass


class GPUInfo:
    """
    GPU adapter information.
    
    Attributes:
        index: Adapter index in system
        name: GPU display name
        dedicated_video_memory: Dedicated VRAM in bytes
        shared_system_memory: Shared system memory in bytes
        vendor_id: PCI vendor ID (0x10DE=NVIDIA, 0x1002=AMD, 0x8086=Intel)
        device_id: PCI device ID
        is_integrated: True if integrated GPU (iGPU)
        is_discrete: True if discrete GPU (dGPU)
        is_software: True if software adapter
    """
    
    def __init__(
        self,
        index: int = 0,
        name: str = "",
        dedicated_video_memory: int = 0,
        shared_system_memory: int = 0,
        vendor_id: int = 0,
        device_id: int = 0,
        is_integrated: bool = False,
        is_discrete: bool = False,
        is_software: bool = False
    ):
        self.index = index
        self.name = name
        self.dedicated_video_memory = dedicated_video_memory
        self.shared_system_memory = shared_system_memory
        self.vendor_id = vendor_id
        self.device_id = device_id
        self.is_integrated = is_integrated
        self.is_discrete = is_discrete
        self.is_software = is_software
    
    def __repr__(self):
        vram_mb = self.dedicated_video_memory // (1024 * 1024)
        gpu_type = "dGPU" if self.is_discrete else ("iGPU" if self.is_integrated else "Software")
        return f"<GPUInfo '{self.name}' ({gpu_type}, {vram_mb}MB)>"


def is_native_available() -> bool:
    """
    Check if the native C++ module is available.
    
    Returns:
        True if native module loaded successfully, False otherwise.
    """
    return _native_available


def enumerate_adapters() -> List[GPUInfo]:
    """
    Enumerate all GPU adapters in the system.
    
    Uses native C++ implementation if available (<1ms), otherwise
    falls back to Python WMI implementation (~200ms).
    
    Returns:
        List of GPUInfo objects sorted by preference:
        - dGPU with most VRAM first
        - Then iGPU
        - Then software adapters
    """
    if _native_available:
        # Use native C++ implementation
        native_gpus = _native_module.enumerate_adapters()
        result = []
        for ng in native_gpus:
            gpu = GPUInfo(
                index=ng.index,
                name=ng.name if isinstance(ng.name, str) else str(ng.name),
                dedicated_video_memory=ng.dedicated_video_memory,
                shared_system_memory=ng.shared_system_memory,
                vendor_id=ng.vendor_id,
                device_id=ng.device_id,
                is_integrated=ng.is_integrated,
                is_discrete=ng.is_discrete,
                is_software=ng.is_software
            )
            result.append(gpu)
        return result
    else:
        # Fallback to Python WMI implementation
        from gpu_utils import enumerate_dxgi_adapters
        return enumerate_dxgi_adapters()


def set_gpu_preference(exe_path: str = None) -> bool:
    """
    Set Windows GPU preference to High Performance.
    
    This is the most reliable method to force dGPU usage on Windows 10/11.
    The preference is stored in registry and persists across runs.
    
    Args:
        exe_path: Full path to executable. If None, uses current process.
    
    Returns:
        True if successful, False otherwise.
    
    Note:
        Registry path: HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences
        Value: GpuPreference=2 (2 = High Performance)
    """
    if exe_path is None:
        exe_path = sys.executable
    
    if _native_available:
        # Use native C++ implementation
        import ctypes
        wstr = ctypes.create_unicode_buffer(exe_path)
        return _native_module.set_gpu_preference(exe_path)
    else:
        # Fallback to Python implementation
        from gpu_utils import set_windows_gpu_preference_high_performance
        return set_windows_gpu_preference_high_performance(exe_path)


def get_preferred_gpu() -> Tuple[bool, Optional[GPUInfo]]:
    """
    Get the preferred GPU for video decoding.
    
    Returns:
        Tuple of (found, gpu_info) where found is True if GPU was detected.
    """
    if _native_available:
        found, native_gpu = _native_module.get_preferred_gpu()
        if found:
            gpu = GPUInfo(
                index=native_gpu.index,
                name=native_gpu.name if isinstance(native_gpu.name, str) else str(native_gpu.name),
                dedicated_video_memory=native_gpu.dedicated_video_memory,
                shared_system_memory=native_gpu.shared_system_memory,
                vendor_id=native_gpu.vendor_id,
                device_id=native_gpu.device_id,
                is_integrated=native_gpu.is_integrated,
                is_discrete=native_gpu.is_discrete,
                is_software=native_gpu.is_software
            )
            return (True, gpu)
        return (False, None)
    else:
        from gpu_utils import get_preferred_gpu
        gpu = get_preferred_gpu()
        if gpu:
            return (True, gpu)
        return (False, None)


def detect_vendor() -> str:
    """
    Detect the primary GPU vendor.
    
    Returns:
        'nvidia', 'amd', 'intel', or 'unknown'
    """
    if _native_available:
        return _native_module.detect_vendor()
    else:
        from gpu_utils import detect_gpu_vendor
        return detect_gpu_vendor()


def init_dgpu_for_video(exe_path: str = None) -> Tuple[bool, bool]:
    """
    Initialize discrete GPU for video playback.
    
    This is the main entry point that should be called BEFORE QApplication.
    
    Performs:
    1. Registry GPU preference setting (persists across runs)
    2. Environment variable setup (for current process)
    3. GPU detection and logging
    
    Args:
        exe_path: Path to executable. If None, uses current process.
    
    Returns:
        Tuple of (registry_success, has_dgpu):
        - registry_success: True if registry write succeeded
        - has_dgpu: True if discrete GPU is available
    """
    if exe_path is None:
        exe_path = sys.executable
    
    if _native_available:
        # Use native C++ implementation
        import ctypes
        wstr_path = exe_path
        registry_ok, has_dgpu = _native_module.init_dgpu_for_video(exe_path)
        
        # Log results
        gpus = enumerate_adapters()
        if gpus:
            print(f"[GPU] Detected {len(gpus)} GPU adapter(s):")
            for i, gpu in enumerate(gpus):
                gpu_type = "dGPU" if gpu.is_discrete else ("iGPU" if gpu.is_integrated else "Software")
                vram_mb = gpu.dedicated_video_memory // (1024 * 1024)
                marker = " <-- PREFERRED" if i == 0 else ""
                print(f"  [{gpu.index}] {gpu.name} ({gpu_type}, {vram_mb}MB VRAM){marker}")
            
            if has_dgpu:
                dgpu = gpus[0]
                print(f"[GPU] Discrete GPU selected: {dgpu.name} ({dgpu.dedicated_video_memory // (1024*1024)}MB VRAM)")
                if registry_ok:
                    print("[GPU] Windows GPU preference set to High Performance (persists)")
            else:
                print(f"[GPU] No discrete GPU found, using: {gpus[0].name}")
        else:
            print("[GPU] No GPUs detected")
        
        return (registry_ok, has_dgpu)
    else:
        # Fallback to Python implementation
        from gpu_utils import init_dgpu_for_video
        result = init_dgpu_for_video()
        return (result, result)


# Module version
__version__ = "1.0.0"


# For backwards compatibility, expose GPUInfo as GPUInfo
__all__ = [
    "GPUInfo",
    "is_native_available",
    "enumerate_adapters",
    "set_gpu_preference",
    "get_preferred_gpu",
    "detect_vendor",
    "init_dgpu_for_video",
]
