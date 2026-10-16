@echo off
title Signal Radar 24/7 Launcher
cd /d "%~dp0"
echo Starting Signal Radar...
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
