"""Contract validation tests for the explanation payload.

Verifies that ``rank_routes`` emits an explanation dict that satisfies the
documented schema shape — all required keys are present and carry the right
types — and that travel-time values in the explanation are copied from the
same ranked route values used internally.
"""
from __future__ import annotations

import pytest

from app.routing.priority_routing import rank_routes


WEIGHT_SCHEDULE = {
    "version": "contract-v1",
    "effective_date": "2026-01-01",
    "weights": {"emergency": 5.0, "commuter_general": 1.0},
}

ROUTES = [
    {"route_id": "r1", "travel_time_s": 300.0, "priority_score": 2.0},
    {"route_id": "r2", "travel_time_s": 400.0, "priority_score": 1.5},
    {"route_id": "r3", "travel_time_s": 500.0, "priority_score": 1.0},
]


def _rank(trip_category: str = "emergency") -> dict:
    return rank_routes(
        trip_category=trip_category,
        routes=[dict(r) for r in ROUTES],
        weight_schedule=WEIGHT_SCHEDULE,
        include_explanation=True,
    )


# ---------------------------------------------------------------------------
# Top-level keys
# ---------------------------------------------------------------------------

def test_explanation_contains_top_level_keys():
    result = _rank()
    assert "ranked_routes" in result
    assert "explanation" in result


def test_explanation_contains_required_explanation_keys():
    explanation = _rank()["explanation"]
    required = {
        "route_id",
        "recommended_route",
        "alternatives_considered",
        "diversification",
        "priority_context",
        "weight_schedule_version",
    }
    assert required.issubset(explanation.keys())


# ---------------------------------------------------------------------------
# recommended_route sub-object
# ---------------------------------------------------------------------------

def test_recommended_route_contains_route_id_and_travel_time():
    rec = _rank()["explanation"]["recommended_route"]
    assert "route_id" in rec
    assert "predicted_travel_time_s" in rec


def test_recommended_route_travel_time_matches_ranked_routes():
    """Travel time in explanation must match what the ranking function used."""
    result = _rank()
    top_ranked = result["ranked_routes"][0]
    rec = result["explanation"]["recommended_route"]
    assert rec["predicted_travel_time_s"] == top_ranked["travel_time_s"]
    assert rec["route_id"] == top_ranked["route_id"]


# ---------------------------------------------------------------------------
# alternatives_considered
# ---------------------------------------------------------------------------

def test_alternatives_considered_includes_all_routes():
    alts = _rank()["explanation"]["alternatives_considered"]
    assert len(alts) == len(ROUTES)


def test_alternatives_considered_have_rank_field():
    alts = _rank()["explanation"]["alternatives_considered"]
    for alt in alts:
        assert "rank" in alt
        assert isinstance(alt["rank"], int)
        assert alt["rank"] >= 1


def test_alternatives_travel_time_matches_ranked_routes():
    """Each alternative's predicted_travel_time_s must match the ranked list."""
    result = _rank()
    ranked_by_id = {r["route_id"]: r["travel_time_s"] for r in result["ranked_routes"]}
    for alt in result["explanation"]["alternatives_considered"]:
        assert alt["predicted_travel_time_s"] == ranked_by_id[alt["route_id"]]


# ---------------------------------------------------------------------------
# diversification sub-object
# ---------------------------------------------------------------------------

def test_diversification_object_has_required_keys():
    div = _rank()["explanation"]["diversification"]
    assert "applied" in div
    assert "reason" in div
    assert "assignment_pool_pct" in div


def test_diversification_applied_is_bool():
    div = _rank()["explanation"]["diversification"]
    assert isinstance(div["applied"], bool)


# ---------------------------------------------------------------------------
# priority_context sub-object
# ---------------------------------------------------------------------------

def test_priority_context_has_required_keys():
    ctx = _rank()["explanation"]["priority_context"]
    assert "trip_category" in ctx
    assert "weight_applied" in ctx
    assert "affected_ranking" in ctx


def test_priority_context_trip_category_matches_input():
    assert _rank("emergency")["explanation"]["priority_context"]["trip_category"] == "emergency"


def test_priority_context_weight_applied_is_float():
    weight = _rank()["explanation"]["priority_context"]["weight_applied"]
    assert isinstance(weight, float)


# ---------------------------------------------------------------------------
# weight_schedule_version
# ---------------------------------------------------------------------------

def test_weight_schedule_version_matches_input():
    result = _rank()
    assert result["explanation"]["weight_schedule_version"] == WEIGHT_SCHEDULE["version"]
