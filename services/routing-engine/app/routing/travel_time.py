"""Travel-time estimation utilities.

This module provides functions to convert between speed-based predictions and
travel-time seconds, and to derive the best available speed estimate for a
route option given prediction service output.
"""
from __future__ import annotations

from typing import Any


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
        Travel time in seconds.  Returns a large sentinel (86_400 s = 1 day)
        when speed is zero or negative to avoid division-by-zero in ranking.
    """
    if speed_kmh <= 0.0 or distance_m <= 0.0:
        return 86_400.0
    speed_ms = speed_kmh * 1000.0 / 3600.0
    return distance_m / speed_ms


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
        Best-estimate travel time in seconds.
    """
    distance_m = route.get("distance_m")
    speed_5m = route.get("predicted_speed_5m")
    if distance_m is not None and speed_5m is not None:
        return speed_to_travel_time(distance_m=float(distance_m), speed_kmh=float(speed_5m))
    return float(route["travel_time_s"])


def enrich_routes_with_travel_time(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mutate ``travel_time_s`` in-place for each route using :func:`derive_travel_time`.

    Parameters
    ----------
    routes:
        List of route option dicts.  Each dict is updated in-place.

    Returns
    -------
    list[dict[str, Any]]
        The same list (modified in-place) for chaining convenience.
    """
    for route in routes:
        route["travel_time_s"] = derive_travel_time(route)
    return routes
