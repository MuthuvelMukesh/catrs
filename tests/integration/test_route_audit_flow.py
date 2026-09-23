from __future__ import annotations

import os
from pathlib import Path
import sys

import httpx
import pytest
from starlette.testclient import TestClient

ROOT_DIR = Path(__file__).parent.parent.parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
AUDIT_DIR = str(ROOT_DIR / "services" / "audit-service")

ROUTING_URL = os.environ.get("ROUTING_URL", "http://localhost:8001")
AUDIT_URL = os.environ.get("AUDIT_URL", "http://localhost:8002")
SCHEDULE = {
    "version": "integration-v1",
    "effective_date": "2026-08-26",
    "weights": {"emergency": 10.0, "commuter_general": 1.0},
}


def service_client() -> httpx.Client:
    return httpx.Client(timeout=5.0)


def test_in_process_end_to_end_route_audit_flow():
    """Verify complete in-process flow: prediction -> routing -> independent audit."""
    # 1. Routing Engine client
    while AUDIT_DIR in sys.path:
        sys.path.remove(AUDIT_DIR)
    while ROUTING_DIR in sys.path:
        sys.path.remove(ROUTING_DIR)
    sys.path.insert(0, ROUTING_DIR)
    for mod in list(sys.modules.keys()):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from app.main import app as routing_app
    routing_client = TestClient(routing_app)

    # 1a. Predict step
    pred_res = routing_client.post(
        "/predict",
        json={
            "segment_id": "seg_e2e_1",
            "current_speed": 48.0,
            "current_volume": 65,
            "historical_baseline_speed": 55.0,
            "weather_severity_score": 0.1,
            "active_incident_flag": False,
        },
    )
    assert pred_res.status_code == 200
    pred_data = pred_res.json()
    assert pred_data["predicted_speed_5m"] > 0

    # 1b. Route step using predicted speed
    route_res = routing_client.post(
        "/route",
        json={
            "trip_category": "emergency",
            "routes": [
                {
                    "route_id": "r_fast",
                    "travel_time_s": 320.0,
                    "priority_score": 3.0,
                    "distance_m": 4000.0,
                    "predicted_speed_5m": pred_data["predicted_speed_5m"],
                },
                {"route_id": "r_alt", "travel_time_s": 450.0, "priority_score": 1.0},
            ],
            "request_count": 10,
            "cap_fraction": 0.7,
            "weight_schedule": SCHEDULE,
        },
    )
    assert route_res.status_code == 200
    route_data = route_res.json()
    recommended = route_data["ranked_routes"][0]
    assert recommended["route_id"] == "r_fast"
    assert "explanation" in route_data

    # 2. Switch to Audit Service (strict microservice isolation)
    while ROUTING_DIR in sys.path:
        sys.path.remove(ROUTING_DIR)
    while AUDIT_DIR in sys.path:
        sys.path.remove(AUDIT_DIR)
    sys.path.insert(0, AUDIT_DIR)
    for mod in list(sys.modules.keys()):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from app.main import app as audit_app
    audit_client = TestClient(audit_app)

    # 2a. Audit valid outcome
    audit_res = audit_client.post(
        "/audit/outcome",
        json={
            "outcome": {
                "route_id": recommended["route_id"],
                "trip_category": "emergency",
                "weight_applied": recommended["weight_applied"],
                "weight_schedule_version": SCHEDULE["version"],
            },
            "weight_schedule": SCHEDULE,
        },
    )
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["valid"] is True
    assert audit_data["failures"] == []

    # 2b. Audit corrupted / tampered outcome (fraud detection)
    tampered_res = audit_client.post(
        "/audit/outcome",
        json={
            "outcome": {
                "route_id": recommended["route_id"],
                "trip_category": "emergency",
                "weight_applied": 1.0,  # should be 10.0
                "weight_schedule_version": SCHEDULE["version"],
            },
            "weight_schedule": SCHEDULE,
        },
    )
    assert tampered_res.status_code == 200
    assert tampered_res.json()["valid"] is False
    assert len(tampered_res.json()["failures"]) > 0


def test_route_outcome_is_accepted_by_independent_audit_service():
    """Live network test when services run in Docker or locally on ports 8001/8002."""
    route_request = {
        "trip_category": "emergency",
        "routes": [
            {"route_id": "r1", "travel_time_s": 400, "priority_score": 3},
            {"route_id": "r2", "travel_time_s": 500, "priority_score": 2},
        ],
        "request_count": 10,
        "cap_fraction": 0.7,
        "weight_schedule": SCHEDULE,
    }

    try:
        with service_client() as client:
            routing_response = client.post(f"{ROUTING_URL}/route", json=route_request)
            audit_response = None
            if routing_response.status_code == 200:
                recommended = routing_response.json()["ranked_routes"][0]
                audit_response = client.post(
                    f"{AUDIT_URL}/audit/outcome",
                    json={
                        "outcome": {
                            "route_id": recommended["route_id"],
                            "trip_category": route_request["trip_category"],
                            "weight_applied": recommended["weight_applied"],
                            "weight_schedule_version": SCHEDULE["version"],
                        },
                        "weight_schedule": SCHEDULE,
                    },
                )
    except httpx.RequestError:
        pytest.skip("Docker services are not running")

    assert routing_response.status_code == 200
    assert audit_response is not None
    assert audit_response.status_code == 200
    assert audit_response.json() == {
        "valid": True,
        "failures": [],
        "weight_schedule_version": SCHEDULE["version"],
    }