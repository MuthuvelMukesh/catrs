from __future__ import annotations

from typing import Any


class PolicyRepository:
    """Read-only access to independently published weight policies."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get_effective(self, *, effective_at: Any) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT version, effective_date, weights
            FROM weight_schedules
            WHERE effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            (effective_at,),
        ).fetchone()
        if row is None:
            return None
        return {
            "version": row[0],
            "effective_date": row[1],
            "weights": row[2],
        }

    def get_version(self, *, version: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT version, effective_date, weights
            FROM weight_schedules
            WHERE version = %s
            """,
            (version,),
        ).fetchone()
        if row is None:
            return None
        return {
            "version": row[0],
            "effective_date": row[1],
            "weights": row[2],
        }


class AuditResultRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def insert(self, result: dict[str, Any]) -> None:
        self._connection.execute(
            """
            INSERT INTO audit_results
                (route_id, outcome_at, weight_schedule_version, valid, failures)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                result["route_id"],
                result["outcome_at"],
                result["weight_schedule_version"],
                result["valid"],
                result["failures"],
            ),
        )
