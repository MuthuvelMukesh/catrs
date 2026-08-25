from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_route_endpoint_returns_ranking_assignments_and_explanation():
    response = client.post(
        "/route",
        json={
            "trip_category": "emergency",
            "routes": [
                {"route_id": "r1", "travel_time_s": 400, "priority_score": 3},
                {"route_id": "r2", "travel_time_s": 500, "priority_score": 2},
            ],
            "request_count": 10,
            "current_counts": {"r1": 0, "r2": 0},
            "cap_fraction": 0.7,
            "weight_schedule": {
                "version": "2026-08-26-v1",
                "effective_date": "2026-08-26",
                "weights": {"emergency": 10.0},
            },
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["ranked_routes"][0]["route_id"] == "r1"
    assert body["assignments"]["r1"] == 7
    assert body["explanation"]["recommended_route"]["predicted_travel_time_s"] == 400.0


def test_route_endpoint_rejects_unknown_request_fields():
    response = client.post(
        "/route",
        json={
            "trip_category": "emergency",
            "routes": [{"route_id": "r1", "travel_time_s": 400}],
            "weight_schedule": {
                "version": "v1",
                "effective_date": "2026-08-26",
                "weights": {},
            },
            "unexpected": True,
        },
    )

    assert response.status_code == 422