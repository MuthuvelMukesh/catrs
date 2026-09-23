from __future__ import annotations

from datetime import datetime, timedelta
import math
import random
from typing import Any

from app.data.feeds.base import (
    DataFeed,
    EventReading,
    IncidentReading,
    TrafficReading,
    WeatherReading,
)
from app.data.synthetic_world import (
    TrafficScenario,
    generate_grid_graph,
    generate_synthetic_history,
)


class SyntheticTrafficFeed(DataFeed):
    """Generate traffic readings from the deterministic synthetic world.

    Wraps :func:`generate_synthetic_history` behind the same
    :class:`DataFeed` interface so the ingestion pipeline can swap
    between synthetic and live feeds transparently.
    """

    def __init__(
        self,
        *,
        days: int = 7,
        interval_minutes: int = 5,
        scenario: TrafficScenario | str = TrafficScenario.NORMAL,
        seed: int = 42,
        start_time: datetime | None = None,
    ) -> None:
        self._days = days
        self._interval_minutes = interval_minutes
        self._scenario = scenario
        self._seed = seed
        self._start_time = start_time

    def fetch(self, *, as_of: datetime | None = None) -> list[TrafficReading]:
        rows = generate_synthetic_history(
            days=self._days,
            interval_minutes=self._interval_minutes,
            scenario=self._scenario,
            seed=self._seed,
            start_time=as_of or self._start_time,
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

    Produces a region with a daily severity cycle, amplified under weather degradation scenarios.
    """

    def __init__(
        self,
        *,
        days: int = 7,
        interval_minutes: int = 5,
        scenario: TrafficScenario | str = TrafficScenario.NORMAL,
        seed: int = 42,
        start_time: datetime | None = None,
    ) -> None:
        self._days = days
        self._interval_minutes = interval_minutes
        self._scenario = (
            TrafficScenario(scenario.lower())
            if isinstance(scenario, str)
            else scenario
        )
        self._seed = seed
        self._start_time = start_time

    def fetch(self, *, as_of: datetime | None = None) -> list[WeatherReading]:
        start = as_of or self._start_time or datetime(2026, 1, 1, 0, 0)
        readings: list[WeatherReading] = []
        is_bad_weather = self._scenario in (
            TrafficScenario.WEATHER_DEGRADATION,
            TrafficScenario.INCIDENT_WEATHER,
        )

        for day_index in range(self._days):
            for step in range((24 * 60) // self._interval_minutes):
                timestamp = start + timedelta(
                    days=day_index, minutes=step * self._interval_minutes,
                )
                hour = timestamp.hour
                if is_bad_weather:
                    severity = min(1.0, 0.65 + 0.3 * math.sin((hour - 4) / 24.0 * 2 * math.pi))
                else:
                    severity = max(0.0, 0.3 * math.sin((hour - 6) / 24.0 * 2 * math.pi))

                readings.append(WeatherReading(
                    region_id="synthetic-region-1",
                    timestamp=timestamp,
                    severity_score=round(max(0.0, min(1.0, severity)), 4),
                ))
        return readings


class SyntheticIncidentFeed(DataFeed):
    """Generate deterministic incident readings for the synthetic world.

    Simulates active incidents on bottleneck segments, amplified under incident scenarios.
    """

    def __init__(
        self,
        *,
        days: int = 7,
        interval_minutes: int = 5,
        scenario: TrafficScenario | str = TrafficScenario.NORMAL,
        seed: int = 42,
        start_time: datetime | None = None,
    ) -> None:
        self._days = days
        self._interval_minutes = interval_minutes
        self._scenario = (
            TrafficScenario(scenario.lower())
            if isinstance(scenario, str)
            else scenario
        )
        self._seed = seed
        self._start_time = start_time

    def fetch(self, *, as_of: datetime | None = None) -> list[IncidentReading]:
        graph = generate_grid_graph()
        incident_segments = [edge["segment_id"] for edge in graph["edges"][:8]]
        start = as_of or self._start_time or datetime(2026, 1, 1, 0, 0)
        readings: list[IncidentReading] = []
        has_incident_scenario = self._scenario in (
            TrafficScenario.TRAFFIC_INCIDENT,
            TrafficScenario.INCIDENT_WEATHER,
            TrafficScenario.EVENT_INCIDENT,
        )

        for day_index in range(self._days):
            for step in range((24 * 60) // self._interval_minutes):
                timestamp = start + timedelta(
                    days=day_index, minutes=step * self._interval_minutes,
                )
                hour = timestamp.hour
                weekday = timestamp.weekday()
                for segment_id in incident_segments:
                    if has_incident_scenario:
                        active = 7 <= hour <= 20
                        severity = 0.85 if active else 0.0
                    else:
                        active = (weekday < 5) and (hour in {7, 8, 17, 18})
                        severity = 0.7 if active else 0.0

                    readings.append(IncidentReading(
                        segment_id=segment_id,
                        timestamp=timestamp,
                        active=active,
                        severity=severity,
                    ))
        return readings


class SyntheticEventFeed(DataFeed):
    """Generate deterministic event readings for the synthetic world.

    Simulates venue events, elevated during major event scenarios.
    """

    def __init__(
        self,
        *,
        days: int = 7,
        interval_minutes: int = 5,
        scenario: TrafficScenario | str = TrafficScenario.NORMAL,
        seed: int = 42,
        start_time: datetime | None = None,
    ) -> None:
        self._days = days
        self._interval_minutes = interval_minutes
        self._scenario = (
            TrafficScenario(scenario.lower())
            if isinstance(scenario, str)
            else scenario
        )
        self._seed = seed
        self._start_time = start_time

    def fetch(self, *, as_of: datetime | None = None) -> list[EventReading]:
        graph = generate_grid_graph()
        event_segments = [edge["segment_id"] for edge in graph["edges"][10:20]]
        start = as_of or self._start_time or datetime(2026, 1, 1, 0, 0)
        readings: list[EventReading] = []
        is_event_scenario = self._scenario in (
            TrafficScenario.MAJOR_EVENT,
            TrafficScenario.EVENT_INCIDENT,
        )

        for day_index in range(self._days):
            for step in range((24 * 60) // self._interval_minutes):
                timestamp = start + timedelta(
                    days=day_index, minutes=step * self._interval_minutes,
                )
                hour = timestamp.hour
                weekday = timestamp.weekday()
                for segment_id in event_segments:
                    if is_event_scenario:
                        proximity = 0.95 if (17 <= hour <= 23) else 0.1
                    else:
                        proximity = 0.8 if (weekday >= 5 and 17 <= hour <= 22) else 0.0

                    readings.append(EventReading(
                        segment_id=segment_id,
                        timestamp=timestamp,
                        proximity_score=proximity,
                    ))
        return readings
