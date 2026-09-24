# Technical Implementation Details

Comprehensive architectural and implementation guide for the Congestion-Aware Traffic Routing System (CATRS).

---

## 1. Synthetic Data & World Simulation

To provide a fully reproducible research and test environment, CATRS includes a deterministic synthetic traffic world engine (`DeterministicSyntheticWorld` and `SyntheticWorld` in `services/routing-engine/app/data/synthetic_world.py`).

### 10x10 Road Network Topology
- 100 graph nodes laid out in a 10x10 planar grid.
- Bidirectional road links connecting adjacent horizontal and vertical vertices.
- Segments are identified deterministically (e.g. `seg_01`, `seg_02`, ...).

### 9 Simulation Scenarios
The world supports explicit scenario configurations via the `TrafficScenario` enumeration:
1. `BASELINE`: Normal off-peak weekday traffic (mean speed ~55 km/h, volume ~40-60 veh/h, clear conditions).
2. `PEAK_AM`: Morning rush hour congestion centered on inbound radial corridors (mean speed drops to ~25-35 km/h, volume surges to 120+ veh/h).
3. `PEAK_PM`: Evening rush hour congestion centered on outbound corridors.
4. `RAINSTORM`: Moderate precipitation across the grid reducing average speeds by 15-20% and increasing weather severity score to 0.5-0.7.
5. `SNOWSTORM`: Severe winter conditions causing 40% speed reductions and high weather severity (0.8-1.0).
6. `MAJOR_ACCIDENT`: Active multi-lane incident injected on primary bottleneck links, reducing speed to <10 km/h with high local spillover congestion.
7. `STADIUM_EVENT`: Massive localized traffic concentration surrounding event venue nodes with elevated event proximity scores.
8. `COMBINED_SEVERITY`: Concurrently active heavy rainstorm and major arterial incident.
9. `GRIDLOCK`: Complete systemic saturation across core intersections, driving speeds below 15 km/h network-wide.

All scenarios accept an optional integer `seed` to guarantee bitwise-identical time series generation across runs.

---

## 2. Data Feeds & Resilient Normalization

### Data Feed Abstraction
- The `DataFeed` abstract base class (`services/routing-engine/app/data/feeds/base.py`) defines the asynchronous contract `fetch_readings()`.
- Four feed types are supported: `traffic`, `weather`, `incident`, and `event`.
- In `ROUTING_MODE=production`, HTTP adapters query external REST feeds. If any external endpoint is unconfigured, unreachable, or returns a 5xx error, the pipeline catches the exception, logs a warning, and gracefully substitutes simulated readings from the fallback synthetic generator.
- In `ROUTING_MODE=synthetic`, synthetic adapters wrap the deterministic world directly.

### Temporal Normalization
- `normalizer.py` merges heterogeneous feeds into unified `SegmentContext` domain models.
- Contexts align traffic speed/volume with the closest weather reading, active incident status, and venue event proximity scores for each segment within a configurable temporal tolerance window.

---

## 3. Ingestion Pipeline & Historical Baselines

### IngestPipeline
- Located in `services/routing-engine/app/data/ingestion.py`.
- Step 1: Poll feeds concurrently.
- Step 2: Normalize feed outputs into `SegmentContext` snapshots.
- Step 3: Persist readings into PostgreSQL / TimescaleDB hypertable `traffic_readings`.
- Step 4: Trigger recalculation of historical baseline speeds.
- Resilient operation: If the database is unreachable, `IngestPipeline` skips SQL operations and returns the normalized contexts in-memory for live routing.

### Database Hypertables & Baselines
- Migration `001_initial_schema.sql`: Sets up TimescaleDB hypertables, weight schedules, and outcome audit tables.
- Migration `002_baseline_refresh.sql`: Creates `refresh_historical_baselines()` stored procedure, grouping readings by `(segment_id, weekday, hour)` to maintain rolling mean and median speeds.
- Migration `003_indices_and_views.sql`: Adds compound indices and analytical views for fast auditing and compliance queries.

---

## 4. Unified Traffic Data Layer & Benchmark Datasets

### Unified Dataset Architecture
CATRS implements an extensible data abstraction layer (`data/datasets/`):
- `TrafficDataset`: Abstract base interface defining contracts for raw loading, feature extraction, graph construction, and sliding-window generation.
- `MetrLaDataset`: Loader and processor for the Los Angeles County highway sensor network (207 sensors, 5-minute sampling interval).
- `PemsBayDataset`: Loader and processor for the California Bay Area highway sensor network (325 sensors, 5-minute sampling interval).
- `SyntheticTrafficDataset`: Wraps the 10x10 deterministic synthetic world (100 nodes, 9 scenarios).

### Preprocessing & Zero-Leakage Pipeline
1. **Timestamp Normalization & Chronological Sorting**: Guarantees strict monotonic progression.
2. **Missing-Value Analysis**: Detects zero-readings from sensor outages and excludes them from mean/variance statistics.
3. **Strict Zero-Leakage Splitting**: Splits data chronologically into 70% Train, 10% Validation, and 20% Test before normalization.
4. **StandardScaler**: Fitted strictly on training observations ($\mu_{train}, \sigma_{train}$) and serialized to JSON.
5. **Sliding-Window Sequence Generation**: Constructs lookback sequence tensors $X \in \mathbb{R}^{B \times 12 \times N \times F}$ and multi-horizon target speed matrices $Y \in \mathbb{R}^{B \times N \times 3}$ (+5m, +15m, +30m).

---

## 5. Spatio-Temporal Prediction Pipeline (ST-GNN)

