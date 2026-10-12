@echo off
title Promote Test Changes to Live Production and GitHub
cd /d "%~dp0"
echo ======================================================================
echo    Promote Test Project to Live Production and GitHub
echo ======================================================================
echo.
echo This will:
echo   1. Backup current live production files to 'backup_production\'
echo   2. Apply tested revisions to 'web_app.py' and 'config.json'
echo   3. Push verified changes directly to your GitHub repository!
echo.
set /p confirm="Do you want to proceed? (Y/N): "
if /i "%confirm%" NEQ "Y" (
    echo.
    echo [CANCELLED] Operation cancelled. Live project was not changed.
    pause
    exit /b
)

echo.
echo [1/3] Creating safety backup in 'backup_production\'...
if not exist backup_production mkdir backup_production
copy /y web_app.py backup_production\web_app.py.bak
copy /y config.json backup_production\config.json.bak
echo      Backup complete!

echo.
echo [2/3] Promoting tested code to live files...
copy /y test_web_app.py web_app.py
echo      Promoted test_web_app.py to web_app.py!

echo.
echo [3/3] Pushing verified changes to GitHub...
call push_to_github.bat

echo.
echo ======================================================================
echo    [SUCCESS] Test revisions are now live and pushed to GitHub!
echo ======================================================================
pause
