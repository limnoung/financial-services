@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "GEMS_EXIT=%errorlevel%"
if not "%GEMS_EXIT%"=="0" pause
exit /b %GEMS_EXIT%
