/**
 * Game Detector Implementation
 *
 * Native C++ game detection engine using Windows API.
 * Replaces Python psutil + win32gui with ToolHelp32 + EnumWindows
 * for significantly faster process scanning and window enumeration.
 */

// Windows.h MUST be included FIRST — TlHelp32.h and Psapi.h depend on
// types like HANDLE, DWORD, BOOL, WINAPI that are defined by Windows.h
#include <Windows.h>
#include <TlHelp32.h>
#include <Psapi.h>

#include "game_detector.h"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <regex>
#include <sstream>

namespace helxaid {

// ============================================================
// Static Constants — compiled in for fast lookup
// ============================================================

// Windows system/service executables that must NEVER be treated as game
// processes. If these end up in a game's game_exe field (e.g. from bad
// auto-detection), they will be silently ignored to prevent constant
// false-positive detection.
static const std::unordered_set<std::string> SYSTEM_PROCESS_BLACKLIST = {
    // Core Windows services and hosts
    "svchost.exe",
    "csrss.exe",
    "smss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "lsaiso.exe",
    "spoolsv.exe",
    "conhost.exe",
    "sihost.exe",
    "taskhostw.exe",
    "dwm.exe",
    "ctfmon.exe",
    "fontdrvhost.exe",
    "dllhost.exe",
    "wmiprvse.exe",
    // Windows Update / Telemetry / Servicing
    "dismhost.exe",
    "compattelrunner.exe",
    "comppkgsrv.exe",
    "sihclient.exe",
    "musnotification.exe",
    "tiworker.exe",
    "wuauclt.exe",
    "trustedinstaller.exe",
    "msiexec.exe",
    // Shell / Explorer
    "explorer.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "searchui.exe",
    "cortana.exe",
    "runtimebroker.exe",
    "applicationframehost.exe",
    // Common runtime hosts (too generic to be a game)
    "java.exe",
    "javaw.exe",
    "python.exe",
    "pythonw.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "wscript.exe",
    "cscript.exe",
    "rundll32.exe",
    "regsvr32.exe",
    "mmc.exe",
    "notepad.exe",
    // Network / Security
    "lsm.exe",
    "wlanext.exe",
    "dashost.exe",
    // Kuro launcher helpers (not the game itself)
    "krinstallexternal.exe",
    // Anti-cheat / overlay (system-level, not game)
    "backgroundtaskhost.exe",
    "audiodg.exe",
    "sppsvc.exe",
    "smartscreen.exe",
    "securityhealthservice.exe",
    "werfault.exe",
    "consent.exe",
};

// Well-known game platform launcher executables (lowercase basenames).
// If a library entry's exe field matches one of these, the process is a
// platform launcher rather than the game itself.
static const std::unordered_set<std::string> KNOWN_LAUNCHERS = {
    "steam.exe",
    "steamwebhelper.exe",
    "epicgameslauncher.exe",
    "epicwebhelper.exe",
    "riotclientservices.exe",
    "riotclientux.exe",
    "riotclientcrashhandler.exe",
    "hoyoplay.exe",
    "launcher.exe",
    "kurolauncher.exe",
    "galaxyclient.exe",
    "galaxyclienthelper.exe",
    "ea.exe",
    "eadesktop.exe",
    "origin.exe",
    "easteamproxy.exe",
    "ubisoftconnect.exe",
    "ubisoftgamelauncher.exe",
    "upc.exe",
    "bethesdalauncher.exe",
    "battle.net.exe",
    "agent.exe",
    "xboxapp.exe",
    "gamingservices.exe",
    "amazon games.exe",
    "itch.exe",
    "tlauncher.exe",
    "overwolf.exe",
};

// Generic Unreal Engine process names that many games share.
static const std::unordered_set<std::string> GENERIC_UE_EXES = {
    "client-win64-shipping.exe",
    "unrealengine.exe",
    "gameoverlayui.exe",
    "crashreportclient.exe",
};

// Window title keywords indicating a launcher/updater rather than the game.
static const std::unordered_set<std::string> LAUNCHER_TITLE_KEYWORDS = {
    "launcher", "updater",        "patcher",  "installer",
    "setup",    "update manager", "download", "login",
    "sign in",  "riot client",    "hoyoplay", "kuro launcher",
};

// ============================================================
// Utility Functions
// ============================================================

std::string GameDetector::wideToUtf8(const std::wstring &wide) {
  if (wide.empty())
    return "";
  int size = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(),
                                 static_cast<int>(wide.size()), nullptr, 0,
                                 nullptr, nullptr);
  if (size <= 0)
    return "";
  std::string result(size, '\0');
  WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), static_cast<int>(wide.size()),
                      result.data(), size, nullptr, nullptr);
  return result;
}

