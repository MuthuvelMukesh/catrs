from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_audit_endpoint_verifies_pinned_policy_version():
    response = client.post(
        "/audit/outcome",
        json={
            "trip_category": "emergency",
            "weight_applied": 10.0,
            "weight_schedule_version": "2026-08-26-v1",
        },
        params={
            "version": "2026-08-26-v1",
        },
    )

    assert response.status_code == 422


def test_audit_endpoint_accepts_outcome_and_schedule_contracts():
    response = client.post(
        "/audit/outcome",
        json={
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
        },
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True