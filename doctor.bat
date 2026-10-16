@echo off
title Signal Radar Doctor
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0status.ps1"
pause
