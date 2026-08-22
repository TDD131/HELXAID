/*
 * Hardware Utilities - C++ Backend for Hardware Panel
 * 
 * Provides system information gathering for:
 * - RAM info and cleaning
 * - CPU usage and frequency
 * - Disk info
 * - Network stats
 * - Temperature readings
 */

#define WINVER 0x0600
#define _WIN32_WINNT 0x0600
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <psapi.h>
#include <pdh.h>
#include <pdhmsg.h>
#include <iphlpapi.h>
#include <string>
#include <vector>

#pragma comment(lib, "psapi.lib")
#pragma comment(lib, "pdh.lib")
#pragma comment(lib, "iphlpapi.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "user32.lib")

// ============================================
// RAM FUNCTIONS
// ============================================

static PyObject* get_ram_info(PyObject* self, PyObject* args) {
    MEMORYSTATUSEX memInfo;
    memInfo.dwLength = sizeof(MEMORYSTATUSEX);
    
    if (!GlobalMemoryStatusEx(&memInfo)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to get memory status");
        return NULL;
    }
    
    double total_gb = (double)memInfo.ullTotalPhys / (1024.0 * 1024.0 * 1024.0);
    double used_gb = (double)(memInfo.ullTotalPhys - memInfo.ullAvailPhys) / (1024.0 * 1024.0 * 1024.0);
    double free_gb = (double)memInfo.ullAvailPhys / (1024.0 * 1024.0 * 1024.0);
    double percent = (double)memInfo.dwMemoryLoad;
    
    return Py_BuildValue("{s:d,s:d,s:d,s:d}",
        "total", total_gb,
        "used", used_gb,
        "free", free_gb,
        "percent", percent
    );
}

static PyObject* clean_ram(PyObject* self, PyObject* args) {
    // Empty working sets of all processes
    DWORD processes[1024], bytesNeeded, processCount;
    int cleanedCount = 0;
    SIZE_T totalFreed = 0;
    
    if (!EnumProcesses(processes, sizeof(processes), &bytesNeeded)) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to enumerate processes");
        return NULL;
    }
    
    processCount = bytesNeeded / sizeof(DWORD);
    
    for (DWORD i = 0; i < processCount; i++) {
        if (processes[i] != 0) {
            HANDLE hProcess = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, FALSE, processes[i]);
            if (hProcess != NULL) {
                PROCESS_MEMORY_COUNTERS pmc;
                if (GetProcessMemoryInfo(hProcess, &pmc, sizeof(pmc))) {
                    SIZE_T beforeWS = pmc.WorkingSetSize;
                    if (EmptyWorkingSet(hProcess)) {
                        cleanedCount++;
                        // Estimate freed memory (not exact)
                        if (GetProcessMemoryInfo(hProcess, &pmc, sizeof(pmc))) {
                            totalFreed += (beforeWS - pmc.WorkingSetSize);
                        }
                    }
                }
                CloseHandle(hProcess);
            }
        }
    }
    
    double freed_mb = (double)totalFreed / (1024.0 * 1024.0);
    
    return Py_BuildValue("{s:i,s:d}",
        "processes_cleaned", cleanedCount,
        "memory_freed_mb", freed_mb
    );
}

// ============================================
// CPU FUNCTIONS
// ============================================

static PDH_HQUERY cpuQuery = NULL;
static PDH_HCOUNTER cpuTotal = NULL;
static bool cpuInitialized = false;

static PyObject* init_cpu_counter(PyObject* self, PyObject* args) {
    if (!cpuInitialized) {
        PdhOpenQuery(NULL, 0, &cpuQuery);
        PdhAddEnglishCounterW(cpuQuery, L"\\Processor(_Total)\\% Processor Time", 0, &cpuTotal);
        PdhCollectQueryData(cpuQuery);
        cpuInitialized = true;
    }
    Py_RETURN_NONE;
}

static PyObject* get_cpu_usage(PyObject* self, PyObject* args) {
    if (!cpuInitialized) {
        init_cpu_counter(self, args);
        // Need two samples for accurate reading
        Sleep(100);
    }
    
    PDH_FMT_COUNTERVALUE counterVal;
    PdhCollectQueryData(cpuQuery);
    PdhGetFormattedCounterValue(cpuTotal, PDH_FMT_DOUBLE, NULL, &counterVal);
    
    return PyFloat_FromDouble(counterVal.doubleValue);
}

