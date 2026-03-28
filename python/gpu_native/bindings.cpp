/**
 * pybind11 Bindings for GPU Native Module
 * 
 * Provides Python bindings for the C++ GPU detection module.
 * 
 * @file bindings.cpp
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>

// Include the main implementation
#include "gpu_native.cpp"

namespace py = pybind11;

PYBIND11_MODULE(gpu_native, m) {
    m.doc() = R"docstring(
Native GPU detection module using DXGI.

This module provides fast GPU detection (<1ms) using Windows DXGI API.
It automatically falls back to Python WMI implementation if native module
is not available.

Example:
    >>> from gpu_native import enumerate_adapters, set_gpu_preference
    >>> adapters = enumerate_adapters()
    >>> for gpu in adapters:
    ...     print(f"{gpu.name}: {gpu.dedicated_video_memory // (1024*1024)}MB")
    NVIDIA GeForce RTX 3080: 10240MB
    Intel UHD Graphics: 0MB
    >>> set_gpu_preference()  # Set for current executable
    True
)docstring";

    // Bind GPUInfo struct as a class
    py::class_<gpu_native::GPUInfo>(m, "GPUInfo", R"docstring(
GPU adapter information structure.
    
Attributes:
    index (int): Adapter index in system
    name (str): GPU display name
    dedicated_video_memory (int): Dedicated VRAM in bytes
    shared_system_memory (int): Shared system memory in bytes
    vendor_id (int): PCI vendor ID (0x10DE=NVIDIA, 0x1002=AMD, 0x8086=Intel)
    device_id (int): PCI device ID
    is_integrated (bool): True if integrated GPU (iGPU)
    is_discrete (bool): True if discrete GPU (dGPU)
    is_software (bool): True if software adapter
)docstring")
        .def_readonly("index", &gpu_native::GPUInfo::index,
                      "Adapter index in system")
        .def_readonly("name", &gpu_native::GPUInfo::name,
                      "GPU display name")
        .def_readonly("dedicated_video_memory", &gpu_native::GPUInfo::dedicated_video_memory,
                      "Dedicated VRAM in bytes")
        .def_readonly("shared_system_memory", &gpu_native::GPUInfo::shared_system_memory,
                      "Shared system memory in bytes")
        .def_readonly("vendor_id", &gpu_native::GPUInfo::vendor_id,
                      "PCI vendor ID (0x10DE=NVIDIA, 0x1002=AMD, 0x8086=Intel)")
        .def_readonly("device_id", &gpu_native::GPUInfo::device_id,
                      "PCI device ID")
        .def_readonly("is_integrated", &gpu_native::GPUInfo::is_integrated,
                      "True if integrated GPU (iGPU)")
        .def_readonly("is_discrete", &gpu_native::GPUInfo::is_discrete,
                      "True if discrete GPU (dGPU)")
        .def_readonly("is_software", &gpu_native::GPUInfo::is_software,
                      "True if software adapter")
        .def("__repr__", [](const gpu_native::GPUInfo& info) {
            size_t vram_mb = info.dedicated_video_memory / (1024 * 1024);
            std::string type = info.is_discrete ? "dGPU" : 
                              (info.is_integrated ? "iGPU" : "Software");
            return "<GPUInfo '" + std::string(info.name.begin(), info.name.end()) + 
                   "' (" + type + ", " + std::to_string(vram_mb) + "MB)>";
        });

    // Bind GPUEnumerator class
    py::class_<gpu_native::GPUEnumerator>(m, "GPUEnumerator", R"docstring(
GPU Enumerator class for detecting and configuring GPUs.
    
Example:
    >>> enumerator = GPUEnumerator()
    >>> gpus = enumerator.enumerate()
    >>> enumerator.set_gpu_preference(r"C:\path\to\app.exe")
)docstring")
        .def(py::init<>(), "Create a new GPU enumerator")
        .def("enumerate", &gpu_native::GPUEnumerator::enumerate,
             "Enumerate all GPU adapters, sorted by preference (dGPU first)")
        .def("set_gpu_preference", &gpu_native::GPUEnumerator::set_gpu_preference,
             py::arg("exe_path") = L"",
             "Set Windows GPU preference to High Performance for the given executable")
        .def("get_preferred_gpu", &gpu_native::GPUEnumerator::get_preferred_gpu,
             "Get the preferred GPU for video decoding")
        .def("detect_vendor", &gpu_native::GPUEnumerator::detect_vendor,
             "Detect the primary GPU vendor ('nvidia', 'amd', 'intel', or 'unknown')")
        .def("init_dgpu", &gpu_native::GPUEnumerator::init_dgpu,
             py::arg("exe_path") = L"",
             "Initialize discrete GPU for video playback");

    // Convenience module-level functions
    m.def("enumerate_adapters", []() {
        gpu_native::GPUEnumerator enumerator;
        return enumerator.enumerate();
    }, R"docstring(
Enumerate all GPU adapters in the system.
    
Returns:
    list[GPUInfo]: List of GPU adapters sorted by preference
                   (dGPU with most VRAM first, then iGPU, then software)
    
Example:
    >>> from gpu_native import enumerate_adapters
    >>> for gpu in enumerate_adapters():
    ...     print(f"{gpu.name}: {gpu.dedicated_video_memory // (1024*1024)}MB")
)docstring");

    m.def("set_gpu_preference", [](const std::wstring& exe_path) {
        gpu_native::GPUEnumerator enumerator;
        return enumerator.set_gpu_preference(exe_path);
    }, py::arg("exe_path") = L"", R"docstring(
Set Windows GPU preference to High Performance.
    
This is the most reliable method to force dGPU usage on Windows 10/11.
The preference is stored in registry and persists across runs.
    
Args:
    exe_path: Full path to executable. If empty, uses current process.
    
Returns:
    bool: True if successful, False otherwise
    
Note:
    Registry path: HKCU\Software\Microsoft\DirectX\UserGpuPreferences
    Value: GpuPreference=2 (2 = High Performance)
)docstring");

    m.def("get_preferred_gpu", []() -> std::pair<bool, gpu_native::GPUInfo> {
        gpu_native::GPUEnumerator enumerator;
        return enumerator.get_preferred_gpu();
    }, R"docstring(
Get the preferred GPU for video decoding.
    
Returns:
    tuple[bool, GPUInfo]: (found, gpu_info) where found is True if GPU detected
)docstring");

    m.def("detect_vendor", []() {
        gpu_native::GPUEnumerator enumerator;
        return enumerator.detect_vendor();
    }, R"docstring(
Detect the primary GPU vendor.
    
Returns:
    str: 'nvidia', 'amd', 'intel', or 'unknown'
)docstring");

    m.def("init_dgpu_for_video", [](const std::wstring& exe_path) -> std::pair<bool, bool> {
        gpu_native::GPUEnumerator enumerator;
        return enumerator.init_dgpu(exe_path);
    }, py::arg("exe_path") = L"", R"docstring(
Initialize discrete GPU for video playback.
    
Performs:
1. Registry GPU preference setting (persists across runs)
2. Environment variable setup (for current process)
3. GPU detection
    
Args:
    exe_path: Path to executable (empty for current process)
    
Returns:
    tuple[bool, bool]: (registry_success, has_dgpu)
)docstring");

    // Module version
    m.attr("__version__") = "1.0.0";
}
