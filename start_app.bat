@echo off
title Multi-Store Sales Scraper Web Dashboard
cd /d "%~dp0"
echo ===================================================
echo   Starting Multi-Store Sales Scraper Web Dashboard
echo   Opening on http://localhost:5000 ...
echo ===================================================
echo.
start /b python sheets_watcher.py
python web_app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Web application closed with an error.
    pause
)