std::string GameDetector::toLower(const std::string &str) {
  std::string result = str;
  std::transform(result.begin(), result.end(), result.begin(),
                 [](unsigned char c) { return std::tolower(c); });
  return result;
}

// Extract basename from a full path and convert to lowercase
static std::string getBasename(const std::string &path) {
  std::string normalized = path;
  // Normalize path separators
  std::replace(normalized.begin(), normalized.end(), '/', '\\');
  auto pos = normalized.rfind('\\');
  std::string basename =
      (pos != std::string::npos) ? normalized.substr(pos + 1) : normalized;
  return GameDetector::toLower(basename);
}

// Get parent directory from a full path (lowercase, normalized)
static std::string getParentDir(const std::string &path) {
  std::string normalized = path;
  std::replace(normalized.begin(), normalized.end(), '/', '\\');
  auto pos = normalized.rfind('\\');
  if (pos != std::string::npos) {
    std::string dir = normalized.substr(0, pos);
    return GameDetector::toLower(dir);
  }
  return "";
}

// Split comma-separated string into trimmed tokens
static std::vector<std::string> splitComma(const std::string &str) {
  std::vector<std::string> result;
  std::istringstream stream(str);
  std::string token;
  while (std::getline(stream, token, ',')) {
    // Trim whitespace
    auto start = token.find_first_not_of(" \t\r\n");
    auto end = token.find_last_not_of(" \t\r\n");
    if (start != std::string::npos && end != std::string::npos) {
      result.push_back(token.substr(start, end - start + 1));
    }
  }
  return result;
}

// ============================================================
// Constructor / Destructor
// ============================================================

GameDetector::GameDetector() = default;

GameDetector::~GameDetector() { stopProcessScanner(); }

// ============================================================
// Game Library Management
// ============================================================

void GameDetector::setGameLibrary(const std::vector<GameInfo> &games) {
  std::unique_lock lock(m_libraryMutex);
  m_games = games;
}

std::vector<SanitizeChange> GameDetector::sanitize() {
  std::unique_lock lock(m_libraryMutex);
  std::vector<SanitizeChange> changes;

  // Build set of all game names for cross-contamination check
  std::unordered_set<std::string> gameNames;
  for (const auto &g : m_games) {
    std::string name = toLower(g.name);
    if (name.size() > 3) {
      gameNames.insert(name);
    }
  }

  for (auto &game : m_games) {
    if (game.game_exe.empty())
      continue;

    std::string gameName = toLower(game.name);
    auto exes = splitComma(game.game_exe);

    std::vector<std::string> clean;
    std::vector<std::string> removed;

    for (const auto &e : exes) {
      std::string eLower = toLower(e);

      // PASS 1: Remove blacklisted system processes
      if (SYSTEM_PROCESS_BLACKLIST.count(eLower)) {
        removed.push_back(eLower);
        continue;
      }

      // PASS 2: Remove exes that contain ANOTHER game's name
      // e.g. "wuthering waves.exe" should not be in Minecraft's game_exe
      bool isForeign = false;
      for (const auto &otherName : gameNames) {
        if (otherName != gameName &&
            eLower.find(otherName) != std::string::npos) {
          removed.push_back(eLower);
          isForeign = true;
          break;
        }
      }

      if (!isForeign) {
        clean.push_back(e);
      }
    }

    if (!removed.empty()) {
      // Rebuild game_exe from clean list
      std::string cleaned;
      for (size_t i = 0; i < clean.size(); ++i) {
        if (i > 0)
          cleaned += ", ";
        cleaned += clean[i];
      }
      game.game_exe = cleaned;

      SanitizeChange change;
      change.gameName = game.name;
      change.removed = removed;
      change.cleanedGameExe = cleaned;
      changes.push_back(change);
    }
  }

  return changes;
}

