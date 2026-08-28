# Traffic Routing System (CATRS)

This repository implements a three-layer congestion-aware traffic prediction, routing, and auditing platform.

## Layer Architecture

- **Layer 1**: Congestion prediction + priority-weighted diversified routing in `services/routing-engine`
- **Layer 2**: Transparency explanation payload generated in the same ranking flow as routing decisions
- **Layer 3**: Independent audit service in `services/audit-service` with no shared code

The project starts with a deterministic synthetic data environment and local infrastructure so all core behaviors can be tested locally before connecting to external feeds and production clusters.

## Technology Stack

- Python 3.12+
- FastAPI & Pydantic v2
- PyTorch (ST-GNN model)
- PostgreSQL 16 + TimescaleDB
- Redis 7
- Prometheus metrics exposition
- JSON Schema contracts & pytest

## Services

### Routing Engine (`services/routing-engine`)

Manages synthetic/production data feeds, data normalization, ingestion pipelines, model-based & heuristic multi-horizon speed prediction, priority-weighted route ranking, diversification caps with Redis rolling-window counters, and explanation payload generation.

**Endpoints:**
- `GET /health` — Liveness check (`?full=true` for dependency status)
- `GET /metrics` — Prometheus metrics exposition
- `POST /predict` — Multi-horizon speed predictions (5m, 15m, 30m)
- `POST /route` — Route ranking, capacity assignments, and explanation payloads

### Audit Service (`services/audit-service`)

Independently queries policy versions and observed route outcomes to verify compliance with published weight schedules, producing structured audit results without importing code from the routing engine.

**Endpoints:**
- `GET /health` — Liveness check (`?full=true` for database status)
- `GET /metrics` — Prometheus metrics exposition
- `POST /audit/outcome` — Single route outcome policy verification
- `POST /audit/batch` — Bulk route outcome verification
- `POST /audit/summary` — Compact aggregate batch audit summary

---

## Implementation Task Tracker

### Complete Phases (1–9)

- [x] **Phase 1 — Foundation**: Module structure, `__init__.py` files, typed configuration with `Settings.from_env()`.
- [x] **Phase 2 — Data Feed Adapters & Normalization**: Base `DataFeed`, production HTTP adapters, synthetic adapters, and timestamp-based `normalizer.py`.
- [x] **Phase 3 — TimescaleDB & Baselines**: `HistoricalBaselineRepository`, `IngestPipeline`, and `002_baseline_refresh.sql`.
- [x] **Phase 4 — ST-GNN Integration**: Feature tensor builder `feature_tensor.py`, `PredictionService.from_config()`, PyTorch GRU ST-GNN model.
- [x] **Phase 5 — Travel-Time Estimation & Routing Refinement**: Dedicated `travel_time.py` module, dynamic weight schedule wiring in `route_trip`, and `/predict` endpoint.
- [x] **Phase 6 — End-to-End Synthetic Pipeline & Contracts**: Full synthetic ingestion tests, explanation payload contract validation, and JSON schemas.
- [x] **Phase 7 — Audit Service Enhancements**: `BatchAuditor`, `/audit/batch`, `/audit/summary` endpoints, and outcome schemas.
- [x] **Phase 8 — Metrics, Observability & Health**: In-memory Prometheus metrics collectors, `/metrics` endpoints, and enriched `/health` checks.
- [x] **Phase 9 — Infrastructure & Documentation**: Migration `003_indices_and_views.sql`, healthchecked `docker-compose.yml`, `docs/configuration.md`, and `docs/api-reference.md`.

---

## Running Tests

Run test suites from the respective service directories:

```bash
# Routing engine (90 tests)
cd services/routing-engine && python -m pytest -v

# Audit service (32 tests)
cd services/audit-service && python -m pytest -v
```

Run all tests together from root:
```bash
python -m pytest services/routing-engine/tests services/audit-service/tests -v
```

---

## Running Locally with Docker Compose

Start TimescaleDB, Redis, and both microservices:

```bash
docker compose -f infra/docker-compose.yml up --build
```
