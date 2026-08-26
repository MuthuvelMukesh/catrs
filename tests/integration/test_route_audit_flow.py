from __future__ import annotations

import os

import httpx
import pytest


ROUTING_URL = os.environ.get("ROUTING_URL", "http://localhost:8001")
AUDIT_URL = os.environ.get("AUDIT_URL", "http://localhost:8002")
SCHEDULE = {
    "version": "integration-v1",
    "effective_date": "2026-08-26",
    "weights": {"emergency": 10.0},
}


def service_client() -> httpx.Client:
    return httpx.Client(timeout=5.0)


def test_route_outcome_is_accepted_by_independent_audit_service():
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