// ============================================================
// Process Scanner Thread
// ============================================================

void GameDetector::startProcessScanner(int intervalMs) {
  if (m_running.load())
    return; // Already running

  m_running.store(true);
  m_scanThread = std::thread(&GameDetector::scanLoop, this, intervalMs);
}

void GameDetector::stopProcessScanner() {
  m_running.store(false);
  if (m_scanThread.joinable()) {
    m_scanThread.join();
  }
}

bool GameDetector::isScannerRunning() const { return m_running.load(); }

void GameDetector::scanLoop(int intervalMs) {
  while (m_running.load()) {
    refreshProcessCache();
    // Sleep in small increments so we can stop quickly
    for (int elapsed = 0; elapsed < intervalMs && m_running.load();
         elapsed += 100) {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
  }
}

void GameDetector::refreshProcessCache() {
  std::unordered_set<std::string> newProcessCache;
  std::unordered_map<std::string, std::unordered_set<std::string>> newPathCache;
  std::unordered_map<uint32_t, uint32_t> newPpidCache;

  // Take a snapshot of all running processes using ToolHelp32
  HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (snapshot == INVALID_HANDLE_VALUE)
    return;

  PROCESSENTRY32W pe;
  pe.dwSize = sizeof(pe);

  if (Process32FirstW(snapshot, &pe)) {
    do {
      // Convert wide process name to UTF-8 lowercase
      std::string exeName = toLower(wideToUtf8(pe.szExeFile));
      newProcessCache.insert(exeName);

      // Store parent PID mapping
      newPpidCache[pe.th32ProcessID] = pe.th32ParentProcessID;

      // Try to get the full exe path for this process
      HANDLE hProc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE,
                                 pe.th32ProcessID);
      if (hProc) {
        wchar_t pathBuf[MAX_PATH * 2];
        DWORD pathLen = sizeof(pathBuf) / sizeof(pathBuf[0]);
        if (QueryFullProcessImageNameW(hProc, 0, pathBuf, &pathLen)) {
          std::string fullPath = toLower(wideToUtf8(pathBuf));
          newPathCache[exeName].insert(fullPath);
        }
        CloseHandle(hProc);
      }
    } while (Process32NextW(snapshot, &pe));
  }

  CloseHandle(snapshot);

  // Swap caches atomically (exclusive lock)
  {
    std::unique_lock lock(m_cacheMutex);
    m_processCache = std::move(newProcessCache);
    m_pathCache = std::move(newPathCache);
    m_ppidCache = std::move(newPpidCache);
  }
}

// ============================================================
// Process Queries
// ============================================================

bool GameDetector::isProcessRunning(const std::string &exeName) {
  std::shared_lock lock(m_cacheMutex);
  return m_processCache.count(toLower(exeName)) > 0;
}

std::unordered_set<std::string> GameDetector::getRunningProcesses() {
  std::shared_lock lock(m_cacheMutex);
  return m_processCache;
}

std::unordered_set<std::string>
GameDetector::getProcessPaths(const std::string &exeName) {
  std::shared_lock lock(m_cacheMutex);
  auto it = m_pathCache.find(toLower(exeName));
  if (it != m_pathCache.end()) {
    return it->second;
  }
  return {};
}

// ============================================================
// Helper Methods
// ============================================================

