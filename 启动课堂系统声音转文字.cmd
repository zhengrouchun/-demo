@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0LocalLecture\scripts\start-growmate.ps1" -Transcript
if errorlevel 1 pause
