from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.data.feeds.base import (
    EventReading,
    IncidentReading,
    TrafficReading,
    WeatherReading,
)


@dataclass(frozen=True)
class SegmentContext:
    """Unified per-segment context ready for feature engineering.

    Combines traffic, weather, incident, and event signals into a
    single record keyed by ``(segment_id, timestamp)``.  Default
    values represent the absence of a signal—equivalent to
    "no weather data available, no incidents, no events."
    """

    segment_id: str
    timestamp: datetime
    avg_speed: float
    vehicle_count: int
    weather_severity_score: float = 0.0
    active_incident: bool = False
    incident_severity: float = 0.0
    event_proximity_score: float = 0.0


def normalize_readings(
    *,
    traffic: list[TrafficReading],
    weather: list[WeatherReading] | None = None,
    incidents: list[IncidentReading] | None = None,
    events: list[EventReading] | None = None,
) -> list[SegmentContext]:
    """Merge heterogeneous feed readings into unified segment contexts.

    Traffic readings form the primary key ``(segment_id, timestamp)``.
    Weather, incident, and event readings are joined by closest
    timestamp match to their respective segment.

    Parameters
    ----------
    traffic:
        Required traffic readings—every resulting context originates
        from a traffic reading.
    weather:
        Optional weather readings.  When provided, severity is matched
        by the closest-timestamp reading.
    incidents:
        Optional incident readings.  Matched by segment_id and
        closest timestamp.
    events:
        Optional event readings.  Matched by segment_id and closest
        timestamp.
    """
    # Build lookup indices for auxiliary feeds
    weather_index = _build_weather_index(weather or [])
    incident_index = _build_segment_index(incidents or [])
    event_index = _build_segment_index(events or [])

    contexts: list[SegmentContext] = []
    for reading in traffic:
        weather_severity = _lookup_weather(
            weather_index, reading.timestamp,
        )
        incident = _lookup_segment_reading(
            incident_index, reading.segment_id, reading.timestamp,
        )
        event = _lookup_segment_reading(
            event_index, reading.segment_id, reading.timestamp,
        )

        contexts.append(SegmentContext(
            segment_id=reading.segment_id,
            timestamp=reading.timestamp,
            avg_speed=reading.avg_speed,
            vehicle_count=reading.vehicle_count,
            weather_severity_score=weather_severity,
            active_incident=incident.active if isinstance(incident, IncidentReading) else False,
            incident_severity=incident.severity if isinstance(incident, IncidentReading) else 0.0,
            event_proximity_score=event.proximity_score if isinstance(event, EventReading) else 0.0,
        ))
    return contexts


def _build_weather_index(
    readings: list[WeatherReading],
) -> list[WeatherReading]:
    """Sort weather readings by timestamp for binary search."""
    return sorted(readings, key=lambda r: r.timestamp)


def _build_segment_index(
    readings: list[Any],
) -> dict[str, list[Any]]:
    """Group readings by segment_id and sort by timestamp."""
    index: dict[str, list[Any]] = {}
    for reading in readings:
        index.setdefault(reading.segment_id, []).append(reading)
    for items in index.values():
        items.sort(key=lambda r: r.timestamp)
    return index


def _lookup_weather(
    sorted_readings: list[WeatherReading],
    timestamp: datetime,
) -> float:
    """Find the closest weather reading by timestamp."""
    if not sorted_readings:
        return 0.0
    best = min(sorted_readings, key=lambda r: abs((r.timestamp - timestamp).total_seconds()))
    return best.severity_score


def _lookup_segment_reading(
    index: dict[str, list[Any]],
    segment_id: str,
    timestamp: datetime,
) -> Any | None:
    """Find the closest reading for a segment by timestamp."""
    readings = index.get(segment_id)
    if not readings:
        return None
    return min(readings, key=lambda r: abs((r.timestamp - timestamp).total_seconds()))
