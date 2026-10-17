from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


def test_routing_engine_api_key_enforcement(monkeypatch):
    monkeypatch.setenv("ROUTING_API_KEY", "secret-route-token-xyz")
    client = TestClient(app)

    # Missing API key -> 401
    res = client.post(
        "/predict",
        json={
            "segment_id": "seg-1",
            "current_speed": 45.0,
            "current_volume": 120,
            "historical_baseline_speed": 50.0,
        },
    )
    assert res.status_code == 401
    assert "Invalid or missing API key" in res.json()["detail"]

    # Invalid API key -> 401
    res = client.post(
        "/predict",
        headers={"X-API-Key": "wrong-token"},
        json={
            "segment_id": "seg-1",
            "current_speed": 45.0,
            "current_volume": 120,
            "historical_baseline_speed": 50.0,
        },
    )
    assert res.status_code == 401

    # Valid API key -> 200
    res = client.post(
        "/predict",
        headers={"X-API-Key": "secret-route-token-xyz"},
        json={
            "segment_id": "seg-1",
            "current_speed": 45.0,
            "current_volume": 120,
            "historical_baseline_speed": 50.0,
        },
    )
    assert res.status_code == 200
    assert "predicted_speed_5m" in res.json()


def test_admin_api_key_enforcement_on_dataset_select(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "secret-admin-pass-999")
    client = TestClient(app)

    # Missing admin key -> 403
    res = client.post(
        "/dataset/select",
        json={"dataset": "metr_la"},
    )
    assert res.status_code == 403
    assert "Invalid or missing Admin API key" in res.json()["detail"]

    # Valid admin key -> 200
    res = client.post(
        "/dataset/select",
        headers={"X-Admin-API-Key": "secret-admin-pass-999"},
        json={"dataset": "synthetic"},
    )
    assert res.status_code == 200
    assert res.json()["selected_dataset"] == "synthetic"


def test_readiness_and_health_endpoints():
    client = TestClient(app)

    # Liveness check
    live_res = client.get("/health")
    assert live_res.status_code == 200
    assert live_res.json() == {"status": "ok"}

    # Full health check contains explicit operational metadata and data freshness
    full_res = client.get("/health?full=true")
    assert full_res.status_code == 200
    data = full_res.json()
    assert data["status"] in ("healthy", "degraded", "unavailable")
    assert "data_freshness" in data
    assert "is_synthetic" in data
    assert "predictor_health" in data

    # Readiness check
    ready_res = client.get("/ready")
    assert ready_res.status_code == 200
    assert ready_res.json() == {"status": "ready"}


def test_plan_route_endpoint_graph_navigation():
    client = TestClient(app)

    # Plan valid trip across urban network from node_nw to node_se
    res = client.post(
        "/route/plan",
        json={
            "origin_node": "node_nw",
            "destination_node": "node_se",
            "trip_category": "emergency",
            "request_count": 2,
            "k_alternatives": 3,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["origin"] == "node_nw"
    assert payload["destination"] == "node_se"
    assert len(payload["ranked_routes"]) >= 1
    assert len(payload["assignments"]) >= 1
    assert "explanation" in payload
    assert payload["trip_category"] == "emergency"
    assert payload["explanation"]["priority_context"]["trip_category"] == "emergency"

    # Plan unreachable route -> 404
    err_res = client.post(
        "/route/plan",
        json={
            "origin_node": "node_nw",
            "destination_node": "NON_EXISTENT_NODE",
        },
    )
    assert err_res.status_code == 404
    assert "No viable route found" in err_res.json()["detail"]
