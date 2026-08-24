param(
    [ValidateRange(1, 60)]
    [int]$RestartDelaySeconds = 5
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot ".venv\\Scripts\\python.exe"
$logDirectory = Join-Path $projectRoot "logs"
$maxLogBytes = 5MB
$retentionDays = 14

if (-not (Test-Path -LiteralPath $python)) {
    throw "Không tìm thấy .venv. Chạy .\\run.ps1 một lần để chuẩn bị môi trường."
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Set-Location $projectRoot

function Get-WorkerLogFile {
    $logFile = Join-Path $logDirectory ("worker-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))
    if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -ge $maxLogBytes) {
        $archive = Join-Path $logDirectory ("worker-{0}.log" -f (Get-Date -Format "yyyy-MM-dd-HHmmss"))
        Move-Item -LiteralPath $logFile -Destination $archive
    }
    Get-ChildItem -LiteralPath $logDirectory -Filter "worker-*.log" -File |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$retentionDays) } |
        Remove-Item -Force
    return $logFile
}

while ($true) {
    $logFile = Get-WorkerLogFile
    "$(Get-Date -Format o) Starting Agent Series worker" | Tee-Object -FilePath $logFile -Append
    & $python -m agent_core.worker 2>&1 | Tee-Object -FilePath $logFile -Append
    $exitCode = $LASTEXITCODE
    "$(Get-Date -Format o) Worker exited with code $exitCode; restarting in $RestartDelaySeconds seconds" | Tee-Object -FilePath (Get-WorkerLogFile) -Append
    Start-Sleep -Seconds $RestartDelaySeconds
}
