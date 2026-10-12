@echo off
title [TEST ENVIRONMENT] Multi-Store Sales Scraper Dashboard (Port 5001)
cd /d "%~dp0"
echo ======================================================================
echo   [TEST / STAGING MODE] Multi-Store Sales Scraper Dashboard
echo   Opening Test Dashboard on http://localhost:5001 ...
echo   (Your LIVE production app on port 5000 remains completely safe!)
echo ======================================================================
echo.

python test_web_app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Test application closed with an error.
    pause
)
