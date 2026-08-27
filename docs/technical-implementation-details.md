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

## 4. Prediction model

- Use a spatio-temporal model over 12 recent timesteps for 5/15/30-minute horizons.
- Keep fallback heuristic separate from ML implementation to support graceful degradation.
- `feature_tensor.py` converts `SegmentContext` windows into `[1, 12, nodes, 9]` tensors via `build_feature_vector`.
- `PredictionService.from_config()` optionally constructs an `STGNNPredictor` from config with checkpoint loading.
- When ST-GNN is unavailable, `compute_prediction()` heuristic is used as fallback.

## 5. Routing and diversification

- Maintain a versioned weight schedule table where each new version is future-dated.
- Rank routes using a priority-weighted equilibrium formulation with diversification caps.
- Use Redis counters to prevent route herding within a rolling time window.

## 6. Explanation payload

- Emit the explanation payload directly inside the ranking function.
- Ensure route travel-time values in the payload are copied from the same local values used to rank alternatives.

## 7. Audit boundary

- The audit service reads from read-only replicas or independent connections.
- Version-pinned queries ensure the policy used for period X matches the schedule in effect during X.
- CI checks reject imports from the routing-engine package in audit-service.

## 8. Configuration

- `app/config.py` in each service provides typed `Settings` with `from_env()` factory.
- `RunMode.SYNTHETIC` (default) and `RunMode.PRODUCTION` control feed source selection.
- ST-GNN, feed URLs, and routing parameters are all configurable via environment variables.

