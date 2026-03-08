/**
 * Boost Engine Implementation
 *
 * Native C++ boost system for HELXAID Game Launcher.
 * Uses Win32 APIs directly for service management and process control.
 *
 * Architecture:
 *   - Service stopping uses a Windows Scheduled Task with elevated privileges.
 *     The task is created once (single UAC prompt via ShellExecuteW runas),
 *     then triggered silently on every boost via `schtasks /run`.
 *   - Service status queries use the Service Control Manager API (no admin).
 *   - Process termination uses ToolHelp32 + OpenProcess + TerminateProcess.
 *
 * IPC between this module and the scheduled task:
 *   - Input file:  %TEMP%\helxaid_boost_input.txt  (category|serviceName per
 * line)
 *   - Output file: %TEMP%\helxaid_boost_svc.log    (category|serviceName|STATUS
 * per line)
 *   - PS1 script:  %APPDATA%\HELXAID\boost_services.ps1
 */

// NOMINMAX prevents min/max macros from Windows.h
#ifndef NOMINMAX
#define NOMINMAX
#endif

// MUST INCLUDE STANDARD C++ HEADERS FIRST!
#include "boost_engine.h"

// clang-format off
#ifdef _WIN32
#include <Windows.h>
#include <TlHelp32.h>
#include <shellapi.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <shobjidl.h>
#include <winsvc.h>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "shell32.lib")
#endif
// clang-format on

#include <algorithm>
#include <chrono>
#include <fstream>
#include <sstream>
#include <thread>

namespace helxaid {

// Static version tag — bump to force recreation of stale scheduled tasks.
// Embedded in the task description XML so we can detect old versions.
const char *BoostEngine::TASK_VERSION = "v4";

BoostEngine::BoostEngine() = default;
BoostEngine::~BoostEngine() = default;

// ============================================================
// Internal Helpers
// ============================================================

// Run a command hidden (no console window) and capture stdout.
// Returns the process exit code, or -1 on failure.
int BoostEngine::runHidden(const std::string &command, std::string &output,
                           int timeoutMs) {
#ifdef _WIN32
  SECURITY_ATTRIBUTES sa{};
  sa.nLength = sizeof(sa);
  sa.bInheritHandle = TRUE;

  HANDLE hReadPipe = nullptr, hWritePipe = nullptr;
  if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0))
    return -1;
  SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);

  STARTUPINFOA si{};
  si.cb = sizeof(si);
  si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
  si.hStdOutput = hWritePipe;
  si.hStdError = hWritePipe;
  si.wShowWindow = SW_HIDE;

  PROCESS_INFORMATION pi{};
  std::string cmdLine = command;

  BOOL ok = CreateProcessA(nullptr, &cmdLine[0], nullptr, nullptr, TRUE,
                           CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
  CloseHandle(hWritePipe);

  if (!ok) {
    CloseHandle(hReadPipe);
    return -1;
  }

  // Read stdout
  output.clear();
  char buf[4096];
  DWORD bytesRead;
  while (ReadFile(hReadPipe, buf, sizeof(buf) - 1, &bytesRead, nullptr) &&
         bytesRead > 0) {
    buf[bytesRead] = '\0';
    output += buf;
  }
  CloseHandle(hReadPipe);

  // Wait for process with timeout
  WaitForSingleObject(pi.hProcess, static_cast<DWORD>(timeoutMs));
  DWORD exitCode = 0;
  GetExitCodeProcess(pi.hProcess, &exitCode);
  CloseHandle(pi.hProcess);
  CloseHandle(pi.hThread);

  return static_cast<int>(exitCode);
#else
  return -1;
#endif
}

