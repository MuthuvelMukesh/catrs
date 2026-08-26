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

### Remaining

- [ ] Connect production traffic, weather, incident, and event feeds
- [ ] Persist live readings and audit results through Postgres/TimescaleDB
- [ ] Run the ST-GNN over the production feature and model pipeline
- [ ] Connect Redis-backed diversification state in deployed environments
- [ ] Add deployment configuration, migrations, observability, and operational runbooks
- [ ] Run service tests from each service directory: `cd services/<service> && pytest -q`
- [ ] Run the integration test with Docker services: `pytest -q tests/integration`

A GitHub Actions workflow runs lint and test checks for both services on push.
