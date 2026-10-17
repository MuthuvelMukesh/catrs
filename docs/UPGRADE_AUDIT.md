# CATRS END-TO-END ENGINEERING UPGRADE AUDIT REPORT

**Date:** 2026-10-17  
**Author:** Principal Architect & Engineering Team  
**Scope:** Full repository audit across ML pipeline, routing engine, real-time ingestion, security, reliability, audit service, and operations.

---

## 1. Executive Overview & Existing Architecture

The **Congestion-Aware Traffic Routing System (CATRS)** is architected to optimize urban vehicle flow while enforcing municipal policy schedules and preventing network-wide corridor collapse through rolling-window diversification.

### Architectural Components and Data Flows

```
               ┌────────────────────────────────────────────────────────┐
               │                     DATA INGESTION                     │
               │  TrafficFeeds (Live API / Fallback Synthetic World)    │
               │  Auxiliary Feeds (Weather, Incidents, Venue Events)    │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │                NORMALIZER & REPOSITORIES               │
               │  SegmentContext Normalization & TimescaleDB Persistence│
               │  Rolling Historical Baseline Computation (Ch 3)        │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │                 ML PREDICTION SERVICE                  │
               │  ST-GNN (Spatial GCN + Temporal GRU) / Heuristic Fallback│
               │  Multi-Horizon Forecasting: 5m, 15m, 30m Speed         │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │                    ROUTING ENGINE                      │
               │  Travel Time Estimation (Distance / Predicted Speed)   │
               │  Priority Policy Weighting & Ranking                   │
               │  Redis Rolling-Window Atomic Diversification Counter   │
               └──────────────┬──────────────────────────┬──────────────┘
                              │                          │
           Route Outcome JSON │                          │ Route Outcome JSON
           Schema Contract    │                          │ Schema Contract
                              ▼                          ▼
               ┌───────────────────────────┐  ┌─────────────────────────┐
               │       VITE FRONTEND       │  │   POLICY AUDIT SERVICE  │
               │ Real-Time Operator Display│  │ Independent Microservice│
               │ Telemetry & Route Ranking │  │ Contract Verification   │
               └───────────────────────────┘  └─────────────────────────┘
```

---

## 2. Confirmed Findings & Defect Register

### Finding 1: ML Pipeline Evaluation Scaling Mismatch & Baseline Inversion
- **Severity:** Critical
- **Affected Files:**
  - `scripts/evaluate_models.py` (lines 51-150)
  - `services/routing-engine/app/models/baselines.py` (lines 23-60)
  - `services/routing-engine/app/models/prediction_service.py` (lines 75-117)
  - `data/datasets/real_dataset.py` (lines 172-215)
  - `results/metr_la/metrics.json` (lines 1-158)
- **Evidence & Reproduction:**
  1. In `real_dataset.py` lines 177-184, `train_feat_norm` normalizes channel 0 (speed) and channel 3 (historical baseline) using `StandardScaler` (z-score: mean ~0, std ~1).
  2. In `real_dataset.py` lines 186-215, targets `Y_train`, `Y_val`, `Y_test` are stored in original unnormalized physical units (mph / km/h, average ~53.7 mph for METR-LA).
  3. In `evaluate_models.py` lines 108-120:
     - `HistoricalMeanModel` reads channel 3 of `X_test` (which is normalized, ~0.0).
     - `PersistenceModel` reads channel 0 of `X_test` (which is normalized, ~0.0).
     - Both baselines predict speeds near 0.0 mph.
     - Compared against ground truth `Y_test` (~56.0 mph), `diff = 0 - 56 = -56.0 mph`, generating MAE = 56.06 mph, RMSE = 57.92 mph, and $R^2 = -13.37$.
  4. In `evaluate_models.py` lines 122-126, `LinearRegressionModel` is fit with `lr_model.fit(X_train, Y_train)`. Since `Y_train` is unnormalized (~56 mph), linear regression's learned weights absorbed the inverse transformation, outputting predictions on the scale of 56 mph, achieving MAE = 5.05 mph and $R^2 = 0.52$.
  5. In neural baselines (`GRU`, `GCN`, ablations, multi-seed), models were trained on unnormalized targets with normalized inputs over 2-3 epochs with Adam lr=0.005. Gradients exploded or failed to converge, resulting in MAE ~48-53 mph.
  6. Verified by running `python scripts/evaluate_models.py --dataset synthetic`:
     - Historical Mean MAE: 51.13 mph
     - Persistence MAE: 51.13 mph
     - Linear Regression MAE: 2.21 mph
