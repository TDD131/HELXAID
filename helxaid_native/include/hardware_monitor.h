/**
 * Hardware Monitor
 *
 * Provides hardware monitoring and RAM cleaning functionality for Windows.
 * Uses Windows API for accurate hardware information and memory management.
 */

#pragma once

#include <cstdint>
#include <string>
#include <vector>


namespace helxaid {

/**
 * RAM Information structure
 */
struct RAMInfo {
  uint64_t totalBytes = 0;     // Total physical memory
  uint64_t usedBytes = 0;      // Used memory
  uint64_t availableBytes = 0; // Available memory
  double percentUsed = 0.0;    // Percentage used

  double totalGB() const { return totalBytes / (1024.0 * 1024.0 * 1024.0); }
  double usedGB() const { return usedBytes / (1024.0 * 1024.0 * 1024.0); }
  double availableGB() const {
    return availableBytes / (1024.0 * 1024.0 * 1024.0);
  }
};

/**
 * CPU Information structure
 */
struct CPUInfo {
  double usage = 0.0;        // CPU usage percentage
  double frequencyGHz = 0.0; // Current frequency in GHz
  int coreCount = 0;         // Number of cores
  int threadCount = 0;       // Number of threads
  std::string name;          // CPU name
};

/**
 * Disk Information structure
 */
struct DiskInfo {
  std::string drive;        // Drive letter (e.g., "C:\\")
  uint64_t totalBytes = 0;  // Total size
  uint64_t usedBytes = 0;   // Used size
  uint64_t freeBytes = 0;   // Free size
  double percentUsed = 0.0; // Percentage used

  double totalGB() const { return totalBytes / (1024.0 * 1024.0 * 1024.0); }
  double usedGB() const { return usedBytes / (1024.0 * 1024.0 * 1024.0); }
  double freeGB() const { return freeBytes / (1024.0 * 1024.0 * 1024.0); }
};

/**
 * RAM Clean Result structure
 */
struct RAMCleanResult {
  int processCount = 0;    // Number of processes cleaned
  uint64_t bytesFreed = 0; // Bytes freed
  bool success = false;    // Whether operation succeeded
  std::string error;       // Error message if failed

  double mbFreed() const { return bytesFreed / (1024.0 * 1024.0); }
  double gbFreed() const { return bytesFreed / (1024.0 * 1024.0 * 1024.0); }
};

/**
 * Temperature Information structure
 */
struct TempInfo {
  double cpuTemp = 0.0;   // CPU temperature in Celsius
  double gpuTemp = 0.0;   // GPU temperature in Celsius
  bool available = false; // Whether temps are available
};

/**
 * Process Priority Result structure
 */
struct PriorityResult {
  uint32_t pid = 0;           // Process ID
  int oldPriority = 0;        // Previous priority class
  int newPriority = 0;        // New priority class
  bool success = false;       // Whether operation succeeded
  std::string error;          // Error message if failed
};

/**
 * Windows Key Hook Result structure
 */
struct WinKeyResult {
  bool disabled = false;      // Whether Windows key is disabled
  bool success = false;       // Whether operation succeeded
  std::string error;          // Error message if failed
};

/**
 * Hardware Monitor class
 * Provides hardware information and RAM cleaning functionality.
 */
class HardwareMonitor {
public:
  HardwareMonitor();
  ~HardwareMonitor();

  // RAM operations
  RAMInfo getRAMInfo();
  RAMCleanResult cleanRAM();

  // CPU operations
  CPUInfo getCPUInfo();

  // Disk operations
  std::vector<DiskInfo> getDiskInfo();

  // Temperature (requires OpenHardwareMonitor or WMI)
  TempInfo getTemperatures();
  
  // Essential Optimizations
  PriorityResult setProcessPriority(const std::string& processName, int priority);
  PriorityResult restoreProcessPriority(uint32_t pid);
  WinKeyResult disableWindowsKey();
  WinKeyResult enableWindowsKey();
  bool isWindowsKeyDisabled() const;

private:
  // CPU usage calculation helpers
  uint64_t m_lastIdleTime = 0;
  uint64_t m_lastKernelTime = 0;
  uint64_t m_lastUserTime = 0;
  bool m_firstCpuRead = true;
  
  // Windows key hook state
  bool m_winKeyDisabled = false;
  
  // Saved process priorities for restoration
  std::vector<std::pair<uint32_t, int>> m_savedPriorities;
};

} // namespace helxaid
