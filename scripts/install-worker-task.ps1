[CmdletBinding()]
param(
    [string]$TaskName = "AgentSeriesWorker",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$workerScript = Join-Path $projectRoot "run-worker.ps1"
$powerShell = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $powerShell) { $powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source }
if (-not (Test-Path -LiteralPath $workerScript)) { throw "Không tìm thấy run-worker.ps1 tại $workerScript" }

$currentUser = "$env:USERDOMAIN\\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $powerShell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$workerScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Agent Series background worker" -Force | Out-Null
if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Đã cài và chạy Scheduled Task '$TaskName' cho user hiện tại." -ForegroundColor Green
} else {
    Write-Host "Đã cài Scheduled Task '$TaskName'. Nó sẽ chạy khi user đăng nhập hoặc khi run.ps1 khởi động stack lần tới." -ForegroundColor Green
}
