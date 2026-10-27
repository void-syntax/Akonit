# Signal Radar - Manual 24/7 Launcher
# Double-click start.bat to run

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$BackendDir  = "$ProjectRoot\backend"
$FrontendDir = "$ProjectRoot\frontend"
$Python      = "$BackendDir\.venv\Scripts\python.exe"
$LogDir      = "$ProjectRoot\logs"
$Requirements = "$BackendDir\requirements.txt"
$FrontendModules = "$FrontendDir\node_modules"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "      Signal Radar 24/7 Startup         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Prepare local configuration without overwriting existing user settings.
if (-not (Test-Path "$BackendDir\.env")) {
    Copy-Item "$BackendDir\.env.example" "$BackendDir\.env"
    Write-Host "Created backend/.env from safe defaults." -ForegroundColor Gray
}
if (-not (Test-Path "$ProjectRoot\.env")) {
    Copy-Item "$ProjectRoot\.env.example" "$ProjectRoot\.env"
    Write-Host "Created root .env for Docker Compose defaults." -ForegroundColor Gray
}

# Bootstrap Python environment on first run.
if (-not (Test-Path $Python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { $pythonCommand = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $pythonCommand) { throw "Python 3.11+ is required. Install Python, then run start.bat again." }
    Write-Host "Creating the local Python environment (first run only)..." -ForegroundColor Yellow
    & $pythonCommand.Source -m venv "$BackendDir\.venv"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment." }
}

& $Python -c "import uvicorn, fastapi" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing backend packages (first run or after an update)..." -ForegroundColor Yellow
    & $Python -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
}

if (-not (Test-Path "$FrontendModules\next\dist\bin\next")) {
    Write-Host "Installing dashboard packages (first run or after an update)..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    try { & npm ci } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "Dashboard dependency installation failed." }
}

# 1. Start Backend API as a quiet background process.
Write-Host "[1/3] Starting Backend API on http://localhost:8000..." -ForegroundColor Yellow
Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $BackendDir -WindowStyle Hidden `
    -RedirectStandardOutput "$LogDir\api.stdout.log" -RedirectStandardError "$LogDir\api.stderr.log" | Out-Null

# 2. Start the low-resource collection scheduler.
Write-Host "[2/3] Starting 24/7 Worker Scheduler..." -ForegroundColor Yellow
Start-Process -FilePath $Python -ArgumentList @("-m", "app.workers.schedule") `
    -WorkingDirectory $BackendDir -WindowStyle Hidden `
    -RedirectStandardOutput "$LogDir\worker.stdout.log" -RedirectStandardError "$LogDir\worker.stderr.log" | Out-Null

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

if (-not (Test-Path $nextCli)) { throw "Next.js CLI not found after dependency setup." }
Start-Process -FilePath $nodeExe -ArgumentList @($nextCli, "dev", "-p", "3000", "--hostname", "127.0.0.1") `
    -WorkingDirectory $FrontendDir -WindowStyle Hidden `
    -RedirectStandardOutput "$LogDir\web.stdout.log" -RedirectStandardError "$LogDir\web.stderr.log" | Out-Null

# Report success only after both services answer their health checks.
$apiReady = $false
$webReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if (-not $apiReady) {
        try { $apiReady = (Invoke-WebRequest "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch {}
    }
    if (-not $webReady) {
        try { $webReady = (Invoke-WebRequest "http://127.0.0.1:3000" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch {}
    }
    if ($apiReady -and $webReady) { break }
    Start-Sleep -Seconds 1
}
if (-not $apiReady -or -not $webReady) {
    Write-Host "Startup failed: API ready=$apiReady, dashboard ready=$webReady." -ForegroundColor Red
    Write-Host "See logs\api.stderr.log and logs\web.stderr.log for details." -ForegroundColor Gray
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Signal Radar is successfully active! " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Dashboard   : http://localhost:3000" -ForegroundColor White
Write-Host "   API Docs    : http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Services are running quietly in the background." -ForegroundColor Gray
Write-Host "To stop everything, run stop.bat." -ForegroundColor Gray
Write-Host ""

# Open browser when Windows permits shell activation (for example, outside a
# restricted automation session). Service startup does not depend on this.
try {
    Start-Process "http://localhost:3000" -ErrorAction Stop
} catch {
    Write-Host "Open http://localhost:3000 in your browser." -ForegroundColor Gray
}
