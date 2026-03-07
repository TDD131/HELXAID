#pragma once

#include <functional>
#include <memory>
#include <string>
#include <vector>


// Forward declarations for Qt types (to avoid Qt dependency in header)
// Actual Qt includes will be in the .cpp file

namespace helxaid {

/**
 * Track metadata structure
 */
struct TrackInfo {
  std::string path;
  std::string title;
  std::string artist;
  std::string album;
  double duration = 0.0; // Duration in seconds
  bool hasVideo = false; // True if file contains video stream
  std::string dateAdded; // ISO date string
};

/**
 * Playback state enumeration
 */
enum class PlaybackState { Stopped, Playing, Paused };

/**
 * Loop mode enumeration
 */
enum class LoopMode {
  Off, // No looping
  All, // Loop entire playlist
  One  // Loop single track
};

/**
 * MediaPlayer class
 *
 * High-performance media player for audio and video playback.
 * Uses native Windows APIs for optimal performance.
 *
 * Features:
 * - Audio playback with volume control
 * - Video playback support
 * - Seek/position tracking
 * - Playlist management
 * - Shuffle and loop modes
 * - Audio output device selection
 */
class MediaPlayer {
public:
  // Callback types
  using PositionCallback = std::function<void(double current, double total)>;
  using StateCallback = std::function<void(PlaybackState state)>;
  using TrackCallback = std::function<void(int index)>;
  using ErrorCallback = std::function<void(const std::string &error)>;

  MediaPlayer();
  ~MediaPlayer();

  // Prevent copying
  MediaPlayer(const MediaPlayer &) = delete;
  MediaPlayer &operator=(const MediaPlayer &) = delete;

  // ==========================================
  // Playback Control
  // ==========================================

  /**
   * Load and play a media file
   * @param path Path to the media file
   * @return true if successfully loaded
   */
  bool load(const std::string &path);

  /**
   * Play/resume playback
   */
  void play();

  /**
   * Pause playback
   */
  void pause();

  /**
   * Stop playback
   */
  void stop();

  /**
   * Toggle play/pause
   */
  void togglePlay();

  /**
   * Seek to position
   * @param position Position in seconds
   */
  void seek(double position);

  /**
   * Seek to percentage
   * @param percent Position as percentage (0.0 - 1.0)
   */
  void seekPercent(double percent);

  // ==========================================
  // Volume Control
  // ==========================================

  /**
   * Set volume level
   * @param volume Volume level (0-100)
   */
  void setVolume(int volume);

  /**
   * Get current volume level
   * @return Volume level (0-100)
   */
  int getVolume() const;

  /**
   * Set mute state
   * @param mute True to mute
   */
  void setMuted(bool mute);

  /**
   * Get mute state
   * @return True if muted
   */
  bool isMuted() const;

  // ==========================================
  // Playlist Management
  // ==========================================

  /**
   * Set playlist
   * @param tracks Vector of track info
   */
  void setPlaylist(const std::vector<TrackInfo> &tracks);

  /**
   * Get current playlist
   * @return Vector of track info
   */
  const std::vector<TrackInfo> &getPlaylist() const;

  /**
   * Play track at index
   * @param index Track index in playlist
   */
  void playTrack(int index);

  /**
   * Play next track
   */
  void nextTrack();

  /**
   * Play previous track
   */
  void prevTrack();

  /**
   * Get current track index
   * @return Current track index, -1 if none
   */
  int getCurrentIndex() const;

  /**
   * Get current track info
   * @return Current track info, empty if none
   */
  TrackInfo getCurrentTrack() const;

  // ==========================================
  // Playback Modes
  // ==========================================

  /**
   * Set shuffle mode
   * @param shuffle True to enable shuffle
   */
  void setShuffle(bool shuffle);

  /**
   * Get shuffle mode
   * @return True if shuffle is enabled
   */
  bool getShuffle() const;

  /**
   * Set loop mode
   * @param mode Loop mode
   */
  void setLoopMode(LoopMode mode);

  /**
   * Get loop mode
   * @return Current loop mode
   */
  LoopMode getLoopMode() const;

  // ==========================================
  // State Queries
  // ==========================================

  /**
   * Get playback state
   * @return Current playback state
   */
  PlaybackState getState() const;

  /**
   * Check if currently playing
   * @return True if playing
   */
  bool isPlaying() const;

  /**
   * Get current position
   * @return Position in seconds
   */
  double getPosition() const;

  /**
   * Get total duration
   * @return Duration in seconds
   */
  double getDuration() const;

  // ==========================================
  // Audio Device
  // ==========================================

  /**
   * Get available audio output devices
   * @return Vector of device names
   */
  std::vector<std::string> getAudioDevices() const;

  /**
   * Set audio output device
   * @param deviceName Name of the device
   * @return True if successfully set
   */
  bool setAudioDevice(const std::string &deviceName);

  // ==========================================
  // Video Support
  // ==========================================

  /**
   * Check if current media has video
   * @return True if video available
   */
  bool hasVideo() const;

  /**
   * Enable/disable video output
   * @param enable True to enable video
   */
  void setVideoEnabled(bool enable);

  /**
   * Check if video output is enabled
   * @return True if video enabled
   */
  bool isVideoEnabled() const;

  // ==========================================
  // Callbacks
  // ==========================================

  /**
   * Set position update callback
   * @param callback Called with (current, total) in seconds
   */
  void setPositionCallback(PositionCallback callback);

  /**
   * Set state change callback
   * @param callback Called when playback state changes
   */
  void setStateCallback(StateCallback callback);

  /**
   * Set track change callback
   * @param callback Called when track changes
   */
  void setTrackCallback(TrackCallback callback);

  /**
   * Set error callback
   * @param callback Called on playback errors
   */
  void setErrorCallback(ErrorCallback callback);

  // ==========================================
  // Metadata
  // ==========================================

  /**
   * Extract metadata from a file
   * @param path Path to media file
   * @return TrackInfo with metadata
   */
  static TrackInfo extractMetadata(const std::string &path);

  /**
   * Scan folder for media files
   * @param folderPath Path to folder
   * @param recursive Scan subfolders
   * @return Vector of TrackInfo
   */
  static std::vector<TrackInfo> scanFolder(const std::string &folderPath,
                                           bool recursive = false);

private:
  struct Impl;
  std::unique_ptr<Impl> pImpl;
};

} // namespace helxaid
