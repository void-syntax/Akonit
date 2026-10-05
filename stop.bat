@echo off
cd /d "%~dp0"
title Stop Signal Radar

echo.
echo   Stopping Signal Radar...
echo.

where docker >nul 2>nul
if %ERRORLEVEL%==0 (
  docker info >nul 2>nul
  if %ERRORLEVEL%==0 (
    docker compose down
    echo.
    echo   Done. Your data is kept in the pgdata volume.
    echo   To remove it as well:  docker compose down -v
    echo.
    pause
    exit /b 0
  )
)

REM Local mode leaves the API, collector and web app in their own windows.
REM PowerShell rather than a netstat|findstr pipeline: cmd parses a pipe inside
REM `for /f` twice, which silently dropped the filter and matched nothing.
REM Inside the double quotes the pipe needs no escaping: cmd passes it through
REM literally, and an escaped ^| reaches PowerShell as a stray caret.
echo   Closing the local processes on ports 8000 and 3000...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 8000 -or $_.LocalPort -eq 3000 } | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Write-Host ('     stopping PID ' + $_); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"

echo.
echo   Done. You can close the other windows too.
echo.
pause
