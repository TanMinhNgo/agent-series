[CmdletBinding()]
param(
    [string]$TaskName = "AgentSeriesWorker"
)

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Đã gỡ Scheduled Task '$TaskName'." -ForegroundColor Green
} else {
    Write-Host "Scheduled Task '$TaskName' chưa được cài." -ForegroundColor Yellow
}
