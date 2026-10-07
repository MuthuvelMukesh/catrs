# CATRS — Step-by-Step Run Guide

A clear, detailed, and simple guide to running the **Congestion-Aware Traffic Routing System (CATRS)** on your machine.

---

## 1. System Architecture at a Glance

CATRS consists of **5 interconnected components**:

```
 ┌──────────────────────────────────────────────────────────────┐
 │                     Web Dashboard (Vite)                     │
 │                    http://localhost:5173                     │
 └──────────────┬───────────────────────────────┬───────────────┘
                │ /routing                      │ /audit
                ▼                               ▼
 ┌──────────────────────────────┐ ┌──────────────────────────────┐
 │   Routing Engine (L1 & L2)   │ │    Audit Service (L3)        │
 │    http://localhost:8001     │ │    http://localhost:8002     │
 │  (ST-GNN AI & Heuristics)    │ │  (Policy Rule Verifier)      │
 └──────────────┬───────────────┘ └──────────────┬───────────────┘
                │                                │
                ▼                                ▼
 ┌──────────────────────────────┐ ┌──────────────────────────────┐
 │        Redis Cache           │ │      TimescaleDB / Postgres  │
 │        Port: 6379            │ │      Port: 5432              │
 │  (Anti-Herding Route Counter)│ │  (Readings, Outcomes, Rules) │
 └──────────────────────────────┘ └──────────────────────────────┘
```

---

## 2. Prerequisites Checklist

Open PowerShell or your terminal and verify the following tools are installed:

| Tool | Minimum Version | Verification Command |
| :--- | :--- | :--- |
| **Python** | 3.12 or 3.13 | `python --version` |
| **Node.js** | 18+ or 20+ | `node --version` |
| **npm** | 9+ or 10+ | `npm --version` |
| **Docker Desktop** *(Optional)* | 24+ | `docker --version` |

> [!NOTE]
> **Docker is optional!** If Docker is not running, CATRS automatically falls back to **synthetic in-memory mode** without errors. However, having Docker running gives you the real TimescaleDB and Redis containers.

---

## 3. First-Time Setup (Run Once)

If you have already installed Python and Node packages, you can skip to [Section 4](#4-method-1-step-by-step-manual-startup-recommended).

### Step A: Install Python Dependencies
```powershell
# From the project root (m:\catrs):
pip install -r services/routing-engine/requirements.txt
pip install -r services/audit-service/requirements.txt
```

### Step B: Install Frontend Dependencies
```powershell
cd frontend
npm install
cd ..
```

---

## 4. Method 1: Step-by-Step Manual Startup (Recommended)

This is the cleanest and most transparent way to run CATRS during development.

### Step 1: Start Database & Cache (Docker)
Open your terminal at the project root:
```powershell
docker compose -f infra/docker-compose.yml up postgres redis -d
```
*Expected Output:* `Container traffic-redis Started` & `Container traffic-postgres Started` *(health check passes in 5 seconds)*.

---

### Step 2: Start the Routing Engine (Port 8001)
Open a **new terminal window**:
```powershell
cd services/routing-engine
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```
*Expected Output:*
```text
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

---

### Step 3: Start the Audit Service (Port 8002)
Open a **new terminal window**:
```powershell
cd services/audit-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```
*Expected Output:*
```text
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8002 (Press CTRL+C to quit)
```

---

### Step 4: Start the Web Dashboard (Port 5173)
Open a **new terminal window**:
```powershell
cd frontend
npm run dev
```
*Expected Output:*
```text
  VITE v6.x.x  ready in ~800 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

---

### Step 5: Open the Application
Open your browser and navigate to:
👉 **`http://localhost:5173`**

You will see the live dark-mode glassmorphic dashboard showing connected nodes, ST-GNN models, and real-time routing metrics!

---

## 5. Method 2: One-Click Startup Script (Windows PowerShell)

We have provided a pre-built script that launches all services in separate windows automatically:

```powershell
# From the project root (m:\catrs):
.\scripts\run_local.ps1
```

To stop all services when you are done:
```powershell
.\scripts\stop_local.ps1
```

---

## 6. Method 3: 100% Standalone Mode (Without Docker)

If you don't have Docker Desktop installed or running:

1. **Start Routing Engine in synthetic mode:**
   ```powershell
   cd services/routing-engine
   $env:ROUTING_MODE="synthetic"
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
   ```

2. **Start Audit Service:**
   ```powershell
   cd services/audit-service
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
   ```

3. **Start Frontend:**
   ```powershell
   cd frontend
   npm run dev
   ```

The application runs entirely with deterministic in-memory simulated traffic and local fallbacks.

---

## 7. How to Verify Everything is Working

### A. Health Check Status
Run this quick Python command to test all running services:
```powershell
python -c "import urllib.request; print('Routing:', urllib.request.urlopen('http://localhost:8001/health?full=true').read().decode()); print('Audit:', urllib.request.urlopen('http://localhost:8002/health?full=true').read().decode()); print('Frontend Status:', urllib.request.urlopen('http://localhost:5173').getcode())"
```

Expected output:
```json
Routing: {"status":"ok","database":"connected","redis":"connected","predictor":"loaded","dataset":"SYNTHETIC",...}
Audit: {"status":"ok","database":"connected"}
Frontend Status: 200
```

### B. Interactive API Docs (Swagger UI)
Visit the interactive documentation in your browser to test endpoints directly:
- **Routing Engine Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)
- **Audit Service Docs**: [http://localhost:8002/docs](http://localhost:8002/docs)

### C. Run the Pytest Test Suite
To verify the entire system passes all unit and integration contracts:
```powershell
python -m pytest -q
```
*Expected: 149 passed, 1 skipped.*

---

## 8. Troubleshooting & FAQs

### Q1: `Error: listen EADDRINUSE: address already in use :5173` (or `:8001`, `:8002`)
**Cause:** A previous instance of the server is still running.  
**Fix:** Run the stop script or kill the process using that port:
```powershell
# Using the stop script:
.\scripts\stop_local.ps1

# Or manually in PowerShell:
Get-NetTCPConnection -LocalPort 8001, 8002, 5173 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

### Q2: `docker : failed to connect to the docker API`
**Cause:** Docker Desktop is closed.  
**Fix:**
1. Open the Docker Desktop application from your Windows Start Menu and wait until the whale icon shows "Engine running".
2. Or use [Method 3](#6-method-3-100-standalone-mode-without-docker) to run without Docker.

---

### Q3: Frontend shows "Service Unavailable" or red indicators
**Cause:** The backend services (port 8001 or 8002) were not started before opening the frontend.  
**Fix:** Start the Routing Engine on 8001 and Audit Service on 8002 first, then refresh `http://localhost:5173`.

---

## 9. Summary of Port Bindings

| Service | Host Port | Protocol | Purpose |
| :--- | :--- | :--- | :--- |
| **Vite Frontend** | `5173` | HTTP | UI Web Dashboard |
| **Routing Engine** | `8001` | HTTP | AI Speed Prediction, Priority Routing, Diversification |
| **Audit Service** | `8002` | HTTP | Independent Policy Verification & Batch Audit |
| **TimescaleDB** | `5432` | TCP | PostgreSQL 16 time-series storage |
| **Redis** | `6379` | TCP | Rolling-window route assignment counters |
