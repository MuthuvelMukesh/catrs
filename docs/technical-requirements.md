# Technical Requirements

## Functional goals

1. Predict congestion from segment-level traffic, weather, incidents, and event activity.
2. Route trips according to a priority-weighted and diversified traffic assignment policy.
3. Emit a route explanation payload from the exact same local variables used in ranking.
4. Independently verify routing outcomes against the published policy schedule.

## Non-functional constraints

- FastAPI services with health endpoints and pytest coverage.
- Local prototype runs on Postgres + TimescaleDB and Redis.
- Service isolation enforced by contracts and CI checks.
- Data and policy versions must be append-only and version-pinned.
