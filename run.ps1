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
}
