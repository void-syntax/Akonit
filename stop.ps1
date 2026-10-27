# Signal Radar - Stop All Services
# Cleanly shuts down backend, worker, and frontend processes

Write-Host ""
Write-Host "  =====================================" -ForegroundColor Red
Write-Host "       Signal Radar - Shutting down      " -ForegroundColor Red
Write-Host "  =====================================" -ForegroundColor Red
Write-Host ""

# Kill processes bound to our ports
$ports = @(8000, 3000)
foreach ($port in $ports) {
    $connections = netstat -ano | Select-String "LISTENING" | Select-String ":$port\s"
    if ($connections) {
        $processIds = $connections | ForEach-Object {
            ($_ -split '\s+')[-1]
        } | Sort-Object -Unique
        foreach ($processId in $processIds) {
            if ($processId -match '^\d+$' -and [int]$processId -ne 0) {
                try {
                    Stop-Process -Id ([int]$processId) -Force -ErrorAction Stop
                    Write-Host "  [OK] Stopped PID $processId (port $port)" -ForegroundColor Yellow
                } catch {
                    Write-Host "  [!!] Could not stop PID $processId (port $port)" -ForegroundColor Gray
                }
            }
        }
    } else {
        Write-Host "  [--] Nothing running on port $port" -ForegroundColor Gray
    }
}

# Kill any background python workers that belong to this project
$backendDir = "$PSScriptRoot\backend"
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        if ($cmdLine -and $cmdLine -like "*$backendDir*") {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  [OK] Stopped python worker PID $($_.Id)" -ForegroundColor Yellow
        }
    } catch {}
}

Write-Host ""
Write-Host "  [OK] Signal Radar stopped" -ForegroundColor Green
Write-Host ""

# Log the stop
$LogDir = "$PSScriptRoot\logs"
if (Test-Path $LogDir) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$ts] Signal Radar stopped by user" | Out-File -FilePath "$LogDir\startup.log" -Append
}