bool GameDetector::isBlacklisted(const std::string &exeName) const {
  return SYSTEM_PROCESS_BLACKLIST.count(toLower(exeName)) > 0;
}

bool GameDetector::isKnownLauncher(const std::string &exeName) const {
  return KNOWN_LAUNCHERS.count(toLower(exeName)) > 0;
}

std::vector<std::string>
GameDetector::getGameExeNames(const GameInfo &game) const {
  std::vector<std::string> names;

  // Main exe (launcher or game itself)
  if (!game.exe.empty()) {
    names.push_back(getBasename(game.exe));
  }

  // Game exe (comma-separated, filtered)
  if (!game.game_exe.empty()) {
    auto parts = splitComma(game.game_exe);
    for (const auto &part : parts) {
      std::string lower = toLower(part);
      if (!lower.empty() && !isBlacklisted(lower)) {
        names.push_back(lower);
      }
    }
  }

  return names;
}

std::string GameDetector::getInstallDir(const GameInfo &game) const {
  if (game.exe.empty())
    return "";
  return getParentDir(game.exe);
}

// ============================================================
// Window Title Methods
// ============================================================

// Callback data for EnumWindows
struct EnumWindowData {
  std::string targetExeName; // lowercase
  std::vector<std::string> titles;
};

static BOOL CALLBACK enumWindowsCallback(HWND hwnd, LPARAM lParam) {
  auto *data = reinterpret_cast<EnumWindowData *>(lParam);

  if (!IsWindowVisible(hwnd))
    return TRUE;

  // Get PID of the window's owning process
  DWORD pid = 0;
  GetWindowThreadProcessId(hwnd, &pid);
  if (pid == 0)
    return TRUE;

  // Open the process to get its name
  HANDLE hProc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
  if (!hProc)
    return TRUE;

  wchar_t pathBuf[MAX_PATH];
  DWORD pathLen = MAX_PATH;
  bool nameMatches = false;

  if (QueryFullProcessImageNameW(hProc, 0, pathBuf, &pathLen)) {
    std::wstring fullPath(pathBuf, pathLen);
    // Extract basename
    auto pos = fullPath.rfind(L'\\');
    std::wstring baseName =
        (pos != std::wstring::npos) ? fullPath.substr(pos + 1) : fullPath;
    // Convert to lowercase UTF-8
    std::string baseNameUtf8 =
        GameDetector::toLower(GameDetector::wideToUtf8(baseName));
    nameMatches = (baseNameUtf8 == data->targetExeName);
  }
  CloseHandle(hProc);

  if (nameMatches) {
    wchar_t titleBuf[512];
    int len = GetWindowTextW(hwnd, titleBuf, 512);
    if (len > 0) {
      data->titles.push_back(
          GameDetector::wideToUtf8(std::wstring(titleBuf, len)));
    }
  }

  return TRUE;
}

std::vector<std::string>
GameDetector::getWindowTitlesForProcess(const std::string &exeName) {
  EnumWindowData data;
  data.targetExeName = toLower(exeName);
  EnumWindows(enumWindowsCallback, reinterpret_cast<LPARAM>(&data));
  return data.titles;
}

bool GameDetector::fuzzyMatchGameName(const std::string &gameName,
                                      const std::string &windowTitle) const {
  if (gameName.empty() || windowTitle.empty())
    return false;

  std::string nameLower = toLower(gameName);
  std::string titleLower = toLower(windowTitle);

  // Strategy 1: Direct substring match (most reliable)
  if (titleLower.find(nameLower) != std::string::npos) {
    return true;
  }

  // Strategy 2: Word-based match — all significant words must appear
  // Split game name into words, skip short filler words
  static const std::unordered_set<std::string> skipWords = {
      "the", "of", "a",  "an",  "and", "or", "in",
      "on",  "at", "to", "for", "is",  "it"};

  std::vector<std::string> nameWords;
  std::istringstream stream(nameLower);
  std::string word;
  while (stream >> word) {
    // Remove non-alphanumeric chars
    std::string cleaned;
    for (char c : word) {
      if (std::isalnum(static_cast<unsigned char>(c))) {
        cleaned += c;
      }
    }
    if (cleaned.size() > 1 && !skipWords.count(cleaned)) {
      nameWords.push_back(cleaned);
    }
  }

  if (nameWords.size() >= 2) {
    bool allMatch = true;
    for (const auto &w : nameWords) {
      if (titleLower.find(w) == std::string::npos) {
        allMatch = false;
        break;
      }
    }
    if (allMatch)
      return true;
  }

  return false;
}