- **Recommended Fix:**
  - Ensure uniform scale handling: all models predict in normalized space and are systematically inverse-transformed via `scaler.inverse_transform()` before metric calculation, or baselines take unnormalized historical inputs.
  - Implement a dedicated `EvaluationRunner` with verified inverse scaling, finite value checking, and non-negative speed clamping.
  - In `PredictionService`, integrate `StandardScaler` to normalize input tensors and inverse-transform neural outputs before returning speeds.

---

### Finding 2: Root Test Suite Failure — Import Mode & Missing Package Initialization
- **Severity:** Critical
- **Affected Files:**
  - `conftest.py` (lines 8-47)
  - `data/__init__.py` (missing)
  - `tests/datasets/test_dataset_loaders.py` (lines 9-13)
  - `tests/integration/test_real_dataset_routing.py` (lines 11-14)
- **Evidence & Reproduction:**
  1. Executing `pytest` in repository root immediately aborts with 4 collection errors: `ModuleNotFoundError: No module named 'data'`.
  2. `conftest.py` modifies `sys.path` to switch between `ROUTING_DIR` and `AUDIT_DIR`, but fails to ensure `ROOT_DIR` remains in `sys.path`.
  3. `data/` lacked an `__init__.py` file.
  4. Tests in `tests/datasets/test_dataset_loaders.py` and `tests/integration/test_real_dataset_routing.py` fail unconditionally when optional external dataset files (`METR-LA.csv`, `adj_mx_METR-LA.pkl`) are absent instead of skipping or utilizing generated fixtures.
- **Recommended Fix:**
  - Add `str(ROOT_DIR)` permanently to `sys.path` in `conftest.py`.
  - Add `data/__init__.py`.
  - Add pytest `skipif` decorators or synthetic fallbacks for raw dataset tests when raw files are omitted.

---

### Finding 3: Missing Realistic Road Network Routing & OSM Graph Adapter
- **Severity:** Critical / High
- **Affected Files:**
  - `services/routing-engine/app/routing/priority_routing.py`
  - `services/routing-engine/app/main.py` (lines 33-45)
  - `services/routing-engine/app/data/synthetic_world.py` (lines 33-58)
- **Evidence & Reproduction:**
  1. The routing engine accepts only pre-computed route options via `routes: list[RouteOption]`. There is no graph pathfinding engine (Dijkstra, A*, or K-shortest paths) anywhere in the repository.
  2. No OpenStreetMap (OSM) graph importer or road network model exists.
  3. `synthetic_world.py` generates a static grid with only unidirectional downward/rightward edges; no path synthesis or dynamic impedance modeling is performed.
  4. Turn restrictions, road classes, one-way constraints, and dynamic closures cannot be evaluated on arbitrary networks.
- **Recommended Fix:**
  - Implement a dedicated `RoadGraph` model representing nodes, directed edges, length, free-flow speed, road class, access restrictions, one-way flags, and dynamic congestion multipliers.
  - Implement an OSM graph importer/adapter supporting GeoJSON / OSM XML / dictionary representations.
  - Implement Dijkstra / A* path search algorithms capable of generating viable alternative paths with live travel cost calculations.
  - Expose `/route/navigate` or enhance `/route` to generate valid paths dynamically between origin-destination coordinates.

---

### Finding 4: Ingestion Feeds Lack Resiliency, Circuit Breakers, & Integrity Metadata
- **Severity:** High
- **Affected Files:**
  - `services/routing-engine/app/data/feeds/base.py` (lines 9-66)
  - `services/routing-engine/app/data/feeds/traffic_feed.py` (lines 18-43)
  - `services/routing-engine/app/data/ingestion.py` (lines 41-94)
- **Evidence & Reproduction:**
  1. `TrafficFeed` fetches from external endpoints without retries, backoff, or circuit breakers.
  2. When disabled or unreachable, feeds silently return empty lists. `IngestPipeline` silently falls back to synthetic data without marking readings as synthetic.
  3. Observations lack provenance metadata: ingestion timestamps, source identifiers, data quality/confidence scores, staleness status, and explicit synthetic flags.
- **Recommended Fix:**
  - Enhance `TrafficReading` dataclass to include `source`, `ingested_at`, `confidence_score`, `is_synthetic`, and `units`.
  - Implement a resilient HTTP client wrapper with bounded exponential backoff, circuit breaking (state machine: closed, open, half-open), and schema validation.
  - Explicitly mark degraded/synthetic mode in ingestion results and API telemetry.

---

### Finding 5: Security Weaknesses & Unsafe Production Defaults
- **Severity:** High
- **Affected Files:**
  - `services/routing-engine/app/main.py` (lines 76-82)
  - `services/audit-service/app/main.py` (lines 42-48)
  - `infra/docker-compose.yml` (lines 7-35)
  - `services/routing-engine/Dockerfile`
  - `services/audit-service/Dockerfile`
  - `.env.example`
