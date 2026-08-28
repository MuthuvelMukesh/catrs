from __future__ import annotations

from typing import Any

from app.routing.travel_time import enrich_routes_with_travel_time


def rank_routes(
    *,
    trip_category: str,
    routes: list[dict[str, object]],
    weight_schedule: dict[str, object],
    include_explanation: bool = False,
) -> list[dict[str, object]] | dict[str, Any]:
    """Rank routes by travel time and trip-category weight.

    The prototype keeps the logic simple but matches the intended architecture:
    a category weight is applied to the route score while preserving a direct
    travel-time ordering component.
    """
    weights = weight_schedule["weights"]
    weight_value = float(weights.get(trip_category, 1.0))
    ranked = []
    for route in routes:
        travel_time = float(route["travel_time_s"])
        priority_score = float(route.get("priority_score", 1.0))
        effective_score = (weight_value * priority_score) / max(travel_time, 1.0)
        ranked.append({
            "route_id": route["route_id"],
            "travel_time_s": travel_time,
            "priority_score": priority_score,
            "weight_applied": weight_value,
            "adjusted_score": effective_score,
        })
    ranked = sorted(ranked, key=lambda item: item["adjusted_score"], reverse=True)
    if not include_explanation:
        return ranked

    alternatives = [
        {
            "route_id": route["route_id"],
            "predicted_travel_time_s": route["travel_time_s"],
            "rank": rank,
        }
        for rank, route in enumerate(ranked, start=1)
    ]
    explanation = {
        "route_id": str(ranked[0]["route_id"]),
        "recommended_route": {
            "route_id": ranked[0]["route_id"],
            "predicted_travel_time_s": ranked[0]["travel_time_s"],
        },
        "alternatives_considered": alternatives,
        "diversification": {
            "applied": False,
            "reason": "No diversification cap was requested for this ranking.",
            "assignment_pool_pct": 100.0,
        },
        "priority_context": {
            "trip_category": trip_category,
            "weight_applied": ranked[0]["weight_applied"],
            "affected_ranking": True,
        },
        "weight_schedule_version": str(weight_schedule["version"]),
    }
    return {"ranked_routes": ranked, "explanation": explanation}


def route_trip(
    *,
    trip_category: str,
    route_options: list[dict[str, object]],
    request_count: int,
    current_counts: dict[str, int],
    cap_fraction: float,
    counter: Any | None = None,
    window_seconds: int = 60,
    weight_schedule: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Apply a simple diversification cap across equivalent OD requests.

    Parameters
    ----------
    weight_schedule:
        The active weight schedule dict used to rank routes before assigning
        capacity.  When ``None`` a neutral single-category fallback is
        constructed so the function remains callable without a live DB.
    """
    effective_schedule = weight_schedule or {
        "version": "default",
        "effective_date": "2026-01-01",
        "weights": {trip_category: 1.0},
    }
    # Derive travel times from predicted speed where available.
    options = enrich_routes_with_travel_time([dict(r) for r in route_options])
    ranked = rank_routes(
        trip_category=trip_category,
        routes=options,
        weight_schedule=effective_schedule,
    )
    max_cap = max(1, int(request_count * cap_fraction))
    assignments: dict[str, int] = {route["route_id"]: 0 for route in route_options}
    for route in ranked:
        route_id = str(route["route_id"])
        available_capacity = max(0, max_cap - current_counts.get(route_id, 0))
        capacity = min(available_capacity, max(0, request_count - sum(assignments.values())))
        if capacity <= 0:
            continue
        if counter is not None and not counter.reserve(
            route_id=route_id,
            amount=capacity,
            limit=max_cap,
            window_seconds=window_seconds,
        ):
            continue
        assignments[route_id] = capacity
    return assignments
