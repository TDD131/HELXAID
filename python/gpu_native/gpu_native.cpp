/**
 * GPU Native Module - C++ Implementation
 * 
 * Uses DXGI for fast GPU enumeration and D3D11 for device creation.
 * Provides native Windows GPU detection with <1ms performance.
 * 
 * @file gpu_native.cpp
 * @author HELXAID
 * @version 1.0.0
 */

#include <windows.h>
#include <dxgi.h>
#include <d3d11.h>
#include <string>
#include <vector>
#include <algorithm>
#include <memory>
#include <stdexcept>

#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3d11.lib")

namespace gpu_native {

/**
 * GPU adapter information structure.
 * Mirrors the Python GPUInfo NamedTuple for seamless binding.
 */
struct GPUInfo {
    int index;
    std::wstring name;
    size_t dedicated_video_memory;
    size_t shared_system_memory;
    unsigned int vendor_id;
    unsigned int device_id;
    bool is_integrated;
    bool is_discrete;
    bool is_software;
};

/**
 * Vendor IDs for common GPU manufacturers.
 */
constexpr unsigned int VENDOR_NVIDIA = 0x10DE;
constexpr unsigned int VENDOR_AMD = 0x1002;
constexpr unsigned int VENDOR_INTEL = 0x8086;

/**
 * DXGI Adapter Flags.
 */
constexpr UINT DXGI_ADAPTER_FLAG_SOFTWARE = 2;

/**
 * RAII wrapper for DXGI Factory.
 * Ensures proper resource cleanup.
 */
class DXGIFactory {
public:
    DXGIFactory() : factory_(nullptr) {
        HRESULT hr = CreateDXGIFactory1(__uuidof(IDXGIFactory1), 
                                        reinterpret_cast<void**>(&factory_));
        if (FAILED(hr) || !factory_) {
            throw std::runtime_error("Failed to create DXGI Factory");
        }
    }
    
    ~DXGIFactory() {
        if (factory_) {
            factory_->Release();
            factory_ = nullptr;
        }
    }
    
    IDXGIFactory1* get() const { return factory_; }
    operator bool() const { return factory_ != nullptr; }
    
private:
    IDXGIFactory1* factory_;
};

/**
 * RAII wrapper for DXGI Adapter.
 */
class DXGIAdapter {
public:
    DXGIAdapter(IDXGIAdapter1* adapter) : adapter_(adapter) {}
    
    ~DXGIAdapter() {
        if (adapter_) {
            adapter_->Release();
            adapter_ = nullptr;
        }
    }
    
    IDXGIAdapter1* get() const { return adapter_; }
    operator bool() const { return adapter_ != nullptr; }
    
private:
    IDXGIAdapter1* adapter_;
};

/**
 * GPU Enumerator class.
 * 
 * Provides methods for:
 * - Enumerating all GPU adapters via DXGI
 * - Setting Windows GPU preference in registry
 * - Detecting GPU type (integrated/discrete/software)
 */
class GPUEnumerator {
public:
    /**
     * Enumerate all GPU adapters in the system.
     * 
     * Uses DXGI 1.1 (IDXGIFactory1) for reliable detection.
     * Automatically sorts results by preference:
     * 1. Discrete GPUs (by VRAM descending)
     * 2. Integrated GPUs
     * 3. Software adapters
     * 
     * @return Vector of GPUInfo structures
     */
    std::vector<GPUInfo> enumerate() {
        std::vector<GPUInfo> gpus;
        
        try {
            DXGIFactory factory;
            if (!factory) {
                return gpus;
            }
            
            UINT index = 0;
            IDXGIAdapter1* adapter = nullptr;
            
            while (factory.get()->EnumAdapters1(index, &adapter) != DXGI_ERROR_NOT_FOUND) {
                DXGI_ADAPTER_DESC1 desc;
                HRESULT hr = adapter->GetDesc1(&desc);
                
                if (SUCCEEDED(hr)) {
                    GPUInfo info = {};
                    info.index = static_cast<int>(index);
                    info.name = desc.Description;
                    info.dedicated_video_memory = desc.DedicatedVideoMemory;
                    info.shared_system_memory = desc.SharedSystemMemory;
                    info.vendor_id = desc.VendorId;
                    info.device_id = desc.DeviceId;
                    
                    // Determine GPU type based on dedicated memory
                    // iGPU typically has < 64MB dedicated VRAM
                    size_t dedicated_mb = desc.DedicatedVideoMemory / (1024 * 1024);
                    info.is_software = (desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) != 0;
                    info.is_integrated = !info.is_software && dedicated_mb < 64;
                    info.is_discrete = !info.is_software && dedicated_mb >= 64;
                    
                    gpus.push_back(info);
                }
                
                // Release this adapter (will be recreated if needed)
                adapter->Release();
                index++;
            }
        } catch (const std::exception& e) {
            // Return empty list on error
            return gpus;
        }
        
        // Sort: dGPU first (by VRAM descending), then iGPU, then software
        std::sort(gpus.begin(), gpus.end(), [](const GPUInfo& a, const GPUInfo& b) {
            // Primary: dGPU first
            if (a.is_discrete != b.is_discrete) {
                return a.is_discrete > b.is_discrete;
            }
            // Secondary: More VRAM = higher priority
            if (a.dedicated_video_memory != b.dedicated_video_memory) {
                return a.dedicated_video_memory > b.dedicated_video_memory;
            }
            // Tertiary: Software last
            return a.is_software < b.is_software;
        });
        
        return gpus;
    }
    
