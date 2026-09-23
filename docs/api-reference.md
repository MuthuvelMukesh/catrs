# API Reference

Complete endpoint specification for the CATRS (Congestion-Aware Traffic Routing System) microservices.

---

## Architecture & Network Addressing

| Service | Container Port | Host Port (Docker) | Local Dev Port | Base URL (Local Dev) |
| :--- | :--- | :--- | :--- | :--- |
| **Routing Engine** | `8000` | `8001` | `8001` (or `8000`) | `http://localhost:8001` |
| **Audit Service** | `8000` | `8002` | `8002` (or `8000`) | `http://localhost:8002` |
| **Frontend UI** | `5173` | `5173` | `5173` | `http://localhost:5173` |

---

## Routing Engine Endpoints

### 1. Health Check
`GET /health`

Returns service operational status. Supports deep dependency diagnostics via query parameter.

**Query Parameters:**
- `full` (optional, boolean, default: `false`): When `true`, inspects live connections to PostgreSQL/TimescaleDB, Redis, and ST-GNN predictor availability.

**Success Response (200 OK):**
```json
{
  "status": "ok"
}
```

**Full Diagnostics Response (200 OK):**
```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "predictor": "st_gnn"
}
```
*(If dependencies are offline in synthetic mode, returns `"disconnected"` and `"fallback"` respectively).*

---

### 2. Multi-Horizon Speed Prediction
`POST /predict`

Calculates 5-minute, 15-minute, and 30-minute predicted traffic speeds (in km/h) for a road segment using either the PyTorch Spatio-Temporal GNN (`st_gnn`) or the deterministic polynomial regression fallback (`heuristic`).

**Headers:**
- `Content-Type: application/json`

**Request Body Schema:**
```json
{
  "segment_id": "seg_01",
  "current_speed": 45.0,
  "current_volume": 80,
  "historical_baseline_speed": 55.0,
  "weather_severity_score": 0.2,
  "active_incident_flag": false,
  "event_proximity_score": 0.0,
  "upstream_segment_congestion": 0.1,
  "time_of_day": 8,
  "day_of_week": 1
}
```

**Field Descriptions:**
- `segment_id` (string, required): Non-empty string identifying the road network segment.
- `current_speed` (float, required, `>= 0.0`): Instantaneous measured speed in km/h.
- `current_volume` (integer, required, `>= 0`): Instantaneous vehicle count per hour.
- `historical_baseline_speed` (float, required, `> 0.0`): Historical expected speed for this hour and day.
- `weather_severity_score` (float, optional, `0.0` to `1.0`, default: `0.0`): Adverse weather impact coefficient.
- `active_incident_flag` (boolean, optional, default: `false`): True if an accident or lane closure is active.
- `event_proximity_score` (float, optional, `0.0` to `1.0`, default: `0.0`): Proximity to high-attendance venue events.
- `upstream_segment_congestion` (float, optional, `0.0` to `1.0`, default: `0.0`): Bottleneck spillover from upstream edges.
- `time_of_day` (integer, optional, `0` to `23`, default: `12`): Hour of day.
- `day_of_week` (integer, optional, `0` to `6`, default: `0`): Day of week (0 = Monday).

**Success Response (200 OK):**
```json
{
  "segment_id": "seg_01",
  "predicted_speed_5m": 50.3,
  "predicted_speed_15m": 46.28,
  "predicted_speed_30m": 42.75,
  "model_used": "st_gnn"
}
```

**Error Responses:**
- `400 Bad Request`: If `segment_id` is empty or non-string.
- `422 Unprocessable Entity`: If speed is negative, scores exceed `[0.0, 1.0]`, or fields contain `NaN`/`Inf`.
```json
{
  "detail": [
    {
      "type": "greater_than_equal",
      "loc": ["body", "current_speed"],
      "msg": "Input should be greater than or equal to 0"
    }
  ]
}
```

---

### 3. Route Trip & Rank Alternatives
`POST /route`

Ranks alternative candidate routes by applying the active policy weight schedule, derives estimated travel times, enforces rolling-window diversification caps (via Redis or in-process counters), and emits an auditable Layer 2 explanation payload.

**Headers:**
- `Content-Type: application/json`

