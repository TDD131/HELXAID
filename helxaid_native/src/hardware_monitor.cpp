/**
 * Hardware Monitor Implementation
 *
 * Uses Windows API for RAM cleaning and hardware information.
 */

// NOMINMAX prevents min/max macros from Windows.h
#ifndef NOMINMAX
#define NOMINMAX
#endif

// Windows headers - ORDER MATTERS! Windows.h must come first
#include <Windows.h>
#include <TlHelp32.h>
#include <intrin.h>


#include <algorithm>

#include "hardware_monitor.h"

#pragma comment(lib, "pdh.lib")
// Note: psapi.lib removed - using SetProcessWorkingSetSize instead of
// EmptyWorkingSet

namespace helxaid {

HardwareMonitor::HardwareMonitor() {}

HardwareMonitor::~HardwareMonitor() {}

RAMInfo HardwareMonitor::getRAMInfo() {
  RAMInfo info;

  MEMORYSTATUSEX memStatus;
  memStatus.dwLength = sizeof(memStatus);

  if (GlobalMemoryStatusEx(&memStatus)) {
    info.totalBytes = memStatus.ullTotalPhys;
    info.availableBytes = memStatus.ullAvailPhys;
    info.usedBytes = info.totalBytes - info.availableBytes;
    info.percentUsed = static_cast<double>(info.usedBytes) /
                       static_cast<double>(info.totalBytes) * 100.0;
  }

  return info;
}

RAMCleanResult HardwareMonitor::cleanRAM() {
  RAMCleanResult result;
  result.success = false;

  // Get RAM usage before cleaning
  MEMORYSTATUSEX memBefore;
  memBefore.dwLength = sizeof(memBefore);
  GlobalMemoryStatusEx(&memBefore);
  uint64_t usedBefore = memBefore.ullTotalPhys - memBefore.ullAvailPhys;

  // Enable SeDebugPrivilege for accessing more processes
  HANDLE hToken;
  if (OpenProcessToken(GetCurrentProcess(),
                       TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &hToken)) {
    TOKEN_PRIVILEGES tkp;
    if (LookupPrivilegeValue(NULL, SE_DEBUG_NAME, &tkp.Privileges[0].Luid)) {
      tkp.PrivilegeCount = 1;
      tkp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
      AdjustTokenPrivileges(hToken, FALSE, &tkp, 0, NULL, NULL);
    }
    CloseHandle(hToken);
  }

  // Enumerate all processes and clean their working sets
  HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (hSnapshot == INVALID_HANDLE_VALUE) {
    result.error = "Failed to create process snapshot";
    return result;
  }

  PROCESSENTRY32W pe32;
  pe32.dwSize = sizeof(pe32);

  int processCount = 0;

  if (Process32FirstW(hSnapshot, &pe32)) {
    do {
      // Skip system idle process
      if (pe32.th32ProcessID == 0)
        continue;

      // Try to open process with minimum required access
      HANDLE hProcess =
          OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, FALSE,
                      pe32.th32ProcessID);

      if (hProcess != NULL) {
        // Empty the working set using SetProcessWorkingSetSize (no Psapi
        // needed) Passing -1, -1 trims the working set to minimum required
        if (SetProcessWorkingSetSize(hProcess, (SIZE_T)-1, (SIZE_T)-1)) {
          processCount++;
        }
        CloseHandle(hProcess);
      }
    } while (Process32NextW(hSnapshot, &pe32));
  }

  CloseHandle(hSnapshot);

  // Get RAM usage after cleaning
  MEMORYSTATUSEX memAfter;
  memAfter.dwLength = sizeof(memAfter);
  GlobalMemoryStatusEx(&memAfter);
  uint64_t usedAfter = memAfter.ullTotalPhys - memAfter.ullAvailPhys;

  // Calculate bytes freed
  if (usedBefore > usedAfter) {
    result.bytesFreed = usedBefore - usedAfter;
  } else {
    result.bytesFreed = 0;
  }

  result.processCount = processCount;
  result.success = true;

  return result;
}

