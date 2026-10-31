@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0LocalLecture\scripts\stop-growmate.ps1"
if errorlevel 1 pause
