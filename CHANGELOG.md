# Changelog - HELXAID

All notable changes, architectural updates, and version releases for HELXAID are documented in this file.

---

## [v4.14.1] - Active Release

### Added
- Native C++ Image Engine integration for ultra-fast asset loading and reduced RAM footprint.
- DirectStream Hub and Cloud Authentication subsystem for stream management.
- Dynamic Taskbar Media Widget synchronized with audio visualizer frequency bars.
- Enhanced lyrics synchronization engine in HELXAIC.

### Fixed
- Fixed audio duration timing discrepancies and memory consumption during long sessions.
- Fixed taskbar controls and Pan & Crop cover image alignment.
- Resolved build size bloat by decoupling unnecessary web engine dependencies.

---

## [v4.14.0]

### Added
- Added quick panel navigation shortcut keys (1-6) for rapid panel switching.
- Added Open File shortcut key (`Ctrl + O`) in HELXAIC.
- Remapped Open Folder shortcut key from `Ctrl + O` to `Ctrl + K + O`.
- Added editable cover art functionality in HELXAIC media player.
- Persisted Shuffle and Loop modes across application restarts.

### Changed
- Migrated audio playback backend to QMediaPlayer for enhanced stability.
- Improved playback duration tracking precision.

### Fixed
- Fixed icon hover-effect visual glitches in HELXAID.
- Fixed unexpected crashes when pasting URLs in YouTube Downloader.
- Fixed version display string consistency across internal modules.

---

## [v4.13.0]

### Added
- Added Estimated File Size calculation in YouTube Downloader.
- Added `--no-playlist` flag to restrict downloads to single target video when copying playlist URLs.
- Converted YouTube Downloader from floating window into an embedded panel with real-time thumbnail preview.

### Changed
- Upgraded network traffic and data usage detection algorithms.

### Fixed
- Fixed playback duration seek bar synchronization issues.

---

## [v4.12.0]

### Added
- Expanded Universal Game Scan support (Epic Games, GOG Galaxy, Ubisoft Connect, Riot Games, EA App).
- Added comprehensive Network Monitoring tab in HELXTATS:
  - Network Interface Name, IP, MAC Address, Speed, Status, Type, and Up Time.
  - Real-time tracking of Bytes/Packets Sent & Received, Errors, and Collisions.

### Changed
- Transformed "Hardware Health" module into unified "System Vital" dashboard.
- Replaced legacy "Fan" tab with dedicated "Network" tab.

### Fixed
- Fixed "Update Interval" label leaking into unintended tabs (now restricted to Quick Setup, CPU, Drive, and System Vital).
