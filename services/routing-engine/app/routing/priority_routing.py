from __future__ import annotations


def rank_routes(*, trip_category: str, routes: list[dict[str, object]], weight_schedule: dict[str, object]) -> list[dict[str, object]]:
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
    return sorted(ranked, key=lambda item: item["adjusted_score"], reverse=True)


def route_trip(*, trip_category: str, route_options: list[dict[str, object]], request_count: int, current_counts: dict[str, int], cap_fraction: float) -> dict[str, int]:
    """Apply a simple diversification cap across equivalent OD requests."""
    ranked = rank_routes(
        trip_category=trip_category,
        routes=route_options,
        weight_schedule={
            "version": "prototype",
            "effective_date": "2026-01-01",
            "weights": {trip_category: 1.0},
        },
    )
    max_cap = max(1, int(request_count * cap_fraction))
    assignments: dict[str, int] = {route["route_id"]: 0 for route in route_options}
    for route in ranked:
        route_id = str(route["route_id"])
        capacity = min(max_cap, max(0, request_count - sum(assignments.values())))
        if capacity <= 0:
            break
        assignments[route_id] = min(capacity, max(0, current_counts.get(route_id, 0) + 1))
    return assignments
