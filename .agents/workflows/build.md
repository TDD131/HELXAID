---
description: Build Game Launcher Project (--onedir and --onefile mode, single command)
---

Build HELXAID Game Launcher to portable .exe with all HID/mouse hardware features working.

## Critical: HID Features Must Work in Built .exe

The application uses USB HID to communicate with Furycube mouse hardware. These features MUST work in the built .exe:
- **Button Switch Dropdowns** (Home tab): Assign actions like Left Click, DPI+, DPI Loop to mouse buttons
- **DPI Settings** (Sensor tab): Configure DPI stages
- **Battery Reading**: Read battery level and charging status

The `--hidden-import=hid` flag ensures the hidapi library is bundled correctly.

## Build Steps

// turbo-all

1. Run the full build pipeline in a single command (kill + backup + clean + build + report):
   ```powershell
   taskkill /F /IM HELXAID.exe /T 2>$null; Get-Process HELXAID -ErrorAction SilentlyContinue | Stop-Process -Force; $timestamp = Get-Date -Format "yyyyMMdd_HHmm"; if (Test-Path "dist/HELXAID") { Compress-Archive -Path "dist/HELXAID" -DestinationPath "dist/HELXAID_Backup_$timestamp.zip" -Force -ErrorAction SilentlyContinue; Remove-Item -Path "dist/HELXAID" -Recurse -Force -ErrorAction SilentlyContinue }; Write-Host "Building --onedir mode..."; & ".venv\Scripts\python.exe" -m PyInstaller -y --onedir --windowed --clean --icon="python/UI Icons/launcher-icon.ico" --add-data="python/UI Icons;UI Icons" --add-data="python/UI Taskbar Icons;UI Taskbar Icons" --add-data="python/icons;icons" --add-data="python/Fonts;Fonts" --add-data="python/helxaid_native.cp314-win_amd64.pyd;." --add-data="python/helxairo_native.cp314-win_amd64.pyd;." --hidden-import=hid --hidden-import=yt_dlp --hidden-import=win32timezone --hidden-import=win32serviceutil --hidden-import=servicemanager --collect-all=mutagen --collect-all=hid --collect-all=hidapi --exclude-module torch --exclude-module scipy --exclude-module pandas --exclude-module matplotlib --name="HELXAID" python/launcher.py; Write-Host "Building --onefile mode..."; & ".venv\Scripts\python.exe" -m PyInstaller -y --onefile --windowed --clean --icon="python/UI Icons/launcher-icon.ico" --add-data="python/UI Icons;UI Icons" --add-data="python/UI Taskbar Icons;UI Taskbar Icons" --add-data="python/icons;icons" --add-data="python/Fonts;Fonts" --add-data="python/helxaid_native.cp314-win_amd64.pyd;." --add-data="python/helxairo_native.cp314-win_amd64.pyd;." --hidden-import=hid --hidden-import=yt_dlp --hidden-import=win32timezone --hidden-import=win32serviceutil --hidden-import=servicemanager --collect-all=mutagen --collect-all=hid --collect-all=hidapi --exclude-module torch --exclude-module scipy --exclude-module pandas --exclude-module matplotlib --name="HELXAID" python/launcher.py; Get-Item "dist/HELXAID" -ErrorAction SilentlyContinue | ForEach-Object { $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB; [PSCustomObject]@{Name=$_.Name; LastWriteTime=$_.LastWriteTime; 'Size(MB)'=[math]::Round($size, 1)} }; Get-Item "dist/HELXAID.exe" -ErrorAction SilentlyContinue | ForEach-Object { $size = $_.Length / 1MB; [PSCustomObject]@{Name=$_.Name; LastWriteTime=$_.LastWriteTime; 'Size(MB)'=[math]::Round($size, 1)} }
   ```

   > **Note:** Uses `.venv\Scripts\python.exe -m PyInstaller` directly to bypass PowerShell execution policy restrictions on Activate.ps1.
   > The `-y` flag auto-confirms overwrite of the dist folder without prompting.

## Output
- `dist/HELXAID/HELXAID.exe` — run from inside the folder (~252 MB)
- `dist/HELXAID.exe` — single portable executable (~252 MB)

## Troubleshooting HID Issues

If button switch or DPI features don't work in built .exe:
1. Ensure `--hidden-import=hid` is in the build command
2. Run .exe from command prompt to see error messages: `.\dist\HELXAID\HELXAID.exe`
3. Check if mouse is connected and detected (battery should show percentage)
4. HID code is in `FurycubeHID.py` - check `set_button_mapping()` and `get_battery_level()`

## Note
Admin privileges are requested dynamically only when needed (CPU Controller) using ShellExecuteW with "runas" verb.