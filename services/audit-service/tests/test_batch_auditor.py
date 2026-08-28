"""Tests for app.batch_auditor."""
from __future__ import annotations

from app.batch_auditor import BatchAuditor


SCHEDULE_V1 = {
    "version": "2026-08-26-v1",
    "effective_date": "2026-08-26",
    "weights": {
        "emergency": 10.0,
        "commuter_general": 1.0,
    },
}

SCHEDULE_V2 = {
    "version": "2026-08-27-v1",
    "effective_date": "2026-08-27",
    "weights": {
        "emergency": 8.0,
        "commuter_general": 1.2,
    },
}


class MockPolicyRepository:
    def __init__(self, schedules: dict[str, dict]):
        self._schedules = schedules

    def get_version(self, *, version: str):
        return self._schedules.get(version)


def test_batch_auditor_all_valid_inline_schedules():
    auditor = BatchAuditor()
    outcomes = [
        {"trip_category": "emergency", "weight_applied": 10.0, "weight_schedule_version": "2026-08-26-v1"},
        {"trip_category": "commuter_general", "weight_applied": 1.0, "weight_schedule_version": "2026-08-26-v1"},
    ]
    schedules = {"2026-08-26-v1": SCHEDULE_V1}

    result = auditor.audit_batch(outcomes, default_schedules=schedules)

    assert result.total == 2
    assert result.valid_count == 2
    assert result.invalid_count == 0
    assert result.unresolved_count == 0
    assert result.all_valid is True
    assert len(result.results) == 2
    assert all(r["valid"] for r in result.results)


def test_batch_auditor_mixed_validity():
    auditor = BatchAuditor()
    outcomes = [
        {"trip_category": "emergency", "weight_applied": 10.0, "weight_schedule_version": "2026-08-26-v1"},
        {"trip_category": "emergency", "weight_applied": 1.0, "weight_schedule_version": "2026-08-26-v1"},  # wrong weight
        {"trip_category": "emergency", "weight_applied": 10.0, "weight_schedule_version": "unknown-v99"},  # unresolved
    ]
    schedules = {"2026-08-26-v1": SCHEDULE_V1}

    result = auditor.audit_batch(outcomes, default_schedules=schedules)

    assert result.total == 3
    assert result.valid_count == 1
    assert result.invalid_count == 1
    assert result.unresolved_count == 1
    assert result.all_valid is False


def test_batch_auditor_uses_policy_repository():
    repo = MockPolicyRepository({
        "2026-08-26-v1": SCHEDULE_V1,
        "2026-08-27-v1": SCHEDULE_V2,
    })
    auditor = BatchAuditor(policies=repo)

    outcomes = [
        {"trip_category": "emergency", "weight_applied": 10.0, "weight_schedule_version": "2026-08-26-v1"},
        {"trip_category": "emergency", "weight_applied": 8.0, "weight_schedule_version": "2026-08-27-v1"},
    ]

    result = auditor.audit_batch(outcomes)

    assert result.total == 2
    assert result.valid_count == 2
    assert result.all_valid is True


def test_batch_auditor_empty_batch():
    auditor = BatchAuditor()
    result = auditor.audit_batch([])

    assert result.total == 0
    assert result.valid_count == 0
    assert result.all_valid is True
    assert result.summary() == {
        "total": 0,
        "valid_count": 0,
        "invalid_count": 0,
        "unresolved_count": 0,
        "all_valid": True,
    }
