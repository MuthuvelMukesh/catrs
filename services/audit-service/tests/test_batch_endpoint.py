"""Endpoint tests for /audit/batch, /audit/summary, and health checks."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)

SCHEDULE_V1 = {
    "version": "2026-08-26-v1",
    "effective_date": "2026-08-26",
    "weights": {
        "emergency": 10.0,
        "commuter_general": 1.0,
    },
}


def test_batch_endpoint_accepts_valid_batch():
    response = client.post(
        "/audit/batch",
        json={
            "outcomes": [
                {
                    "trip_category": "emergency",
                    "weight_applied": 10.0,
                    "weight_schedule_version": "2026-08-26-v1",
                },
                {
                    "trip_category": "commuter_general",
                    "weight_applied": 1.0,
                    "weight_schedule_version": "2026-08-26-v1",
                },
            ],
            "schedules": {
                "2026-08-26-v1": SCHEDULE_V1,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["valid_count"] == 2
    assert body["invalid_count"] == 0
    assert body["all_valid"] is True
    assert len(body["results"]) == 2


def test_batch_endpoint_rejects_empty_outcomes():
    response = client.post(
        "/audit/batch",
        json={
            "outcomes": [],
            "schedules": {"2026-08-26-v1": SCHEDULE_V1},
        },
    )
    assert response.status_code == 422


def test_batch_endpoint_rejects_extra_fields():
    response = client.post(
        "/audit/batch",
        json={
            "outcomes": [
                {
                    "trip_category": "emergency",
                    "weight_applied": 10.0,
                    "weight_schedule_version": "2026-08-26-v1",
                    "extra_unexpected_field": "bad",
                }
            ],
            "schedules": {"2026-08-26-v1": SCHEDULE_V1},
        },
    )
    assert response.status_code == 422


def test_summary_endpoint_returns_compact_metrics():
    response = client.post(
        "/audit/summary",
        json={
            "outcomes": [
                {
                    "trip_category": "emergency",
                    "weight_applied": 10.0,
                    "weight_schedule_version": "2026-08-26-v1",
                }
            ],
            "schedules": {
                "2026-08-26-v1": SCHEDULE_V1,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["valid_count"] == 1
    assert body["all_valid"] is True
    assert "results" not in body


def test_health_endpoint_reports_status_and_db():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    response_full = client.get("/health?full=true")
    assert response_full.status_code == 200
    body = response_full.json()
    assert body["status"] == "ok"
    assert "database" in body
