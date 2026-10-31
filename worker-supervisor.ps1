# Keeps the collector alive after a crash and prevents automatic Windows sleep.
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$BackendDir,
    [Parameter(Mandatory = $true)][string]$LogDir
)

$ErrorActionPreference = "Stop"
$StopFile = Join-Path $LogDir "worker.supervisor.stop"
$LockPath = Join-Path $LogDir "worker.supervisor.lock"
$OutLog = Join-Path $LogDir "worker.stdout.log"
$ErrLog = Join-Path $LogDir "worker.stderr.log"
$SupervisorLog = Join-Path $LogDir "worker-supervisor.log"
$lock = $null
$worker = $null
$restartDelay = 5

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PowerKeepAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);

    public static void KeepSystemAwake() {
        SetThreadExecutionState(0x80000001u); // ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    }

    public static void RestoreSleepPolicy() {
        SetThreadExecutionState(0x80000000u); // ES_CONTINUOUS
    }
}
"@

try {
    try {
        $lock = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch {
        exit 0 # another supervisor already owns this installation
    }

    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: allow the display to turn off, keep the PC awake.
    [PowerKeepAwake]::KeepSystemAwake()
    while (-not (Test-Path $StopFile)) {
        $started = Get-Date
        $worker = Start-Process -FilePath $Python -ArgumentList @("-m", "app.workers.schedule") `
            -WorkingDirectory $BackendDir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
        $worker.WaitForExit()

        if (Test-Path $StopFile) { break }
        $runtime = ((Get-Date) - $started).TotalSeconds
        $reason = "exit code $($worker.ExitCode) after $([math]::Round($runtime))s"
        "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Worker exited ($reason); restart in ${restartDelay}s." | Out-File -FilePath $SupervisorLog -Append -Encoding utf8
        Start-Sleep -Seconds $restartDelay
        if ($runtime -ge 300) { $restartDelay = 5 } else { $restartDelay = [math]::Min($restartDelay * 2, 120) }
    }
} catch {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Supervisor error: $($_.Exception.Message)" | Out-File -FilePath $SupervisorLog -Append -Encoding utf8
} finally {
    if ($worker -and -not $worker.HasExited) { Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue }
    [PowerKeepAwake]::RestoreSleepPolicy()
    if ($lock) { $lock.Dispose() }
}
