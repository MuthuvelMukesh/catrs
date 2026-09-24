# Configuration Guide

CATRS uses typed configuration classes (`Settings`) initialized from environment variables in each microservice.

---

## Configuration Architecture

Both `services/routing-engine` and `services/audit-service` parse their configuration at application startup using custom `Settings` objects that inspect `os.environ`. 

- In local development, variables can be defined in a `.env` file at the root or exported in your shell.
- In Docker Compose, variables are injected via `infra/docker-compose.yml` or an `.env` file.
- All configuration options have resilient defaults, allowing the entire system to boot in synthetic mode even when zero environment variables are defined.

---

## Routing Engine Configuration (`services/routing-engine`)

Class: `app.config.Settings` in `services/routing-engine/app/config.py`

### General & Infrastructure Settings

| Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `ROUTING_MODE` | `string` | `synthetic` | Operating mode: `synthetic` or `production`. In `synthetic` mode, deterministic simulated feeds are used regardless of external feed URLs. |
| `DATASET_MODE` | `string` | `synthetic` | Selectable traffic data source: `synthetic`, `metr_la`, or `pems_bay`. |
| `METR_LA_DATA_PATH` | `string` | `data/raw/METR-LA.csv` | File path to METR-LA sensor readings CSV. |
| `METR_LA_GRAPH_PATH` | `string` | `data/raw/adj_mx_METR-LA.pkl` | File path to METR-LA adjacency matrix pickle. |
| `PEMS_BAY_DATA_PATH` | `string` | `data/raw/PEMS-BAY.csv` | File path to PEMS-BAY sensor readings CSV. |
| `PEMS_BAY_GRAPH_PATH` | `string` | `data/raw/adj_mx_PEMS-BAY.pkl` | File path to PEMS-BAY adjacency matrix pickle. |
| `DATABASE_URL` | `string` | `None` | PostgreSQL / TimescaleDB connection URI (e.g. `postgresql://traffic:traffic@localhost:5432/traffic`). If unset or unreachable, the service operates in in-memory mode without persistence. |
| `REDIS_URL` | `string` | `None` | Redis connection URI (e.g. `redis://localhost:6379/0`). If unset or unreachable, diversification counters fall back to thread-safe in-memory sliding window counters. |

### External Production Data Feeds (Production Mode Only)

When `ROUTING_MODE=production`, the engine will attempt to query these HTTP endpoints:

| Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `TRAFFIC_FEED_URL` | `string` | `None` | External sensor/GPS traffic feed URL. |
| `WEATHER_FEED_URL` | `string` | `None` | External weather API endpoint URL. |
| `INCIDENT_FEED_URL` | `string` | `None` | External incident/lane-closure API endpoint URL. |
| `EVENT_FEED_URL` | `string` | `None` | External stadium/venue event API endpoint URL. |

*Note: If any production feed URL is unset or fails to respond, the ingestion pipeline gracefully substitutes simulated readings from the fallback synthetic world without failing the request.*

### Spatio-Temporal Graph Neural Network (ST-GNN) Settings

| Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `STGNN_ENABLED` | `boolean` (`true`/`false`/`1`/`0`) | `false` | When `true`, loads the PyTorch ST-GNN model from `STGNN_CHECKPOINT_PATH`. If disabled or if the checkpoint fails to load, predictions automatically fall back to the deterministic heuristic. |
| `STGNN_CHECKPOINT_PATH` | `string` | `None` | Path to the PyTorch model checkpoint (`.pt` or `.pth` file). Recommended: `checkpoints/stgnn_default.pt`. |
| `STGNN_FEATURE_COUNT` | `integer` | `9` | Number of features per road node per timestep (speed, volume, weather, incidents, etc.). |
| `STGNN_NODE_COUNT` | `integer` | `100` | Number of nodes in the traffic network graph (10x10 synthetic grid = 100). |
| `STGNN_HIDDEN_SIZE` | `integer` | `32` | GRU hidden dimension size for the recurrent temporal layer. |
| `PREDICTION_WINDOW_STEPS` | `integer` | `12` | Historical lookback window length (12 timesteps @ 5-min intervals = 60 minutes). |
| `PREDICTION_INTERVAL_MINUTES` | `integer` | `5` | Temporal resolution of each sequence step. |

### Priority Routing & Diversification Settings

| Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `DEFAULT_CAP_FRACTION` | `float` | `1.0` | Default capacity limit assigned to the best route before splitting traffic (1.0 = no splitting). Values in `(0.0, 1.0)` enforce diversification. |
| `DIVERSIFICATION_WINDOW_SECONDS` | `integer` | `60` | Rolling time window in seconds for Redis/in-memory rate limiters and route assignment counters. |

---

## Audit Service Configuration (`services/audit-service`)

Class: `app.config.Settings` in `services/audit-service/app/config.py`

### Settings

| Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | `string` | `None` | Read-only connection URI to PostgreSQL / TimescaleDB. If unset or offline, policy verification relies on caller-supplied weight schedules in the audit payload. |

*Architectural Isolation Guarantee: The Audit Service configuration does NOT define Redis, ST-GNN, or feed URL variables. It has zero coupling with the Routing Engine.*

---

## Frontend Configuration (`frontend/`)

The web UI communicates with both backend services. In local development, the default ports are:
- Routing Engine: `http://localhost:8001` (Docker: `8001`, Local: `8000` or `8001`)
- Audit Service: `http://localhost:8002` (Docker: `8002`, Local: `8000` or `8002`)

The frontend UI includes input controls at the top of the dashboard allowing the user to dynamically adjust the API base URLs for both services without rebuilding.

---

## Complete `.env` Reference File

```bash
# Database & Cache Infrastructure
POSTGRES_DB=traffic
POSTGRES_USER=traffic
POSTGRES_PASSWORD=traffic
DATABASE_URL=postgresql://traffic:traffic@localhost:5432/traffic
REDIS_URL=redis://localhost:6379/0

# Service Port Bindings
ROUTING_ENGINE_PORT=8001
AUDIT_SERVICE_PORT=8002
FRONTEND_PORT=3000

# Operating Mode
ROUTING_MODE=synthetic

# Spatio-Temporal GNN Predictor
STGNN_ENABLED=false
STGNN_CHECKPOINT_PATH=checkpoints/stgnn_default.pt
STGNN_FEATURE_COUNT=9
STGNN_NODE_COUNT=100
STGNN_HIDDEN_SIZE=32

# Lookback Window
PREDICTION_WINDOW_STEPS=12
PREDICTION_INTERVAL_MINUTES=5

# Routing Parameters
DEFAULT_CAP_FRACTION=1.0
DIVERSIFICATION_WINDOW_SECONDS=60
```
