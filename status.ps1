# Signal Radar - System Status
# Shows the state of all services, resources, and recent activity

$ProjectRoot = $PSScriptRoot
$LogDir      = "$ProjectRoot\logs"
$BackendDir  = "$ProjectRoot\backend"
$Python      = "$BackendDir\.venv\Scripts\python.exe"

function Test-Port($port) {
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $tcpClient.Connect("localhost", $port)
        $tcpClient.Close()
        return $true
    } catch { return $false }
}

Write-Host ""
Write-Host "  =====================================" -ForegroundColor Cyan
Write-Host "        Signal Radar - Status            " -ForegroundColor Cyan
Write-Host "  =====================================" -ForegroundColor Cyan
Write-Host ""

# --- Backend API ---
Write-Host "  Backend API (port 8000):" -ForegroundColor White -NoNewline
if (Test-Port 8000) {
    Write-Host " RUNNING" -ForegroundColor Green
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "    Health: $($health | ConvertTo-Json -Compress)" -ForegroundColor Gray
    } catch {
        Write-Host "    Health endpoint: not available or errored" -ForegroundColor Yellow
    }
} else {
    Write-Host " STOPPED" -ForegroundColor Red
}

# --- Frontend ---
Write-Host "  Frontend    (port 3000):" -ForegroundColor White -NoNewline
if (Test-Port 3000) {
    Write-Host " RUNNING" -ForegroundColor Green
} else {
    Write-Host " STOPPED" -ForegroundColor Red
}

# --- Worker scheduler ---
Write-Host "  Worker scheduler:       " -ForegroundColor White -NoNewline
$workerProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        $cmdLine -and $cmdLine -like "*app.workers.schedule*"
    } catch { $false }
}
if ($workerProcs) {
    Write-Host " RUNNING (PID: $($workerProcs.Id -join ', '))" -ForegroundColor Green
} else {
    Write-Host " STOPPED" -ForegroundColor Red
}

Write-Host ""

# --- Database signal count ---
Write-Host "  Database:" -ForegroundColor White
if (Test-Port 8000) {
    try {
        $signals = Invoke-RestMethod -Uri "http://localhost:8000/api/signals?limit=1" -TimeoutSec 5 -ErrorAction Stop
        if ($signals.total) {
            Write-Host "    Total signals: $($signals.total)" -ForegroundColor Cyan
        } elseif ($signals.Count -ge 0) {
            Write-Host "    Signals returned: $($signals.Count) (total unknown)" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "    Could not query signals API" -ForegroundColor Yellow
    }
} else {
    Write-Host "    Backend offline - cannot query" -ForegroundColor Yellow
}

# --- Last collection from worker log ---
Write-Host ""
Write-Host "  Recent activity:" -ForegroundColor White
$workerLog = "$LogDir\worker.log"
if (Test-Path $workerLog) {
    $lastLines = Get-Content $workerLog -Tail 5 -ErrorAction SilentlyContinue
    if ($lastLines) {
        foreach ($line in $lastLines) {
            Write-Host "    $line" -ForegroundColor Gray
        }
    } else {
        Write-Host "    Worker log is empty" -ForegroundColor Yellow
    }
} else {
    Write-Host "    No worker log found" -ForegroundColor Yellow
}

# --- Memory usage ---
Write-Host ""
Write-Host "  Memory usage:" -ForegroundColor White
$pythonProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue
$nodeProcs   = Get-Process -Name "node" -ErrorAction SilentlyContinue

$totalMB = 0
if ($pythonProcs) {
    $pyMB = [math]::Round(($pythonProcs | Measure-Object -Property WorkingSet64 -Sum).Sum / 1MB, 1)
    $totalMB += $pyMB
    Write-Host "    Python processes: ${pyMB} MB ($($pythonProcs.Count) proc)" -ForegroundColor Gray
}
if ($nodeProcs) {
    $nodeMB = [math]::Round(($nodeProcs | Measure-Object -Property WorkingSet64 -Sum).Sum / 1MB, 1)
    $totalMB += $nodeMB
    Write-Host "    Node processes:   ${nodeMB} MB ($($nodeProcs.Count) proc)" -ForegroundColor Gray
}
if ($totalMB -gt 0) {
    Write-Host "    Total Signal Radar: ${totalMB} MB" -ForegroundColor Cyan
} else {
    Write-Host "    No Signal Radar processes detected" -ForegroundColor Yellow
}

# --- System memory ---
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os) {
    $freeMB  = [math]::Round($os.FreePhysicalMemory / 1024, 0)
    $totalGB = [math]::Round($os.TotalVisibleMemorySize / 1048576, 1)
    Write-Host "    System free: ${freeMB} MB / ${totalGB} GB total" -ForegroundColor Gray
}

Write-Host ""
Write-Host "  =====================================" -ForegroundColor Cyan
Write-Host ""
