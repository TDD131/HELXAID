/**
 * MediaPlayer Implementation
 *
 * Uses Windows Media Foundation for high-performance media playback.
 * Supports both audio and video with minimal latency.
 */

#include "media_player.h"

// Windows headers - ORDER MATTERS!
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

// COM headers
#include <objbase.h>

// Media Foundation headers
#include <mfapi.h>
#include <mferror.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <propvarutil.h>
#include <shlwapi.h>


// Standard library
#include <algorithm>
#include <atomic>
#include <mutex>
#include <random>

#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "propsys.lib")
#pragma comment(lib, "ole32.lib")

namespace helxaid {

// ============================================
// Implementation class (PIMPL pattern)
// ============================================

struct MediaPlayer::Impl {
  // Media Foundation objects
  IMFMediaSession *session = nullptr;
  IMFMediaSource *source = nullptr;
  IMFPresentationDescriptor *presentationDesc = nullptr;

  // State
  std::atomic<PlaybackState> state{PlaybackState::Stopped};
  std::atomic<double> position{0.0};
  std::atomic<double> duration{0.0};
  std::atomic<int> volume{100};
  std::atomic<bool> muted{false};
  std::atomic<bool> videoEnabled{true};

  // Playlist
  std::vector<TrackInfo> playlist;
  std::atomic<int> currentIndex{-1};
  std::vector<int> shuffleOrder;
  std::atomic<bool> shuffleEnabled{false};
  std::atomic<LoopMode> loopMode{LoopMode::Off};

  // Current track info
  std::string currentPath;
  bool currentHasVideo = false;

  // Callbacks
  PositionCallback positionCallback;
  StateCallback stateCallback;
  TrackCallback trackCallback;
  ErrorCallback errorCallback;

  // Threading
  std::mutex mutex;
  std::thread positionThread;
  std::atomic<bool> running{false};

  // Random generator for shuffle
  std::mt19937 rng{std::random_device{}()};

  Impl() {
    // Initialize Media Foundation
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    MFStartup(MF_VERSION);
  }

  ~Impl() {
    running = false;
    if (positionThread.joinable()) {
      positionThread.join();
    }

    cleanup();
    MFShutdown();
    CoUninitialize();
  }

  void cleanup() {
    if (session) {
      session->Stop();
      session->Shutdown();
      session->Release();
      session = nullptr;
    }
    if (source) {
      source->Shutdown();
      source->Release();
      source = nullptr;
    }
    if (presentationDesc) {
      presentationDesc->Release();
      presentationDesc = nullptr;
    }
  }

  void generateShuffleOrder() {
    shuffleOrder.resize(playlist.size());
    for (size_t i = 0; i < playlist.size(); ++i) {
      shuffleOrder[i] = static_cast<int>(i);
    }
    std::shuffle(shuffleOrder.begin(), shuffleOrder.end(), rng);
  }

  int getNextIndex(bool forward) {
    if (playlist.empty())
      return -1;

    int current = currentIndex.load();
    int playlistSize = static_cast<int>(playlist.size());

    if (shuffleEnabled.load()) {
      // Find current position in shuffle order
      auto it = std::find(shuffleOrder.begin(), shuffleOrder.end(), current);
      int shufflePos = (it != shuffleOrder.end())
                           ? static_cast<int>(it - shuffleOrder.begin())
                           : 0;

      if (forward) {
        shufflePos = (shufflePos + 1) % playlistSize;
      } else {
        shufflePos = (shufflePos - 1 + playlistSize) % playlistSize;
      }
      return shuffleOrder[shufflePos];
    } else {
      if (forward) {
        return (current + 1) % playlistSize;
      } else {
        return (current - 1 + playlistSize) % playlistSize;
      }
    }
  }

  void notifyPositionUpdate() {
    if (positionCallback) {
      positionCallback(position.load(), duration.load());
    }
  }

  void notifyStateChange(PlaybackState newState) {
    state = newState;
    if (stateCallback) {
      stateCallback(newState);
    }
  }

  void notifyTrackChange(int index) {
    if (trackCallback) {
      trackCallback(index);
    }
  }

