# ==============================================================================
# CATRS - Local Stop Script (PowerShell)
# Stops Routing Engine, Audit Service, Frontend, and optional Docker containers
# ==============================================================================

$WorkspaceRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Stopping CATRS services..." -ForegroundColor Yellow

# Function to stop process by local port
function Stop-PortProcess([int]$port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($conn in $conns) {
            $pidToKill = $conn.OwningProcess
            if ($pidToKill -and $pidToKill -ne 0) {
                Write-Host " Terminating process $pidToKill on port $port..." -ForegroundColor Yellow
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        # ignore
    }
}

Stop-PortProcess 8001
Stop-PortProcess 8002
Stop-PortProcess 5173

# Optional: stop docker containers
try {
    $null = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " Stopping Docker database and cache..." -ForegroundColor Yellow
        docker compose -f "$WorkspaceRoot\infra\docker-compose.yml" stop postgres redis
    }
} catch {
    # ignore
}

Write-Host "All CATRS services stopped." -ForegroundColor Green
