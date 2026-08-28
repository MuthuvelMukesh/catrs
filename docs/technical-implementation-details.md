# Technical Implementation Details

## 1. Synthetic data and storage

- Build a synthetic 10x10 grid road graph as the initial prototype.
- Generate segment speed, volume, weather, incident, and venue-event data with daily and weekly seasonality.
- Persist readings in Postgres and use TimescaleDB hypertables for time-series storage.
- Maintain a historical baseline view keyed by segment, weekday, and hour.

## 2. Data feeds and normalization

- Abstract `DataFeed` interface for all feed sources (traffic, weather, incident, event).
- Production adapters use `httpx` with configurable base URLs; return empty lists when unconfigured.
- Synthetic adapters wrap the deterministic world behind the same interface.
- `normalizer.py` merges heterogeneous feed readings into unified `SegmentContext` records by segment_id and closest-timestamp matching.
- System operates without external feeds by falling back to synthetic data (rule 12).

## 3. Ingestion pipeline

- `IngestPipeline` orchestrates: fetch from feeds → normalize → persist traffic readings → refresh historical baselines.
- Works without a database (returns contexts only for in-process use).
- `HistoricalBaselineRepository.refresh_from_readings()` recomputes baselines from the full `traffic_readings` table.
- Migration `002_baseline_refresh.sql` adds a server-side refresh function and performance indices.
- Migration `003_indices_and_views.sql` adds analytical reporting views and compound indices for route outcomes and audits.

## 4. Prediction model

- Use a spatio-temporal model over 12 recent timesteps for 5/15/30-minute horizons.
- Keep fallback heuristic separate from ML implementation to support graceful degradation.
- `feature_tensor.py` converts `SegmentContext` windows into `[1, 12, nodes, 9]` tensors via `build_feature_vector`.
- `PredictionService.from_config()` optionally constructs an `STGNNPredictor` from config with checkpoint loading.
- When ST-GNN is unavailable, `compute_prediction()` heuristic is used as fallback.
- Dedicated `/predict` endpoint exposes multi-horizon predictions over HTTP.

## 5. Travel-time estimation & routing

- Dedicated `app/routing/travel_time.py` handles speed-to-time conversions with sentinel handling for division-by-zero prevention.
- `route_trip` receives caller's active weight schedule rather than using hardcoded constants.
- Maintain a versioned weight schedule table where each new version is future-dated.
- Rank routes using a priority-weighted equilibrium formulation with diversification caps.
- Use Redis counters to prevent route herding within a rolling time window.

## 6. Explanation payload

- Emit the explanation payload directly inside the ranking function.
- Ensure route travel-time values in the payload are copied from the same local values used to rank alternatives.
- Validated against schema in `contracts/explanation-payload.schema.json`.

## 7. Audit boundary & Batch Auditing

- The audit service reads from read-only replicas or independent connections.
- `BatchAuditor` handles bulk outcome verification against pinned weight schedule versions.
- `/audit/batch` and `/audit/summary` endpoints support high-throughput auditing.
- Version-pinned queries ensure the policy used for period X matches the schedule in effect during X.
- CI checks reject imports from the routing-engine package in audit-service.
- Contracts codified in `contracts/route-outcome.schema.json` and `contracts/audit-result.schema.json`.

## 8. Metrics & Observability

- In-memory `RoutingMetrics` and `AuditMetrics` collectors expose Prometheus exposition format on `/metrics`.
- `/health` endpoints support both lightweight liveness checks and detailed dependency readiness inspections via `?full=true`.

## 9. Configuration

- `app/config.py` in each service provides typed `Settings` with `from_env()` factory.
- `RunMode.SYNTHETIC` (default) and `RunMode.PRODUCTION` control feed source selection.
- ST-GNN, feed URLs, and routing parameters are all configurable via environment variables.
