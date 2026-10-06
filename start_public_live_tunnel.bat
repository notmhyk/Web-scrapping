@echo off
title Cloudflare Live Public Tunnel for Executive Dashboard
cd /d "%~dp0"
echo ======================================================================
echo    Starting Cloudflare Public Tunnel for Executive Sales Dashboard
echo ======================================================================
echo.

if not exist "cloudflared.exe" (
    echo [INFO] cloudflared.exe not found in this folder.
    echo [INFO] Downloading official Cloudflare Tunnel tool from GitHub...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
    if not exist "cloudflared.exe" (
        echo [ERROR] Automatic download failed. Please download cloudflared.exe manually.
        pause
        exit /b 1
    )
    echo [SUCCESS] Cloudflare tool downloaded successfully!
    echo.
)

echo [INFO] Connecting your local dashboard (localhost:5000) to Cloudflare...
echo [INFO] Cloudflare will generate a secure public HTTPS link below.
echo.
echo [IMPORTANT] Share this URL with your boss:
echo    ^<Cloudflare-URL^>/viewer
echo.
echo ======================================================================
cloudflared.exe tunnel --url http://localhost:5000
pause