    /**
     * Set Windows Graphics Performance preference to High Performance.
     * 
     * This is the most reliable method to force dGPU usage on Windows 10/11.
     * The preference is stored in registry and persists across runs.
     * 
     * Registry path: HKCU\Software\Microsoft\DirectX\UserGpuPreferences
     * Value name: Full path to executable
     * Value data: "GpuPreference=2" (2 = High Performance)
     * 
     * @param exe_path Full path to executable (or empty for current process)
     * @return true if successful, false otherwise
     */
    bool set_gpu_preference(const std::wstring& exe_path) {
        // Use current executable if no path provided
        std::wstring path = exe_path;
        if (path.empty()) {
            // Get current module path
            wchar_t buffer[MAX_PATH];
            GetModuleFileNameW(nullptr, buffer, MAX_PATH);
            path = buffer;
        }
        
        const wchar_t* key_path = L"Software\\Microsoft\\DirectX\\UserGpuPreferences";
        const wchar_t* value_data = L"GpuPreference=2";
        
        // Open or create registry key
        HKEY key = nullptr;
        LSTATUS status = RegCreateKeyExW(
            HKEY_CURRENT_USER,
            key_path,
            0,
            nullptr,
            0,
            KEY_SET_VALUE | KEY_WRITE,
            nullptr,
            &key,
            nullptr
        );
        
        if (status != ERROR_SUCCESS || !key) {
            return false;
        }
        
        // Set the GPU preference value
        // GpuPreference values: 0=Unspecified, 1=Minimum Power, 2=High Performance
        status = RegSetValueExW(
            key,
            path.c_str(),
            0,
            REG_SZ,
            reinterpret_cast<const BYTE*>(value_data),
            static_cast<DWORD>((wcslen(value_data) + 1) * sizeof(wchar_t))
        );
        
        RegCloseKey(key);
        return status == ERROR_SUCCESS;
    }
    
    /**
     * Get the preferred GPU for video decoding.
     * 
     * Returns the first GPU from enumerate() which is already
     * sorted by preference (dGPU with most VRAM first).
     * 
     * @return Optional GPUInfo (empty if no GPUs found)
     */
    std::pair<bool, GPUInfo> get_preferred_gpu() {
        auto gpus = enumerate();
        if (gpus.empty()) {
            return {false, GPUInfo{}};
        }
        return {true, gpus[0]};
    }
    
    /**
     * Detect the primary GPU vendor.
     * 
     * @return Vendor name string: "nvidia", "amd", "intel", or "unknown"
     */
    std::string detect_vendor() {
        auto gpus = enumerate();
        if (gpus.empty()) {
            return "unknown";
        }
        
        switch (gpus[0].vendor_id) {
            case VENDOR_NVIDIA:
                return "nvidia";
            case VENDOR_AMD:
                return "amd";
            case VENDOR_INTEL:
                return "intel";
            default:
                return "unknown";
        }
    }
    
    /**
     * Initialize discrete GPU for video playback.
     * 
     * Performs:
     * 1. Registry GPU preference setting
     * 2. Environment variable setup (for current process)
     * 3. GPU detection
     * 
     * @param exe_path Path to executable (empty for current)
     * @return Pair: (success, has_dgpu)
     */
    std::pair<bool, bool> init_dgpu(const std::wstring& exe_path = L"") {
        // Step 1: Set registry preference
        bool registry_ok = set_gpu_preference(exe_path);
        
        // Step 2: Set environment variables (for current process)
        // These are hints that may or may not work depending on driver
        SetEnvironmentVariableW(L"NvOptimusEnablement", L"1");
        SetEnvironmentVariableW(L"AmdPowerXpressRequestHighPerformance", L"1");
        
        // Step 3: Detect GPUs
        auto gpus = enumerate();
        
        if (gpus.empty()) {
            return {registry_ok, false};
        }
        
        // Check if we have a dGPU
        for (const auto& gpu : gpus) {
            if (gpu.is_discrete) {
                return {registry_ok, true};
            }
        }
        
        return {registry_ok, false};
    }
};

} // namespace gpu_native