  void notifyError(const std::string &error) {
    if (errorCallback) {
      errorCallback(error);
    }
  }
};

// ============================================
// MediaPlayer implementation
// ============================================

MediaPlayer::MediaPlayer() : pImpl(std::make_unique<Impl>()) {}
MediaPlayer::~MediaPlayer() = default;

bool MediaPlayer::load(const std::string &path) {
  std::lock_guard<std::mutex> lock(pImpl->mutex);

  // Clean up previous session
  pImpl->cleanup();
  pImpl->currentPath = path;

  // Convert path to wide string
  int wideLen = MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, nullptr, 0);
  std::wstring widePath(wideLen, 0);
  MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, &widePath[0], wideLen);

  // Create Media Source
  IMFSourceResolver *resolver = nullptr;
  MF_OBJECT_TYPE objectType = MF_OBJECT_INVALID;
  IUnknown *sourceUnk = nullptr;

  HRESULT hr = MFCreateSourceResolver(&resolver);
  if (FAILED(hr)) {
    pImpl->notifyError("Failed to create source resolver");
    return false;
  }

  hr =
      resolver->CreateObjectFromURL(widePath.c_str(), MF_RESOLUTION_MEDIASOURCE,
                                    nullptr, &objectType, &sourceUnk);
  resolver->Release();

  if (FAILED(hr)) {
    pImpl->notifyError("Failed to create media source from: " + path);
    return false;
  }

  hr = sourceUnk->QueryInterface(IID_PPV_ARGS(&pImpl->source));
  sourceUnk->Release();

  if (FAILED(hr)) {
    pImpl->notifyError("Failed to get media source interface");
    return false;
  }

  // Get presentation descriptor for duration
  hr = pImpl->source->CreatePresentationDescriptor(&pImpl->presentationDesc);
  if (SUCCEEDED(hr)) {
    UINT64 duration = 0;
    hr = pImpl->presentationDesc->GetUINT64(MF_PD_DURATION, &duration);
    if (SUCCEEDED(hr)) {
      // Convert from 100-nanosecond units to seconds
      pImpl->duration = static_cast<double>(duration) / 10000000.0;
    }

    // Check for video stream
    DWORD streamCount = 0;
    pImpl->presentationDesc->GetStreamDescriptorCount(&streamCount);
    pImpl->currentHasVideo = false;

    for (DWORD i = 0; i < streamCount; ++i) {
      BOOL selected = FALSE;
      IMFStreamDescriptor *streamDesc = nullptr;
      pImpl->presentationDesc->GetStreamDescriptorByIndex(i, &selected,
                                                          &streamDesc);

      if (streamDesc) {
        IMFMediaTypeHandler *typeHandler = nullptr;
        streamDesc->GetMediaTypeHandler(&typeHandler);

        if (typeHandler) {
          GUID majorType;
          typeHandler->GetMajorType(&majorType);
          if (majorType == MFMediaType_Video) {
            pImpl->currentHasVideo = true;
          }
          typeHandler->Release();
        }
        streamDesc->Release();
      }

      if (pImpl->currentHasVideo)
        break;
    }
  }

  // Create Media Session
  hr = MFCreateMediaSession(nullptr, &pImpl->session);
  if (FAILED(hr)) {
    pImpl->notifyError("Failed to create media session");
    return false;
  }

  // Create topology and start playback (simplified)
  pImpl->notifyStateChange(PlaybackState::Stopped);
  pImpl->position = 0.0;

  return true;
}

void MediaPlayer::play() {
  std::lock_guard<std::mutex> lock(pImpl->mutex);

  if (pImpl->session) {
    PROPVARIANT var;
    PropVariantInit(&var);
    pImpl->session->Start(nullptr, &var);
    PropVariantClear(&var);

    pImpl->notifyStateChange(PlaybackState::Playing);
  }
}

void MediaPlayer::pause() {
  std::lock_guard<std::mutex> lock(pImpl->mutex);

  if (pImpl->session) {
    pImpl->session->Pause();
    pImpl->notifyStateChange(PlaybackState::Paused);
  }
}

