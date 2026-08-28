# Configuration Guide

CATRS uses typed configuration classes (`Settings`) initialized from environment variables in each service.

---

## Routing Engine Configuration

Configured via `app.config.Settings` in `services/routing-engine/app/config.py`.

### Environment Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `ROUTING_MODE` | `string` (`synthetic` \| `production`) | `synthetic` | Operating mode. When `synthetic`, synthetic feeds are used regardless of feed URLs. |
| `DATABASE_URL` | `string` | `None` | PostgreSQL / TimescaleDB connection URI. |
| `REDIS_URL` | `string` | `None` | Redis connection URI for rolling-window diversification counters. |
| `TRAFFIC_FEED_URL` | `string` | `None` | External traffic feed endpoint URL (production mode). |
| `WEATHER_FEED_URL` | `string` | `None` | External weather feed endpoint URL (production mode). |
| `INCIDENT_FEED_URL` | `string` | `None` | External incident feed endpoint URL (production mode). |
| `EVENT_FEED_URL` | `string` | `None` | External venue-event feed endpoint URL (production mode). |
| `STGNN_ENABLED` | `boolean` (`1`/`true`/`yes`) | `false` | Enable PyTorch Spatio-Temporal GNN predictor. |
| `STGNN_CHECKPOINT_PATH`| `string` | `None` | Path to `.pt` / `.pth` PyTorch model checkpoint. |
| `STGNN_FEATURE_COUNT` | `integer` | `9` | Number of input features per node per timestep. |
| `STGNN_NODE_COUNT` | `integer` | `100` | Number of graph nodes (10x10 grid = 100). |
| `STGNN_HIDDEN_SIZE` | `integer` | `32` | GRU hidden dimension size. |
| `PREDICTION_WINDOW_STEPS`| `integer` | `12` | Historical timesteps required for ST-GNN inference. |
| `PREDICTION_INTERVAL_MINUTES` | `integer` | `5` | Minutes per timestep window. |
| `DEFAULT_CAP_FRACTION` | `float` | `1.0` | Default capacity allocation fraction across equivalent OD pairs. |
| `DIVERSIFICATION_WINDOW_SECONDS` | `integer` | `60` | Rolling time window for route counter rate-limiting. |

---

## Audit Service Configuration

Configured via `app.config.Settings` in `services/audit-service/app/config.py`.

### Environment Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | `string` | `None` | Read-only connection URI to TimescaleDB for policy and outcome audits. |

---

## Docker Compose Example

```yaml
environment:
  DATABASE_URL: postgresql://traffic:traffic@postgres:5432/traffic
  REDIS_URL: redis://redis:6379/0
  ROUTING_MODE: synthetic
  STGNN_ENABLED: "false"
```
