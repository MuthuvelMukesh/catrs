from app.policy_verifier import verify_route_outcome


SCHEDULE = {
    "version": "2026-08-26-v1",
    "effective_date": "2026-08-26",
    "weights": {"emergency": 10.0, "commuter_general": 1.0},
}


def test_verifier_accepts_outcome_matching_published_policy():
    result = verify_route_outcome(
        outcome={
            "trip_category": "emergency",
            "weight_applied": 10.0,
            "weight_schedule_version": "2026-08-26-v1",
        },
        weight_schedule=SCHEDULE,
    )

    assert result == {
        "valid": True,
        "failures": [],
        "weight_schedule_version": "2026-08-26-v1",
    }


def test_verifier_reports_version_and_weight_mismatches():
    result = verify_route_outcome(
        outcome={
            "trip_category": "emergency",
            "weight_applied": 1.0,
            "weight_schedule_version": "2026-08-25-v1",
        },
        weight_schedule=SCHEDULE,
    )

    assert result["valid"] is False
    assert len(result["failures"]) == 2
