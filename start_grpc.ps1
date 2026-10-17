# start_grpc.ps1 — Chạy memora-ai gRPC Technical Proxy Server
$ErrorActionPreference = 'Stop'

if (-not (Test-Path 'venv')) {
    Write-Host '>>> Tao venv...' -ForegroundColor Yellow
    python -m venv venv
    & .\venv\Scripts\python.exe -m pip install -r requirements.txt
}

if (-not $env:GRPC_PORT) {
    if (Test-Path '.env') {
        foreach ($line in Get-Content '.env') {
            if ($line -match '^GRPC_PORT=(\d+)') { $env:GRPC_PORT = $Matches[1]; break }
        }
    }
    if (-not $env:GRPC_PORT) { $env:GRPC_PORT = '50051' }
}

Write-Host ">>> Khoi chay Stateless AI gRPC Server tren port $env:GRPC_PORT..." -ForegroundColor Green
$env:PYTHONPATH = "$PWD;$PWD\proto;$PWD\app\interfaces\grpc"
& .\venv\Scripts\python.exe -m app.interfaces.grpc.server