static PyObject* get_cpu_freq(PyObject* self, PyObject* args) {
    SYSTEM_INFO sysInfo;
    GetSystemInfo(&sysInfo);
    
    // Query processor frequency from registry
    HKEY hKey;
    DWORD mhz = 0;
    DWORD size = sizeof(DWORD);
    
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, 
        L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0", 
        0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        RegQueryValueExW(hKey, L"~MHz", NULL, NULL, (LPBYTE)&mhz, &size);
        RegCloseKey(hKey);
    }
    
    double freq_ghz = (double)mhz / 1000.0;
    
    return Py_BuildValue("{s:d,s:i}",
        "freq_ghz", freq_ghz,
        "cores", (int)sysInfo.dwNumberOfProcessors
    );
}

// ============================================
// DISK FUNCTIONS
// ============================================

static PyObject* get_disk_info(PyObject* self, PyObject* args) {
    PyObject* diskList = PyList_New(0);
    
    DWORD drives = GetLogicalDrives();
    char drivePath[4] = "A:\\";
    
    for (int i = 0; i < 26; i++) {
        if (drives & (1 << i)) {
            drivePath[0] = 'A' + i;
            
            UINT driveType = GetDriveTypeA(drivePath);
            if (driveType == DRIVE_FIXED || driveType == DRIVE_REMOVABLE) {
                ULARGE_INTEGER freeSpace, totalSpace, totalFree;
                
                if (GetDiskFreeSpaceExA(drivePath, &freeSpace, &totalSpace, &totalFree)) {
                    double total_gb = (double)totalSpace.QuadPart / (1024.0 * 1024.0 * 1024.0);
                    double free_gb = (double)freeSpace.QuadPart / (1024.0 * 1024.0 * 1024.0);
                    double used_gb = total_gb - free_gb;
                    double percent = (used_gb / total_gb) * 100.0;
                    
                    PyObject* diskInfo = Py_BuildValue("{s:s,s:d,s:d,s:d,s:d}",
                        "drive", drivePath,
                        "total", total_gb,
                        "used", used_gb,
                        "free", free_gb,
                        "percent", percent
                    );
                    PyList_Append(diskList, diskInfo);
                    Py_DECREF(diskInfo);
                }
            }
        }
    }
    
    return diskList;
}

// ============================================
// NETWORK FUNCTIONS
// ============================================

static ULONG64 lastBytesIn = 0;
static ULONG64 lastBytesOut = 0;
static DWORD lastNetworkTick = 0;

static PyObject* get_network_stats(PyObject* self, PyObject* args) {
    MIB_IF_TABLE2* ifTable = NULL;
    
    if (GetIfTable2(&ifTable) != NO_ERROR) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to get network stats");
        return NULL;
    }
    
    ULONG64 totalBytesIn = 0;
    ULONG64 totalBytesOut = 0;
    
    for (ULONG i = 0; i < ifTable->NumEntries; i++) {
        MIB_IF_ROW2* row = &ifTable->Table[i];
        if (row->OperStatus == IfOperStatusUp && row->Type != IF_TYPE_SOFTWARE_LOOPBACK) {
            totalBytesIn += row->InOctets;
            totalBytesOut += row->OutOctets;
        }
    }
    
    FreeMibTable(ifTable);
    
    DWORD currentTick = GetTickCount();
    double elapsed = (currentTick - lastNetworkTick) / 1000.0;
    
    double downloadSpeed = 0;
    double uploadSpeed = 0;
    
    if (lastNetworkTick > 0 && elapsed > 0) {
        downloadSpeed = ((totalBytesIn - lastBytesIn) / elapsed) / (1024.0 * 1024.0);  // MB/s
        uploadSpeed = ((totalBytesOut - lastBytesOut) / elapsed) / (1024.0 * 1024.0);  // MB/s
    }
    
    lastBytesIn = totalBytesIn;
    lastBytesOut = totalBytesOut;
    lastNetworkTick = currentTick;
    
    return Py_BuildValue("{s:d,s:d,s:K,s:K}",
        "download_mbps", downloadSpeed * 8,  // Convert to Mbps
        "upload_mbps", uploadSpeed * 8,
        "total_received_bytes", totalBytesIn,
        "total_sent_bytes", totalBytesOut
    );
}