bool GameDetector::isTLauncherOrMinecraftRunning() const {
  // Check for TLauncher/Minecraft windows by enumerating java/javaw windows
  // Need non-const access for EnumWindows, so we cast (safe — EnumWindows is
  // read-only)
  auto *self = const_cast<GameDetector *>(this);

  auto javaTitles = self->getWindowTitlesForProcess("java.exe");
  auto javawTitles = self->getWindowTitlesForProcess("javaw.exe");

  // Combine all Java window titles
  std::vector<std::string> allTitles;
  allTitles.insert(allTitles.end(), javaTitles.begin(), javaTitles.end());
  allTitles.insert(allTitles.end(), javawTitles.begin(), javawTitles.end());

  for (const auto &title : allTitles) {
    std::string lower = toLower(title);
    if (lower.find("minecraft") != std::string::npos ||
        lower.find("tlauncher") != std::string::npos) {
      return true;
    }
  }
  return false;
}

std::string GameDetector::checkGameStatus(const GameInfo &game) {
  std::string gameName = toLower(game.name);
  std::string launcherExe = getBasename(game.exe);
  auto exeNames = getGameExeNames(game);

  // STEP 1: Special case for java.exe games (TLauncher/Minecraft)
  for (const auto &n : exeNames) {
    if (n == "java.exe" || n == "javaw.exe") {
      if (gameName.find("tlauncher") != std::string::npos ||
          gameName.find("minecraft") != std::string::npos) {
        if (isTLauncherOrMinecraftRunning()) {
          return "game";
        }
        return "unknown";
      }
    }
  }

  // STEP 2: Collect window titles from all related processes
  std::vector<std::string> allTitles;
  std::vector<std::string> gameExeTitles;

  if (!launcherExe.empty()) {
    auto titles = getWindowTitlesForProcess(launcherExe);
    allTitles.insert(allTitles.end(), titles.begin(), titles.end());
  }

  if (!game.game_exe.empty()) {
    auto parts = splitComma(game.game_exe);
    for (const auto &exe : parts) {
      std::string exeLower = toLower(exe);
      if (!exeLower.empty() && !isBlacklisted(exeLower)) {
        auto titles = getWindowTitlesForProcess(exeLower);
        gameExeTitles.insert(gameExeTitles.end(), titles.begin(), titles.end());
        allTitles.insert(allTitles.end(), titles.begin(), titles.end());
      }
    }
  }

  // STEP 3: If game_exe has a visible window, check its title
  for (const auto &title : gameExeTitles) {
    std::string titleLower = toLower(title);
    bool isLauncherWindow = false;
    for (const auto &kw : LAUNCHER_TITLE_KEYWORDS) {
      if (titleLower.find(kw) != std::string::npos) {
        isLauncherWindow = true;
        break;
      }
    }
    if (!isLauncherWindow) {
      return "game";
    }
  }

  if (allTitles.empty()) {
    // No windows found — check if game_exe process is running
    if (!game.game_exe.empty()) {
      auto parts = splitComma(game.game_exe);
      for (const auto &exe : parts) {
        std::string exeLower = toLower(exe);
        if (!exeLower.empty() && !isBlacklisted(exeLower) &&
            isProcessRunning(exeLower)) {
          return "game";
        }
      }
    }
    return "unknown";
  }

  // STEP 4: Analyze window titles
  bool hasGameWindow = false;
  bool hasLauncherWindow = false;

  for (const auto &title : allTitles) {
    std::string titleLower = toLower(title);

    bool isLauncher = false;
    for (const auto &kw : LAUNCHER_TITLE_KEYWORDS) {
      if (titleLower.find(kw) != std::string::npos) {
        isLauncher = true;
        break;
      }
    }
    if (isLauncher) {
      hasLauncherWindow = true;
      continue;
    }

    if (fuzzyMatchGameName(game.name, title)) {
      hasGameWindow = true;
    }
  }

  if (hasGameWindow)
    return "game";
  if (hasLauncherWindow)
    return "launcher";

  // STEP 5: Main exe is a known launcher
  if (isKnownLauncher(launcherExe)) {
    if (!game.game_exe.empty()) {
      auto parts = splitComma(game.game_exe);
      for (const auto &exe : parts) {
        std::string exeLower = toLower(exe);
        if (!exeLower.empty() && !isBlacklisted(exeLower) &&
            isProcessRunning(exeLower)) {
          return "game";
        }
      }
    }
    return "launcher";
  }

  // STEP 6: UE generic exe detection
  if (GENERIC_UE_EXES.count(launcherExe) && !game.exe.empty()) {
    std::string gameInstallDir = getInstallDir(game);
    auto runningPaths = getProcessPaths(launcherExe);
    for (const auto &rpath : runningPaths) {
      if (!gameInstallDir.empty() && rpath.find(gameInstallDir) == 0) {
        return "game";
      }
    }
  }

  // STEP 7: Fallback — check if game_exe process is running
  if (!game.game_exe.empty()) {
    auto parts = splitComma(game.game_exe);
    for (const auto &exe : parts) {
      std::string exeLower = toLower(exe);
      if (!exeLower.empty() && !isBlacklisted(exeLower) &&
          isProcessRunning(exeLower)) {
        return "game";
      }
    }
  }

  return "unknown";
}

