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

HELXAID currently consists of the following main components:

- **HELXAID Launcher**  
  Game library management and launching system.

- **HELXAID Overlay**  
  In-game overlay features such as crosshair and future HUD utilities.

- **HELXAID Control**  
  System-level utilities and performance controls.

---

## Modules & Progress

| Module | Status |
|------|------|
| Game Launcher | ~95% |
| Music Player | ~90% |
| CPU Controller | ~90% |
| Crosshair Overlay | ~100% | (New Feature Maybe?)
| Macro System | ~74% | 
| RAM & Drive Cleaner | 50% | (Driver Cleaner didnt applied yet)
| Hardware Stats | 90% |
| System Optimization (OMEN AI–like concept) | Planned |

---

## Feature Notes

### Game Launcher
- Scan and manage Steam & Google Play Games libraries automatically
- Manage local custom game folders
- Track playtime and automatically fetch game icons and background metadata

### Music Player
- Import music from Spotify library
- Import video/audio from YouTube
- Download YouTube video or Spotify music using ResitaAPI

### CPU Controller
- CPU control via RyzenAdj
- Accessible only when required tools (RyzenAdj / UXTU) are available
- Debug handling when required dependencies are missing

### Crosshair Overlay
- Customizable on-screen crosshair overlay (color, size, opacity)
- Works without hooking into game memory (safer for anti-cheats)

### Macro System
- Map hardware keys to custom sequences and mouse inputs (integrated natively with C++)
- Control DPI, rapid fire, and basic multimedia actions

### System Monitoring & Cleaning
- Real-time Hardware stats (CPU, GPU, RAM) tracking
- Memory (RAM) cleaning optimization capabilities

---

## Known Issues

This project is under active development and contains known limitations:

- Application may freeze for several minutes when adding a large number of games
- RAM usage and performance issues under heavy operations
- Image import from game executable icons may fail in virtualized/shared folder environments
- Some UI elements overlap at certain sizes
- Select All option does not properly select all items in some panels
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
