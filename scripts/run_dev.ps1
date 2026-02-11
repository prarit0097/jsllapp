$ErrorActionPreference = 'Stop'

function Write-Log($message, $level = 'INFO') {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[$ts] [$level] $message"
}

$root = Split-Path -Parent $PSScriptRoot
$venvBin = Join-Path $root '.venv\Scripts'
$python = Join-Path $venvBin 'python.exe'
$celery = Join-Path $venvBin 'celery.exe'
$logsDir = Join-Path $root 'logs'

if (-not (Test-Path $python)) {
    Write-Log 'Virtual environment not found. Create it with: python -m venv .venv' 'ERROR'
    exit 1
}

if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Force $logsDir | Out-Null
}

$redisListening = netstat -aon | Select-String ':6379' | Select-String 'LISTENING'
if ($redisListening) {
    Write-Log 'Redis already listening on 6379.'
} else {
    $redisService = Get-Service | Where-Object { $_.Name -like 'redis*' -or $_.DisplayName -like 'Redis*' } | Select-Object -First 1
    if ($redisService -and $redisService.Status -ne 'Running') {
        Write-Log "Starting Redis service: $($redisService.Name)"
        Start-Service $redisService.Name
        Start-Sleep -Seconds 1
    } else {
        $redisCmd = Get-Command redis-server -ErrorAction SilentlyContinue
        if ($redisCmd) {
            Write-Log 'Starting redis-server (standalone).'
            Start-Process -FilePath $redisCmd.Source -WorkingDirectory $root | Out-Null
            Start-Sleep -Seconds 1
        } else {
            Write-Log 'redis-server not found in PATH. Start Redis separately.' 'WARN'
        }
    }
}

$workerOut = Join-Path $logsDir 'celery-worker.out.log'
$workerErr = Join-Path $logsDir 'celery-worker.err.log'
$beatOut = Join-Path $logsDir 'celery-beat.out.log'
$beatErr = Join-Path $logsDir 'celery-beat.err.log'

Write-Log 'Starting Celery worker (logs/celery-worker.*.log)'
Start-Process -FilePath $celery -ArgumentList '-A config worker -l info' -WorkingDirectory $root -RedirectStandardOutput $workerOut -RedirectStandardError $workerErr | Out-Null

Write-Log 'Starting Celery beat (logs/celery-beat.*.log)'
Start-Process -FilePath $celery -ArgumentList '-A config beat -l info' -WorkingDirectory $root -RedirectStandardOutput $beatOut -RedirectStandardError $beatErr | Out-Null

Write-Log 'Starting Django runserver'
& $python (Join-Path $root 'manage.py') runserver