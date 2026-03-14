@echo off
setlocal
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" echo vswhere.exe not found: "%VSWHERE%" & exit /b 1

for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSINSTALL=%%i"
if not defined VSINSTALL echo Visual Studio with C++ tools not found. & exit /b 1

call "%VSINSTALL%\VC\Auxiliary\Build\vcvars64.bat" || exit /b 1
cd /d D:\Software\tididi\Game Launcher\helxaid_native\build
cmake --build . --config Release 2>&1 > build_log.txt
set BUILDERR=%ERRORLEVEL%
type build_log.txt
echo Build completed with exit code %BUILDERR%
exit /b %BUILDERR%