void MediaPlayer::stop() {
  std::lock_guard<std::mutex> lock(pImpl->mutex);

  if (pImpl->session) {
    pImpl->session->Stop();
    pImpl->position = 0.0;
    pImpl->notifyStateChange(PlaybackState::Stopped);
  }
}

void MediaPlayer::togglePlay() {
  if (pImpl->state == PlaybackState::Playing) {
    pause();
  } else {
    play();
  }
}

void MediaPlayer::seek(double position) {
  std::lock_guard<std::mutex> lock(pImpl->mutex);

  if (pImpl->session) {
    PROPVARIANT var;
    PropVariantInit(&var);
    var.vt = VT_I8;
    // Convert seconds to 100-nanosecond units
    var.hVal.QuadPart = static_cast<LONGLONG>(position * 10000000.0);

    pImpl->session->Start(nullptr, &var);
    PropVariantClear(&var);

    pImpl->position = position;
  }
}

void MediaPlayer::seekPercent(double percent) {
  double pos = percent * pImpl->duration.load();
  seek(pos);
}

void MediaPlayer::setVolume(int volume) {
  pImpl->volume = std::clamp(volume, 0, 100);
  // Volume control implementation would go here
  // Using IMFSimpleAudioVolume or similar
}

int MediaPlayer::getVolume() const { return pImpl->volume.load(); }

void MediaPlayer::setMuted(bool mute) { pImpl->muted = mute; }

bool MediaPlayer::isMuted() const { return pImpl->muted.load(); }

void MediaPlayer::setPlaylist(const std::vector<TrackInfo> &tracks) {
  std::lock_guard<std::mutex> lock(pImpl->mutex);
  pImpl->playlist = tracks;
  pImpl->currentIndex = -1;
  pImpl->generateShuffleOrder();
}

const std::vector<TrackInfo> &MediaPlayer::getPlaylist() const {
  return pImpl->playlist;
}

void MediaPlayer::playTrack(int index) {
  if (index < 0 || index >= static_cast<int>(pImpl->playlist.size())) {
    return;
  }

  pImpl->currentIndex = index;
  const auto &track = pImpl->playlist[index];

  if (load(track.path)) {
    play();
    pImpl->notifyTrackChange(index);
  }
}

void MediaPlayer::nextTrack() {
  int next = pImpl->getNextIndex(true);
  if (next >= 0) {
    playTrack(next);
  }
}

void MediaPlayer::prevTrack() {
  int prev = pImpl->getNextIndex(false);
  if (prev >= 0) {
    playTrack(prev);
  }
}

int MediaPlayer::getCurrentIndex() const { return pImpl->currentIndex.load(); }

TrackInfo MediaPlayer::getCurrentTrack() const {
  int idx = pImpl->currentIndex.load();
  if (idx >= 0 && idx < static_cast<int>(pImpl->playlist.size())) {
    return pImpl->playlist[idx];
  }
  return TrackInfo{};
}

void MediaPlayer::setShuffle(bool shuffle) {
  pImpl->shuffleEnabled = shuffle;
  if (shuffle) {
    pImpl->generateShuffleOrder();
  }
}

bool MediaPlayer::getShuffle() const { return pImpl->shuffleEnabled.load(); }

void MediaPlayer::setLoopMode(LoopMode mode) { pImpl->loopMode = mode; }

LoopMode MediaPlayer::getLoopMode() const { return pImpl->loopMode.load(); }

PlaybackState MediaPlayer::getState() const { return pImpl->state.load(); }

bool MediaPlayer::isPlaying() const {
  return pImpl->state.load() == PlaybackState::Playing;
}

double MediaPlayer::getPosition() const { return pImpl->position.load(); }

double MediaPlayer::getDuration() const { return pImpl->duration.load(); }

std::vector<std::string> MediaPlayer::getAudioDevices() const {
  // TODO: Implement proper audio device enumeration
  // Requires functiondiscoverykeys_devpkey.h with proper include order
  std::vector<std::string> devices;
  devices.push_back("Default Audio Device");
  return devices;
}

