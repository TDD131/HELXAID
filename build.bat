@echo off
setlocal enabledelayedexpansion

echo =============================================
echo    TDD Launcher Build Script
echo =============================================
echo.

:: Check if running from correct directory
if not exist "python\launcher.py" (
    echo ERROR: Please run this script from the Game Launcher root directory
    pause
    exit /b 1
)

:: Show menu
echo Select build option:
echo   1. Portable EXE only
echo   2. Installer only
echo   3. Both Portable and Installer
echo   4. Exit
echo.
set /p choice="Enter choice (1-4): "

if "%choice%"=="4" goto :eof
if "%choice%"=="" goto :eof

:: Activate virtual environment if exists
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
    set "PYINSTALLER=.venv\Scripts\pyinstaller.exe"
) else (
    set "PYINSTALLER=pyinstaller"
)

echo.
echo =============================================
echo    Building Portable EXE...
echo =============================================

:: Build portable exe using correct pyinstaller path
"%PYINSTALLER%" --noconfirm python\launcher.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

:: Copy exe to python\dist for installer
if not exist "python\dist" mkdir python\dist
copy /Y "dist\HELXAID.exe" "python\dist\"

echo.
echo Portable EXE built: dist\HELXAID.exe
for %%A in ("dist\HELXAID.exe") do echo Size: %%~zA bytes

if "%choice%"=="1" goto :done

echo.
echo =============================================
echo    Building Installer...
echo =============================================

:: Find Inno Setup
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if "!ISCC!"=="" (
    echo ERROR: Inno Setup 6 not found!
    echo Please install from: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

:: Build installer
"!ISCC!" python\installer.iss
if errorlevel 1 (
    echo ERROR: Installer build failed!
    pause
    exit /b 1
)

echo.
echo Installer built: python\dist\HELXAID Setup.exe
for %%A in ("python\dist\HELXAID Setup.exe") do echo Size: %%~zA bytes

:done
echo.
echo =============================================
echo    Build Complete!
echo =============================================
echo.
echo Output files:
if exist "dist\HELXAID.exe" (
    for %%A in ("dist\HELXAID.exe") do echo   Portable: dist\HELXAID.exe (%%~zA bytes^)
)
if exist "python\dist\HELXAID Setup.exe" (
    for %%A in ("python\dist\HELXAID Setup.exe") do echo   Installer: python\dist\HELXAID Setup.exe (%%~zA bytes^)
)
echo.
pause
