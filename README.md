# HELXAID

![Status](https://img.shields.io/badge/status-active_development-blue)

**HELXAID** is an actively developed desktop utility suite for gamers and power users.  
It combines a game launcher, overlay tools, system controls, and automation features into a single unified platform.

---

## Overview

HELXAID is designed to reduce tool fragmentation.  
Instead of running multiple separate applications for launching games, controlling system performance, managing media, and using overlays or macros, HELXAID provides a centralized control layer.

The project is modular by design, allowing each component to evolve independently while sharing a common core.

---

## Components

HELXAID currently consists of the following main components, each operating as a focused module:

- **HELXAID** (Game Launcher)  
  Core hub for game library management and universal launching.

- **HELXAIC** (Music Player)  
  Integrated local media player acting as your gaming background soundtrack.

- **HELXAIL** (CPU Controller)  
  System-level processor management integrating with tools like RyzenAdj.

- **HELXAIR** (Crosshair Overlay)  
  In-game custom crosshair layer to aid in first-person shooters.

- **HELXAIRO** (Macro Setting)  
  Hardware key mapping and input sequence automation.

- **HELXTATS** (Stats & Monitoring)  
  Hardware monitoring suite integrating PC booster, CPU stats, and driver health.

---

## Modules & Progress

| Module | Status |
|------|------|
| HELXAID (Game Launcher) | ~95% |
| HELXAIC (Music Player) | ~90% |
| HELXAIL (CPU Controller) | ~90% |
| HELXAIR (Crosshair Overlay) | ~100% | (New Feature Maybe?)
| HELXAIRO (Macro Setting) | ~74% | 
| HELXTATS (System Monitoring & Cleaning) | ~50% | (Driver Cleaner didnt applied yet)
| System Optimization (OMEN AI like concept) | Planned |

---

## Feature Notes

### HELXAID (Game Launcher)
- Scan and manage Steam & Google Play Games libraries automatically
- Manage local custom game folders
- Track playtime and automatically fetch game icons and background metadata

### HELXAIC (Music Player)
- Play local audio and video files (MP3, WAV, FLAC, MP4) as background music
- Modern, animated Spotify-style playlist interface with smooth column sorting
- Auto-extracts file metadata, playback duration, and album cover art
- Built-in volume, repeat/shuffle, and video background fit controls

### HELXAIL (CPU Controller)
- CPU control via RyzenAdj
- Accessible only when required tools (RyzenAdj / UXTU) are available
- Debug handling when required dependencies are missing

### HELXAIR (Crosshair Overlay)
- Customizable on-screen crosshair overlay (color, size, opacity)
- Works without hooking into game memory (safer for anti-cheats)

### HELXAIRO (Macro Setting)
- Map hardware keys to custom sequences and mouse inputs (integrated natively with C++)
- Control DPI, rapid fire, and basic multimedia actions

### HELXTATS (System Monitoring & Cleaning)
- Real-time Hardware stats (CPU, GPU, RAM) tracking
- Memory (RAM) cleaning optimization capabilities

---

## Known Issues

This project is under active development and contains known limitations:

- Application may freeze for several minutes when adding a large number of games
- Some UI elements overlap at certain sizes
- Certain fields should be empty on first launch but are not yet fully enforced

---

## Changelog

### v4.6
- Ensure only one launcher instance runs at a time
- Game library defaults to empty on first launch
- Bulk action delete text fixed

### v4.7
- Improved first-launch state handling
- CPU Controller access restricted based on tool availability
- Added debug feedback when RyzenAdj is missing
- Macro state resets on first launch

### v4.8
- Universal Scan (combines Steam & Google Play Games library scanning)
- Check for Updates functionality via GitHub releases
- Settings persistence fix (migrated to `%APPDATA%\HELXAID`)
- Installer now defaults to `C:\Program Files` with Administrator privileges
- Fullscreen (F11) and window maximize state behavior fixes

---

## Development Status

HELXAID is under active development.  
Features, APIs, and internal structures may change as the project evolves.

This project prioritizes:
- Modular architecture
- Low system overhead
- Long-term maintainability
- Practical system control over visual gimmicks

---

## Platform

- Windows
- Built primarily with Python, HTML, CSS and JS

---

## Disclaimer

This project is experimental and intended for personal or advanced user use.  
Use at your own discretion.
