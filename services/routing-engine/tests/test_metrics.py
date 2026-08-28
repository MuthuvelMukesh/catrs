"""Tests for routing-engine metrics collection and /metrics endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.metrics import RoutingMetrics, metrics


client = TestClient(app)


def test_routing_metrics_recording():
    m = RoutingMetrics()
    m.record_route_request("emergency", status="success")
    m.record_route_request("commuter_general", status="success")
    m.record_prediction(model_used="heuristic", status="success")
    m.record_diversification_event()

    text = m.generate_metrics_text()
    assert 'catrs_route_requests_total{trip_category="emergency",status="success"} 1' in text
    assert 'catrs_route_requests_total{trip_category="commuter_general",status="success"} 1' in text
    assert 'catrs_predictions_total{model_used="heuristic",status="success"} 1' in text
    assert "catrs_diversification_events_total 1" in text


def test_routing_metrics_endpoint_accessible():
    metrics.reset()
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "catrs_route_requests_total" in response.text
    assert "catrs_predictions_total" in response.text
    assert "catrs_diversification_events_total" in response.text


def test_route_and_predict_update_metrics():
    metrics.reset()

    # Route request
    client.post(
        "/route",
        json={
            "trip_category": "emergency",
            "routes": [{"route_id": "r1", "travel_time_s": 400}],
            "weight_schedule": {
                "version": "2026-08-26-v1",
                "effective_date": "2026-08-26",
                "weights": {"emergency": 10.0},
            },
        },
    )

    # Predict request
    client.post(
        "/predict",
        json={
            "segment_id": "s1",
            "current_speed": 50.0,
            "current_volume": 100,
            "historical_baseline_speed": 55.0,
        },
    )

    response = client.get("/metrics")
    assert response.status_code == 200
    assert 'catrs_route_requests_total{trip_category="emergency",status="success"} 1' in response.text
    assert 'catrs_predictions_total{model_used="heuristic",status="success"} 1' in response.text
