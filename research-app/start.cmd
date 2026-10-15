@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -X utf8 start.py %*
) else (
  py -3 -X utf8 start.py %*
)
set "GEMS_EXIT=%errorlevel%"
if not "%GEMS_EXIT%"=="0" pause
exit /b %GEMS_EXIT%