// Run schtasks.exe with elevation via ShellExecuteW + "runas" verb.
// Returns true if ShellExecute reports success (ret > 32).
bool BoostEngine::runElevated(const std::string &args) {
#ifdef _WIN32
  // Convert to wide string for ShellExecuteW
  int wideLen = MultiByteToWideChar(CP_UTF8, 0, args.c_str(), -1, nullptr, 0);
  std::wstring wideArgs(wideLen, L'\0');
  MultiByteToWideChar(CP_UTF8, 0, args.c_str(), -1, &wideArgs[0], wideLen);

  // SW_HIDE = 0, completely hides the schtasks window
  HINSTANCE ret = ShellExecuteW(nullptr, L"runas", L"schtasks.exe",
                                wideArgs.c_str(), nullptr, SW_HIDE);
  return reinterpret_cast<intptr_t>(ret) > 32;
#else
  return false;
#endif
}

// ============================================================
// Scheduled Task Management
// ============================================================

bool BoostEngine::isTaskReady(const std::string &taskName) {
  std::string output;
  std::string cmd = "schtasks /query /tn \"" + taskName + "\" /fo LIST /v";
  int ret = runHidden(cmd, output);
  if (ret == 0 && output.find(TASK_VERSION) != std::string::npos) {
    return true;
  }
  return false;
}

bool BoostEngine::deleteTask(const std::string &taskName) {
  std::string output;
  std::string cmd = "schtasks /delete /tn \"" + taskName + "\" /f";
  return runHidden(cmd, output) == 0;
}

bool BoostEngine::createTaskWithXml(const std::string &taskName,
                                    const std::string &scriptPath) {
#ifdef _WIN32
  // Build Task Scheduler XML with Hidden=true to suppress console window.
  // RunLevel=HighestAvailable grants admin rights without per-use UAC.
  // The disabled TimeTrigger is required by schema but we only use /run.
  std::string escapedPath = scriptPath;
  // XML-escape special characters in the script path
  std::string result;
  for (char c : escapedPath) {
    switch (c) {
    case '&':
      result += "&amp;";
      break;
    case '<':
      result += "&lt;";
      break;
    case '>':
      result += "&gt;";
      break;
    case '"':
      result += "&quot;";
      break;
    default:
      result += c;
      break;
    }
  }
  escapedPath = result;

  std::string xml = R"(<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>HELXAID Boost Service - stops Windows services for game performance. )" +
                    std::string(TASK_VERSION) + R"(</Description>
    <Version>)" + std::string(TASK_VERSION) +
                    R"(</Version>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>2000-01-01T00:00:00</StartBoundary>
      <Enabled>false</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>wscript.exe</Command>
      <Arguments>//B //Nologo ")" +
                    escapedPath + R"("</Arguments>
    </Exec>
  </Actions>
</Task>)";

  // Write XML to temp file (UTF-16 as required by Task Scheduler)
  char tempPath[MAX_PATH];
  GetTempPathA(MAX_PATH, tempPath);
  std::string xmlPath = std::string(tempPath) + "helxaid_boost_task.xml";

  // Write as UTF-16 LE with BOM
  std::ofstream xmlFile(xmlPath, std::ios::binary);
  if (!xmlFile.is_open())
    return false;

  // UTF-16 LE BOM
  const unsigned char bom[] = {0xFF, 0xFE};
  xmlFile.write(reinterpret_cast<const char *>(bom), 2);

  // Convert UTF-8 XML to UTF-16 LE
  int wideLen = MultiByteToWideChar(CP_UTF8, 0, xml.c_str(), -1, nullptr, 0);
  std::wstring wideXml(wideLen, L'\0');
  MultiByteToWideChar(CP_UTF8, 0, xml.c_str(), -1, &wideXml[0], wideLen);
  // Write without null terminator
  xmlFile.write(reinterpret_cast<const char *>(wideXml.c_str()),
                (wideLen - 1) * sizeof(wchar_t));
  xmlFile.close();

  // Create task via ShellExecuteW with runas (triggers UAC once)
  std::string createArgs =
      "/create /tn \"" + taskName + "\" /xml \"" + xmlPath + "\" /f";
  bool elevated = runElevated(createArgs);

  if (!elevated) {
    DeleteFileA(xmlPath.c_str());
    return false;
  }

  // Wait for task registration to complete
  std::this_thread::sleep_for(std::chrono::seconds(2));

  // Verify creation
  bool created = isTaskReady(taskName);

  // Clean up temp XML
  DeleteFileA(xmlPath.c_str());

  return created;