// ============================================================
// Main Detection
// ============================================================

std::vector<GameDetector::Candidate> GameDetector::collectCandidates() const {
  std::vector<Candidate> candidates;

  // Need shared lock on both cache and library
  std::shared_lock cacheLock(m_cacheMutex);
  std::shared_lock libLock(m_libraryMutex);

  for (size_t i = 0; i < m_games.size(); ++i) {
    auto exeNames = getGameExeNames(m_games[i]);
    if (exeNames.empty())
      continue;

    for (const auto &exeName : exeNames) {
      if (exeName.empty() || m_processCache.count(exeName) == 0) {
        continue;
      }

      // Special case for java.exe (TLauncher/Minecraft)
      if (exeName == "java.exe" || exeName == "javaw.exe") {
        std::string gameName = toLower(m_games[i].name);
        if (gameName.find("tlauncher") != std::string::npos ||
            gameName.find("minecraft") != std::string::npos) {
          if (!isTLauncherOrMinecraftRunning()) {
            continue; // No Minecraft window found, skip
          }
        } else {
          continue; // Non-Minecraft game matched java.exe, skip
        }
      }

      candidates.push_back({i, exeName});
      break; // One match per game is enough
    }
  }

  return candidates;
}

size_t
GameDetector::disambiguate(const std::vector<Candidate> &candidates) const {
  size_t bestIndex = 0;
  int bestScore = -1;

  // Need shared lock on cache and library
  std::shared_lock cacheLock(m_cacheMutex);
  std::shared_lock libLock(m_libraryMutex);

  for (size_t i = 0; i < candidates.size(); ++i) {
    const auto &candidate = candidates[i];
    const auto &game = m_games[candidate.gameIndex];
    int score = 0;

    std::string installDir = getInstallDir(game);

    // PATH MATCH (+10): Process is running from this game's install tree
    if (!installDir.empty()) {
      auto it = m_pathCache.find(candidate.matchedExe);
      if (it != m_pathCache.end()) {
        for (const auto &path : it->second) {
          if (path.find(installDir) == 0) {
            score += 10;
            break;
          }
        }
      }
    }

    // NAME-IN-EXE (+5): The exe filename contains the game's name
    std::string gameName = toLower(game.name);
    if (!gameName.empty() &&
        candidate.matchedExe.find(gameName) != std::string::npos) {
      score += 5;
    }

    // WINDOW TITLE (+3/+1): Check visible windows
    // Cast away const for window enumeration (read-only operation)
    auto *self = const_cast<GameDetector *>(this);
    std::string status = self->checkGameStatus(game);
    if (status == "game") {
      score += 3;
    } else if (status == "launcher") {
      score += 1;
    }

    // NON-LAUNCHER EXE BONUS (+1): matched exe is a game_exe entry
    std::string mainExe = getBasename(game.exe);
    if (candidate.matchedExe != mainExe) {
      score += 1;
    }

    if (score > bestScore) {
      bestScore = score;
      bestIndex = i;
    }
  }

  return bestIndex;
}

