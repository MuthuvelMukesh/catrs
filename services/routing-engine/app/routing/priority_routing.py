from __future__ import annotations

import math
from typing import Any

from app.routing.travel_time import enrich_routes_with_travel_time


def rank_routes(
    *,
    trip_category: str,
    routes: list[dict[str, object]],
    weight_schedule: dict[str, object],
    include_explanation: bool = False,
    diversification_context: dict[str, Any] | None = None,
) -> list[dict[str, object]] | dict[str, Any]:
    """Rank candidate routes by priority weight and travel time.

    Mathematical Formulation:
    -------------------------
    Each candidate route i is scored via:

        adjusted_score_i = (weight_applied * priority_score_i) / max(travel_time_s_i, 1.0)

    where:
    - weight_applied is the category multiplier looked up from the active weight schedule
    - priority_score_i is the inherent segment/corridor priority score (default 1.0)
    - travel_time_s_i is the predicted or baseline travel time in seconds

    Routes are sorted in descending order of adjusted_score_i.
    """
    weights = weight_schedule["weights"]
    weight_value = float(weights.get(trip_category, 1.0))

    # Baseline order (pure shortest travel time without priority multipliers)
    baseline_sorted = sorted(
        routes,
        key=lambda r: float(r.get("travel_time_s", 86400.0)),
    )
    baseline_order = [str(r["route_id"]) for r in baseline_sorted]

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
            "adjusted_score": round(effective_score, 6),
        })
    ranked = sorted(ranked, key=lambda item: item["adjusted_score"], reverse=True)

    if not include_explanation:
        return ranked

    ranked_order = [str(r["route_id"]) for r in ranked]
    # Check whether priority weight or priority score actually altered the route ordering
    affected_ranking = (ranked_order != baseline_order)

    alternatives = [
        {
            "route_id": route["route_id"],
            "predicted_travel_time_s": route["travel_time_s"],
            "rank": rank,
        }
        for rank, route in enumerate(ranked, start=1)
    ]

    # Use provided diversification context or sensible default
    if diversification_context is not None:
        div_payload = {
            "applied": bool(diversification_context.get("applied", False)),
            "reason": str(diversification_context.get("reason", "Diversification evaluated.")),
            "assignment_pool_pct": float(diversification_context.get("assignment_pool_pct", 100.0)),
        }
    else:
        div_payload = {
            "applied": False,
            "reason": "No diversification cap was requested for this ranking.",
            "assignment_pool_pct": 100.0,
        }

    explanation = {
        "route_id": str(ranked[0]["route_id"]),
        "recommended_route": {
            "route_id": ranked[0]["route_id"],
            "predicted_travel_time_s": ranked[0]["travel_time_s"],
        },
        "alternatives_considered": alternatives,
        "diversification": div_payload,
        "priority_context": {
            "trip_category": trip_category,
            "weight_applied": ranked[0]["weight_applied"],
            "affected_ranking": affected_ranking,
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
    return_diversification_info: bool = False,
) -> dict[str, int] | tuple[dict[str, int], dict[str, Any]]:
    """Apply diversification cap across equivalent OD requests.

    Parameters
    ----------
    trip_category:
        Trip category string (e.g. emergency, commuter_general).
    route_options:
        List of candidate route options.
    request_count:
        Number of trips to allocate.
    current_counts:
        Current active assignments per route.
    cap_fraction:
        Maximum fraction of total request pool allowed on any single route (0.0 < cap_fraction <= 1.0).
    counter:
        Optional RedisDiversificationCounter for atomic window enforcement.
    window_seconds:
        Rolling window duration.
    weight_schedule:
        The active weight schedule dictionary.
    return_diversification_info:
        If True, returns tuple of (assignments, diversification_dict).
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

    cap_fraction = max(0.01, min(1.0, float(cap_fraction)))
    max_cap = max(1, int(request_count * cap_fraction))
    assignments: dict[str, int] = {route["route_id"]: 0 for route in route_options}

    for route in ranked:
        route_id = str(route["route_id"])
        remaining_needed = max(0, request_count - sum(assignments.values()))
        if remaining_needed <= 0:
            break

        current_route_load = current_counts.get(route_id, 0)
        available_capacity = max(0, max_cap - current_route_load)
        capacity = min(available_capacity, remaining_needed)
        if capacity <= 0:
            continue

        if counter is not None and counter.is_available:
            if not counter.reserve(
                route_id=route_id,
                amount=capacity,
                limit=max_cap,
                window_seconds=window_seconds,
            ):
                continue

        assignments[route_id] = capacity

    # Build diversification transparency payload
    top_route_id = str(ranked[0]["route_id"]) if ranked else ""
    top_assigned = assignments.get(top_route_id, 0)
    pool_pct = round((top_assigned / max(1, request_count)) * 100.0, 2)
    routes_assigned_count = sum(1 for c in assignments.values() if c > 0)
    diversification_applied = (routes_assigned_count > 1) or (cap_fraction < 1.0 and request_count > 1)

    if diversification_applied:
        reason = (
            f"Cap fraction {cap_fraction:.2f} applied: primary route {top_route_id} allocated "
            f"{top_assigned}/{request_count} trips ({pool_pct}%), remaining {request_count - top_assigned} "
            f"trips distributed across {routes_assigned_count - 1} alternative route(s)."
        )
    else:
        reason = f"Primary route {top_route_id} received 100% of requested allocation ({request_count} trips)."

    div_info = {
        "applied": diversification_applied,
        "reason": reason,
        "assignment_pool_pct": pool_pct,
    }

    if return_diversification_info:
        return assignments, div_info
    return assignments
