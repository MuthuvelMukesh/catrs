"""Contract tests for the audit-service weight schedule verification logic.

Validates the ``verify_route_outcome`` function behaviour against a range of
valid, mismatched, and edge-case weight schedule / outcome combinations.
"""
from __future__ import annotations

import pytest

from app.policy_verifier import verify_route_outcome


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCHEDULE_V1 = {
    "version": "v1",
    "effective_date": "2026-01-01",
    "weights": {
        "emergency": 5.0,
        "commuter_general": 1.0,
        "freight": 2.0,
    },
}


def _outcome(
    trip_category: str = "emergency",
    weight_applied: float = 5.0,
    version: str = "v1",
    route_id: str = "r1",
) -> dict:
    return {
        "trip_category": trip_category,
        "weight_applied": weight_applied,
        "weight_schedule_version": version,
        "route_id": route_id,
    }


# ---------------------------------------------------------------------------
# Happy-path: valid outcomes
# ---------------------------------------------------------------------------

def test_valid_outcome_returns_valid_true():
    result = verify_route_outcome(outcome=_outcome(), weight_schedule=SCHEDULE_V1)
    assert result["valid"] is True
    assert result["failures"] == []


def test_valid_outcome_reflects_correct_version():
    result = verify_route_outcome(outcome=_outcome(), weight_schedule=SCHEDULE_V1)
    assert result["weight_schedule_version"] == "v1"


def test_valid_outcome_for_each_trip_category():
    for cat, weight in SCHEDULE_V1["weights"].items():
        result = verify_route_outcome(
            outcome=_outcome(trip_category=cat, weight_applied=weight),
            weight_schedule=SCHEDULE_V1,
        )
        assert result["valid"] is True, f"Expected valid for category {cat!r}"


# ---------------------------------------------------------------------------
# Version mismatch
# ---------------------------------------------------------------------------

def test_version_mismatch_fails():
    outcome = _outcome(version="wrong-version")
    result = verify_route_outcome(outcome=outcome, weight_schedule=SCHEDULE_V1)
    assert result["valid"] is False
    assert any("version" in f for f in result["failures"])


# ---------------------------------------------------------------------------
# Weight mismatch
# ---------------------------------------------------------------------------

def test_weight_mismatch_fails():
    outcome = _outcome(weight_applied=99.0)  # correct version, wrong weight
    result = verify_route_outcome(outcome=outcome, weight_schedule=SCHEDULE_V1)
    assert result["valid"] is False
    assert any("weight" in f for f in result["failures"])


def test_both_version_and_weight_wrong_produces_two_failures():
    outcome = _outcome(version="bad-version", weight_applied=0.0)
    result = verify_route_outcome(outcome=outcome, weight_schedule=SCHEDULE_V1)
    assert result["valid"] is False
    assert len(result["failures"]) == 2


# ---------------------------------------------------------------------------
# Unknown trip category falls back to default weight 1.0
# ---------------------------------------------------------------------------

def test_unknown_trip_category_defaults_to_weight_one():
    outcome = _outcome(trip_category="unknown_cat", weight_applied=1.0)
    result = verify_route_outcome(outcome=outcome, weight_schedule=SCHEDULE_V1)
    assert result["valid"] is True


def test_unknown_trip_category_with_wrong_weight_fails():
    outcome = _outcome(trip_category="unknown_cat", weight_applied=5.0)
    result = verify_route_outcome(outcome=outcome, weight_schedule=SCHEDULE_V1)
    assert result["valid"] is False


# ---------------------------------------------------------------------------
# Result schema shape
# ---------------------------------------------------------------------------

def test_result_always_contains_required_keys():
    for outcome_fn, schedule in [
        (_outcome(), SCHEDULE_V1),
        (_outcome(version="bad"), SCHEDULE_V1),
    ]:
        result = verify_route_outcome(outcome=outcome_fn, weight_schedule=schedule)
        assert "valid" in result
        assert "failures" in result
        assert "weight_schedule_version" in result


def test_failures_is_always_a_list():
    result = verify_route_outcome(outcome=_outcome(), weight_schedule=SCHEDULE_V1)
    assert isinstance(result["failures"], list)
