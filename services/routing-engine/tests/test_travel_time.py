"""Tests for app.routing.travel_time."""
from __future__ import annotations

import pytest

from app.routing.travel_time import (
    derive_travel_time,
    enrich_routes_with_travel_time,
    speed_to_travel_time,
)


# ---------------------------------------------------------------------------
# speed_to_travel_time
# ---------------------------------------------------------------------------

def test_speed_to_travel_time_basic():
    """1 km at 36 km/h = 100 s."""
    assert speed_to_travel_time(distance_m=1000.0, speed_kmh=36.0) == pytest.approx(100.0)


def test_speed_to_travel_time_zero_speed_returns_sentinel():
    assert speed_to_travel_time(distance_m=500.0, speed_kmh=0.0) == 86_400.0


def test_speed_to_travel_time_negative_speed_returns_sentinel():
    assert speed_to_travel_time(distance_m=500.0, speed_kmh=-10.0) == 86_400.0


def test_speed_to_travel_time_zero_distance_returns_sentinel():
    assert speed_to_travel_time(distance_m=0.0, speed_kmh=50.0) == 86_400.0


def test_speed_to_travel_time_large_distance():
    """10 km at 90 km/h → 400 s."""
    assert speed_to_travel_time(distance_m=10_000.0, speed_kmh=90.0) == pytest.approx(400.0)


# ---------------------------------------------------------------------------
# derive_travel_time
# ---------------------------------------------------------------------------

def test_derive_travel_time_uses_speed_when_both_present():
    route = {
        "route_id": "r1",
        "travel_time_s": 999.0,  # should be overridden
        "distance_m": 1000.0,
        "predicted_speed_5m": 36.0,
    }
    assert derive_travel_time(route) == pytest.approx(100.0)


def test_derive_travel_time_falls_back_to_raw_when_distance_missing():
    route = {
        "route_id": "r1",
        "travel_time_s": 300.0,
        "predicted_speed_5m": 60.0,
    }
    assert derive_travel_time(route) == pytest.approx(300.0)


def test_derive_travel_time_falls_back_when_speed_missing():
    route = {
        "route_id": "r1",
        "travel_time_s": 300.0,
        "distance_m": 2000.0,
    }
    assert derive_travel_time(route) == pytest.approx(300.0)


def test_derive_travel_time_falls_back_when_both_absent():
    route = {"route_id": "r1", "travel_time_s": 250.0}
    assert derive_travel_time(route) == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# enrich_routes_with_travel_time
# ---------------------------------------------------------------------------

def test_enrich_routes_updates_travel_time_in_place():
    routes = [
        {"route_id": "r1", "travel_time_s": 999.0, "distance_m": 1000.0, "predicted_speed_5m": 36.0},
        {"route_id": "r2", "travel_time_s": 500.0},
    ]
    result = enrich_routes_with_travel_time(routes)
    assert result is routes  # same list returned
    assert routes[0]["travel_time_s"] == pytest.approx(100.0)
    assert routes[1]["travel_time_s"] == pytest.approx(500.0)


def test_enrich_routes_returns_same_list():
    routes = [{"route_id": "r1", "travel_time_s": 60.0}]
    assert enrich_routes_with_travel_time(routes) is routes


def test_enrich_routes_empty_list():
    assert enrich_routes_with_travel_time([]) == []
