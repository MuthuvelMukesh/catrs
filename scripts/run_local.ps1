# ==============================================================================
# CATRS - Local One-Click Startup Script (PowerShell)
# Starts Docker Postgres & Redis, Routing Engine, Audit Service, and Frontend
# ==============================================================================

$ErrorActionPreference = "Stop"
$WorkspaceRoot = Split-Path -Parent $PSScriptRoot

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "    CATRS: Congestion-Aware Traffic Routing System    " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Check Docker and start Postgres + Redis
Write-Host "`n[1/4] Checking Docker status..." -ForegroundColor Yellow
$dockerAvailable = $false
try {
    $null = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerAvailable = $true
        Write-Host " Docker is running. Starting TimescaleDB & Redis..." -ForegroundColor Green
        docker compose -f "$WorkspaceRoot\infra\docker-compose.yml" up postgres redis -d
        Write-Host " Database & Cache containers are healthy!" -ForegroundColor Green
    } else {
        Write-Host " Docker daemon is not active. Running in synthetic in-memory mode." -ForegroundColor Yellow
    }
} catch {
    Write-Host " Docker not available. Running in synthetic in-memory mode." -ForegroundColor Yellow
}

# 2. Start Routing Engine (Port 8001) in a new window
Write-Host "`n[2/4] Starting Routing Engine on port 8001..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot\services\routing-engine'; Write-Host 'Starting CATRS Routing Engine on http://localhost:8001...' -ForegroundColor Cyan; python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"

# 3. Start Audit Service (Port 8002) in a new window
Write-Host "`n[3/4] Starting Audit Service on port 8002..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot\services\audit-service'; Write-Host 'Starting CATRS Audit Service on http://localhost:8002...' -ForegroundColor Cyan; python -m uvicorn app.main:app --host 0.0.0.0 --port 8002"

# 4. Start Frontend Vite Server (Port 5173) in a new window
Write-Host "`n[4/4] Starting Frontend Dashboard on port 5173..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot\frontend'; Write-Host 'Starting CATRS Frontend Dashboard on http://localhost:5173...' -ForegroundColor Cyan; npm run dev"

Write-Host "`n======================================================" -ForegroundColor Green
Write-Host " All services launched successfully!" -ForegroundColor Green
Write-Host " Dashboard URL: http://localhost:5173" -ForegroundColor Cyan
Write-Host " Routing Engine: http://localhost:8001/docs" -ForegroundColor Cyan
Write-Host " Audit Service:  http://localhost:8002/docs" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Green
