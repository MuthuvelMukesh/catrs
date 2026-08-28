"""Tests for audit-service metrics collection and /metrics endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.metrics import AuditMetrics, metrics


client = TestClient(app)


def test_audit_metrics_recording():
    m = AuditMetrics()
    m.record_audit("emergency", valid=True)
    m.record_audit("commuter_general", valid=False)
    m.record_batch_audit()
    m.record_policy_lookup(hit=True)
    m.record_policy_lookup(hit=False)

    text = m.generate_metrics_text()
    assert 'catrs_audits_total{trip_category="emergency",result="valid"} 1' in text
    assert 'catrs_audits_total{trip_category="commuter_general",result="invalid"} 1' in text
    assert "catrs_batch_audits_total 1" in text
    assert 'catrs_policy_lookups_total{status="hit"} 1' in text
    assert 'catrs_policy_lookups_total{status="miss"} 1' in text


def test_audit_metrics_endpoint_accessible():
    metrics.reset()
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "catrs_audits_total" in response.text
    assert "catrs_batch_audits_total" in response.text
    assert "catrs_policy_lookups_total" in response.text


def test_audit_and_batch_endpoints_update_metrics():
    metrics.reset()

    # Single audit
    client.post(
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

    # Batch audit
    client.post(
        "/audit/batch",
        json={
            "outcomes": [
                {
                    "trip_category": "commuter_general",
                    "weight_applied": 1.0,
                    "weight_schedule_version": "2026-08-26-v1",
                }
            ],
            "schedules": {
                "2026-08-26-v1": {
                    "version": "2026-08-26-v1",
                    "effective_date": "2026-08-26",
                    "weights": {"commuter_general": 1.0},
                }
            },
        },
    )

    response = client.get("/metrics")
    assert response.status_code == 200
    assert 'catrs_audits_total{trip_category="emergency",result="valid"} 1' in response.text
    assert 'catrs_audits_total{trip_category="commuter_general",result="valid"} 1' in response.text
    assert "catrs_batch_audits_total 1" in response.text
