from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class TrafficRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def insert_readings(self, rows: Iterable[dict[str, Any]]) -> None:
        values = [
            (
                row["segment_id"],
                row["timestamp"],
                row["avg_speed"],
                row["vehicle_count"],
            )
            for row in rows
        ]
        if values:
            self._connection.executemany(
                """
                INSERT INTO traffic_readings
                    (segment_id, observed_at, avg_speed, vehicle_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (segment_id, observed_at) DO UPDATE SET
                    avg_speed = EXCLUDED.avg_speed,
                    vehicle_count = EXCLUDED.vehicle_count
                """,
                values,
            )

    def get_baseline(self, *, segment_id: str, weekday: int, hour: int) -> float | None:
        row = self._connection.execute(
            """
            SELECT avg_speed
            FROM historical_baselines
            WHERE segment_id = %s AND weekday = %s AND hour = %s
            """,
            (segment_id, weekday, hour),
        ).fetchone()
        return None if row is None else float(row[0])

    def get_recent_readings(
        self,
        *,
        segment_id: str,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Fetch the most recent readings for a segment, ordered newest-first."""
        rows = self._connection.execute(
            """
            SELECT segment_id, observed_at, avg_speed, vehicle_count
            FROM traffic_readings
            WHERE segment_id = %s
            ORDER BY observed_at DESC
            LIMIT %s
            """,
            (segment_id, limit),
        ).fetchall()
        return [
            {
                "segment_id": row[0],
                "timestamp": row[1],
                "avg_speed": float(row[2]),
                "vehicle_count": int(row[3]),
            }
            for row in rows
        ]


class HistoricalBaselineRepository:
    """Manage historical baseline averages by segment, weekday, and hour."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def upsert_baseline(
        self,
        *,
        segment_id: str,
        weekday: int,
        hour: int,
        avg_speed: float,
        sample_count: int,
    ) -> None:
        """Insert or update a baseline record."""
        self._connection.execute(
            """
            INSERT INTO historical_baselines
                (segment_id, weekday, hour, avg_speed, sample_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (segment_id, weekday, hour) DO UPDATE SET
                avg_speed = EXCLUDED.avg_speed,
                sample_count = EXCLUDED.sample_count
            """,
            (segment_id, weekday, hour, avg_speed, sample_count),
        )

    def refresh_from_readings(self) -> int:
        """Recompute all baselines from the traffic_readings table.

        Returns the number of baseline rows upserted.
        """
        result = self._connection.execute(
            """
            INSERT INTO historical_baselines (segment_id, weekday, hour, avg_speed, sample_count)
            SELECT
                segment_id,
                EXTRACT(DOW FROM observed_at)::smallint AS weekday,
                EXTRACT(HOUR FROM observed_at)::smallint AS hour,
                AVG(avg_speed) AS avg_speed,
                COUNT(*)::integer AS sample_count
            FROM traffic_readings
            GROUP BY segment_id, weekday, hour
            ON CONFLICT (segment_id, weekday, hour) DO UPDATE SET
                avg_speed = EXCLUDED.avg_speed,
                sample_count = EXCLUDED.sample_count
            """
        )
        return result.rowcount if hasattr(result, "rowcount") else 0

    def get_baseline(self, *, segment_id: str, weekday: int, hour: int) -> float | None:
        """Read a single baseline value."""
        row = self._connection.execute(
            """
            SELECT avg_speed
            FROM historical_baselines
            WHERE segment_id = %s AND weekday = %s AND hour = %s
            """,
            (segment_id, weekday, hour),
        ).fetchone()
        return None if row is None else float(row[0])


class WeightScheduleRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def insert_version(self, row: dict[str, Any]) -> None:
        self._connection.execute(
            """
            INSERT INTO weight_schedules (version, effective_date, weights)
            VALUES (%s, %s, %s)
            """,
            (row["version"], row["effective_date"], row["weights"]),
        )

    def get_version(self, *, version: str) -> dict[str, Any] | None:
        """Retrieve a specific weight schedule version."""
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


class RouteOutcomeRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def insert(self, outcome: dict[str, Any]) -> None:
        self._connection.execute(
            """
            INSERT INTO route_outcomes
                (route_id, trip_category, weight_schedule_version,
                 weight_applied, predicted_travel_time_s, observed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                outcome["route_id"],
                outcome["trip_category"],
                outcome["weight_schedule_version"],
                outcome["weight_applied"],
                outcome["predicted_travel_time_s"],
                outcome["observed_at"],
            ),
        )

