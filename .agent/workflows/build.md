---
description: Build Game Launcher Project
---

Build HELXAID Game Launcher to portable .exe with all HID/mouse hardware features working, then package it into an installer using Inno Setup.

## Critical: HID Features Must Work in Built .exe

The application uses USB HID to communicate with Furycube mouse hardware. These features MUST work in the built .exe:
- **Button Switch Dropdowns** (Home tab): Assign actions like Left Click, DPI+, DPI Loop to mouse buttons
- **DPI Settings** (Sensor tab): Configure DPI stages
- **Battery Reading**: Read battery level and charging status

The `--hidden-import=hidapi` flag ensures the hidapi library is bundled correctly.

## Build Steps

// turbo-all

1. Activate virtual environment:
   ```bash
   cd "D:\Software\tididi\Game Launcher"
   .\.venv\Scripts\activate
   ```

2. Build portable .exe (includes all resources):
   ```bash
   pyinstaller --onefile --windowed --clean --icon="python/UI Icons/launcher-icon.ico" --add-data="python/UI Icons;UI Icons" --add-data="python/UI Taskbar Icons;UI Taskbar Icons" --add-data="python/icons;icons" --add-data="python/Fonts;Fonts" --add-data="python/helxaid_native.cp314-win_amd64.pyd;." --add-data="python/helxairo_native.cp314-win_amd64.pyd;." --hidden-import=hid --collect-all=hid --collect-all=hidapi --name="HELXAID" python/launcher.py
   ```

3. Show build timestamp:
   ```bash
   Get-Item "dist/HELXAID.exe" | Select-Object Name, LastWriteTime, Length
   ```

4. Compile installer with Inno Setup (creates `dist/HELXAID Setup.exe`):
   ```bash
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer.iss"
   ```
   If Inno Setup is not installed at the default path, check other common paths:
   - `C:\Program Files\Inno Setup 6\ISCC.exe`
   
   If ISCC.exe is not found at any path, inform the user that Inno Setup must be installed first from https://jrsoftware.org/isdownload.php

5. Show final output files:
   ```bash
   Get-Item "dist/HELXAID.exe", "dist/HELXAID Setup.exe" | Select-Object Name, LastWriteTime, @{N='Size(MB)';E={[math]::Round($_.Length/1MB,1)}}
   ```

## Output
- Portable: `dist/HELXAID.exe` (~120MB)
- Installer: `dist/HELXAID Setup.exe` (smaller, compressed with LZMA2)

## Troubleshooting HID Issues

If button switch or DPI features don't work in built .exe:
1. Ensure `--hidden-import=hidapi` is in build command
2. Run .exe from command prompt to see error messages: `.\HELXAID.exe`
3. Check if mouse is connected and detected (battery should show percentage)
4. HID code is in `FurycubeHID.py` - check `set_button_mapping()` and `get_battery_level()`

## Note
Admin privileges are requested dynamically only when needed (CPU Controller) using ShellExecuteW with "runas" verb.