#else
  return false;
#endif
}

bool BoostEngine::ensureTaskExists(const std::string &taskName,
                                   const std::string &scriptPath) {
  // Cache: only verify once per session
  if (taskVerified_)
    return true;

  // Check if task exists with correct version
  std::string output;
  std::string cmd = "schtasks /query /tn \"" + taskName + "\" /fo LIST /v";
  int ret = runHidden(cmd, output);

  if (ret == 0 && output.find(TASK_VERSION) != std::string::npos) {
    taskVerified_ = true;
    return true;
  }

  // Task exists but old version — delete first
  if (ret == 0) {
    deleteTask(taskName);
  }

  // Create new task with XML
  bool created = createTaskWithXml(taskName, scriptPath);
  if (created) {
    taskVerified_ = true;
  }
  return created;
}

// ============================================================
// PowerShell Script Management
// ============================================================

bool BoostEngine::writeBoostScript(const std::string &scriptPath,
                                   const std::string &vbsPath,
                                   const std::string &inputPath,
                                   const std::string &logPath) {
  // Escape backslashes for PowerShell string literals
  auto escapePs = [](const std::string &path) -> std::string {
    std::string out;
    for (char c : path) {
      if (c == '\\')
        out += "\\\\";
      else
        out += c;
    }
    return out;
  };

  std::string script = R"(
$inputFile = ")" + escapePs(inputPath) +
                       R"("
$logFile = ")" + escapePs(logPath) +
                       R"("

if (-not (Test-Path $inputFile)) { exit }

$lines = Get-Content $inputFile -Encoding UTF8
$results = @()

foreach ($line in $lines) {
    $line = $line.Trim()
    if (-not $line -or -not $line.Contains('|')) { continue }
    $parts = $line.Split('|', 2)
    $cat = $parts[0]
    $svcName = $parts[1]
    
    try {
        $s = Get-Service -Name $svcName -ErrorAction Stop
        if ($s.Status -eq 'Running') {
            Stop-Service -Name $svcName -Force -ErrorAction Stop
            $results += "$cat|$svcName|OK"
        } else {
            $results += "$cat|$svcName|ALREADY_STOPPED"
        }
    } catch {
        $results += "$cat|$svcName|FAIL"
    }
}

$results | Out-File -FilePath $logFile -Encoding utf8
Remove-Item $inputFile -Force -ErrorAction SilentlyContinue
)";

  std::ofstream file(scriptPath, std::ios::trunc);
  if (!file.is_open())
    return false;
  file << script;
  file.close();

  // Write VBS wrapper
  std::ofstream vbsFile(vbsPath, std::ios::trunc);
  if (vbsFile.is_open()) {
    std::string vbsScript =
        "Set objShell = CreateObject(\"WScript.Shell\")\n"
        "objShell.Run \"powershell.exe -NoProfile -ExecutionPolicy Bypass "
        "-WindowStyle Hidden -File \"\"\" & \"" +
        scriptPath + "\" & \"\"\"\", 0, False\n";
    vbsFile << vbsScript;
    vbsFile.close();
  }

  return true;
}

// ============================================================
// Service Operations
// ============================================================

