@echo off
title Signal Radar Stopper
cd /d "%~dp0"
echo Stopping Signal Radar services...
powershell -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo Done.
pause
