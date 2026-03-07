/**
 * Game Detector
 *
 * High-performance game detection engine for the HELXAID Game Launcher.
 * Replaces Python-based detection (psutil + win32gui) with native Windows API
 * calls (ToolHelp32 + EnumWindows) for ~10x faster process scanning.
 *
 * Features:
 * - Background process scanning thread with shared_mutex cache
 * - Two-pass detection with multi-signal disambiguation scoring
 * - Startup sanitization of corrupted game_exe fields
 * - Auto-learn with 4-layer filtering (blacklist, self, cross-game, path)
 * - Window title enumeration and fuzzy game name matching
 */

#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace helxaid {

// ============================================================
// Data Structures
// ============================================================

/**
 * Game information structure.
 * Mirrors the Python game library dict with the fields relevant
 * to detection. Passed from Python via pybind11.
 */
struct GameInfo {
  std::string name;     // Display name (e.g. "Wuthering Waves")
  std::string exe;      // Full path to launcher exe
  std::string game_exe; // Comma-separated list of game process names
  std::string app_type; // "auto" or empty
};

/**
 * Result of a game detection scan.
 * Returned by detectRunningGame() to Python for UI updates.
 */
struct DetectionResult {
  bool detected = false;  // Whether a game was detected
  std::string gameName;   // Name of the detected game
  std::string matchedExe; // Which exe name matched
  std::string status;     // "game", "launcher", or "unknown"
  int score = 0;          // Disambiguation score (for debugging)
};

/**
 * Record of a sanitization change applied to one game.
 * Returned by sanitize() so Python can update the JSON data.
 */
struct SanitizeChange {
  std::string gameName;             // Which game was cleaned
  std::vector<std::string> removed; // Exe names that were removed
  std::string cleanedGameExe;       // Resulting game_exe string after cleanup
};

// ============================================================
// Game Detector Class
// ============================================================

/**
 * High-performance native game detection engine.
 *
 * Usage from Python:
 *   detector = helxaid_native.GameDetector()
 *   detector.set_game_library(games_list)
 *   changes = detector.sanitize()
 *   detector.start_process_scanner(3000)
 *   ...
 *   result = detector.detect_running_game()
 *   ...
 *   detector.stop_process_scanner()
 */
class GameDetector {
public:
  GameDetector();
  ~GameDetector();

  // Static utilities (public for use by helper functions)
  static std::string wideToUtf8(const std::wstring &wide);
  static std::string toLower(const std::string &str);

  // ---- Game library management ----

  /**
   * Set the game library data from Python.
   * Thread-safe: acquires exclusive lock on library data.
   *
   * @param games  Vector of GameInfo structs (converted from Python dicts)
   */
  void setGameLibrary(const std::vector<GameInfo> &games);

  /**
   * Sanitize all games' game_exe fields.
   * Removes blacklisted system processes and cross-game contamination
   * (exe names containing another game's name).
   *
   * @return Vector of SanitizeChange records describing what was cleaned.
   *         Python should apply these changes back to the JSON data.
   */
  std::vector<SanitizeChange> sanitize();

  // ---- Background process scanner ----

  /**
   * Start background thread that periodically snapshots all running processes.
   * Populates the internal process cache (name, path, ppid).
   *
   * @param intervalMs  Scan interval in milliseconds (default 3000)
   */
  void startProcessScanner(int intervalMs = 3000);

  /**
   * Stop the background process scanning thread.
   * Blocks until the thread has joined.
   */
  void stopProcessScanner();

  /**
   * Check if the process scanner is currently running.
   */
  bool isScannerRunning() const;

  // ---- Main detection ----

  /**
   * Perform a two-pass game detection scan.
   *
   * Pass 1: Collect ALL candidate games with at least one matching process.
   * Pass 2: If multiple candidates, disambiguate using scoring:
   *         +10 path match, +5 name-in-exe, +3 window title, +1 non-launcher
   * exe.
   *
   * @return DetectionResult with the best match (or detected=false)
   */
  DetectionResult detectRunningGame();

