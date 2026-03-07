@echo off
REM Build script for HELXAID portable executable
REM Run this from the python directory

echo ========================================
echo    HELXAID - Build Portable EXE
echo ========================================
echo.

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    pip install pyinstaller
)

REM Check if UPX is available (optional, for compression)
where upx >nul 2>&1
if errorlevel 1 (
    echo [!] UPX not found - exe will be larger without compression
    echo     Download from: https://github.com/upx/upx/releases
    echo.
)

REM Clean previous builds
echo [*] Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM Build the executable
echo [*] Building portable executable...
echo.
pyinstaller launcher.spec --clean

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo    BUILD COMPLETE!
echo ========================================
echo.
echo Portable executable created at:
echo   dist\HELXAID.exe
echo.
echo You can now copy this file anywhere and run it!
echo.

REM Show file size
for %%A in ("dist\HELXAID.exe") do echo File size: %%~zA bytes

echo.
echo ========================================
echo    Building Installer...
echo ========================================
echo.

REM Check if Inno Setup compiler is available
where iscc >nul 2>&1
if errorlevel 1 (
    REM Try common install paths
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    ) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
        set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
    ) else (
        echo [!] Inno Setup not found - skipping installer creation
        echo     Download from: https://jrsoftware.org/isdl.php
        echo.
        echo Portable EXE is ready at: dist\HELXAID.exe
        pause
        exit /b 0
    )
) else (
    set ISCC=iscc
)

echo [*] Compiling installer with Inno Setup...
%ISCC% installer.iss

if errorlevel 1 (
    echo.
    echo [ERROR] Installer build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo    ALL BUILDS COMPLETE!
echo ========================================
echo.
echo Files created:
echo   - dist\HELXAID.exe       (Portable)
echo   - dist\HELXAID Setup.exe (Installer)
echo.

pause
