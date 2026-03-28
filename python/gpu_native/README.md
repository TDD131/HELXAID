# GPU Native Module

Native C++ GPU detection module using Windows DXGI for fast (<1ms) GPU enumeration.

## Features

- **Fast Detection**: <1ms GPU enumeration via DXGI (vs ~200ms with Python WMI)
- **Direct DXGI Access**: Full access to DXGI adapter information
- **Registry GPU Preference**: Set Windows GPU preference to High Performance
- **Automatic Fallback**: Falls back to Python WMI implementation if native module unavailable

## Building

### Prerequisites

- CMake 3.15+
- Visual Studio 2019+ (MSVC)
- Python 3.8+
- pybind11 2.10+

### Build Steps

```powershell
# Navigate to module directory
cd python/gpu_native

# Create build directory
mkdir build
cd build

# Configure with CMake
cmake .. -DCMAKE_BUILD_TYPE=Release

# Build
cmake --build . --config Release

# The .pyd file will be in the gpu_native directory
```

### Alternative: pip install

```powershell
cd python/gpu_native
pip install .
```

## Usage

```python
from gpu_native import init_dgpu_for_video, enumerate_adapters, is_native_available

# Check if native module is loaded
if is_native_available():
    print("Using native C++ DXGI module")
else:
    print("Using Python WMI fallback")

# Initialize GPU for video playback
registry_ok, has_dgpu = init_dgpu_for_video()

# Enumerate all GPUs
for gpu in enumerate_adapters():
    vram_mb = gpu.dedicated_video_memory // (1024 * 1024)
    gpu_type = "dGPU" if gpu.is_discrete else "iGPU"
    print(f"{gpu.name} ({gpu_type}, {vram_mb}MB)")
```

## API Reference

### Functions

| Function | Description | Returns |
|----------|-------------|---------|
| `is_native_available()` | Check if native module loaded | `bool` |
| `enumerate_adapters()` | List all GPU adapters | `List[GPUInfo]` |
| `set_gpu_preference(exe_path)` | Set Windows GPU preference | `bool` |
| `get_preferred_gpu()` | Get preferred GPU | `Tuple[bool, GPUInfo]` |
| `detect_vendor()` | Detect GPU vendor | `str` |
| `init_dgpu_for_video(exe_path)` | Initialize dGPU for video | `Tuple[bool, bool]` |

### GPUInfo Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `index` | int | Adapter index |
| `name` | str | GPU display name |
| `dedicated_video_memory` | int | Dedicated VRAM (bytes) |
| `shared_system_memory` | int | Shared memory (bytes) |
| `vendor_id` | int | PCI vendor ID |
| `device_id` | int | PCI device ID |
| `is_integrated` | bool | True if iGPU |
| `is_discrete` | bool | True if dGPU |
| `is_software` | bool | True if software adapter |

## How It Works

1. **DXGI Enumeration**: Uses `IDXGIFactory1::EnumAdapters1()` to enumerate GPUs
2. **GPU Classification**: Determines iGPU vs dGPU by dedicated VRAM (<64MB = iGPU)
3. **Registry Setting**: Sets `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` to `GpuPreference=2`
4. **Sorting**: Returns GPUs sorted by preference (dGPU with most VRAM first)

## Performance Comparison

| Method | Time | Accuracy |
|--------|------|----------|
| Native DXGI (C++) | <1ms | Exact |
| Python WMI | ~200ms | Good |
| Python ctypes DXGI | ~5ms | Exact |

## Troubleshooting

### "Native module not available"

The native module requires compilation. Either:
1. Build the module using CMake
2. Use the Python fallback (automatic)

### "Failed to create DXGI Factory"

This typically means:
- Running on non-Windows system (use Python fallback)
- DirectX not installed (rare on modern Windows)

## License

MIT License - Part of HELXAID Game Launcher