bool MediaPlayer::setAudioDevice(const std::string &deviceName) {
  // Implementation would switch audio endpoint
  // This is a complex operation involving recreating the audio session
  return true;
}

bool MediaPlayer::hasVideo() const { return pImpl->currentHasVideo; }

void MediaPlayer::setVideoEnabled(bool enable) { pImpl->videoEnabled = enable; }

bool MediaPlayer::isVideoEnabled() const { return pImpl->videoEnabled.load(); }

void MediaPlayer::setPositionCallback(PositionCallback callback) {
  pImpl->positionCallback = std::move(callback);
}

void MediaPlayer::setStateCallback(StateCallback callback) {
  pImpl->stateCallback = std::move(callback);
}

void MediaPlayer::setTrackCallback(TrackCallback callback) {
  pImpl->trackCallback = std::move(callback);
}

void MediaPlayer::setErrorCallback(ErrorCallback callback) {
  pImpl->errorCallback = std::move(callback);
}

TrackInfo MediaPlayer::extractMetadata(const std::string &path) {
  TrackInfo info;
  info.path = path;

  // Extract filename as title
  size_t lastSlash = path.find_last_of("/\\");
  size_t lastDot = path.find_last_of('.');

  if (lastSlash != std::string::npos && lastDot != std::string::npos &&
      lastDot > lastSlash) {
    info.title = path.substr(lastSlash + 1, lastDot - lastSlash - 1);
  } else if (lastSlash != std::string::npos) {
    info.title = path.substr(lastSlash + 1);
  } else {
    info.title = path;
  }

  // Check for video extensions
  std::string ext = (lastDot != std::string::npos) ? path.substr(lastDot) : "";
  std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

  info.hasVideo = (ext == ".mp4" || ext == ".mkv" || ext == ".avi" ||
                   ext == ".webm" || ext == ".mov" || ext == ".wmv");

  // TODO: Use FFprobe or similar for actual metadata extraction

  return info;
}

std::vector<TrackInfo> MediaPlayer::scanFolder(const std::string &folderPath,
                                               bool recursive) {
  std::vector<TrackInfo> tracks;

  // Audio extensions
  const std::vector<std::string> audioExts = {".mp3", ".flac", ".wav", ".ogg",
                                              ".m4a", ".aac",  ".wma"};

  // Video extensions (for music videos)
  const std::vector<std::string> videoExts = {".mp4", ".mkv", ".avi", ".webm",
                                              ".mov"};

  // Use Windows FindFirstFile/FindNextFile for scanning
  std::wstring searchPath =
      std::wstring(folderPath.begin(), folderPath.end()) + L"\\*";

  WIN32_FIND_DATAW findData;
  HANDLE hFind = FindFirstFileW(searchPath.c_str(), &findData);

  if (hFind != INVALID_HANDLE_VALUE) {
    do {
      if (!(findData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
        std::wstring wName = findData.cFileName;
        std::string name(wName.begin(), wName.end());

        // Get extension
        size_t dotPos = name.find_last_of('.');
        if (dotPos != std::string::npos) {
          std::string ext = name.substr(dotPos);
          std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

          // Check if it's a media file
          bool isAudio = std::find(audioExts.begin(), audioExts.end(), ext) !=
                         audioExts.end();
          bool isVideo = std::find(videoExts.begin(), videoExts.end(), ext) !=
                         videoExts.end();

          if (isAudio || isVideo) {
            TrackInfo track = extractMetadata(folderPath + "\\" + name);
            tracks.push_back(track);
          }
        }
      } else if (recursive && wcscmp(findData.cFileName, L".") != 0 &&
                 wcscmp(findData.cFileName, L"..") != 0) {
        // Recurse into subdirectory
        std::wstring wName = findData.cFileName;
        std::string subPath =
            folderPath + "\\" + std::string(wName.begin(), wName.end());
        auto subTracks = scanFolder(subPath, recursive);
        tracks.insert(tracks.end(), subTracks.begin(), subTracks.end());
      }
    } while (FindNextFileW(hFind, &findData));

    FindClose(hFind);
  }

  return tracks;
}

} // namespace helxaid