CPUInfo HardwareMonitor::getCPUInfo() {
  CPUInfo info;

  // Get CPU name
  int cpuInfo[4] = {0};
  char cpuBrand[0x40] = {0};

  __cpuid(cpuInfo, 0x80000002);
  memcpy(cpuBrand, cpuInfo, sizeof(cpuInfo));
  __cpuid(cpuInfo, 0x80000003);
  memcpy(cpuBrand + 16, cpuInfo, sizeof(cpuInfo));
  __cpuid(cpuInfo, 0x80000004);
  memcpy(cpuBrand + 32, cpuInfo, sizeof(cpuInfo));

  info.name = cpuBrand;

  // Get core/thread count
  SYSTEM_INFO sysInfo;
  GetSystemInfo(&sysInfo);
  info.coreCount = sysInfo.dwNumberOfProcessors;
  info.threadCount = sysInfo.dwNumberOfProcessors;

  // Get CPU usage
  FILETIME idleTime, kernelTime, userTime;
  if (GetSystemTimes(&idleTime, &kernelTime, &userTime)) {
    uint64_t idle = (static_cast<uint64_t>(idleTime.dwHighDateTime) << 32) |
                    idleTime.dwLowDateTime;
    uint64_t kernel = (static_cast<uint64_t>(kernelTime.dwHighDateTime) << 32) |
                      kernelTime.dwLowDateTime;
    uint64_t user = (static_cast<uint64_t>(userTime.dwHighDateTime) << 32) |
                    userTime.dwLowDateTime;

    if (!m_firstCpuRead) {
      uint64_t idleDiff = idle - m_lastIdleTime;
      uint64_t kernelDiff = kernel - m_lastKernelTime;
      uint64_t userDiff = user - m_lastUserTime;
      uint64_t totalSystem = kernelDiff + userDiff;

      if (totalSystem > 0) {
        info.usage = (1.0 - static_cast<double>(idleDiff) /
                                static_cast<double>(totalSystem)) *
                     100.0;
        if (info.usage < 0)
          info.usage = 0;
        if (info.usage > 100)
          info.usage = 100;
      }
    }

    m_lastIdleTime = idle;
    m_lastKernelTime = kernel;
    m_lastUserTime = user;
    m_firstCpuRead = false;
  }

  // Get CPU frequency (simplified - shows base frequency)
  HKEY hKey;
  if (RegOpenKeyExW(HKEY_LOCAL_MACHINE,
                    L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0", 0,
                    KEY_READ, &hKey) == ERROR_SUCCESS) {
    DWORD mhz = 0;
    DWORD size = sizeof(mhz);
    if (RegQueryValueExW(hKey, L"~MHz", NULL, NULL,
                         reinterpret_cast<LPBYTE>(&mhz),
                         &size) == ERROR_SUCCESS) {
      info.frequencyGHz = mhz / 1000.0;
    }
    RegCloseKey(hKey);
  }

  return info;
}

std::vector<DiskInfo> HardwareMonitor::getDiskInfo() {
  std::vector<DiskInfo> disks;

  DWORD drives = GetLogicalDrives();

  for (char letter = 'A'; letter <= 'Z'; ++letter) {
    if (drives & (1 << (letter - 'A'))) {
      wchar_t root[4] = {static_cast<wchar_t>(letter), L':', L'\\', L'\0'};

      UINT driveType = GetDriveTypeW(root);
      // Only include fixed drives (not removable, CD-ROM, etc.)
      if (driveType == DRIVE_FIXED) {
        ULARGE_INTEGER freeBytesAvailable, totalBytes, totalFreeBytes;

        if (GetDiskFreeSpaceExW(root, &freeBytesAvailable, &totalBytes,
                                &totalFreeBytes)) {
          DiskInfo info;
          info.drive = std::string(1, letter) + ":\\";
          info.totalBytes = totalBytes.QuadPart;
          info.freeBytes = totalFreeBytes.QuadPart;
          info.usedBytes = info.totalBytes - info.freeBytes;
          info.percentUsed = static_cast<double>(info.usedBytes) /
                             static_cast<double>(info.totalBytes) * 100.0;
          disks.push_back(info);
        }
      }
    }
  }

  return disks;
}

TempInfo HardwareMonitor::getTemperatures() {
  TempInfo info;
  info.available = false;

  // Temperature monitoring requires either:
  // 1. WMI queries (complex)
  // 2. OpenHardwareMonitor/LibreHardwareMonitor integration
  // 3. Direct hardware access (very complex)

  // For now, we return unavailable - can be expanded later
  // with LibreHardwareMonitorLib integration

  return info;
}

// ===== Essential Optimizations Implementation =====

// Global hook handle for Windows key blocking
static HHOOK g_winKeyHook = NULL;

// Low-level keyboard hook procedure
static LRESULT CALLBACK LowLevelKeyboardProc(int nCode, WPARAM wParam,
                                             LPARAM lParam) {
  if (nCode >= 0) {
    KBDLLHOOKSTRUCT *pKbd = reinterpret_cast<KBDLLHOOKSTRUCT *>(lParam);
    // Block left and right Windows keys
    if (pKbd->vkCode == VK_LWIN || pKbd->vkCode == VK_RWIN) {
      return 1; // Block the key
    }
  }
  return CallNextHookEx(g_winKeyHook, nCode, wParam, lParam);
}

