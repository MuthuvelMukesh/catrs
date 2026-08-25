from app.routing.weight_schedule import WeightSchedule
from app.routing.priority_routing import (
    rank_routes,
    route_trip,
)


def test_emergency_trip_ranks_route_higher_than_commuter_trip():
    route_scores = rank_routes(
        trip_category="emergency",
        routes=[
            {"route_id": "r1", "travel_time_s": 500, "priority_score": 10},
            {"route_id": "r2", "travel_time_s": 1000, "priority_score": 1},
        ],
        weight_schedule={
            "version": "2026-07-30-v1",
            "effective_date": "2026-07-30",
            "weights": {"emergency": 10.0, "commuter_general": 1.0},
        },
    )
    commuter_scores = rank_routes(
        trip_category="commuter_general",
        routes=[
            {"route_id": "r1", "travel_time_s": 500, "priority_score": 10},
            {"route_id": "r2", "travel_time_s": 1000, "priority_score": 1},
        ],
        weight_schedule={
            "version": "2026-07-30-v1",
            "effective_date": "2026-07-30",
            "weights": {"emergency": 10.0, "commuter_general": 1.0},
        },
    )

    assert route_scores[0]["route_id"] == "r1"
    assert commuter_scores[0]["route_id"] == "r1"
    assert route_scores[0]["adjusted_score"] > commuter_scores[0]["adjusted_score"]


def test_route_trip_applies_capacity_cap_for_equivalent_od_batch():
    assignments = route_trip(
        trip_category="commuter_general",
        route_options=[
            {"route_id": "r1", "travel_time_s": 400, "priority_score": 2},
            {"route_id": "r2", "travel_time_s": 440, "priority_score": 2},
        ],
        request_count=100,
        current_counts={"r1": 60, "r2": 20},
        cap_fraction=0.35,
    )

    assert assignments["r1"] <= 35


def test_weight_schedule_rejects_updates_to_existing_version():
    schedule = WeightSchedule()
    schedule.insert_version({
        "version": "2026-07-30-v1",
        "effective_date": "2026-07-30",
        "weights": {"emergency": 10.0, "commuter_general": 1.0},
    })

    try:
        schedule.insert_version({
            "version": "2026-07-30-v1",
            "effective_date": "2026-07-31",
            "weights": {"emergency": 9.0, "commuter_general": 1.0},
        })
        assert False, "Expected duplicate version rejection"
    except ValueError:
        pass
