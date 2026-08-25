from __future__ import annotations

from typing import Any


def verify_route_outcome(
    *,
    outcome: dict[str, Any],
    weight_schedule: dict[str, Any],
) -> dict[str, Any]:
    """Verify an observed route outcome against an independently supplied policy row."""
    failures: list[str] = []
    expected_version = str(weight_schedule["version"])
    if outcome.get("weight_schedule_version") != expected_version:
        failures.append("weight schedule version does not match the published policy")

    trip_category = outcome.get("trip_category")
    expected_weight = weight_schedule["weights"].get(trip_category, 1.0)
    if outcome.get("weight_applied") != expected_weight:
        failures.append("applied priority weight does not match the published policy")

    return {
        "valid": not failures,
        "failures": failures,
        "weight_schedule_version": expected_version,
    }
