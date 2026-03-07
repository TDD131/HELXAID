@echo off
REM HELXAIRO Native Macro Build Script
REM Requires: Visual Studio 2022, Python 3.10+, pybind11 (pip install pybind11)

echo ========================================
echo HELXAIRO Native Macro Build Script
echo ========================================
echo.

REM Detect Python
setlocal EnableDelayedExpansion
set PY_EXE=python
if exist "..\.venv\Scripts\python.exe" (
    set PY_EXE="..\.venv\Scripts\python.exe"
    echo [INFO] Using venv python: !PY_EXE!
) else (
    echo [INFO] Using system python: !PY_EXE!
)

REM Check for pybind11
!PY_EXE! -c "import pybind11" 2>NUL
if errorlevel 1 (
    echo [ERROR] pybind11 not found in !PY_EXE!. Installing...
    !PY_EXE! -m pip install pybind11
)

REM Create build directory
if not exist build mkdir build
cd build

REM Force clean cache to pick up new Python path
if exist CMakeCache.txt del /f /q CMakeCache.txt

REM Configure with CMake
echo [1/3] Configuring CMake...
cmake .. -G "Visual Studio 17 2022" -A x64 -DPython3_EXECUTABLE=!PY_EXE!

if errorlevel 1 (
    echo [ERROR] CMake configuration failed!
    echo Make sure Visual Studio 2022 is installed.
    pause
    exit /b 1
)

REM Build Release
echo.
echo [2/3] Building Release...
cmake --build . --config Release

if errorlevel 1 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

REM Verify output
echo.
echo [3/3] Verifying...
if exist "..\python\helxairo_native.pyd" (
    echo [SUCCESS] helxairo_native.pyd created in python folder!
) else (
    echo [WARNING] .pyd not found in expected location
    dir /s *.pyd 2>NUL
)

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Test with: python -c "import helxairo_native; print(helxairo_native.__version__)"
echo.

cd ..
pause
