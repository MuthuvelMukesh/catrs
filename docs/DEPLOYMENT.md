# CATRS Deployment and Operations Guide

## 1. Quickstart — Local Development (Synthetic Mode)

The system supports a completely self-contained, offline development workflow that does not require external data subscriptions, paid APIs, or GPU accelerators.

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend dashboard)
- Docker & Docker Compose (optional, for TimescaleDB/Redis infrastructure)

### Local Step-by-Step Setup
1. **Clone repository and configure environment**:
   ```bash
   cp .env.example .env
   ```
2. **Install Python dependencies**:
   ```bash
   pip install -r services/routing-engine/requirements.txt
   pip install -r services/audit-service/requirements.txt
   ```
3. **Run local services**:
   - Terminal 1 (Routing Engine):
     ```bash
     cd services/routing-engine
     uvicorn app.main:app --port 8001 --reload
     ```
   - Terminal 2 (Audit Service):
     ```bash
     cd services/audit-service
     uvicorn app.main:app --port 8002 --reload
     ```
   - Terminal 3 (Frontend Dashboard):
     ```bash
     cd frontend
     npm install
     npm run dev
     ```
   Access the dashboard at `http://localhost:3000`.

---

## 2. Docker Compose Deployment

The containerized stack includes TimescaleDB, Redis 7, the Routing Engine, Policy Audit Service, and the Vite frontend.

### Production-Hardened Startup
```bash
# Build and launch all containers in detached mode
docker compose -f infra/docker-compose.yml up -d --build

# Verify container health and startup state
docker compose -f infra/docker-compose.yml ps
```

### Container Stack Architecture
| Container Name | Service | Exposed Port | Health Check | Non-Root User |
| :--- | :--- | :--- | :--- | :--- |
| `traffic-postgres` | TimescaleDB (PostgreSQL 16) | `127.0.0.1:5432` | `pg_isready` | `postgres` |
| `traffic-redis` | Redis 7 Alpine | `127.0.0.1:6379` | `redis-cli ping` | `redis` |
| `catrs-routing-engine` | FastAPI Routing Engine | `8001` (host) -> `8000` | HTTP `/health` | `appuser` (1000) |
| `catrs-audit-service` | FastAPI Policy Audit Service | `8002` (host) -> `8000` | HTTP `/health` | `appuser` (1000) |
| `catrs-frontend` | Nginx / Vite Web Dashboard | `3000` | Port listen check | `nginx` |

---

## 3. Database Migrations & TimescaleDB Setup

Database schemas and hypertables are managed via SQL migration scripts located in `infra/migrations/`.

### Migration Ordering
1. `001_create_traffic_readings.sql`: Creates `traffic_readings` table and converts it to a TimescaleDB hypertable partitioned by `observed_at`.
2. `002_create_route_outcomes.sql`: Creates `route_outcomes` table with index on `observed_at` and `route_id`.
3. `003_create_audit_results.sql`: Creates independent `audit_results` hypertable.
4. `004_create_weight_schedules.sql`: Creates policy tables enforcing immutable version constraints.

### Executing Migrations Manually
```bash
psql -h localhost -U traffic -d traffic -f infra/migrations/001_create_traffic_readings.sql
psql -h localhost -U traffic -d traffic -f infra/migrations/002_create_route_outcomes.sql
psql -h localhost -U traffic -d traffic -f infra/migrations/003_create_audit_results.sql
psql -h localhost -U traffic -d traffic -f infra/migrations/004_create_weight_schedules.sql
```

---

## 4. Observability & Health Probes

### Health Endpoints
- **Liveness Probe**: `GET /health` returns `{"status": "ok"}` when the HTTP event loop is active.
- **Readiness Probe**: `GET /ready` returns `{"status": "ready"}`. In production mode, returns HTTP 503 if the database connection cannot be acquired.
- **Full Operational Health**: `GET /health?full=true` returns deep dependency statuses:
  ```json
  {
    "status": "healthy",
    "mode": "synthetic",
    "database": "synthetic_memory",
    "redis": "connected",
    "predictor": "heuristic_fallback",
    "predictor_health": "verified_champion_persistence",
    "dataset": "SYNTHETIC",
    "dataset_mode": "synthetic",
    "num_nodes": 100,
    "sampling_interval": "5 min",
    "model": "Persistence",
    "model_version": "persistence-champion-v1",
    "horizons": ["5m", "15m", "30m"],
    "is_synthetic": true,
    "data_freshness": "simulated"
  }
  ```

### Prometheus Metrics
Exposed at `GET /metrics` on both services:
- `routing_requests_total{trip_category, status}`
- `route_ranking_latency_seconds`
- `prediction_latency_seconds{model_used}`
- `diversification_events_total`
- `audit_verifications_total{trip_category, valid}`
- `circuit_breaker_trips_total{feed_type}`

---

## 5. Backup, Recovery, and Rollback Procedures

### TimescaleDB Backup & Restore
```bash
# Dump TimescaleDB database
docker exec -t traffic-postgres pg_dump -U traffic -d traffic -Fc > backup_$(date +%Y%m%d).dump

# Restore from dump
docker exec -i traffic-postgres pg_restore -U traffic -d traffic --clean < backup_20261017.dump
```

### Redis State Persistence
Redis is configured with an append-only file (AOF) volume mount (`redis-data:/data`). Counters reset gracefully across expiration windows without corrupting state.

### Graceful Rollback
If a newly deployed container version encounters issues:
```bash
# Revert container image to previous tag
docker compose -f infra/docker-compose.yml stop routing-engine
docker compose -f infra/docker-compose.yml up -d --no-deps routing-engine
```
Because weight schedules are immutable and database migrations are strictly additive, rollback does not require destructive schema downgrades.
