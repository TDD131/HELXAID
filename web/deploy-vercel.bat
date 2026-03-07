@echo off
title TDD Launcher - Vercel Deploy
color 0A

echo ============================================
echo    TDD Launcher - Vercel Deployment Tool
echo ============================================
echo.

:: Check if Vercel CLI is installed
where vercel >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Vercel CLI tidak terinstall!
    echo.
    echo Jalankan command ini di terminal untuk install:
    echo   npm install -g vercel
    echo.
    pause
    exit /b 1
)

echo [INFO] Vercel CLI ditemukan!
echo.
echo [INFO] Memulai deployment ke Vercel...
echo.

:: Change to web directory
cd /d "%~dp0"

:: Deploy to Vercel (production)
echo Pilih mode deployment:
echo   1. Production (--prod)
echo   2. Preview (development)
echo.
set /p choice="Masukkan pilihan (1/2): "

if "%choice%"=="1" (
    echo.
    echo [INFO] Deploying ke PRODUCTION...
    vercel --prod
) else (
    echo.
    echo [INFO] Deploying ke PREVIEW...
    vercel
)

echo.
echo ============================================
echo    Deployment selesai!
echo ============================================
echo.
pause
