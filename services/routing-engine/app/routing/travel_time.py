"""Travel-time estimation utilities.

This module provides functions to convert between speed-based predictions and
travel-time seconds, and to derive the best available speed estimate for a
route option given prediction service output.
"""
from __future__ import annotations

import math
from typing import Any

SENTINEL_TRAVEL_TIME_S = 86_400.0  # 24 hours fallback sentinel for impassable or invalid routes
MAX_REALISTIC_SPEED_KMH = 300.0     # Realistic highway speed upper bound


def speed_to_travel_time(
    *,
    distance_m: float,
    speed_kmh: float,
) -> float:
    """Convert a speed (km/h) and distance (m) to travel-time in seconds.

    Parameters
    ----------
    distance_m:
        Route segment length in metres.
    speed_kmh:
        Speed in kilometres per hour.

    Returns
    -------
    float
        Travel time in seconds: distance_m / (speed_kmh * 1000 / 3600).
        Returns a large sentinel (86_400 s = 24 hours) when speed or distance
        is zero, negative, NaN, or infinite to avoid division-by-zero or undefined ranking scores.
    """
    try:
        dist = float(distance_m)
        spd = float(speed_kmh)
    except (TypeError, ValueError):
        return SENTINEL_TRAVEL_TIME_S

    if math.isnan(dist) or math.isinf(dist) or math.isnan(spd) or math.isinf(spd):
        return SENTINEL_TRAVEL_TIME_S

    if spd <= 0.0 or dist <= 0.0:
        return SENTINEL_TRAVEL_TIME_S

    # Clamp extreme unrealistic speeds to realistic physical threshold
    spd = min(spd, MAX_REALISTIC_SPEED_KMH)

    speed_ms = spd * 1000.0 / 3600.0
    tt = dist / speed_ms
    return max(0.1, round(tt, 3))


def derive_travel_time(route: dict[str, Any]) -> float:
    """Return the best travel-time estimate for a route option dict.

    Priority order:
    1. If both ``distance_m`` and ``predicted_speed_5m`` are present, derive
       travel time from them (most accurate, uses short-horizon speed).
    2. Otherwise fall back to the raw ``travel_time_s`` field.

    Parameters
    ----------
    route:
        A route option dict with at least ``travel_time_s`` and optionally
        ``distance_m`` and ``predicted_speed_5m``.

    Returns
    -------
    float
        Best-estimate travel time in seconds, validated and non-negative.
    """
    distance_m = route.get("distance_m")
    speed_5m = route.get("predicted_speed_5m")
    if distance_m is not None and speed_5m is not None:
        return speed_to_travel_time(distance_m=float(distance_m), speed_kmh=float(speed_5m))

    try:
        raw_tt = float(route.get("travel_time_s", SENTINEL_TRAVEL_TIME_S))
    except (TypeError, ValueError):
        return SENTINEL_TRAVEL_TIME_S

    if math.isnan(raw_tt) or math.isinf(raw_tt) or raw_tt <= 0.0:
        return SENTINEL_TRAVEL_TIME_S

    return round(raw_tt, 3)


def enrich_routes_with_travel_time(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mutate ``travel_time_s`` in-place for each route using :func:`derive_travel_time`.

    Parameters
    ----------
    routes:
        List of route option dicts. Each dict is updated in-place.

    Returns
    -------
    list[dict[str, Any]]
        The same list (modified in-place) for chaining convenience.
    """
    for route in routes:
        route["travel_time_s"] = derive_travel_time(route)
    return routes
