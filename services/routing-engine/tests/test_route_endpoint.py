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


def test_route_endpoint_derives_travel_time_from_predicted_speed():
    response = client.post(
        "/route",
        json={
            "trip_category": "commuter_general",
            "routes": [
                {
                    "route_id": "r1",
                    "travel_time_s": 999,
                    "distance_m": 1000,
                    "predicted_speed_5m": 36,
                },
                {"route_id": "r2", "travel_time_s": 120},
            ],
            "weight_schedule": {
                "version": "2026-08-26-v1",
                "effective_date": "2026-08-26",
                "weights": {"commuter_general": 1.0},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["ranked_routes"][0]["route_id"] == "r1"
    assert response.json()["ranked_routes"][0]["travel_time_s"] == 100.0


def test_route_endpoint_returns_422_when_no_weight_schedule_provided():
    """Without a weight_schedule or version, the endpoint should return 422."""
    response = client.post(
        "/route",
        json={
            "trip_category": "commuter_general",
            "routes": [{"route_id": "r1", "travel_time_s": 300}],
        },
    )
    assert response.status_code == 422


def test_predict_endpoint_returns_three_horizons():
    response = client.post(
        "/predict",
        json={
            "segment_id": "seg_01",
            "current_speed": 45.0,
            "current_volume": 80,
            "historical_baseline_speed": 55.0,
            "weather_severity_score": 0.2,
            "active_incident_flag": False,
            "event_proximity_score": 0.0,
            "upstream_segment_congestion": 0.1,
            "time_of_day": 8,
            "day_of_week": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["segment_id"] == "seg_01"
    assert "predicted_speed_5m" in body
    assert "predicted_speed_15m" in body
    assert "predicted_speed_30m" in body
    assert body["predicted_speed_5m"] > 0


def test_predict_endpoint_rejects_invalid_speed():
    response = client.post(
        "/predict",
        json={
            "segment_id": "seg_01",
            "current_speed": -5.0,   # invalid
            "current_volume": 80,
            "historical_baseline_speed": 55.0,
        },
    )
    assert response.status_code == 422