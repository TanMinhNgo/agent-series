# Script tiện dụng cho Windows: chuẩn bị backend và chạy cả API + frontend.
# Chạy trong PowerShell:  .\run.ps1
# (Nếu PowerShell chặn script, chạy 1 lần: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1) Tạo môi trường ảo nếu chưa có
if (-not (Test-Path ".venv")) {
    Write-Host "Tao moi truong ao (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
}

# 2) Kích hoạt venv
. .\.venv\Scripts\Activate.ps1

# 3) Cài thư viện (nhẹ, cài nhanh)
Write-Host "Cai dat thu vien..." -ForegroundColor Cyan
pip install -r requirements.txt

# 4) Nhắc tạo .env nếu chưa có
if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "Da tao .env tu .env.example — hay mo ra dien API key!" -ForegroundColor Yellow
}

# 5) Khởi động PostgreSQL + pgvector và áp schema.
# Docker Desktop cần đang chạy; nếu chưa chạy, lệnh này sẽ dừng với lỗi rõ ràng.
Write-Host "Khoi dong PostgreSQL + pgvector..." -ForegroundColor Cyan
docker compose up -d
Write-Host "Ap dung database migration..." -ForegroundColor Cyan
python -m alembic upgrade head

# 6) Chuẩn bị và khởi động Vite trong background.
$frontendPath = Join-Path $PSScriptRoot "frontend"
if (-not (Test-Path (Join-Path $frontendPath "node_modules"))) {
    Write-Host "Cai dat dependencies frontend..." -ForegroundColor Cyan
    Push-Location $frontendPath
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

Write-Host "Mo React tai http://localhost:5173..." -ForegroundColor Green
$frontendJob = Start-Job -ScriptBlock {
    param($Path)
    Set-Location $Path
    npm run dev -- --host 127.0.0.1
} -ArgumentList $frontendPath

# Worker riêng: ưu tiên Scheduled Task bền vững theo user. Khi task chưa được
# cài, vẫn fallback sang background job để local dev tiếp tục hoạt động.
$workerScript = Join-Path $PSScriptRoot "run-worker.ps1"
$workerTaskName = "AgentSeriesWorker"
$schedulerJob = $null
$workerTask = Get-ScheduledTask -TaskName $workerTaskName -ErrorAction SilentlyContinue
if ($workerTask) {
    Start-ScheduledTask -TaskName $workerTaskName -ErrorAction SilentlyContinue
    Write-Host "Dung worker Scheduled Task '$workerTaskName'." -ForegroundColor Green
} else {
    Write-Host "Chua cai Scheduled Task. Dang dung worker local; cai ben vung bang .\\scripts\\install-worker-task.ps1" -ForegroundColor Yellow
    $schedulerJob = Start-Job -ScriptBlock {
        param($Script)
        & $Script
    } -ArgumentList $workerScript
}

# Wait for a fresh heartbeat before exposing the local stack. It catches a
# missing database/model dependency instead of leaving queued jobs unnoticed.
$workerOnline = $false
for ($attempt = 0; $attempt -lt 10; $attempt++) {
    Start-Sleep -Seconds 1
    $workerOnline = & .\.venv\Scripts\python.exe -c "from datetime import UTC, datetime; from agent_core.config import load_settings; from agent_core.storage import BackgroundJobRepository, Database; print(BackgroundJobRepository(Database(load_settings().database_url)).worker_status(datetime.now(UTC))['online'])"
    if ($workerOnline -eq "True") { break }
}
if ($workerOnline -ne "True") {
    Stop-Job -Job $schedulerJob -ErrorAction SilentlyContinue
    Remove-Job -Job $schedulerJob -Force -ErrorAction SilentlyContinue
    throw "Worker không gửi heartbeat. Xem logs\\worker-YYYY-MM-DD.log hoặc chạy .\\run-worker.ps1 để chẩn đoán."
}

# 7) Chạy FastAPI ở foreground để Ctrl+C dừng toàn bộ stack local.
Write-Host "Mo FastAPI tai http://localhost:8000..." -ForegroundColor Green
Write-Host "Mo ung dung tai http://localhost:5173" -ForegroundColor Green
try {
    python -m uvicorn api.main:app --reload
}
finally {
    if ($frontendJob) {
        Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
        Remove-Job -Job $frontendJob -Force -ErrorAction SilentlyContinue
    }
    if ($schedulerJob) {
        Stop-Job -Job $schedulerJob -ErrorAction SilentlyContinue
        Remove-Job -Job $schedulerJob -Force -ErrorAction SilentlyContinue
    }
}
