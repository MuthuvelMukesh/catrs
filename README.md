# Traffic Routing System

This repository implements a three-layer traffic congestion prediction and routing platform.

## Layer architecture

- Layer 1: prediction + weighted diversified routing in `services/routing-engine`
- Layer 2: explanation payload generated in the same ranking flow as routing decisions
- Layer 3: independent audit service in `services/audit-service` with no shared code

The project starts with a synthetic data environment and local infrastructure so the core behavior can be tested before moving to production feeds and dedicated clusters.

## Local stack

- Python 3.12
- FastAPI
- PyTorch
- Postgres 16 + TimescaleDB
- Redis 7
- pytest

## Services

### Routing engine

The routing engine manages synthetic data generation, model-based prediction, route ranking, diversification, and explanation payload generation.

### Audit service

The audit service independently reads policy and observed system data to detect divergence from the published weight schedule and produce structured audit reports.

## Implementation status

### Complete

- [x] Synthetic 10x10 road graph and seasonal traffic-world data
- [x] Versioned, future-dated weight schedules with repository support
- [x] Prediction service with a standalone fallback heuristic
- [x] Priority-weighted route ranking, diversification caps, and Redis counters
- [x] Explanation payload generated from ranking variables
- [x] Contract-isolated audit verification and health endpoints
- [x] Route-to-audit cross-service integration test
- [x] Typed configuration modules with synthetic/production mode switching
- [x] Production data feed adapters (traffic, weather, incident, event) with configurable URLs
- [x] Synthetic feed adapters wrapping the deterministic world behind the same interface
- [x] Data normalizer merging heterogeneous feeds into unified SegmentContext records
- [x] Ingestion pipeline orchestrating feed → normalize → persist → baseline-refresh
- [x] TimescaleDB baseline refresh migration and performance indices
- [x] HistoricalBaselineRepository with upsert and SQL-based refresh
- [x] ST-GNN feature tensor construction from SegmentContext windows
- [x] PredictionService wired to ST-GNN with config-driven model loading
- [x] Enhanced RuntimeDependencies with PredictionService and baseline repository

### Remaining

- [ ] Dedicated travel-time estimation module and `/predict` endpoint
- [ ] Fix `route_trip` hardcoded weight schedule to accept caller's schedule
- [ ] End-to-end synthetic pipeline test (data → prediction → routing → explanation → audit)
- [ ] Contract schema validation tests (JSON Schema)
- [ ] Audit service batch auditor and `/audit/batch`, `/audit/summary` endpoints
- [ ] Versioned contracts for audit results and route outcomes
- [ ] Prometheus metrics and `/metrics` endpoint for both services
- [ ] Enriched `/health` endpoints with dependency checks
- [ ] Deployment configuration, additional migrations, and observability
- [ ] Updated documentation: configuration guide, API reference

### Running tests

Run service tests from each service directory:
```
cd services/routing-engine && python -m pytest -q
cd services/audit-service && python -m pytest -q
```

Run the integration test with Docker services:
```
pytest -q tests/integration
```

A GitHub Actions workflow runs lint and test checks for both services on push.