- **Evidence & Reproduction:**
  1. Both FastAPI services use `CORSMiddleware` with `allow_origins=["*"]` combined with `allow_credentials=True`, an invalid and insecure combination.
  2. No authentication or API key checks exist for administrative actions (e.g. `/dataset/select`, `/metrics`).
  3. Docker Compose exposes database (`5432`) and Redis (`6379`) to host `0.0.0.0` with hardcoded credentials `traffic:traffic` and unauthenticated Redis.
  4. Dockerfiles run as default `root` user without security contexts or resource bounds.
  5. `main.py` lines 317-330 uses bare `except Exception: pass` when persisting route outcomes to TimescaleDB, masking database write failures.
- **Recommended Fix:**
  - Configure explicit CORS origin lists from settings.
  - Implement API key / token header authentication for sensitive and administrative endpoints.
  - Remove hardcoded credentials from compose and require environment-injected secrets.
  - Run container processes under dedicated non-root user `appuser`.
  - Add structured logging and operational error propagation instead of silent exception suppression.

---

### Finding 6: TimescaleDB & Database Reliability
- **Severity:** Medium
- **Affected Files:**
  - `services/routing-engine/app/data/repositories.py`
  - `services/audit-service/app/repositories.py`
  - `infra/migrations/001_initial_schema.sql`
- **Evidence & Reproduction:**
  1. Repositories manage single raw database connections without pooling or query timeouts.
  2. Lack of explicit health checks validating query responsiveness; `/health` simply checks if connection object is not None.
- **Recommended Fix:**
  - Implement connection pooling and query timeouts.
  - Add migration validation and health probes that execute lightweight test queries (`SELECT 1`).

---

### Finding 7: Frontend Operational Transparency & Real Road Network Visualization
- **Severity:** Medium
- **Affected Files:**
  - `frontend/main.js`
  - `frontend/index.html`
- **Evidence & Reproduction:**
  1. Frontend currently displays a simple synthetic grid; it lacks interactive map rendering for imported road networks.
  2. Stale or degraded data states are not highlighted with prominent visual badges.
- **Recommended Fix:**
  - Add road network visualization and route overlay capabilities.
  - Prominently indicate data source (Live vs Synthetic) and model status (ST-GNN vs Baseline vs Fallback).

---

## 3. Prioritized Implementation Roadmap

1. **Step 1 (P0): Core Framework & Test Collection Fix**
   - Fix `conftest.py` sys.path handling.
   - Create `data/__init__.py`.
   - Ensure all existing and new tests run seamlessly under `pytest`.

2. **Step 2 (P0): ML Pipeline Remediation & Baseline Normalization**
   - Refactor `evaluate_models.py` and `baselines.py` to ensure all models evaluate on unnormalized physical units via proper inverse transformation.
   - Add model verification checks: reject non-finite (NaN, Inf) and negative speed predictions.
   - Re-run benchmark evaluation and generate verified `results/synthetic` and `results/metr_la` metrics.

3. **Step 3 (P1): Realistic Road-Network Routing & OpenStreetMap Adapter**
   - Build `RoadGraph` data structure supporting directed links, restrictions, and capacities.
   - Implement OpenStreetMap (OSM) importer adapter.
   - Implement Dijkstra / A* multi-path generation.
   - Integrate with priority weighting and Redis rolling-window diversification.

4. **Step 4 (P1): Real-Time Data Ingestion & Feed Resiliency**
   - Upgrade feed abstractions with schema validation, timeouts, retries, and circuit breakers.
   - Add data provenance, timestamps, confidence scores, and synthetic indicators.

5. **Step 5 (P1): Security & API Hardening**
   - Strict CORS allowlists.
   - API key authorization for administrative and sensitive endpoints.
   - Replace bare `except Exception: pass` with structured error handling.
   - Hardened non-root Dockerfiles and secure Docker Compose configuration.

6. **Step 6 (P2): Policy Audit, Explainability & Database Reliability**
   - Add comprehensive trace explanations to route responses.
   - Verify audit service boundary with extensive negative and malformed payload tests.
   - Enhance database connection handling and operational status endpoints.

7. **Step 7 (P2): Frontend & Dashboard Enhancements**
   - Upgrade dashboard to reflect live vs synthetic data status, road graph routing, and model health.

8. **Step 8 (P0): Verification & Documentation Deliverables**
   - Run end-to-end regression test suite.
   - Author `docs/ML_PIPELINE_AUDIT.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/DEPLOYMENT.md`, `docs/TESTING.md`, and `docs/UPGRADE_CHANGELOG.md`.
