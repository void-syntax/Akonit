@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Signal Radar - check

color 0B
echo.
echo   ==========================================================
echo      SIGNAL RADAR - is this machine ready?
echo   ==========================================================
echo.

set "PROBLEMS=0"

REM ---------------------------------------------------------------- Docker
where docker >nul 2>nul
if errorlevel 1 (
  echo   [ ] Docker      not found
  echo                 optional - start.bat falls back to a local setup
) else (
  docker info >nul 2>nul
  if errorlevel 1 (
    echo   [ ] Docker      installed but not running
    echo                 start Docker Desktop, then run start.bat again
  ) else (
    echo   [ok] Docker      ready
  )
)

REM ---------------------------------------------------------------- Python
where python >nul 2>nul
if errorlevel 1 (
  echo   [ ] Python      not found
  echo                 needed only for local mode - https://python.org
  set /a PROBLEMS+=1
) else (
  echo   [ok] Python      ready
)

REM ------------------------------------------------------------------- Node
where node >nul 2>nul
if errorlevel 1 (
  echo   [ ] Node.js     not found
  echo                 needed only for local mode - https://nodejs.org
  set /a PROBLEMS+=1
) else (
  echo   [ok] Node.js     ready
)

REM ------------------------------------------------------------------- .env
if exist ".env" (
  echo   [ok] .env         present
) else (
  echo   [ ] .env         missing
  echo                 start.bat creates it from .env.example
)

echo.

REM ------------------------------------------------------------- Is it up?
curl -fsS -o NUL http://localhost:8000/api/v1/health >nul 2>nul
if errorlevel 1 (
  echo   [ ] API          not running
  echo                 start it with start.bat
) else (
  echo   [ok] API          answering on http://localhost:8000
)

curl -fsS -o NUL http://localhost:3000 >nul 2>nul
if errorlevel 1 (
  echo   [ ] Web          not running
) else (
  echo   [ok] Web          answering on http://localhost:3000
)

echo.
if "%PROBLEMS%"=="0" (
  echo   Everything needed is available.
) else (
  echo   %PROBLEMS% required tool^(s^) missing - see above.
)
echo.
pause
