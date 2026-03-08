/**
 * Boost Engine Header
 *
 * Native C++ implementation for the HELXAID boost system.
 * Handles service management, process termination, and scheduled task
 * orchestration using direct Win32 APIs for maximum performance
 * and reliability.
 */

#pragma once

#include <string>
#include <vector>
#include <map>
#include <functional>

namespace helxaid {

// Result of a single service stop operation
struct ServiceStopResult {
    std::string name;        // Service internal name
    std::string displayName; // Human-readable display name
    std::string category;    // "basic", "advanced", or "essential"
    bool success = false;
    std::string status;      // "OK", "ALREADY_STOPPED", "FAIL", "TIMEOUT"
};

// Result of a process kill operation
struct ProcessKillResult {
    std::string name;       // Process name
    int totalPids = 0;      // Number of PIDs found
    int killedPids = 0;     // Number of PIDs successfully terminated
    bool success = false;
};

// Aggregated result of a complete boost cycle
struct BoostResult {
    std::vector<ServiceStopResult> serviceResults;
    std::vector<ProcessKillResult> processResults;
    int servicesStoppedCount = 0;
    int servicesFailedCount = 0;
    int processesClosedCount = 0;
    int processesFailedCount = 0;
    bool success = false;
    std::string error;
};

// Service status info for UI display
struct ServiceStatus {
    std::string name;       // Service internal name
    std::string status;     // "Running", "Stopped", "Unknown"
    bool isRunning = false;
};

// Service entry for batch operations
struct ServiceEntry {
    std::string name;        // Windows service name (e.g. "SysMain")
    std::string displayName; // Human-readable name
    std::string category;    // "basic", "advanced", "essential"
};

/**
 * BoostEngine - Native game boost orchestrator.
 *
 * Manages the scheduled task lifecycle for elevated service operations
 * and provides process termination via Win32 API. The scheduled task
 * approach allows stopping services without per-boost UAC prompts:
 *   1. First use: create task with admin (single UAC prompt)
 *   2. Subsequent uses: trigger task silently via schtasks /run
 *
 * Service status queries use OpenSCManager (no admin needed).
 * Process termination uses OpenProcess + TerminateProcess.
 */
class BoostEngine {
public:
    BoostEngine();
    ~BoostEngine();

    // ---- Scheduled Task Management ----

    // Check if task exists with correct version, create if needed.
    // Returns true if task is ready. May trigger UAC on first call.
    bool ensureTaskExists(const std::string& taskName,
                         const std::string& scriptPath);

    // Check if task already exists (no creation attempt)
    bool isTaskReady(const std::string& taskName);

    // ---- Service Operations ----

    // Stop multiple services via scheduled task trigger.
    // Writes input file, triggers task, polls for results.
    // Returns per-service results.
    std::vector<ServiceStopResult> stopServices(
        const std::vector<ServiceEntry>& services,
        const std::string& taskName);

    // Query current status of services (no admin needed, uses SC Manager).
    std::vector<ServiceStatus> queryServiceStatuses(
        const std::vector<std::string>& serviceNames);

    // ---- Process Operations ----

    // Terminate processes by name. Returns per-process results.
    std::vector<ProcessKillResult> killProcesses(
        const std::vector<std::string>& processNames);

    // ---- PowerShell Script ----

    // Write/update the PS1 script that the scheduled task executes.
    // The script reads service names from inputPath, stops them,
    // writes results to logPath.
    bool writeBoostScript(const std::string& scriptPath,
                         const std::string& inputPath,
                         const std::string& logPath);

    // ---- Task Version ----
    static const char* TASK_VERSION;

private:
    bool taskVerified_ = false;

    // Create scheduled task via XML + schtasks with elevation
    bool createTaskWithXml(const std::string& taskName,
                          const std::string& scriptPath);

    // Delete existing scheduled task
    bool deleteTask(const std::string& taskName);

    // Run a process hidden (CREATE_NO_WINDOW) and capture output
    int runHidden(const std::string& command,
                 std::string& output, int timeoutMs = 10000);

    // Run schtasks with elevation via ShellExecuteW runas
    bool runElevated(const std::string& args);
};

} // namespace helxaid
