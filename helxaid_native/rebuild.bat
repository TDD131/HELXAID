@echo off
cd /d D:\Software\tididi\Game Launcher\helxaid_native
rd /s /q build 2>nul
mkdir build
cd build
"C:\Program Files\CMake\bin\cmake.exe" .. -DCMAKE_BUILD_TYPE=Release > D:\Software\tididi\Game Launcher\helxaid_native\cmake_config.log 2>&1
"C:\Program Files\CMake\bin\cmake.exe" --build . --config Release > D:\Software\tididi\Game Launcher\helxaid_native\build_log2.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> D:\Software\tididi\Game Launcher\helxaid_native\build_log2.txt
