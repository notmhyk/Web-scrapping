@echo off
title Push Project to GitHub
cd /d "%~dp0"

set "PATH=C:\Users\ADMIN MHYK\AppData\Local\Programs\Git\cmd;C:\Program Files\Git\cmd;%PATH%"

echo ======================================================================
echo    Pushing Multi-Store Sales Scraper Dashboard to GitHub
echo    Repository: https://github.com/notmhyk/Web-scrapping.git
echo ======================================================================
echo.

git remote set-url origin https://github.com/notmhyk/Web-scrapping.git
git branch -M main
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo    [SUCCESS] Project successfully pushed to your GitHub repository!
    echo    View your code at: https://github.com/notmhyk/Web-scrapping
    echo ======================================================================
) else (
    echo.
    echo [NOTE] If a browser login window appeared, please authorize your account.
)

echo.
pause
