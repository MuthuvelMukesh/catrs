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

## CI

A GitHub Actions workflow runs lint and test checks for both services on push.