**Request Body Schema:**
```json
{
  "trip_category": "emergency",
  "routes": [
    {
      "route_id": "route_north",
      "travel_time_s": 400.0,
      "priority_score": 2.0,
      "distance_m": 4000.0,
      "predicted_speed_5m": 36.0
    },
    {
      "route_id": "route_south",
      "travel_time_s": 500.0,
      "priority_score": 1.0,
      "distance_m": 4500.0,
      "predicted_speed_5m": 32.4
    }
  ],
  "request_count": 10,
  "current_counts": {
    "route_north": 0,
    "route_south": 0
  },
  "cap_fraction": 0.7,
  "weight_schedule": {
    "version": "2026-08-26-v1",
    "effective_date": "2026-08-26",
    "weights": {
      "emergency": 10.0,
      "public_transit": 3.0,
      "high_occupancy": 1.5,
      "commuter_general": 1.0
    }
  }
}
```

**Field Descriptions:**
- `trip_category` (string, required): Category of vehicle (e.g. `emergency`, `public_transit`, `commuter_general`).
- `routes` (array of objects, required): Candidate paths. Each must specify `route_id` and either `travel_time_s` or both `distance_m` and `predicted_speed_5m`.
- `request_count` (integer, optional, default: `1`): Batch volume of vehicles being routed simultaneously.
- `current_counts` (object, optional): Active reservation counts per route if tracking in-process.
- `cap_fraction` (float, optional, `0.0` to `1.0`, default: `1.0`): Maximum fraction of total traffic permitted on the primary route before forced diversification.
- `weight_schedule` (object, required): Explicit versioned policy definition with `version`, `effective_date`, and `weights`.

**Success Response (200 OK):**
```json
{
  "ranked_routes": [
    {
      "route_id": "route_north",
      "travel_time_s": 400.0,
      "priority_score": 2.0,
      "weight_applied": 10.0,
      "adjusted_score": 0.05
    },
    {
      "route_id": "route_south",
      "travel_time_s": 500.0,
      "priority_score": 1.0,
      "weight_applied": 10.0,
      "adjusted_score": 0.02
    }
  ],
  "assignments": {
    "route_north": 7,
    "route_south": 3
  },
  "explanation": {
    "route_id": "route_north",
    "recommended_route": {
      "route_id": "route_north",
      "predicted_travel_time_s": 400.0
    },
    "alternatives_considered": [
      {
        "route_id": "route_north",
        "predicted_travel_time_s": 400.0,
        "rank": 1
      },
      {
        "route_id": "route_south",
        "predicted_travel_time_s": 500.0,
        "rank": 2
      }
    ],
    "diversification": {
      "applied": true,
      "reason": "Traffic volume diversified across alternative corridors to prevent downstream congestion collapse.",
      "assignment_pool_pct": 70.0
    },
    "priority_context": {
      "trip_category": "emergency",
      "weight_applied": 10.0,
      "affected_ranking": true
    },
    "weight_schedule_version": "2026-08-26-v1"
  }
}
```

**Error Responses:**
- `400 Bad Request`: If routes list is empty or weight schedule is malformed.
- `422 Unprocessable Entity`: Missing required trip attributes or invalid data types.

---

### 4. Prometheus Metrics Exposition
`GET /metrics`

Returns Prometheus exposition text for scraping by Prometheus or parsing by the frontend dashboard.

**Success Response (200 OK):**
```text
# HELP catrs_route_requests_total Total number of route trip requests received.
# TYPE catrs_route_requests_total counter
catrs_route_requests_total{status="success"} 42

# HELP catrs_predictions_total Total number of speed prediction requests.
# TYPE catrs_predictions_total counter
catrs_predictions_total{status="success",model_used="st_gnn"} 38
catrs_predictions_total{status="success",model_used="heuristic"} 4

# HELP catrs_diversification_events_total Total number of times traffic diversification cap triggered.
# TYPE catrs_diversification_events_total counter
catrs_diversification_events_total 12
```

---

## Audit Service Endpoints

The Audit Service is completely isolated from the Routing Engine. It verifies that recorded routing outcomes comply with published policy schedules.

### 1. Health Check
`GET /health`

**Query Parameters:**
- `full` (optional, boolean, default: `false`): When `true`, tests database connectivity.

**Success Response (200 OK):**
```json
{
  "status": "ok"
}
```

---

### 2. Single Route Outcome Policy Verification
`POST /audit/outcome`

Verifies that a recorded route outcome applied the exact priority multiplier mandated by the weight schedule for its trip category and timestamp.

**Headers:**
- `Content-Type: application/json`

