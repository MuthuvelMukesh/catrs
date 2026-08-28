# API Reference

Complete endpoint specification for CATRS microservices.

---

## Routing Engine (Port 8001 / 8000)

### 1. Health Check
`GET /health`

**Parameters:**
- `full` (optional, boolean): If `true`, returns detailed connection statuses.

**Response (200 OK):**
```json
{
  "status": "ok"
}
```
*With `full=true`:*
```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "predictor": "fallback"
}
```

---

### 2. Multi-Horizon Speed Prediction
`POST /predict`

Calculates 5-minute, 15-minute, and 30-minute predicted speeds for a segment using ST-GNN (if loaded) or the deterministic heuristic fallback.

**Request Body:**
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

**Response (200 OK):**
```json
{
  "segment_id": "seg_01",
  "predicted_speed_5m": 50.3,
  "predicted_speed_15m": 46.276,
  "predicted_speed_30m": 42.755
}
```

---

### 3. Route Trip & Rank Alternatives
`POST /route`

Ranks alternative candidate routes by applying the active weight schedule to trip categories, derives travel times, enforces diversification caps, and returns an explanation payload.

**Request Body:**
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
      "priority_score": 1.0
    }
  ],
  "request_count": 10,
  "current_counts": {"route_north": 0, "route_south": 0},
  "cap_fraction": 0.7,
  "weight_schedule": {
    "version": "2026-08-26-v1",
    "effective_date": "2026-08-26",
    "weights": { "emergency": 10.0, "commuter_general": 1.0 }
  }
}
```

**Response (200 OK):**
```json
{
  "ranked_routes": [
    {
      "route_id": "route_north",
      "travel_time_s": 400.0,
      "priority_score": 2.0,
      "weight_applied": 10.0,
      "adjusted_score": 0.05
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
      { "route_id": "route_north", "predicted_travel_time_s": 400.0, "rank": 1 },
      { "route_id": "route_south", "predicted_travel_time_s": 500.0, "rank": 2 }
    ],
    "diversification": {
      "applied": false,
      "reason": "No diversification cap was requested for this ranking.",
      "assignment_pool_pct": 100.0
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

---

### 4. Prometheus Metrics
`GET /metrics`

Returns Prometheus exposition formatted text containing `catrs_route_requests_total`, `catrs_predictions_total`, and `catrs_diversification_events_total`.

---

## Audit Service (Port 8002 / 8000)

### 1. Health Check
`GET /health`

**Parameters:**
- `full` (optional, boolean): If `true`, returns database connectivity status.

**Response (200 OK):**
```json
{ "status": "ok" }
```

---

### 2. Single Outcome Audit
`POST /audit/outcome`

Verifies a single recorded route decision against an independently supplied policy schedule.

**Request Body:**
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
    "weights": { "emergency": 10.0 }
  }
}
```

**Response (200 OK):**
```json
{
  "valid": true,
  "failures": [],
  "weight_schedule_version": "2026-08-26-v1"
}
```

---

### 3. Batch Outcome Audit
`POST /audit/batch`

Audits a batch of route decisions, looking up weight schedules from the request body or database.

**Request Body:**
```json
{
  "outcomes": [
    {
      "trip_category": "emergency",
      "weight_applied": 10.0,
      "weight_schedule_version": "2026-08-26-v1"
    }
  ],
  "schedules": {
    "2026-08-26-v1": {
      "version": "2026-08-26-v1",
      "effective_date": "2026-08-26",
      "weights": { "emergency": 10.0 }
    }
  }
}
```

**Response (200 OK):**
```json
{
  "total": 1,
  "valid_count": 1,
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
    }
  ]
}
```

---

### 4. Batch Audit Summary
`POST /audit/summary`

Returns compact batch aggregate statistics without per-item detail arrays.

**Response (200 OK):**
```json
{
  "total": 1,
  "valid_count": 1,
  "invalid_count": 0,
  "unresolved_count": 0,
  "all_valid": true
}
```

---

### 5. Prometheus Metrics
`GET /metrics`

Returns Prometheus exposition formatted text containing `catrs_audits_total`, `catrs_batch_audits_total`, and `catrs_policy_lookups_total`.