std::vector<ServiceStopResult>
BoostEngine::stopServices(const std::vector<ServiceEntry> &services,
                          const std::string &taskName) {

  std::vector<ServiceStopResult> results;
  if (services.empty())
    return results;

#ifdef _WIN32
  // Get temp/appdata paths
  char tempPath[MAX_PATH];
  GetTempPathA(MAX_PATH, tempPath);
  std::string inputPath = std::string(tempPath) + "helxaid_boost_input.txt";
  std::string logPath = std::string(tempPath) + "helxaid_boost_svc.log";

  // Get APPDATA for script storage
  char appdataPath[MAX_PATH];
  if (SUCCEEDED(
          SHGetFolderPathA(nullptr, CSIDL_APPDATA, nullptr, 0, appdataPath))) {
    std::string scriptDir = std::string(appdataPath) + "\\HELXAID";
    CreateDirectoryA(scriptDir.c_str(), nullptr);
    std::string scriptPath = scriptDir + "\\boost_services.ps1";
    std::string vbsPath = scriptDir + "\\boost_wrapper.vbs";

    // Write the scripts (idempotent)
    writeBoostScript(scriptPath, vbsPath, inputPath, logPath);

    // Ensure scheduled task exists. The task is now explicitly tied to the VBS
    // script.
    if (!ensureTaskExists(taskName, vbsPath)) {
      // UAC denied or creation failed — all services fail
      for (auto &svc : services) {
        ServiceStopResult r;
        r.name = svc.name;
        r.displayName = svc.displayName;
        r.category = svc.category;
        r.success = false;
        r.status = "SETUP_NEEDED";
        results.push_back(r);
      }
      return results;
    }
  }

  // Delete old log file if exists
  DeleteFileA(logPath.c_str());

  // Write input file with service names
  {
    std::ofstream inputFile(inputPath, std::ios::trunc);
    if (!inputFile.is_open())
      return results;
    for (auto &svc : services) {
      inputFile << svc.category << "|" << svc.name << "\n";
    }
    inputFile.close();
  }

  // Trigger the scheduled task (no admin needed)
  {
    std::string output;
    std::string cmd = "schtasks /run /tn \"" + taskName + "\"";
    runHidden(cmd, output);
  }

  // Poll for results (max 30 seconds, 1 second intervals)
  bool logFound = false;
  for (int i = 0; i < 30; i++) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
    std::ifstream logFile(logPath);
    if (logFile.is_open()) {
      std::string content((std::istreambuf_iterator<char>(logFile)),
                          std::istreambuf_iterator<char>());
      logFile.close();
      if (!content.empty()) {
        logFound = true;
        break;
      }
    }
  }

  // Parse results from log file
  if (logFound) {
    std::ifstream logFile(logPath);
    std::string line;
    while (std::getline(logFile, line)) {
      // Trim whitespace and BOM
      while (!line.empty() && (line.back() == '\r' || line.back() == '\n' ||
                               line.back() == ' ')) {
        line.pop_back();
      }
      // Skip BOM if present (UTF-8 BOM: 0xEF 0xBB 0xBF)
      if (line.size() >= 3 && static_cast<unsigned char>(line[0]) == 0xEF &&
          static_cast<unsigned char>(line[1]) == 0xBB &&
          static_cast<unsigned char>(line[2]) == 0xBF) {
        line = line.substr(3);
      }
      if (line.empty())
        continue;

      // Parse: category|serviceName|STATUS
      auto pos1 = line.find('|');
      if (pos1 == std::string::npos)
        continue;
      auto pos2 = line.find('|', pos1 + 1);
      if (pos2 == std::string::npos)
        continue;

      std::string cat = line.substr(0, pos1);
      std::string svcName = line.substr(pos1 + 1, pos2 - pos1 - 1);
      std::string status = line.substr(pos2 + 1);

      ServiceStopResult r;
      r.name = svcName;
      r.category = cat;
      r.status = status;
      r.success = (status == "OK" || status == "ALREADY_STOPPED");

      // Find display name from input list
      for (auto &svc : services) {
        if (svc.name == svcName) {
          r.displayName = svc.displayName;
          break;
        }
      }
      if (r.displayName.empty())
        r.displayName = svcName;

      results.push_back(r);
    }
    logFile.close();
    DeleteFileA(logPath.c_str());
  } else {
    // Timeout — all services marked as failed
    for (auto &svc : services) {
      ServiceStopResult r;
      r.name = svc.name;
      r.displayName = svc.displayName;
      r.category = svc.category;
      r.success = false;
      r.status = "TIMEOUT";
      results.push_back(r);
    }
  }
#endif

  return results;
}

