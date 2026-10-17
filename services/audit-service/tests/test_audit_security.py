from datetime import date, datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.policy_verifier import verify_route_outcome


def test_audit_service_api_key_enforcement(monkeypatch):
    monkeypatch.setenv("AUDIT_API_KEY", "audit-guard-key-42")
    client = TestClient(app)

    # Missing key -> 401
    res = client.post(
        "/audit/outcome",
        json={
            "outcome": {
                "trip_category": "commuter",
                "weight_applied": 1.0,
                "weight_schedule_version": "v1",
            },
            "weight_schedule": {
                "version": "v1",
                "effective_date": "2026-01-01",
                "weights": {"commuter": 1.0},
            },
        },
    )
    assert res.status_code == 401

    # Valid key -> 200
    res = client.post(
        "/audit/outcome",
        headers={"X-API-Key": "audit-guard-key-42"},
        json={
            "outcome": {
                "trip_category": "commuter",
                "weight_applied": 1.0,
                "weight_schedule_version": "v1",
            },
            "weight_schedule": {
                "version": "v1",
                "effective_date": "2026-01-01",
                "weights": {"commuter": 1.0},
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_audit_policy_expiration_verification():
    schedule_with_expiry = {
        "version": "promo-v1",
        "effective_date": "2026-01-01",
        "expiration_date": "2026-06-30",
        "weights": {"commuter": 1.5},
    }

    # Outcome within valid window
    valid_outcome = {
        "trip_category": "commuter",
        "weight_applied": 1.5,
        "weight_schedule_version": "promo-v1",
        "outcome_at": "2026-03-15T12:00:00Z",
    }
    result = verify_route_outcome(outcome=valid_outcome, weight_schedule=schedule_with_expiry)
    assert result["valid"] is True
    assert result["failures"] == []

    # Outcome after expiration
    expired_outcome = {
        "trip_category": "commuter",
        "weight_applied": 1.5,
        "weight_schedule_version": "promo-v1",
        "outcome_at": "2026-07-01T12:00:00Z",
    }
    expired_result = verify_route_outcome(outcome=expired_outcome, weight_schedule=schedule_with_expiry)
    assert expired_result["valid"] is False
    assert any("has expired" in f for f in expired_result["failures"])


def test_audit_readiness_and_health_endpoints():
    client = TestClient(app)

    live_res = client.get("/health")
    assert live_res.status_code == 200
    assert live_res.json() == {"status": "ok"}

    full_res = client.get("/health?full=true")
    assert full_res.status_code == 200
    data = full_res.json()
    assert data["status"] == "ok"
    assert "operational_status" in data
    assert "contract_version" in data

    ready_res = client.get("/ready")
    assert ready_res.status_code == 200
    assert ready_res.json() == {"status": "ready"}