PriorityResult
HardwareMonitor::setProcessPriority(const std::string &processName,
                                    int priority) {
  PriorityResult result;
  result.success = false;

  // Convert process name to wide string using Windows API
  int wideLen =
      MultiByteToWideChar(CP_UTF8, 0, processName.c_str(), -1, NULL, 0);
  std::wstring wProcessName(wideLen, L'\0');
  MultiByteToWideChar(CP_UTF8, 0, processName.c_str(), -1, &wProcessName[0],
                      wideLen);
  wProcessName.resize(wideLen - 1); // Remove null terminator

  // Convert to lowercase for case-insensitive comparison
  for (auto &c : wProcessName) {
    c = towlower(c);
  }

  // Enumerate processes
  HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (hSnapshot == INVALID_HANDLE_VALUE) {
    result.error = "Failed to create process snapshot";
    return result;
  }

  PROCESSENTRY32W pe32;
  pe32.dwSize = sizeof(pe32);

  if (Process32FirstW(hSnapshot, &pe32)) {
    do {
      // Convert process name to lowercase
      std::wstring currentName = pe32.szExeFile;
      for (auto &c : currentName) {
        c = towlower(c);
      }

      if (currentName == wProcessName) {
        // Found the process
        HANDLE hProcess =
            OpenProcess(PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION,
                        FALSE, pe32.th32ProcessID);

        if (hProcess != NULL) {
          // Get current priority
          DWORD oldPriority = GetPriorityClass(hProcess);
          result.oldPriority = static_cast<int>(oldPriority);
          result.pid = pe32.th32ProcessID;

          // Save for restoration
          m_savedPriorities.push_back({pe32.th32ProcessID, result.oldPriority});

          // Set new priority
          DWORD newPriorityClass;
          switch (priority) {
          case 0:
            newPriorityClass = IDLE_PRIORITY_CLASS;
            break;
          case 1:
            newPriorityClass = BELOW_NORMAL_PRIORITY_CLASS;
            break;
          case 2:
            newPriorityClass = NORMAL_PRIORITY_CLASS;
            break;
          case 3:
            newPriorityClass = ABOVE_NORMAL_PRIORITY_CLASS;
            break;
          case 4:
            newPriorityClass = HIGH_PRIORITY_CLASS;
            break;
          case 5:
            newPriorityClass = REALTIME_PRIORITY_CLASS;
            break;
          default:
            newPriorityClass = HIGH_PRIORITY_CLASS;
            break;
          }

          if (SetPriorityClass(hProcess, newPriorityClass)) {
            result.newPriority = static_cast<int>(newPriorityClass);
            result.success = true;
          } else {
            result.error = "Failed to set priority";
          }

          CloseHandle(hProcess);
        } else {
          result.error = "Cannot open process";
        }
        break;
      }
    } while (Process32NextW(hSnapshot, &pe32));
  }

  CloseHandle(hSnapshot);

  if (!result.success && result.error.empty()) {
    result.error = "Process not found: " + processName;
  }

  return result;
}

PriorityResult HardwareMonitor::restoreProcessPriority(uint32_t pid) {
  PriorityResult result;
  result.success = false;
  result.pid = pid;

  // Find saved priority
  int savedPriority = -1;
  auto it = std::find_if(m_savedPriorities.begin(), m_savedPriorities.end(),
                         [pid](const auto &p) { return p.first == pid; });

  if (it != m_savedPriorities.end()) {
    savedPriority = it->second;
    m_savedPriorities.erase(it);
  } else {
    result.error = "No saved priority for PID";
    return result;
  }

  HANDLE hProcess = OpenProcess(PROCESS_SET_INFORMATION, FALSE, pid);
  if (hProcess != NULL) {
    if (SetPriorityClass(hProcess, static_cast<DWORD>(savedPriority))) {
      result.oldPriority = 0;
      result.newPriority = savedPriority;
      result.success = true;
    } else {
      result.error = "Failed to restore priority";
    }
    CloseHandle(hProcess);
  } else {
    result.error = "Cannot open process";
  }

  return result;
}

WinKeyResult HardwareMonitor::disableWindowsKey() {
  WinKeyResult result;

  if (m_winKeyDisabled) {
    result.disabled = true;
    result.success = true;
    result.error = "Already disabled";
    return result;
  }

  // Install low-level keyboard hook
  g_winKeyHook = SetWindowsHookExW(WH_KEYBOARD_LL, LowLevelKeyboardProc,
                                   GetModuleHandleW(NULL), 0);

  if (g_winKeyHook != NULL) {
    m_winKeyDisabled = true;
    result.disabled = true;
    result.success = true;
  } else {
    result.error = "Failed to install keyboard hook";
    result.success = false;
  }

  return result;
}

WinKeyResult HardwareMonitor::enableWindowsKey() {
  WinKeyResult result;

  if (!m_winKeyDisabled) {
    result.disabled = false;
    result.success = true;
    result.error = "Already enabled";
    return result;
  }

  if (g_winKeyHook != NULL) {
    UnhookWindowsHookEx(g_winKeyHook);
    g_winKeyHook = NULL;
  }

  m_winKeyDisabled = false;
  result.disabled = false;
  result.success = true;

  return result;
}

bool HardwareMonitor::isWindowsKeyDisabled() const { return m_winKeyDisabled; }

} // namespace helxaid
