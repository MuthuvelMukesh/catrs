from __future__ import annotations


def fallback_urgency_score(*, current_speed: float, historical_baseline_speed: float) -> float:
    """Compute urgency directly from raw speed before model output is used downstream.

    This function intentionally avoids any import from the ML model code. It only
    exposes a raw urgency signal consumed by downstream routing logic.
    """
    if historical_baseline_speed <= 0:
        return 0.0
    return current_speed / historical_baseline_speed