// ============================================
// TEMPERATURE FUNCTIONS (WMI-based)
// ============================================

static PyObject* get_temperatures(PyObject* self, PyObject* args) {
    // Note: Getting temperatures requires WMI or specific hardware APIs
    // This is a placeholder that returns dummy data
    // For real temps, integrate with OpenHardwareMonitor/LibreHardwareMonitor DLL
    
    return Py_BuildValue("{s:d,s:d,s:s}",
        "cpu_temp", 0.0,
        "gpu_temp", 0.0,
        "status", "requires_external_lib"
    );
}

// ============================================
// WINDOW MANAGEMENT FUNCTIONS (Native C++ / Win32)
// ============================================

static PyObject* center_window_on_primary_display(PyObject* self, PyObject* args) {
    unsigned long long hwnd_val = 0;
    int min_w = 1380;
    int min_h = 790;
    
    if (!PyArg_ParseTuple(args, "K|ii", &hwnd_val, &min_w, &min_h)) {
        return NULL;
    }
    
    HWND hwnd = (HWND)(uintptr_t)hwnd_val;
    if (!hwnd || !IsWindow(hwnd)) {
        Py_RETURN_FALSE;
    }
    
    // Get primary display work area (excludes Windows Taskbar)
    RECT workArea = {0};
    if (!SystemParametersInfoW(SPI_GETWORKAREA, 0, &workArea, 0)) {
        workArea.left = 0;
        workArea.top = 0;
        workArea.right = GetSystemMetrics(SM_CXSCREEN);
        workArea.bottom = GetSystemMetrics(SM_CYSCREEN);
    }
    
    int screenW = workArea.right - workArea.left;
    int screenH = workArea.bottom - workArea.top;
    
    // Get current window bounds
    RECT winRect = {0};
    GetWindowRect(hwnd, &winRect);
    int winW = winRect.right - winRect.left;
    int winH = winRect.bottom - winRect.top;
    
    if (winW < min_w) winW = min_w;
    if (winH < min_h) winH = min_h;
    if (winW > screenW) winW = screenW;
    if (winH > screenH) winH = screenH;
    
    // Calculate centered coordinates on primary display
    int posX = workArea.left + (screenW - winW) / 2;
    int posY = workArea.top + (screenH - winH) / 2;
    
    // Atomically move and resize window using Win32 API
    BOOL success = SetWindowPos(
        hwnd, 
        NULL, 
        posX, 
        posY, 
        winW, 
        winH, 
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
    );
    
    return Py_BuildValue("{s:O,s:i,s:i,s:i,s:i}",
        "success", success ? Py_True : Py_False,
        "x", posX,
        "y", posY,
        "width", winW,
        "height", winH
    );
}

// ============================================
// MODULE DEFINITION
// ============================================

static PyMethodDef HardwareMethods[] = {
    {"get_ram_info", get_ram_info, METH_NOARGS, "Get RAM usage information"},
    {"clean_ram", clean_ram, METH_NOARGS, "Clean RAM by emptying working sets"},
    {"init_cpu_counter", init_cpu_counter, METH_NOARGS, "Initialize CPU counter"},
    {"get_cpu_usage", get_cpu_usage, METH_NOARGS, "Get current CPU usage percentage"},
    {"get_cpu_freq", get_cpu_freq, METH_NOARGS, "Get CPU frequency and core count"},
    {"get_disk_info", get_disk_info, METH_NOARGS, "Get disk usage for all drives"},
    {"get_network_stats", get_network_stats, METH_NOARGS, "Get network upload/download stats"},
    {"get_temperatures", get_temperatures, METH_NOARGS, "Get CPU/GPU temperatures"},
    {"center_window_on_primary_display", center_window_on_primary_display, METH_VARARGS, "Center a window HWND on the primary display work area"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef hardwaremodule = {
    PyModuleDef_HEAD_INIT,
    "hardware_utils",
    "Hardware utilities for system monitoring",
    -1,
    HardwareMethods
};

PyMODINIT_FUNC PyInit_hardware_utils(void) {
    return PyModule_Create(&hardwaremodule);
}
