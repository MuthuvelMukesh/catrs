from __future__ import annotations

from datetime import date, datetime
from typing import Any


def verify_route_outcome(
    *,
    outcome: dict[str, Any],
    weight_schedule: dict[str, Any],
) -> dict[str, Any]:
    """Verify an observed route outcome against an independently supplied policy row."""
    failures: list[str] = []
    expected_version = str(weight_schedule.get("version", ""))

    # 1. Version check
    outcome_version = outcome.get("weight_schedule_version")
    if outcome_version != expected_version:
        failures.append("weight schedule version does not match the published policy")

    # 2. Trip category check
    trip_category = outcome.get("trip_category")
    if not trip_category:
        failures.append("trip_category is missing or empty")

    # 3. Applied weight check (unknown category defaults to weight 1.0)
    weight_applied = outcome.get("weight_applied")
    if weight_applied is None:
        failures.append("weight_applied is missing")
    else:
        weights = weight_schedule.get("weights", {})
        expected_weight = float(weights.get(trip_category, 1.0))
        if float(weight_applied) != expected_weight:
            failures.append("applied priority weight does not match the published policy")

    # 4. Effective date check (if outcome timestamp is present)
    outcome_at = outcome.get("outcome_at")
    effective_date_str = weight_schedule.get("effective_date")
    if outcome_at and effective_date_str:
        try:
            if isinstance(outcome_at, datetime):
                outcome_dt = outcome_at.date()
            else:
                outcome_dt = datetime.fromisoformat(str(outcome_at).replace("Z", "+00:00")).date()
            eff_dt = date.fromisoformat(str(effective_date_str))
            if outcome_dt < eff_dt:
                failures.append(
                    f"policy schedule {expected_version!r} was not yet effective "
                    f"at outcome date {outcome_dt.isoformat()} (effective from {eff_dt.isoformat()})"
                )
        except (ValueError, TypeError):
            pass

    return {
        "valid": len(failures) == 0,
        "failures": failures,
        "weight_schedule_version": expected_version,
    }