DetectionResult GameDetector::detectRunningGame() {
  DetectionResult result;

  auto candidates = collectCandidates();

  if (candidates.empty()) {
    result.detected = false;
    return result;
  }

  size_t bestIdx;
  if (candidates.size() == 1) {
    bestIdx = 0;
  } else {
    bestIdx = disambiguate(candidates);
  }

  const auto &best = candidates[bestIdx];
  std::shared_lock libLock(m_libraryMutex);
  const auto &game = m_games[best.gameIndex];

  result.detected = true;
  result.gameName = game.name;
  result.matchedExe = best.matchedExe;
  result.status = checkGameStatus(game);

  return result;
}

// ============================================================
// Auto-Learn
// ============================================================

void GameDetector::snapshotProcesses() {
  std::shared_lock lock(m_cacheMutex);
  m_prelaunchSnapshot = m_processCache;
}

std::vector<std::string>
GameDetector::learnNewProcesses(const std::string &gameName,
                                const std::string &launchExePath) {
  std::vector<std::string> learned;

  std::string launcherExe = getBasename(launchExePath);
  std::string installDir = getParentDir(launchExePath);

  // Get current processes
  std::unordered_set<std::string> currentProcesses;
  {
    std::shared_lock lock(m_cacheMutex);
    currentProcesses = m_processCache;
  }

  // Diff: new processes = current - prelaunch
  std::unordered_set<std::string> newProcesses;
  for (const auto &proc : currentProcesses) {
    if (m_prelaunchSnapshot.count(proc) == 0) {
      newProcesses.insert(proc);
    }
  }

  // Build set of exes owned by other games
  std::unordered_set<std::string> otherGameExes;
  {
    std::shared_lock lock(m_libraryMutex);
    std::string gameNameLower = toLower(gameName);
    for (const auto &g : m_games) {
      if (toLower(g.name) != gameNameLower) {
        auto exeNames = getGameExeNames(g);
        for (const auto &e : exeNames) {
          otherGameExes.insert(e);
        }
      }
    }
  }

  // Apply 4-layer filter to each new process
  for (const auto &proc : newProcesses) {
    std::string procLower = toLower(proc);

    // FILTER 1: Skip blacklisted system processes
    if (isBlacklisted(procLower))
      continue;

    // FILTER 2: Skip the launcher exe itself
    if (procLower == launcherExe)
      continue;

    // FILTER 3: Skip processes already owned by another game
    if (otherGameExes.count(procLower))
      continue;

    // FILTER 4: Path check — only learn processes from game's install tree
    auto paths = getProcessPaths(procLower);
    if (!paths.empty()) {
      bool pathMatch = false;
      for (const auto &p : paths) {
        if (!installDir.empty() && p.find(installDir) == 0) {
          pathMatch = true;
          break;
        }
      }
      if (!pathMatch)
        continue;
    }

    learned.push_back(proc);
  }

  return learned;
}

} // namespace helxaid