  // ---- Auto-learn support ----

  /**
   * Take a snapshot of currently running processes.
   * Call this BEFORE launching a game so learnNewProcesses() can diff.
   */
  void snapshotProcesses();

  /**
   * After launching a game, diff processes against the pre-launch snapshot
   * and return new processes that pass the 4-layer filter:
   * 1. Not in SYSTEM_PROCESS_BLACKLIST
   * 2. Not the launcher exe itself
   * 3. Not already owned by another game
   * 4. Running from the game's install directory
   *
   * @param gameName      Name of the launched game
   * @param launchExePath Full path to the launched exe
   * @return Vector of new exe names that should be added to game_exe
   */
  std::vector<std::string> learnNewProcesses(const std::string &gameName,
                                             const std::string &launchExePath);

  // ---- Process queries (for Python code that still needs them) ----

  /**
   * Check if a process with the given exe name is currently running.
   * Thread-safe read from cached data.
   */
  bool isProcessRunning(const std::string &exeName);

  /**
   * Get set of all running process names (lowercase).
   * Thread-safe read from cached data.
   */
  std::unordered_set<std::string> getRunningProcesses();

  /**
   * Get the full exe path(s) for a process name.
   * Returns empty set if process not found or path unavailable.
   */
  std::unordered_set<std::string> getProcessPaths(const std::string &exeName);

  // ---- Window title queries ----

  /**
   * Get visible window titles for all instances of a process.
   * Uses EnumWindows + GetWindowTextW, converts to UTF-8.
   */
  std::vector<std::string>
  getWindowTitlesForProcess(const std::string &exeName);

  /**
   * Determine if a game is actively being played or just showing its launcher.
   * Uses window title analysis, process presence, and directory matching.
   *
   * @return "game", "launcher", or "unknown"
   */
  std::string checkGameStatus(const GameInfo &game);

private:
  // ---- Internal types ----
  struct Candidate {
    size_t gameIndex;       // Index into m_games
    std::string matchedExe; // Which exe name matched
  };

  // ---- Process cache (thread-safe) ----
  mutable std::shared_mutex m_cacheMutex;
  std::unordered_set<std::string> m_processCache; // lowercase exe names
  // Maps lowercase exe name -> set of full paths (lowercase)
  std::unordered_map<std::string, std::unordered_set<std::string>> m_pathCache;
  // Maps PID -> parent PID
  std::unordered_map<uint32_t, uint32_t> m_ppidCache;

  // ---- Pre-launch snapshot for auto-learn ----
  std::unordered_set<std::string> m_prelaunchSnapshot;

  // ---- Game library (thread-safe) ----
  mutable std::shared_mutex m_libraryMutex;
  std::vector<GameInfo> m_games;

  // ---- Scanner thread ----
  std::thread m_scanThread;
  std::atomic<bool> m_running{false};

  // ---- Internal methods ----

  // Process scanning: populate caches from Windows ToolHelp32 snapshot
  void refreshProcessCache();

  // Scanner thread main loop
  void scanLoop(int intervalMs);

  // Extract lowercase exe names from a GameInfo, filtering blacklisted entries
  std::vector<std::string> getGameExeNames(const GameInfo &game) const;

  // Get install directory from a game's exe path (lowercase)
  std::string getInstallDir(const GameInfo &game) const;

  // Collect all candidate games whose exe names appear in the process cache
  std::vector<Candidate> collectCandidates() const;

  // Score candidates and pick the best match
  size_t disambiguate(const std::vector<Candidate> &candidates) const;

  // Multi-strategy fuzzy game name matching against window title
  bool fuzzyMatchGameName(const std::string &gameName,
                          const std::string &windowTitle) const;

  // Check if exe name is in the system process blacklist
  bool isBlacklisted(const std::string &exeName) const;

  // Check if exe name is in the known launchers set
  bool isKnownLauncher(const std::string &exeName) const;

  // Check for TLauncher/Minecraft by window title (java.exe special case)
  bool isTLauncherOrMinecraftRunning() const;

};

} // namespace helxaid
