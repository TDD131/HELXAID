@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
cd /d D:\Software\tididi\Game Launcher\helxaid_native\build
cmake .. -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release 2>&1 > build_log.txt
type build_log.txt
echo Build completed with exit code %ERRORLEVEL%
