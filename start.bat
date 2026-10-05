@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title Signal Radar
color 0B

echo.
echo   ==========================================================
echo      SIGNAL RADAR
echo      Catch what's starting to trend before it becomes obvious.
echo   ==========================================================
echo.

REM ---------------------------------------------------------------- .env
if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo   Created .env from .env.example
  ) else (
    echo   ERROR: .env.example is missing, cannot continue.
    pause
    exit /b 1
  )
)
echo.

REM -------------------------------------------------------------- Docker?
set "USE_DOCKER=0"
where docker >nul 2>nul
if %ERRORLEVEL%==0 (
  docker info >nul 2>nul
  if %ERRORLEVEL%==0 (
    set "USE_DOCKER=1"
  )
)

if "%USE_DOCKER%"=="1" goto :docker

echo   Docker was not found or is not running.
echo   Falling back to a local setup with Python and Node.
echo   (Install Docker Desktop for the easier path.)
echo.
goto :local

REM ==========================================================================
:docker
echo   Mode: Docker
echo.
echo   First run builds images and takes a few minutes.
echo   The browser opens automatically when the API is healthy.
echo.
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo   ERROR: docker compose failed. Scroll up for the reason.
  pause
  exit /b 1
)

echo.
echo   Waiting for the API to answer...
set /a TRIES=0
:wait_docker
set /a TRIES+=1
curl -fsS http://localhost:8000/api/v1/health >nul 2>nul
if not errorlevel 1 goto :wait_docker_web
if !TRIES! gtr 90 (
  echo.
  echo   ERROR: the API did not become healthy in time.
  echo   Check what happened:  docker compose logs api
  pause
  exit /b 1
)
timeout /t 2 >nul
goto :wait_docker

REM The API being healthy is not enough: the browser would still land on a
REM web container that is still booting.
:wait_docker_web
echo   Waiting for the web app...
set /a TRIES=0
:wait_docker_web_loop
set /a TRIES+=1
curl -fsS -o NUL http://localhost:3000 >nul 2>nul
if not errorlevel 1 goto :open
if !TRIES! gtr 90 (
  echo.
  echo   ERROR: the web app did not come up. Check:  docker compose logs web
  pause
  exit /b 1
)
timeout /t 2 >nul
goto :wait_docker_web_loop

REM ==========================================================================
:local
where python >nul 2>nul
if errorlevel 1 (
  echo   ERROR: Python is not installed or not on PATH.
  echo   Install Python 3.11+ from https://python.org and run this again.
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo   ERROR: Node.js is not installed or not on PATH.
  echo   Install Node.js 20+ from https://nodejs.org and run this again.
  pause
  exit /b 1
)

echo   Mode: local ^(no Docker^)
echo.

if not exist "backend\.venv" (
  echo   Creating the Python environment ^(first run only^)...
  python -m venv backend\.venv
  if errorlevel 1 (
    echo   ERROR: could not create the virtual environment.
    pause
    exit /b 1
  )
)

echo   Installing Python packages...
call backend\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
call backend\.venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt
if errorlevel 1 (
  echo   ERROR: installing Python packages failed.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo   Installing web packages ^(first run only^)...
  call npm --prefix frontend install --silent
  if errorlevel 1 (
    echo   ERROR: installing web packages failed.
    pause
    exit /b 1
  )
)

REM A local .env so DATABASE_URL points at SQLite. The Docker stack injects its
REM own environment and ignores this file.
if not exist "backend\.env" (
  copy "backend\.env.example" "backend\.env" >nul
  echo   Created backend\.env for local mode
)

echo   Starting the API and the collector...
start "Signal Radar - API" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
timeout /t 6 >nul
start "Signal Radar - Collector" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m app.workers.schedule"

echo   Waiting for the API to answer...
set /a TRIES=0
REM Jumps to :start_web, not :open - going straight to :open would skip the
REM web app entirely and the browser would land on a dead port.
:wait_local
set /a TRIES+=1
curl -fsS http://localhost:8000/api/v1/health >nul 2>nul
if not errorlevel 1 goto :start_web
if !TRIES! gtr 45 (
  echo.
  echo   ERROR: the API did not start. Look at the "Signal Radar - API" window.
  pause
  exit /b 1
)
timeout /t 2 >nul
goto :wait_local

:start_web
echo   Starting the web app...
start "Signal Radar - Web" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo   Waiting for the web app...
set /a TRIES=0
:wait_web
set /a TRIES+=1
curl -fsS -o NUL http://localhost:3000 >nul 2>nul
if not errorlevel 1 goto :open
if !TRIES! gtr 90 (
  echo.
  echo   ERROR: the web app did not start. Look at the "Signal Radar - Web" window.
  pause
  exit /b 1
)
timeout /t 2 >nul
goto :wait_web

REM ==========================================================================
:open
echo.
echo   ==========================================================
echo      Ready. Opening http://localhost:3000
echo   ==========================================================
echo.
echo   The collector runs every 60 seconds, so the first signals
echo   appear within about a minute.
echo.
echo   To stop: close this window, or run  stop.bat
echo.
start "" http://localhost:3000
timeout /t 3 >nul
exit /b 0
