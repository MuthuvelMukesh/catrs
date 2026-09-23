"""Contract validation tests for frontend-to-backend payloads and JSON schemas."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
from jsonschema import validate

ROOT_DIR = Path(__file__).parent.parent.parent.resolve()
CONTRACTS_DIR = ROOT_DIR / "contracts"


def load_schema(name: str) -> dict:
    path = CONTRACTS_DIR / f"{name}.schema.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_weight_schedule_schema_validates_valid_payload():
    schema = load_schema("weight-schedule")
    payload = {
        "version": "2026-08-26-v1",
        "effective_date": "2026-08-26",
        "weights": {
            "emergency": 10.0,
            "commuter_general": 1.0,
            "freight": 2.0,
            "transit": 3.0,
        },
    }
    validate(instance=payload, schema=schema)


def test_route_outcome_schema_validates_valid_payload():
    schema = load_schema("route-outcome")
    payload = {
        "trip_category": "emergency",
        "weight_applied": 10.0,
        "weight_schedule_version": "2026-08-26-v1",
        "route_id": "route_north",
        "outcome_at": "2026-08-28T12:00:00Z",
    }
    validate(instance=payload, schema=schema)


def test_explanation_payload_schema_validates_route_endpoint_output():
    import sys
    routing_path = str(ROOT_DIR / "services" / "routing-engine")
    if routing_path not in sys.path:
        sys.path.insert(0, routing_path)

    for mod in list(sys.modules.keys()):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from starlette.testclient import TestClient
    from app.main import app as routing_app

    client = TestClient(routing_app)
    req = {
        "trip_category": "emergency",
        "routes": [
            {"route_id": "r1", "travel_time_s": 400.0, "priority_score": 3.0},
            {"route_id": "r2", "travel_time_s": 500.0, "priority_score": 1.0},
        ],
        "request_count": 10,
        "cap_fraction": 0.7,
        "weight_schedule": {
            "version": "2026-08-26-v1",
            "effective_date": "2026-08-26",
            "weights": {"emergency": 10.0, "commuter_general": 1.0},
        },
    }
    res = client.post("/route", json=req)
    assert res.status_code == 200
    data = res.json()

    schema = load_schema("explanation-payload")
    validate(instance=data["explanation"], schema=schema)


def test_audit_result_schema_validates_audit_endpoint_output():
    import sys
    audit_path = str(ROOT_DIR / "services" / "audit-service")
    if audit_path not in sys.path:
        sys.path.insert(0, audit_path)

    # Clean app from sys.modules for audit service
    for mod in list(sys.modules.keys()):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from starlette.testclient import TestClient
    from app.main import app as audit_app

    client = TestClient(audit_app)
    req = {
        "outcome": {
            "trip_category": "emergency",
            "weight_applied": 10.0,
            "weight_schedule_version": "2026-08-26-v1",
        },
        "weight_schedule": {
            "version": "2026-08-26-v1",
            "effective_date": "2026-08-26",
            "weights": {"emergency": 10.0},
        },
    }
    res = client.post("/audit/outcome", json=req)
    assert res.status_code == 200
    data = res.json()

    schema = load_schema("audit-result")
    validate(instance=data, schema=schema)
