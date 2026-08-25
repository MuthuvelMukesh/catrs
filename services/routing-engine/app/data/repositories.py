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