std::vector<ServiceStatus> BoostEngine::queryServiceStatuses(
    const std::vector<std::string> &serviceNames) {

  std::vector<ServiceStatus> results;

#ifdef _WIN32
  // Open Service Control Manager (read-only, no admin needed)
  SC_HANDLE scm = OpenSCManagerA(nullptr, nullptr, SC_MANAGER_CONNECT);
  if (!scm) {
    // Fallback: return all as Unknown
    for (auto &name : serviceNames) {
      ServiceStatus s;
      s.name = name;
      s.status = "Unknown";
      s.isRunning = false;
      results.push_back(s);
    }
    return results;
  }

  for (auto &name : serviceNames) {
    ServiceStatus s;
    s.name = name;
    s.isRunning = false;

    // Open service handle with query access only
    SC_HANDLE svc = OpenServiceA(scm, name.c_str(), SERVICE_QUERY_STATUS);
    if (svc) {
      SERVICE_STATUS_PROCESS ssp{};
      DWORD bytesNeeded;
      if (QueryServiceStatusEx(svc, SC_STATUS_PROCESS_INFO,
                               reinterpret_cast<LPBYTE>(&ssp), sizeof(ssp),
                               &bytesNeeded)) {
        if (ssp.dwCurrentState == SERVICE_RUNNING) {
          s.status = "Running";
          s.isRunning = true;
        } else if (ssp.dwCurrentState == SERVICE_STOPPED) {
          s.status = "Stopped";
        } else if (ssp.dwCurrentState == SERVICE_START_PENDING) {
          s.status = "Starting";
        } else if (ssp.dwCurrentState == SERVICE_STOP_PENDING) {
          s.status = "Stopping";
        } else {
          s.status = "Unknown";
        }
      } else {
        s.status = "Unknown";
      }
      CloseServiceHandle(svc);
    } else {
      s.status = "Not Found";
    }

    results.push_back(s);
  }

  CloseServiceHandle(scm);
#endif

  return results;
}

// ============================================================
// Process Operations
// ============================================================

std::vector<ProcessKillResult>
BoostEngine::killProcesses(const std::vector<std::string> &processNames) {

  std::vector<ProcessKillResult> results;

#ifdef _WIN32
  // Build a lowercase set of target process names for fast lookup
  std::map<std::string, ProcessKillResult *> targetMap;
  for (auto &name : processNames) {
    results.emplace_back();
    auto &r = results.back();
    r.name = name;
    r.totalPids = 0;
    r.killedPids = 0;
    r.success = false;

    // Lowercase for case-insensitive matching
    std::string lower = name;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    targetMap[lower] = &results.back();
  }

  // Snapshot all processes using ToolHelp32
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (snap == INVALID_HANDLE_VALUE)
    return results;

  PROCESSENTRY32W pe{};
  pe.dwSize = sizeof(pe);

  if (Process32FirstW(snap, &pe)) {
    do {
      // Convert process name to lowercase UTF-8
      char nameUtf8[260];
      WideCharToMultiByte(CP_UTF8, 0, pe.szExeFile, -1, nameUtf8,
                          sizeof(nameUtf8), nullptr, nullptr);
      std::string procName(nameUtf8);
      std::transform(procName.begin(), procName.end(), procName.begin(),
                     ::tolower);

      auto it = targetMap.find(procName);
      if (it != targetMap.end()) {
        it->second->totalPids++;

        // Open process and terminate
        HANDLE hProc = OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, FALSE,
                                   pe.th32ProcessID);
        if (hProc) {
          if (TerminateProcess(hProc, 1)) {
            // Wait up to 2 seconds for clean exit
            WaitForSingleObject(hProc, 2000);
            it->second->killedPids++;
          }
          CloseHandle(hProc);
        }
      }
    } while (Process32NextW(snap, &pe));
  }
  CloseHandle(snap);

  // Set success flags
  for (auto &r : results) {
    r.success = (r.killedPids > 0 || r.totalPids == 0);
  }
#endif

  return results;
}

} // namespace helxaid
