# Signal Radar - Manual 24/7 Launcher
# Double-click start.bat to run

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$BackendDir  = "$ProjectRoot\backend"
$FrontendDir = "$ProjectRoot\frontend"
$Python      = "$BackendDir\.venv\Scripts\python.exe"
$LogDir      = "$ProjectRoot\logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "      Signal Radar 24/7 Startup         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python venv
if (-not (Test-Path $Python)) {
    Write-Host "[ERROR] Python venv not found at $Python" -ForegroundColor Red
    pause
    exit 1
}

# 1. Start Backend API (FastAPI + Telegram Bot + Laya AI)
Write-Host "[1/3] Starting Backend API on http://localhost:8000..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k title Signal Radar Backend && cd /d `"$BackendDir`" && `"$Python`" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Sleep -Seconds 3

# 2. Start Worker Scheduler (24/7 collection & matching)
Write-Host "[2/3] Starting 24/7 Worker Scheduler..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k title Signal Radar Worker && cd /d `"$BackendDir`" && `"$Python`" -m app.workers.schedule"
Start-Sleep -Seconds 2

# 3. Start Frontend Dashboard (Next.js)
Write-Host "[3/3] Starting Frontend Dashboard on http://localhost:3000..." -ForegroundColor Yellow

$nodeExe = "C:\Program Files\nodejs\node.exe"
if (-not (Test-Path $nodeExe)) {
    $nodeCheck = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCheck) { $nodeExe = $nodeCheck.Source } else { $nodeExe = "node" }
}

$nextCli = "$FrontendDir\node_modules\next\dist\bin\next"
if (-not (Test-Path $nextCli)) {
    $nextCli = "$FrontendDir\node_modules\.bin\next.cmd"
}

if (Test-Path $nextCli) {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k title Signal Radar Frontend && cd /d `"$FrontendDir`" && `"$nodeExe`" `"$nextCli`" dev"
} else {
    Write-Host "[ERROR] Next.js CLI not found in node_modules. Run 'npm install' in frontend directory." -ForegroundColor Red
}

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Signal Radar is successfully active! " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Dashboard   : http://localhost:3000" -ForegroundColor White
Write-Host "   API Docs    : http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Telegram Bot: @akonit_analitik_bot" -ForegroundColor Cyan
Write-Host ""
Write-Host "Services are running in their own background windows." -ForegroundColor Gray
Write-Host "To stop everything, run stop.bat or close those windows." -ForegroundColor Gray
Write-Host ""

# Open browser
Start-Process "http://localhost:3000"