### Model Architecture
- Implemented in `services/routing-engine/app/models/st_gnn.py` using PyTorch.
- **Dynamic Variable Node Count**: Dynamically operates on variable sensor networks without hardcoded dimensions ($N \in \{100, 207, 325\}$).
- **Spatial Message Passing**: 2-layer Graph Convolution (GCN) using symmetric normalized adjacency:
  $$\hat{A} = \tilde{D}^{-\frac{1}{2}} \tilde{A} \tilde{D}^{-\frac{1}{2}}, \quad \tilde{A} = A + I_N$$
  $$H^{(l+1)} = \text{ReLU}(\hat{A} H^{(l)} W^{(l)})$$
- **Temporal Recurrence**: Gated Recurrent Unit (GRU) modeling time dependencies over spatial embeddings across historical timesteps.
- **Node-Level Multi-Horizon Output Head**: Fully-connected projection emitting $[B, N, 3]$ speeds for all nodes across 5m, 15m, and 30m horizons.

### Node-to-Road Mapping Layer
- Implemented in `app/routing/node_mapping.py` (`SensorToRouteMapper`).
- Translates sensor node predictions into directed routing segments:
  $$\text{travel\_time} = \frac{\text{segment\_length}}{\text{predicted\_speed}} \times 3600$$
- Maintains clear separation: Real benchmark datasets validate speed forecasting accuracy; synthetic scenarios validate priority routing, accident avoidance, and equilibrium diversification.

### Heuristic Fallback
- `compute_prediction()` in `services/routing-engine/app/models/pipeline.py` provides a deterministic polynomial formulation.
- If model checkpoint loading fails or PyTorch is unavailable, the service automatically executes this heuristic and flags the response with `model_used="heuristic"`.

---

## 5. Travel Time, Routing Equilibrium & Diversification

### Travel Time Estimation
- Located in `services/routing-engine/app/routing/travel_time.py`.
- Formulates travel time as $T = \frac{D}{v}$ with rigorous bounds:
  - If $v \le 0$ or either input is `NaN`/`Inf`, returns sentinel travel time of $86,400.0\text{ s}$ (24 hours) to avoid division by zero while penalizing impassable edges.
  - Normal travel time clamped between 1 second and 86,400 seconds.

### Priority-Weighted Route Ranking
- Located in `services/routing-engine/app/routing/priority_routing.py`.
- Base cost of route $r$ is derived from predicted travel time $T_r$ and intrinsic priority score $P_r$:
  $$\text{adjusted\_score}(r) = \frac{T_r}{P_r \cdot W(c)}$$
  where $W(c)$ is the priority multiplier for trip category $c$ from the active policy schedule (e.g. `emergency` = 10.0, `commuter` = 1.0).
- Lower adjusted score corresponds to higher ranking (rank 1 is best).

### Equilibrium Diversification
- Prevents Braess's paradox and herd routing into a single corridor.
- The top-ranked route is allocated a maximum fraction of total requests:
  $$\text{max\_cap} = \lfloor N \cdot \text{cap\_fraction} \rfloor$$
- Overflow vehicles are distributed to alternative ranked routes, backed by sliding-window Redis counters (`redis_counter.py`) or thread-safe in-memory sliding logs.
- Prevents capacity spillover beyond `max_cap`.

---

## 6. Layer 2 Explanation Payload

Every routing decision emits a comprehensive Layer 2 explanation payload complying with `contracts/explanation-payload.schema.json`.
- Crucial Architectural Rule: Explanation attributes are extracted directly from the local variables of the active ranking calculation.
- Contains:
  - `recommended_route`: Chosen route ID and predicted travel time.
  - `alternatives_considered`: Ranked list of evaluated candidate routes.
  - `diversification`: Boolean flag indicating if traffic splitting was applied, human-readable reason, and assignment pool percentage.
  - `priority_context`: Trip category, applied weight, and `affected_ranking` boolean (indicating if the priority multiplier altered the winner).
  - `weight_schedule_version`: Pinned policy version string.

---

## 7. Layer 3 Independent Audit Service

- Located in `services/audit-service/`.
- Strict isolation: **Zero import dependencies** on `services/routing-engine`. Communication happens solely via contracts and database tables.
- Evaluates route outcomes against version-pinned weight schedules.
- Verifies:
  1. Outcome timestamp falls within the policy's effective date window.
  2. Trip category is valid.
  3. Applied weight matches the published schedule (unlisted categories default to 1.0 per policy).
  4. Policy version string matches.
- Supports both single outcome auditing (`/audit/outcome`), bulk itemized auditing (`/audit/batch`), and aggregate summary verification (`/audit/summary`).

---

## 8. Root Test Runner Architecture

Both microservices use the package name `app` internally (`services/routing-engine/app` and `services/audit-service/app`). To enable unified, seamless root test execution:
- `pytest.ini` configures `--import-mode=importlib`.
- Root `conftest.py` implements custom test collection and module caching management:
  - Dynamically injects the specific service path into `sys.path`.
  - Implements `_purge_app_modules()` before running tests from each service directory, clearing out cached `app.*` submodules from `sys.modules`.
- Result: Developers can run `python -m pytest -q` from the repository root to execute all 136 tests across both services without collision.

---

## 9. Research & Evaluation Scripts

Located in `scripts/`:
1. `generate_synthetic_data.py`: CLI tool for generating synthetic traffic datasets across all 9 scenarios with metadata.
2. `evaluate_models.py`: Calculates multi-horizon speed prediction accuracy (MAE, RMSE, MAPE) across 5m, 15m, and 30m intervals.
3. `evaluate_routing.py`: Measures traffic distribution equilibrium and Herfindahl-Hirschman Index (HHI) concentration reduction.
4. `evaluate_audit.py`: Validates policy defect detection rates, false acceptance rates, and verification throughput.
5. `run_experiments.py`: Master orchestrator running the entire reproducible research evaluation suite and outputting summary reports.
