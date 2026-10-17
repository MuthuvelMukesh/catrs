"""End-to-End Live Stack Verification Script.

Boots both microservices in-process, tests contracts, executes live graph routing,
multi-horizon speed prediction, and independent policy audits.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).parent.parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
AUDIT_DIR = str(ROOT_DIR / "services" / "audit-service")

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ── 1. Test Routing Engine ─────────────────────────────────────────────────
print("================================================================================")
print("             1. VERIFYING ROUTING ENGINE API & GRAPH CAPABILITIES               ")
print("================================================================================")
if ROUTING_DIR in sys.path:
    sys.path.remove(ROUTING_DIR)
sys.path.insert(0, ROUTING_DIR)
for m in list(sys.modules.keys()):
    if m == "app" or m.startswith("app."):
        del sys.modules[m]

from fastapi.testclient import TestClient
import app.main as r_main

routing_client = TestClient(r_main.app)

# Health & Readiness
r_health = routing_client.get("/health?full=true")
print(f"[PASSED] GET /health?full=true -> Status: {r_health.status_code}")
print(f"         Operational Status: {r_health.json()['status']}, Predictor: {r_health.json()['predictor']}, Mode: {r_health.json()['mode']}")
assert r_health.status_code == 200
assert r_health.json()["status"] in ("healthy", "degraded", "ok")

r_ready = routing_client.get("/ready")
print(f"[PASSED] GET /ready -> Status: {r_ready.status_code}, Body: {r_ready.json()}")
assert r_ready.status_code == 200

# Predict
r_predict = routing_client.post(
    "/predict",
    json={
        "segment_id": "seg_downtown_arterial_1",
        "current_speed": 34.5,
        "current_volume": 450,
        "historical_baseline_speed": 40.0,
        "weather_severity_score": 0.1,
        "active_incident_flag": False,
        "event_proximity_score": 0.0,
        "upstream_segment_congestion": 0.25,
        "time_of_day": 8,
        "day_of_week": 1,
    },
)
print(f"[PASSED] POST /predict -> Status: {r_predict.status_code}")
p_body = r_predict.json()
print(f"         5m: {p_body['predicted_speed_5m']} mph | 15m: {p_body['predicted_speed_15m']} mph | 30m: {p_body['predicted_speed_30m']} mph | Model: {p_body['model_used']}")
assert r_predict.status_code == 200
assert p_body["predicted_speed_5m"] > 0

# Classical Route
r_route = routing_client.post(
    "/route",
    json={
        "trip_category": "emergency",
        "routes": [
            {"route_id": "corridor_primary", "travel_time_s": 320.0, "priority_score": 2.5},
            {"route_id": "corridor_arterial", "travel_time_s": 360.0, "priority_score": 1.5},
            {"route_id": "corridor_express", "travel_time_s": 400.0, "priority_score": 1.0},
        ],
        "request_count": 5,
        "cap_fraction": 0.6,
        "weight_schedule": {
            "version": "promo-2026-v1",
            "effective_date": "2026-01-01",
            "weights": {"emergency": 5.0, "commuter_general": 1.0},
        },
    },
)
print(f"[PASSED] POST /route -> Status: {r_route.status_code}")
rt_body = r_route.json()
print(f"         Assignments: {rt_body['assignments']}")
print(f"         Top Recommended Route: {rt_body['ranked_routes'][0]['route_id']} (Weight: {rt_body['ranked_routes'][0]['weight_applied']})")
assert r_route.status_code == 200

# Graph Route Plan (OSM / Dijkstra / A* / Yen's KSP)
r_plan = routing_client.post(
    "/route/plan",
    json={
        "origin_node": "node_nw",
        "destination_node": "node_se",
        "trip_category": "emergency",
        "request_count": 4,
        "cap_fraction": 0.5,
        "k_alternatives": 3,
    },
)
print(f"[PASSED] POST /route/plan -> Status: {r_plan.status_code}")
plan_body = r_plan.json()
print(f"         Origin: {plan_body['origin']} -> Destination: {plan_body['destination']}")
print(f"         Candidate Alternatives: {len(plan_body['candidate_paths'])} physical paths discovered")
for idx, p in enumerate(plan_body['candidate_paths'], 1):
    print(f"           Path {idx}: {p['route_id']} | Dist: {p['distance_m']}m | Est. Travel Time: {p['travel_time_s']}s | Nodes: {' -> '.join(p['nodes'])}")
print(f"         Diversification Assignments: {plan_body['assignments']}")
assert r_plan.status_code == 200
assert len(plan_body["candidate_paths"]) >= 2

# Prometheus Metrics
r_metrics = routing_client.get("/metrics")
print(f"[PASSED] GET /metrics -> Status: {r_metrics.status_code}, Length: {len(r_metrics.text)} bytes")
assert r_metrics.status_code == 200

# ── 2. Test Policy Audit Service ───────────────────────────────────────────
print("\n================================================================================")
print("             2. VERIFYING INDEPENDENT POLICY AUDIT SERVICE                     ")
print("================================================================================")
if ROUTING_DIR in sys.path:
    sys.path.remove(ROUTING_DIR)
if AUDIT_DIR in sys.path:
    sys.path.remove(AUDIT_DIR)
sys.path.insert(0, AUDIT_DIR)
for m in list(sys.modules.keys()):
    if m == "app" or m.startswith("app."):
        del sys.modules[m]

import app.main as a_main

audit_client = TestClient(a_main.app)

# Health & Readiness
a_health = audit_client.get("/health?full=true")
print(f"[PASSED] GET /health?full=true -> Status: {a_health.status_code}")
print(f"         Status: {a_health.json()['status']}, Contract: {a_health.json()['contract_version']}")
assert a_health.status_code == 200

a_ready = audit_client.get("/ready")
print(f"[PASSED] GET /ready -> Status: {a_ready.status_code}, Body: {a_ready.json()}")
assert a_ready.status_code == 200

# Audit Single Outcome
a_single = audit_client.post(
    "/audit/outcome",
    json={
        "outcome": {
            "trip_category": "emergency",
            "weight_applied": 10.0,
            "weight_schedule_version": "2026-08-26-v1",
            "route_id": "corridor_primary",
            "outcome_at": "2026-09-01T12:00:00Z",
        },
        "weight_schedule": {
            "version": "2026-08-26-v1",
            "effective_date": "2026-08-26",
            "expiration_date": "2026-12-31",
            "weights": {"emergency": 10.0, "commuter_general": 1.0},
        },
    },
)
print(f"[PASSED] POST /audit/outcome -> Status: {a_single.status_code}")
print(f"         Result: Valid={a_single.json()['valid']}, Failures={a_single.json()['failures']}")
assert a_single.status_code == 200
assert a_single.json()["valid"] is True

# Audit Expired Policy
a_expired = audit_client.post(
    "/audit/outcome",
    json={
        "outcome": {
            "trip_category": "emergency",
            "weight_applied": 10.0,
            "weight_schedule_version": "2026-summer-v1",
            "route_id": "corridor_primary",
            "outcome_at": "2026-10-01T12:00:00Z",
        },
        "weight_schedule": {
            "version": "2026-summer-v1",
            "effective_date": "2026-06-01",
            "expiration_date": "2026-08-31",
            "weights": {"emergency": 10.0},
        },
    },
)
print(f"[PASSED] POST /audit/outcome (Expired Policy Detection) -> Status: {a_expired.status_code}")
print(f"         Result: Valid={a_expired.json()['valid']}, Failures={a_expired.json()['failures']}")
assert a_expired.status_code == 200
assert a_expired.json()["valid"] is False
assert any("expired" in f for f in a_expired.json()["failures"])

# Audit Batch Summary
a_batch = audit_client.post(
    "/audit/summary",
    json={
        "outcomes": [
            {"trip_category": "emergency", "weight_applied": 10.0, "weight_schedule_version": "v1"},
            {"trip_category": "commuter_general", "weight_applied": 1.0, "weight_schedule_version": "v1"},
            {"trip_category": "freight", "weight_applied": 1.0, "weight_schedule_version": "v1"},  # Mismatch: policy requires 2.0
        ],
        "schedules": {
            "v1": {
                "version": "v1",
                "effective_date": "2026-01-01",
                "weights": {"emergency": 10.0, "commuter_general": 1.0, "freight": 2.0},
            }
        },
    },
)
print(f"[PASSED] POST /audit/summary -> Status: {a_batch.status_code}")
print(f"         Batch Summary: {a_batch.json()}")
assert a_batch.status_code == 200
assert a_batch.json()["valid_count"] == 2
assert a_batch.json()["invalid_count"] == 1

print("\n================================================================================")
print("             ALL LIVE STACK VERIFICATIONS SUCCESSFULLY PASSED!                 ")
print("================================================================================")
