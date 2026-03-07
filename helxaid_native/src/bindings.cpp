/**
 * pybind11 Python Bindings
 *
 * Exposes C++ classes and functions to Python.
 */

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "boost_engine.h"
#include "game_detector.h"
#include "helxaid.h"
#include "hid_controller.h"
#include "input_hook.h"
#include "macro_engine.h"

namespace py = pybind11;

PYBIND11_MODULE(helxaid_native, m) {
  m.doc() = "HELXAID Native Performance Extensions";

  // Version info
  m.attr("__version__") = "1.0.0";
  m.attr("VERSION_MAJOR") = HELXAID_VERSION_MAJOR;
  m.attr("VERSION_MINOR") = HELXAID_VERSION_MINOR;
  m.attr("VERSION_PATCH") = HELXAID_VERSION_PATCH;

  // ===== IconResult =====
  py::class_<helxaid::IconResult>(m, "IconResult",
                                  "Result of icon extraction operation")
      .def(py::init<>())
      .def_readonly("width", &helxaid::IconResult::width,
                    "Image width in pixels")
      .def_readonly("height", &helxaid::IconResult::height,
                    "Image height in pixels")
      .def_readonly("success", &helxaid::IconResult::success,
                    "Whether extraction succeeded")
      .def_readonly("error", &helxaid::IconResult::error,
                    "Error message if failed")
      .def("is_valid", &helxaid::IconResult::isValid,
           "Check if result contains valid image data")
      .def("get_data_size", &helxaid::IconResult::getDataSize,
           "Get size of raw pixel data in bytes")
      .def(
          "to_bytes",
          [](const helxaid::IconResult &self) {
            // Return raw RGBA data as Python bytes
            return py::bytes(reinterpret_cast<const char *>(self.getData()),
                             self.getDataSize());
          },
          "Get raw RGBA pixel data as bytes")
      .def("__repr__", [](const helxaid::IconResult &self) {
        if (self.success) {
          return "<IconResult " + std::to_string(self.width) + "x" +
                 std::to_string(self.height) + " success=True>";
        } else {
          return "<IconResult success=False error='" + self.error + "'>";
        }
      });

  // ===== IconExtractor =====
  py::class_<helxaid::IconExtractor>(
      m, "IconExtractor",
      "High-performance icon extractor using Windows Shell API")
      .def(py::init<>(), "Create a new IconExtractor instance")
      .def("extract", &helxaid::IconExtractor::extract, py::arg("path"),
           py::arg("size") = 256,
           "Extract icon from file (exe, lnk, dll, etc.)")
      .def("extract_batch", &helxaid::IconExtractor::extractBatch,
           py::arg("paths"), py::arg("size") = 256, py::arg("num_threads") = 4,
           "Extract icons from multiple files in parallel")
      .def("get_video_thumbnail", &helxaid::IconExtractor::getVideoThumbnail,
           py::arg("path"), py::arg("size") = 512, "Extract video thumbnail");

  // ===== FileInfo =====
  py::class_<helxaid::FileInfo>(m, "FileInfo", "File information structure")
      .def(py::init<>())
      .def_readonly("path", &helxaid::FileInfo::path, "Full file path")
      .def_readonly("name", &helxaid::FileInfo::name, "File name")
      .def_readonly("extension", &helxaid::FileInfo::extension,
                    "File extension (lowercase)")
      .def_readonly("size", &helxaid::FileInfo::size, "File size in bytes")
      .def_readonly("modified_time", &helxaid::FileInfo::modifiedTime,
                    "Last modification time")
      .def_readonly("is_directory", &helxaid::FileInfo::isDirectory,
                    "Whether this is a directory")
      .def("__repr__", [](const helxaid::FileInfo &self) {
        return "<FileInfo '" + self.name +
               "' size=" + std::to_string(self.size) + ">";
      });

  // ===== FileScanner =====
  py::class_<helxaid::FileScanner>(
      m, "FileScanner", "High-performance file scanner for game discovery")
      .def(py::init<>(), "Create a new FileScanner instance")
      .def("scan", &helxaid::FileScanner::scan, py::arg("directory"),
           py::arg("recursive") = true, py::arg("filter") = nullptr,
           "Scan directory for files")
      .def("find_executables", &helxaid::FileScanner::findExecutables,
           py::arg("directory"),
           "Find executable files (.exe, .lnk, .url, .bat, .cmd)")
      .def("find_media_files", &helxaid::FileScanner::findMediaFiles,
           py::arg("directory"), "Find media files (audio and video)");

  // ===== Convenience functions =====
  m.def(
      "extract_icon",
      [](const std::string &path, int size) {
        helxaid::IconExtractor extractor;
        return extractor.extract(path, size);
      },
      py::arg("path"), py::arg("size") = 256,
      "Quick icon extraction (convenience function)");

  m.def(
      "extract_icons_batch",
      [](const std::vector<std::string> &paths, int size, int num_threads) {
        helxaid::IconExtractor extractor;
        return extractor.extractBatch(paths, size, num_threads);
      },
      py::arg("paths"), py::arg("size") = 256, py::arg("num_threads") = 4,
      "Quick batch icon extraction (convenience function)");

  m.def(
      "find_executables",
      [](const std::string &directory) {
        helxaid::FileScanner scanner;
        return scanner.findExecutables(directory);
      },
      py::arg("directory"),
      "Find executables in directory (convenience function)");

  m.def(
      "find_media_files",
      [](const std::string &directory) {
        helxaid::FileScanner scanner;
        return scanner.findMediaFiles(directory);
      },
      py::arg("directory"),
      "Find media files in directory (convenience function)");

  // ===== PlaybackState enum =====
  py::enum_<helxaid::PlaybackState>(m, "PlaybackState", "Media playback state")
      .value("Stopped", helxaid::PlaybackState::Stopped)
      .value("Playing", helxaid::PlaybackState::Playing)
      .value("Paused", helxaid::PlaybackState::Paused)
      .export_values();

  // ===== LoopMode enum =====
  py::enum_<helxaid::LoopMode>(m, "LoopMode", "Playlist loop mode")
      .value("Off", helxaid::LoopMode::Off)
      .value("All", helxaid::LoopMode::All)
      .value("One", helxaid::LoopMode::One)
      .export_values();

  // ===== TrackInfo =====
  py::class_<helxaid::TrackInfo>(m, "TrackInfo", "Track metadata information")
      .def(py::init<>())
      .def_readwrite("path", &helxaid::TrackInfo::path, "File path")
      .def_readwrite("title", &helxaid::TrackInfo::title, "Track title")
      .def_readwrite("artist", &helxaid::TrackInfo::artist, "Artist name")
      .def_readwrite("album", &helxaid::TrackInfo::album, "Album name")
      .def_readwrite("duration", &helxaid::TrackInfo::duration,
                     "Duration in seconds")
      .def_readwrite("has_video", &helxaid::TrackInfo::hasVideo,
                     "Has video stream")
      .def_readwrite("date_added", &helxaid::TrackInfo::dateAdded, "Date added")
      .def("__repr__", [](const helxaid::TrackInfo &self) {
        return "<TrackInfo '" + self.title +
               "' duration=" + std::to_string(self.duration) + ">";
      });

  // ===== MediaPlayer =====
  py::class_<helxaid::MediaPlayer>(
      m, "MediaPlayer",
      "High-performance media player for audio and video playback")
      .def(py::init<>(), "Create a new MediaPlayer instance")
      // Playback control
      .def("load", &helxaid::MediaPlayer::load, py::arg("path"),
           "Load media file")
      .def("play", &helxaid::MediaPlayer::play, "Start/resume playback")
      .def("pause", &helxaid::MediaPlayer::pause, "Pause playback")
      .def("stop", &helxaid::MediaPlayer::stop, "Stop playback")
      .def("toggle_play", &helxaid::MediaPlayer::togglePlay,
           "Toggle play/pause")
      .def("seek", &helxaid::MediaPlayer::seek, py::arg("position"),
           "Seek to position in seconds")
      .def("seek_percent", &helxaid::MediaPlayer::seekPercent,
           py::arg("percent"), "Seek to percentage (0.0-1.0)")
      // Volume
      .def("set_volume", &helxaid::MediaPlayer::setVolume, py::arg("volume"),
           "Set volume (0-100)")
      .def("get_volume", &helxaid::MediaPlayer::getVolume, "Get volume")
      .def("set_muted", &helxaid::MediaPlayer::setMuted, py::arg("mute"),
           "Set mute state")
      .def("is_muted", &helxaid::MediaPlayer::isMuted, "Get mute state")
      // Playlist
      .def("set_playlist", &helxaid::MediaPlayer::setPlaylist,
           py::arg("tracks"), "Set playlist")
      .def("get_playlist", &helxaid::MediaPlayer::getPlaylist,
           py::return_value_policy::reference_internal, "Get playlist")
      .def("play_track", &helxaid::MediaPlayer::playTrack, py::arg("index"),
           "Play track at index")
      .def("next_track", &helxaid::MediaPlayer::nextTrack, "Play next track")
      .def("prev_track", &helxaid::MediaPlayer::prevTrack,
           "Play previous track")
      .def("get_current_index", &helxaid::MediaPlayer::getCurrentIndex,
           "Get current track index")
      .def("get_current_track", &helxaid::MediaPlayer::getCurrentTrack,
           "Get current track info")
      // Playback modes
      .def("set_shuffle", &helxaid::MediaPlayer::setShuffle, py::arg("shuffle"),
           "Enable/disable shuffle")
      .def("get_shuffle", &helxaid::MediaPlayer::getShuffle,
           "Get shuffle state")
      .def("set_loop_mode", &helxaid::MediaPlayer::setLoopMode, py::arg("mode"),
           "Set loop mode")
      .def("get_loop_mode", &helxaid::MediaPlayer::getLoopMode, "Get loop mode")
      // State
      .def("get_state", &helxaid::MediaPlayer::getState, "Get playback state")
      .def("is_playing", &helxaid::MediaPlayer::isPlaying, "Check if playing")
      .def("get_position", &helxaid::MediaPlayer::getPosition,
           "Get position in seconds")
      .def("get_duration", &helxaid::MediaPlayer::getDuration,
           "Get duration in seconds")
      // Audio devices
      .def("get_audio_devices", &helxaid::MediaPlayer::getAudioDevices,
           "Get available audio devices")
      .def("set_audio_device", &helxaid::MediaPlayer::setAudioDevice,
           py::arg("device"), "Set audio output device")
      // Video
      .def("has_video", &helxaid::MediaPlayer::hasVideo,
           "Check if media has video")
      .def("set_video_enabled", &helxaid::MediaPlayer::setVideoEnabled,
           py::arg("enable"), "Enable/disable video")
      .def("is_video_enabled", &helxaid::MediaPlayer::isVideoEnabled,
           "Check if video is enabled")
      // Callbacks
      .def("set_position_callback", &helxaid::MediaPlayer::setPositionCallback,
           py::arg("callback"), "Set position update callback")
      .def("set_state_callback", &helxaid::MediaPlayer::setStateCallback,
           py::arg("callback"), "Set state change callback")
      .def("set_track_callback", &helxaid::MediaPlayer::setTrackCallback,
           py::arg("callback"), "Set track change callback")
      .def("set_error_callback", &helxaid::MediaPlayer::setErrorCallback,
           py::arg("callback"), "Set error callback");

  // ===== MediaPlayer static methods =====
  m.def("extract_metadata", &helxaid::MediaPlayer::extractMetadata,
        py::arg("path"), "Extract metadata from media file");

  m.def("scan_media_folder", &helxaid::MediaPlayer::scanFolder,
        py::arg("folder_path"), py::arg("recursive") = false,
        "Scan folder for media files and get track info");

  // ===== RAMInfo =====
  py::class_<helxaid::RAMInfo>(m, "RAMInfo", "RAM information structure")
      .def(py::init<>())
      .def_readonly("total_bytes", &helxaid::RAMInfo::totalBytes,
                    "Total physical memory in bytes")
      .def_readonly("used_bytes", &helxaid::RAMInfo::usedBytes,
                    "Used memory in bytes")
      .def_readonly("available_bytes", &helxaid::RAMInfo::availableBytes,
                    "Available memory in bytes")
      .def_readonly("percent_used", &helxaid::RAMInfo::percentUsed,
                    "Percentage of memory used")
      .def("total_gb", &helxaid::RAMInfo::totalGB, "Total memory in GB")
      .def("used_gb", &helxaid::RAMInfo::usedGB, "Used memory in GB")
      .def("available_gb", &helxaid::RAMInfo::availableGB,
           "Available memory in GB")
      .def("__repr__", [](const helxaid::RAMInfo &self) {
        return "<RAMInfo used=" + std::to_string(self.usedGB()) + "GB/" +
               std::to_string(self.totalGB()) + "GB (" +
               std::to_string(static_cast<int>(self.percentUsed)) + "%)>";
      });

  // ===== CPUInfo =====
  py::class_<helxaid::CPUInfo>(m, "CPUInfo", "CPU information structure")
      .def(py::init<>())
      .def_readonly("usage", &helxaid::CPUInfo::usage, "CPU usage percentage")
      .def_readonly("frequency_ghz", &helxaid::CPUInfo::frequencyGHz,
                    "Current frequency in GHz")
      .def_readonly("core_count", &helxaid::CPUInfo::coreCount,
                    "Number of cores")
      .def_readonly("thread_count", &helxaid::CPUInfo::threadCount,
                    "Number of threads")
      .def_readonly("name", &helxaid::CPUInfo::name, "CPU name")
      .def("__repr__", [](const helxaid::CPUInfo &self) {
        return "<CPUInfo '" + self.name +
               "' usage=" + std::to_string(static_cast<int>(self.usage)) + "%>";
      });

  // ===== DiskInfo =====
  py::class_<helxaid::DiskInfo>(m, "DiskInfo", "Disk information structure")
      .def(py::init<>())
      .def_readonly("drive", &helxaid::DiskInfo::drive, "Drive letter")
      .def_readonly("total_bytes", &helxaid::DiskInfo::totalBytes,
                    "Total size in bytes")
      .def_readonly("used_bytes", &helxaid::DiskInfo::usedBytes,
                    "Used size in bytes")
      .def_readonly("free_bytes", &helxaid::DiskInfo::freeBytes,
                    "Free size in bytes")
      .def_readonly("percent_used", &helxaid::DiskInfo::percentUsed,
                    "Percentage used")
      .def("total_gb", &helxaid::DiskInfo::totalGB, "Total size in GB")
      .def("used_gb", &helxaid::DiskInfo::usedGB, "Used size in GB")
      .def("free_gb", &helxaid::DiskInfo::freeGB, "Free size in GB")
      .def("__repr__", [](const helxaid::DiskInfo &self) {
        return "<DiskInfo '" + self.drive + "' " +
               std::to_string(self.usedGB()) + "GB/" +
               std::to_string(self.totalGB()) + "GB>";
      });

  // ===== RAMCleanResult =====
  py::class_<helxaid::RAMCleanResult>(m, "RAMCleanResult",
                                      "Result of RAM cleaning operation")
      .def(py::init<>())
      .def_readonly("process_count", &helxaid::RAMCleanResult::processCount,
                    "Number of processes cleaned")
      .def_readonly("bytes_freed", &helxaid::RAMCleanResult::bytesFreed,
                    "Bytes freed")
      .def_readonly("success", &helxaid::RAMCleanResult::success,
                    "Whether operation succeeded")
      .def_readonly("error", &helxaid::RAMCleanResult::error,
                    "Error message if failed")
      .def("mb_freed", &helxaid::RAMCleanResult::mbFreed, "MB freed")
      .def("gb_freed", &helxaid::RAMCleanResult::gbFreed, "GB freed")
      .def("__repr__", [](const helxaid::RAMCleanResult &self) {
        if (self.success) {
          return "<RAMCleanResult processes=" +
                 std::to_string(self.processCount) +
                 " freed=" + std::to_string(self.mbFreed()) + "MB>";
        } else {
          return "<RAMCleanResult success=False error='" + self.error + "'>";
        }
      });

  // ===== TempInfo =====
  py::class_<helxaid::TempInfo>(m, "TempInfo", "Temperature information")
      .def(py::init<>())
      .def_readonly("cpu_temp", &helxaid::TempInfo::cpuTemp,
                    "CPU temperature in Celsius")
      .def_readonly("gpu_temp", &helxaid::TempInfo::gpuTemp,
                    "GPU temperature in Celsius")
      .def_readonly("available", &helxaid::TempInfo::available,
                    "Whether temps are available");

  // ===== PriorityResult =====
  py::class_<helxaid::PriorityResult>(m, "PriorityResult",
                                      "Result of process priority operation")
      .def(py::init<>())
      .def_readonly("pid", &helxaid::PriorityResult::pid, "Process ID")
      .def_readonly("old_priority", &helxaid::PriorityResult::oldPriority,
                    "Previous priority class")
      .def_readonly("new_priority", &helxaid::PriorityResult::newPriority,
                    "New priority class")
      .def_readonly("success", &helxaid::PriorityResult::success,
                    "Whether operation succeeded")
      .def_readonly("error", &helxaid::PriorityResult::error,
                    "Error message if failed")
      .def("__repr__", [](const helxaid::PriorityResult &self) {
        if (self.success) {
          return "<PriorityResult pid=" + std::to_string(self.pid) +
                 " priority=" + std::to_string(self.newPriority) + ">";
        } else {
          return "<PriorityResult success=False error='" + self.error + "'>";
        }
      });

  // ===== WinKeyResult =====
  py::class_<helxaid::WinKeyResult>(m, "WinKeyResult",
                                    "Result of Windows key hook operation")
      .def(py::init<>())
      .def_readonly("disabled", &helxaid::WinKeyResult::disabled,
                    "Whether Windows key is disabled")
      .def_readonly("success", &helxaid::WinKeyResult::success,
                    "Whether operation succeeded")
      .def_readonly("error", &helxaid::WinKeyResult::error,
                    "Error message if failed");

  // ===== HardwareMonitor =====
  py::class_<helxaid::HardwareMonitor>(
      m, "HardwareMonitor",
      "Hardware monitoring and RAM cleaning functionality")
      .def(py::init<>(), "Create a new HardwareMonitor instance")
      .def("get_ram_info", &helxaid::HardwareMonitor::getRAMInfo,
           "Get RAM information")
      .def("clean_ram", &helxaid::HardwareMonitor::cleanRAM,
           "Clean RAM by emptying working sets of processes")
      .def("get_cpu_info", &helxaid::HardwareMonitor::getCPUInfo,
           "Get CPU information")
      .def("get_disk_info", &helxaid::HardwareMonitor::getDiskInfo,
           "Get disk information for all fixed drives")
      .def("get_temperatures", &helxaid::HardwareMonitor::getTemperatures,
           "Get CPU and GPU temperatures (may not be available)")
      // Essential Optimizations
      .def("set_process_priority",
           &helxaid::HardwareMonitor::setProcessPriority,
           py::arg("process_name"), py::arg("priority") = 4,
           "Set process priority (0=Idle, 1=BelowNormal, 2=Normal, "
           "3=AboveNormal, 4=High, 5=Realtime)")
      .def("restore_process_priority",
           &helxaid::HardwareMonitor::restoreProcessPriority, py::arg("pid"),
           "Restore process to original priority")
      .def("disable_windows_key", &helxaid::HardwareMonitor::disableWindowsKey,
           "Disable Windows key using low-level keyboard hook")
      .def("enable_windows_key", &helxaid::HardwareMonitor::enableWindowsKey,
           "Enable Windows key by removing keyboard hook")
      .def("is_windows_key_disabled",
           &helxaid::HardwareMonitor::isWindowsKeyDisabled,
           "Check if Windows key is currently disabled");

  // ===== Convenience functions =====
  m.def(
      "clean_ram",
      []() {
        helxaid::HardwareMonitor monitor;
        return monitor.cleanRAM();
      },
      "Quick RAM cleaning (convenience function)");

  m.def(
      "get_ram_info",
      []() {
        helxaid::HardwareMonitor monitor;
        return monitor.getRAMInfo();
      },
      "Quick RAM info (convenience function)");

  m.def(
      "get_cpu_info",
      []() {
        helxaid::HardwareMonitor monitor;
        return monitor.getCPUInfo();
      },
      "Quick CPU info (convenience function)");

  m.def(
      "get_disk_info",
      []() {
        helxaid::HardwareMonitor monitor;
        return monitor.getDiskInfo();
      },
      "Quick disk info (convenience function)");

  // ===== InputHook =====
  py::class_<helxaid::InputHook>(m, "InputHook")
      .def(py::init<>())
      .def("start", &helxaid::InputHook::start)
      .def("stop", &helxaid::InputHook::stop)
      .def("is_running", &helxaid::InputHook::isRunning)
      .def("set_mouse_callback", &helxaid::InputHook::setMouseCallback)
      .def("set_keyboard_callback", &helxaid::InputHook::setKeyboardCallback)
      .def("set_listen_to_move", &helxaid::InputHook::setListenToMove)
      .def("get_modifier_state", &helxaid::InputHook::getModifierState);

  py::class_<helxaid::MouseEvent>(m, "MouseEvent")
      .def_readonly("x", &helxaid::MouseEvent::x)
      .def_readonly("y", &helxaid::MouseEvent::y)
      .def_readonly("button", &helxaid::MouseEvent::button)
      .def_readonly("is_down", &helxaid::MouseEvent::isDown)
      .def_readonly("is_move", &helxaid::MouseEvent::isMove)
      .def_readonly("timestamp", &helxaid::MouseEvent::timestamp);

  py::enum_<helxaid::MouseButton>(m, "MouseButton")
      .value("None", helxaid::MouseButton::None)
      .value("Left", helxaid::MouseButton::Left)
      .value("Right", helxaid::MouseButton::Right)
      .value("Middle", helxaid::MouseButton::Middle)
      .value("X1", helxaid::MouseButton::X1)
      .value("X2", helxaid::MouseButton::X2)
      .export_values();

  py::class_<helxaid::KeyboardEvent>(m, "KeyboardEvent")
      .def_readonly("vk_code", &helxaid::KeyboardEvent::vkCode)
      .def_readonly("is_down", &helxaid::KeyboardEvent::isDown)
      .def_readonly("timestamp", &helxaid::KeyboardEvent::timestamp);

  // ===== MacroEngine =====
  py::class_<helxaid::MacroBinding>(m, "MacroBinding")
      .def(py::init<>())
      .def_readwrite("macro_id", &helxaid::MacroBinding::macroId)
      .def_readwrite("trigger_type", &helxaid::MacroBinding::triggerType)
      .def_readwrite("trigger_value", &helxaid::MacroBinding::triggerValue)
      .def_readwrite("event_type", &helxaid::MacroBinding::eventType)
      .def_readwrite("layer", &helxaid::MacroBinding::layer);

  py::class_<helxaid::NativeMacroEngine>(m, "NativeMacroEngine")
      .def(py::init<>())
      .def("add_binding", &helxaid::NativeMacroEngine::addBinding)
      .def("clear_bindings", &helxaid::NativeMacroEngine::clearBindings)
      .def("check_match_mouse",
           static_cast<std::string (helxaid::NativeMacroEngine::*)(
               const helxaid::MouseEvent &, const std::string &)>(
               &helxaid::NativeMacroEngine::checkMatch))
      .def("check_match_keyboard",
           static_cast<std::string (helxaid::NativeMacroEngine::*)(
               const helxaid::KeyboardEvent &, const std::string &)>(
               &helxaid::NativeMacroEngine::checkMatch));

  // ===== HIDController =====
  py::class_<helxaid::HIDController>(m, "HIDController")
      .def(py::init<>())
      .def("connect", &helxaid::HIDController::connect)
      .def("disconnect", &helxaid::HIDController::disconnect)
      .def("is_connected", &helxaid::HIDController::isConnected)
      .def("get_connection_type", &helxaid::HIDController::getConnectionType)
      .def("set_button_mapping", &helxaid::HIDController::setButtonMapping)
      .def("get_battery_level", &helxaid::HIDController::getBatteryLevel)
      .def("get_active_dpi_stage", &helxaid::HIDController::getActiveDpiStage);

  // ===== GameInfo =====
  py::class_<helxaid::GameInfo>(m, "GameInfo",
                                "Game information for detection engine")
      .def(py::init<>())
      .def_readwrite("name", &helxaid::GameInfo::name, "Display name")
      .def_readwrite("exe", &helxaid::GameInfo::exe, "Launcher exe full path")
      .def_readwrite("game_exe", &helxaid::GameInfo::game_exe,
                     "Comma-separated game exe names")
      .def_readwrite("app_type", &helxaid::GameInfo::app_type, "App type")
      .def("__repr__", [](const helxaid::GameInfo &self) {
        return "<GameInfo '" + self.name + "'>";
      });

  // ===== DetectionResult =====
  py::class_<helxaid::DetectionResult>(m, "DetectionResult",
                                       "Result of game detection scan")
      .def(py::init<>())
      .def_readonly("detected", &helxaid::DetectionResult::detected,
                    "Whether a game was detected")
      .def_readonly("game_name", &helxaid::DetectionResult::gameName,
                    "Name of detected game")
      .def_readonly("matched_exe", &helxaid::DetectionResult::matchedExe,
                    "Which exe name matched")
      .def_readonly("status", &helxaid::DetectionResult::status,
                    "game/launcher/unknown")
      .def_readonly("score", &helxaid::DetectionResult::score,
                    "Disambiguation score")
      .def("__repr__", [](const helxaid::DetectionResult &self) {
        if (self.detected) {
          return "<DetectionResult '" + self.gameName +
                 "' status=" + self.status + ">";
        }
        return std::string("<DetectionResult detected=False>");
      });

  // ===== SanitizeChange =====
  py::class_<helxaid::SanitizeChange>(
      m, "SanitizeChange", "Record of sanitization applied to a game")
      .def(py::init<>())
      .def_readonly("game_name", &helxaid::SanitizeChange::gameName,
                    "Which game was cleaned")
      .def_readonly("removed", &helxaid::SanitizeChange::removed,
                    "Exe names removed")
      .def_readonly("cleaned_game_exe",
                    &helxaid::SanitizeChange::cleanedGameExe,
                    "Resulting game_exe after cleanup")
      .def("__repr__", [](const helxaid::SanitizeChange &self) {
        return "<SanitizeChange '" + self.gameName +
               "' removed=" + std::to_string(self.removed.size()) + ">";
      });

  // ===== GameDetector =====
  py::class_<helxaid::GameDetector>(
      m, "GameDetector",
      "High-performance native game detection engine.\n"
      "Replaces Python psutil + win32gui with Windows ToolHelp32 + "
      "EnumWindows.")
      .def(py::init<>(), "Create a new GameDetector instance")
      // Game library management
      .def("set_game_library", &helxaid::GameDetector::setGameLibrary,
           py::arg("games"), "Set game library data from Python")
      .def("sanitize", &helxaid::GameDetector::sanitize,
           "Sanitize game_exe fields, returns list of changes")
      // Process scanner
      .def("start_process_scanner", &helxaid::GameDetector::startProcessScanner,
           py::arg("interval_ms") = 3000,
           "Start background process scanning thread")
      .def("stop_process_scanner", &helxaid::GameDetector::stopProcessScanner,
           "Stop background process scanning thread")
      .def("is_scanner_running", &helxaid::GameDetector::isScannerRunning,
           "Check if scanner is running")
      // Main detection
      .def("detect_running_game", &helxaid::GameDetector::detectRunningGame,
           "Two-pass game detection with disambiguation scoring")
      // Auto-learn
      .def("snapshot_processes", &helxaid::GameDetector::snapshotProcesses,
           "Take pre-launch process snapshot")
      .def("learn_new_processes", &helxaid::GameDetector::learnNewProcesses,
           py::arg("game_name"), py::arg("launch_exe_path"),
           "Diff processes and return new game exes")
      // Process queries
      .def("is_process_running", &helxaid::GameDetector::isProcessRunning,
           py::arg("exe_name"), "Check if process is running")
      .def("get_running_processes", &helxaid::GameDetector::getRunningProcesses,
           "Get all running process names")
      .def("get_process_paths", &helxaid::GameDetector::getProcessPaths,
           py::arg("exe_name"), "Get full paths for a process")
      // Window queries
      .def("get_window_titles",
           &helxaid::GameDetector::getWindowTitlesForProcess,
           py::arg("exe_name"), "Get window titles for process")
      .def("check_game_status", &helxaid::GameDetector::checkGameStatus,
           py::arg("game"), "Check if game/launcher/unknown");

  // ===== ServiceStopResult =====
  py::class_<helxaid::ServiceStopResult>(
      m, "ServiceStopResult", "Result of stopping a single Windows service")
      .def(py::init<>())
      .def_readonly("name", &helxaid::ServiceStopResult::name,
                    "Service internal name")
      .def_readonly("display_name", &helxaid::ServiceStopResult::displayName,
                    "Human-readable name")
      .def_readonly("category", &helxaid::ServiceStopResult::category,
                    "basic/advanced/essential")
      .def_readonly("success", &helxaid::ServiceStopResult::success,
                    "Whether stop succeeded")
      .def_readonly("status", &helxaid::ServiceStopResult::status,
                    "OK/ALREADY_STOPPED/FAIL/TIMEOUT")
      .def("__repr__", [](const helxaid::ServiceStopResult &self) {
        return "<ServiceStopResult '" + self.name + "' " + self.status + ">";
      });

  // ===== ProcessKillResult =====
  py::class_<helxaid::ProcessKillResult>(m, "ProcessKillResult",
                                         "Result of killing a process")
      .def(py::init<>())
      .def_readonly("name", &helxaid::ProcessKillResult::name, "Process name")
      .def_readonly("total_pids", &helxaid::ProcessKillResult::totalPids,
                    "Number of PIDs found")
      .def_readonly("killed_pids", &helxaid::ProcessKillResult::killedPids,
                    "Number of PIDs terminated")
      .def_readonly("success", &helxaid::ProcessKillResult::success,
                    "Whether kill succeeded")
      .def("__repr__", [](const helxaid::ProcessKillResult &self) {
        return "<ProcessKillResult '" + self.name +
               "' killed=" + std::to_string(self.killedPids) + "/" +
               std::to_string(self.totalPids) + ">";
      });

  // ===== ServiceStatus =====
  py::class_<helxaid::ServiceStatus>(m, "ServiceStatus",
                                     "Current status of a Windows service")
      .def(py::init<>())
      .def_readonly("name", &helxaid::ServiceStatus::name,
                    "Service internal name")
      .def_readonly("status", &helxaid::ServiceStatus::status,
                    "Running/Stopped/Unknown/Not Found")
      .def_readonly("is_running", &helxaid::ServiceStatus::isRunning,
                    "Whether service is currently running")
      .def("__repr__", [](const helxaid::ServiceStatus &self) {
        return "<ServiceStatus '" + self.name + "' " + self.status + ">";
      });

  // ===== ServiceEntry =====
  py::class_<helxaid::ServiceEntry>(m, "ServiceEntry",
                                    "Service entry for batch operations")
      .def(py::init<>())
      .def(py::init([](const std::string &name, const std::string &display,
                       const std::string &cat) {
             helxaid::ServiceEntry e;
             e.name = name;
             e.displayName = display;
             e.category = cat;
             return e;
           }),
           py::arg("name"), py::arg("display_name"), py::arg("category"))
      .def_readwrite("name", &helxaid::ServiceEntry::name)
      .def_readwrite("display_name", &helxaid::ServiceEntry::displayName)
      .def_readwrite("category", &helxaid::ServiceEntry::category);

  // ===== BoostEngine =====
  py::class_<helxaid::BoostEngine>(
      m, "BoostEngine",
      "Native game boost engine for service/process management.\n"
      "Uses Win32 APIs for process termination and Service Control Manager\n"
      "for status queries. Service stopping uses a scheduled task to avoid\n"
      "per-boost UAC prompts.")
      .def(py::init<>(), "Create a new BoostEngine instance")
      // Scheduled task
      .def("ensure_task_exists", &helxaid::BoostEngine::ensureTaskExists,
           py::arg("task_name"), py::arg("script_path"),
           "Ensure scheduled task exists (may trigger UAC on first call)")
      .def("is_task_ready", &helxaid::BoostEngine::isTaskReady,
           py::arg("task_name"),
           "Check if scheduled task exists with correct version")
      // Service operations
      .def("stop_services", &helxaid::BoostEngine::stopServices,
           py::arg("services"), py::arg("task_name"),
           "Stop services via scheduled task, returns per-service results")
      .def("query_service_statuses",
           &helxaid::BoostEngine::queryServiceStatuses,
           py::arg("service_names"),
           "Query service statuses using SC Manager (no admin needed)")
      // Process operations
      .def("kill_processes", &helxaid::BoostEngine::killProcesses,
           py::arg("process_names"),
           "Terminate processes by name using Win32 API")
      // Script management
      .def("write_boost_script", &helxaid::BoostEngine::writeBoostScript,
           py::arg("script_path"), py::arg("input_path"), py::arg("log_path"),
           "Write/update the PowerShell script for the scheduled task");

  // ===== BoostEngine convenience functions =====
  m.def(
      "query_service_status",
      [](const std::string &serviceName) {
        helxaid::BoostEngine engine;
        auto results = engine.queryServiceStatuses({serviceName});
        if (!results.empty())
          return results[0];
        helxaid::ServiceStatus s;
        s.name = serviceName;
        s.status = "Unknown";
        return s;
      },
      py::arg("service_name"),
      "Quick service status query (convenience function)");

  m.def(
      "kill_process",
      [](const std::string &processName) {
        helxaid::BoostEngine engine;
        auto results = engine.killProcesses({processName});
        if (!results.empty())
          return results[0];
        helxaid::ProcessKillResult r;
        r.name = processName;
        return r;
      },
      py::arg("process_name"), "Quick process kill (convenience function)");

  // Version constant for task compatibility
  m.attr("BOOST_TASK_VERSION") = helxaid::BoostEngine::TASK_VERSION;
}
