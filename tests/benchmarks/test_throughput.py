"""Performance benchmarks and latency stress tests for CATRS."""
from __future__ import annotations

import os
import subprocess
import sys
import time

# Ensure routing engine is in sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROUTING_APP = os.path.join(ROOT_DIR, "services", "routing-engine")
AUDIT_APP = os.path.join(ROOT_DIR, "services", "audit-service")

if ROUTING_APP not in sys.path:
    sys.path.insert(0, ROUTING_APP)

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def routing_client():
    from app.main import app
    return TestClient(app)


def test_predict_latency_benchmark(routing_client):
    """Verify that single prediction requests respond within 50ms."""
    payload = {
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
    }

    # Warm-up
    routing_client.post("/predict", json=payload)

    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        res = routing_client.post("/predict", json=payload)
        assert res.status_code == 200
    duration = time.perf_counter() - start

    avg_ms = (duration / iterations) * 1000
    print(f"\n[Benchmark] Average /predict latency: {avg_ms:.2f} ms ({iterations} iterations)")
    assert avg_ms < 50.0, f"Average /predict latency {avg_ms:.2f}ms exceeds 50ms threshold"


def test_route_ranking_latency_benchmark(routing_client):
    """Verify that multi-candidate route ranking completes in under 50ms."""
    payload = {
        "trip_category": "emergency",
        "routes": [
            {"route_id": "r1", "travel_time_s": 400.0, "priority_score": 3.0, "distance_m": 4000.0, "predicted_speed_5m": 36.0},
            {"route_id": "r2", "travel_time_s": 450.0, "priority_score": 2.5, "distance_m": 4200.0, "predicted_speed_5m": 35.0},
            {"route_id": "r3", "travel_time_s": 500.0, "priority_score": 1.0, "distance_m": 4500.0, "predicted_speed_5m": 30.0},
            {"route_id": "r4", "travel_time_s": 550.0, "priority_score": 1.0},
        ],
        "request_count": 50,
        "cap_fraction": 0.6,
        "weight_schedule": {
            "version": "2026-08-26-v1",
            "effective_date": "2026-08-26",
            "weights": {"emergency": 10.0, "commuter_general": 1.0},
        },
    }

    # Warm-up
    routing_client.post("/route", json=payload)

    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        res = routing_client.post("/route", json=payload)
        assert res.status_code == 200
    duration = time.perf_counter() - start

    avg_ms = (duration / iterations) * 1000
    print(f"\n[Benchmark] Average /route ranking latency: {avg_ms:.2f} ms ({iterations} iterations)")
    assert avg_ms < 50.0, f"Average /route latency {avg_ms:.2f}ms exceeds 50ms threshold"


def test_batch_audit_throughput_benchmark():
    """Verify that batch policy verification processes 1,000 items in <200ms."""
    code = """
import time
from app.batch_auditor import BatchAuditor

schedule = {
    "version": "v1",
    "effective_date": "2026-08-26",
    "weights": {"emergency": 10.0, "commuter": 1.0},
}
schedules = {"v1": schedule}
outcomes = [
    {
        "trip_category": "emergency",
        "weight_applied": 10.0,
        "weight_schedule_version": "v1",
    }
    for _ in range(1000)
]
auditor = BatchAuditor()
start = time.perf_counter()
res = auditor.audit_batch(outcomes, default_schedules=schedules)
duration = time.perf_counter() - start
ms = duration * 1000
print(f"BATCH_TIME:{ms:.2f}")
assert res.total == 1000
assert res.all_valid is True
assert ms < 200.0
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=AUDIT_APP,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Audit benchmark failed:\n{result.stderr}"
    for line in result.stdout.splitlines():
        if line.startswith("BATCH_TIME:"):
            ms = float(line.split(":")[1])
            print(f"\n[Benchmark] Batch audit for 1,000 outcomes: {ms:.2f} ms")
            assert ms < 200.0

