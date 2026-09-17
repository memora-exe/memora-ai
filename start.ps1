# start.ps1 — chạy memora-ai (FastAPI) chỉ bằng 1 lệnh
#   .\start.ps1
$ErrorActionPreference = 'Stop'

# 1. Tao venv neu chua co
if (-not (Test-Path 'venv')) {
    Write-Host '>>> Tao venv...' -ForegroundColor Yellow
    python -m venv venv
}

# 2. Cai deps (verbose de nhin loi ngay)
Write-Host '>>> Cai dat dependencies tu requirements.txt...' -ForegroundColor Yellow
& .\venv\Scripts\python.exe -m pip install --upgrade pip --disable-pip-version-check
& .\venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt

# Self-heal: probe import nhung module de loi (pydantic_core, psycopg2)
$probe = & .\venv\Scripts\python.exe -c "import fastapi, pydantic" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host '>>> Phat hien venv hong -> tao lai tu dau...' -ForegroundColor Red
    Remove-Item -Recurse -Force venv
    python -m venv venv
    & .\venv\Scripts\python.exe -m pip install --upgrade pip --disable-pip-version-check
    & .\venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
}

# 3. Khoi tao .env neu chua co
if (-not (Test-Path '.env')) {
    Write-Host '>>> Copy .env.example -> .env (hay dien GOOGLE_API_KEY)' -ForegroundColor Yellow
    Copy-Item '.env.example' '.env'
}

# 4. Chay server (set PYTHONPATH=. de Python thay package "app.*")
# Bo --reload: uvicorn reload spawn worker con, Ctrl+C PowerShell khong forward tin hieu,
# worker giu port -> khong thoat duoc. Dung restart_ai.py neu can reload.
if (-not $env:PORT) {
    if (Test-Path '.env') {
        foreach ($line in Get-Content '.env') {
            if ($line -match '^PORT=(\d+)') { $env:PORT = $Matches[1]; break }
        }
    }
    if (-not $env:PORT) { $env:PORT = '8000' }
}
Write-Host ">>> Chay FastAPI server tren port $env:PORT (Ctrl+C de dung)..." -ForegroundColor Green
$env:PYTHONPATH = "$PWD"
& .\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $env:PORT
if ($LASTEXITCODE -ne 0) { Write-Host "uvicorn exited with code $LASTEXITCODE" -ForegroundColor Red }
