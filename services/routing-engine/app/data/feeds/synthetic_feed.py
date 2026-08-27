from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

from app.data.feeds.base import (
    DataFeed,
    EventReading,
    IncidentReading,
    TrafficReading,
    WeatherReading,
)
from app.data.synthetic_world import generate_grid_graph, generate_synthetic_history


class SyntheticTrafficFeed(DataFeed):
    """Generate traffic readings from the deterministic synthetic world.

    Wraps :func:`generate_synthetic_history` behind the same
    :class:`DataFeed` interface so the ingestion pipeline can swap
    between synthetic and live feeds transparently.
    """

    def __init__(self, *, days: int = 7, interval_minutes: int = 5) -> None:
        self._days = days
        self._interval_minutes = interval_minutes

    def fetch(self, *, as_of: datetime | None = None) -> list[TrafficReading]:
        rows = generate_synthetic_history(
            days=self._days,
            interval_minutes=self._interval_minutes,
        )
        return [
            TrafficReading(
                segment_id=row["segment_id"],
                timestamp=row["timestamp"],
                avg_speed=row["avg_speed"],
                vehicle_count=row["vehicle_count"],
            )
            for row in rows
        ]


class SyntheticWeatherFeed(DataFeed):
    """Generate deterministic weather readings for the synthetic world.

    Produces a single region with a daily severity cycle that
    peaks in the afternoon.
    """

    def __init__(self, *, days: int = 7, interval_minutes: int = 5) -> None:
        self._days = days
        self._interval_minutes = interval_minutes

    def fetch(self, *, as_of: datetime | None = None) -> list[WeatherReading]:
        start = datetime(2026, 1, 1, 0, 0)
        readings: list[WeatherReading] = []
        for day_index in range(self._days):
            for step in range((24 * 60) // self._interval_minutes):
                timestamp = start + timedelta(
                    days=day_index, minutes=step * self._interval_minutes,
                )
                hour = timestamp.hour
                # Deterministic severity: peaks afternoon, low at night
                severity = max(0.0, 0.3 * math.sin((hour - 6) / 24.0 * 2 * math.pi))
                readings.append(WeatherReading(
                    region_id="synthetic-region-1",
                    timestamp=timestamp,
                    severity_score=round(severity, 4),
                ))
        return readings


class SyntheticIncidentFeed(DataFeed):
    """Generate deterministic incident readings for the synthetic world.

    Simulates incidents on a fixed set of segments during rush hours.
    """

    def __init__(self, *, days: int = 7, interval_minutes: int = 5) -> None:
        self._days = days
        self._interval_minutes = interval_minutes

    def fetch(self, *, as_of: datetime | None = None) -> list[IncidentReading]:
        graph = generate_grid_graph()
        # Use a fixed subset of segments for deterministic incidents
        incident_segments = [edge["segment_id"] for edge in graph["edges"][:5]]
        start = datetime(2026, 1, 1, 0, 0)
        readings: list[IncidentReading] = []
        for day_index in range(self._days):
            for step in range((24 * 60) // self._interval_minutes):
                timestamp = start + timedelta(
                    days=day_index, minutes=step * self._interval_minutes,
                )
                hour = timestamp.hour
                weekday = timestamp.weekday()
                for segment_id in incident_segments:
                    # Active during weekday rush hours
                    active = (weekday < 5) and (hour in {7, 8, 17, 18})
                    readings.append(IncidentReading(
                        segment_id=segment_id,
                        timestamp=timestamp,
                        active=active,
                        severity=0.7 if active else 0.0,
                    ))
        return readings


class SyntheticEventFeed(DataFeed):
    """Generate deterministic event readings for the synthetic world.

    Simulates evening events near a fixed set of segments on weekends.
    """

    def __init__(self, *, days: int = 7, interval_minutes: int = 5) -> None:
        self._days = days
        self._interval_minutes = interval_minutes

    def fetch(self, *, as_of: datetime | None = None) -> list[EventReading]:
        graph = generate_grid_graph()
        # Use a fixed subset of segments for deterministic events
        event_segments = [edge["segment_id"] for edge in graph["edges"][10:15]]
        start = datetime(2026, 1, 1, 0, 0)
        readings: list[EventReading] = []
        for day_index in range(self._days):
            for step in range((24 * 60) // self._interval_minutes):
                timestamp = start + timedelta(
                    days=day_index, minutes=step * self._interval_minutes,
                )
                hour = timestamp.hour
                weekday = timestamp.weekday()
                for segment_id in event_segments:
                    # Active on weekends during evening hours
                    proximity = 0.8 if (weekday >= 5 and 17 <= hour <= 22) else 0.0
                    readings.append(EventReading(
                        segment_id=segment_id,
                        timestamp=timestamp,
                        proximity_score=proximity,
                    ))
        return readings