**Request Body Schema:**
```json
{
  "outcome": {
    "trip_category": "emergency",
    "weight_applied": 10.0,
    "weight_schedule_version": "2026-08-26-v1",
    "route_id": "route_north",
    "outcome_at": "2026-08-28T12:00:00Z"
  },
  "weight_schedule": {
    "version": "2026-08-26-v1",
    "effective_date": "2026-08-26",
    "weights": {
      "emergency": 10.0,
      "public_transit": 3.0,
      "commuter_general": 1.0
    }
  }
}
```

**Success Response (200 OK) - Compliant:**
```json
{
  "valid": true,
  "failures": [],
  "weight_schedule_version": "2026-08-26-v1"
}
```

**Success Response (200 OK) - Non-Compliant (Audit Failure):**
```json
{
  "valid": false,
  "failures": [
    "Weight applied (2.0) does not match scheduled weight (10.0) for category 'emergency'"
  ],
  "weight_schedule_version": "2026-08-26-v1"
}
```

---

### 3. Batch Outcome Audit
`POST /audit/batch`

Audits a collection of recorded route outcomes in parallel against one or more version-pinned weight schedules.

**Request Body Schema:**
```json
{
  "outcomes": [
    {
      "trip_category": "emergency",
      "weight_applied": 10.0,
      "weight_schedule_version": "2026-08-26-v1"
    },
    {
      "trip_category": "commuter_general",
      "weight_applied": 1.0,
      "weight_schedule_version": "2026-08-26-v1"
    }
  ],
  "schedules": {
    "2026-08-26-v1": {
      "version": "2026-08-26-v1",
      "effective_date": "2026-08-26",
      "weights": {
        "emergency": 10.0,
        "commuter_general": 1.0
      }
    }
  }
}
```

**Success Response (200 OK):**
```json
{
  "total": 2,
  "valid_count": 2,
  "invalid_count": 0,
  "unresolved_count": 0,
  "all_valid": true,
  "results": [
    {
      "outcome": {
        "trip_category": "emergency",
        "weight_applied": 10.0,
        "weight_schedule_version": "2026-08-26-v1"
      },
      "valid": true,
      "failures": [],
      "weight_schedule_version": "2026-08-26-v1"
    },
    {
      "outcome": {
        "trip_category": "commuter_general",
        "weight_applied": 1.0,
        "weight_schedule_version": "2026-08-26-v1"
      },
      "valid": true,
      "failures": [],
      "weight_schedule_version": "2026-08-26-v1"
    }
  ]
}
```

---

### 4. Batch Audit Summary
`POST /audit/summary`

Processes a batch audit identical to `/audit/batch`, but returns an ultra-compact summary suitable for high-volume automated verification streams without per-item detail allocations.

**Success Response (200 OK):**
```json
{
  "total": 5000,
  "valid_count": 5000,
  "invalid_count": 0,
  "unresolved_count": 0,
  "all_valid": true
}
```

---

### 5. Prometheus Metrics Exposition
`GET /metrics`

Returns Prometheus exposition text for audit performance tracking.

**Success Response (200 OK):**
```text
# HELP catrs_audits_total Total number of single outcome audits performed.
# TYPE catrs_audits_total counter
catrs_audits_total{status="valid"} 150
catrs_audits_total{status="invalid"} 2

# HELP catrs_batch_audits_total Total number of batch audit requests processed.
# TYPE catrs_batch_audits_total counter
catrs_batch_audits_total 14

# HELP catrs_policy_lookups_total Total number of policy version lookups.
# TYPE catrs_policy_lookups_total counter
catrs_policy_lookups_total{source="body"} 28
catrs_policy_lookups_total{source="database"} 0
```

---

## Standard Error Codes

| Status Code | Reason | Cause | Resolution |
| :--- | :--- | :--- | :--- |
| **`400 Bad Request`** | Input Semantics Invalid | Empty route list, non-numeric values, or malformed JSON syntax. | Check payload structure against OpenAPI/JSON schema contracts. |
| **`422 Unprocessable Entity`** | Validation Error | Field failed validation (e.g. `current_speed < 0`, `cap_fraction > 1.0`, `NaN` or `Inf` floating point values). | Ensure numbers are positive, bounded, and finite. |
| **`503 Service Unavailable`** | Dependency Failure | Database or required external resource unreachable in strict mode. | Verify container networking or switch `ROUTING_MODE=synthetic`. |
