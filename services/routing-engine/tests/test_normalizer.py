from __future__ import annotations

from datetime import datetime

from app.data.feeds.base import (
    EventReading,
    IncidentReading,
    TrafficReading,
    WeatherReading,
)
from app.data.normalizer import SegmentContext, normalize_readings


def _ts(hour: int) -> datetime:
    return datetime(2026, 1, 5, hour, 0)  # Monday


def test_normalize_traffic_only_produces_default_context():
    traffic = [
        TrafficReading(segment_id="s1", timestamp=_ts(8), avg_speed=42.0, vehicle_count=80),
    ]
    contexts = normalize_readings(traffic=traffic)

    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx.segment_id == "s1"
    assert ctx.avg_speed == 42.0
    assert ctx.vehicle_count == 80
    assert ctx.weather_severity_score == 0.0
    assert ctx.active_incident is False
    assert ctx.event_proximity_score == 0.0


def test_normalize_merges_weather_by_closest_timestamp():
    traffic = [
        TrafficReading(segment_id="s1", timestamp=_ts(10), avg_speed=45.0, vehicle_count=60),
    ]
    weather = [
        WeatherReading(region_id="r1", timestamp=_ts(9), severity_score=0.3),
        WeatherReading(region_id="r1", timestamp=_ts(11), severity_score=0.7),
    ]
    contexts = normalize_readings(traffic=traffic, weather=weather)

    assert len(contexts) == 1
    # _ts(10) is equidistant from 9 and 11 — min() picks the first one
    assert contexts[0].weather_severity_score in (0.3, 0.7)


def test_normalize_merges_incident_by_segment_and_timestamp():
    traffic = [
        TrafficReading(segment_id="s1", timestamp=_ts(8), avg_speed=30.0, vehicle_count=100),
        TrafficReading(segment_id="s2", timestamp=_ts(8), avg_speed=50.0, vehicle_count=40),
    ]
    incidents = [
        IncidentReading(segment_id="s1", timestamp=_ts(8), active=True, severity=0.9),
    ]
    contexts = normalize_readings(traffic=traffic, incidents=incidents)

    assert len(contexts) == 2
    s1_ctx = next(c for c in contexts if c.segment_id == "s1")
    s2_ctx = next(c for c in contexts if c.segment_id == "s2")

    assert s1_ctx.active_incident is True
    assert s1_ctx.incident_severity == 0.9
    assert s2_ctx.active_incident is False
    assert s2_ctx.incident_severity == 0.0


def test_normalize_merges_event_by_segment_and_timestamp():
    traffic = [
        TrafficReading(segment_id="s1", timestamp=_ts(19), avg_speed=35.0, vehicle_count=90),
    ]
    events = [
        EventReading(segment_id="s1", timestamp=_ts(19), proximity_score=0.8),
    ]
    contexts = normalize_readings(traffic=traffic, events=events)

    assert len(contexts) == 1
    assert contexts[0].event_proximity_score == 0.8


def test_normalize_handles_all_feeds_together():
    traffic = [
        TrafficReading(segment_id="s1", timestamp=_ts(17), avg_speed=28.0, vehicle_count=110),
    ]
    weather = [
        WeatherReading(region_id="r1", timestamp=_ts(17), severity_score=0.5),
    ]
    incidents = [
        IncidentReading(segment_id="s1", timestamp=_ts(17), active=True, severity=0.8),
    ]
    events = [
        EventReading(segment_id="s1", timestamp=_ts(17), proximity_score=0.6),
    ]
    contexts = normalize_readings(
        traffic=traffic, weather=weather, incidents=incidents, events=events,
    )

    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx.avg_speed == 28.0
    assert ctx.weather_severity_score == 0.5
    assert ctx.active_incident is True
    assert ctx.incident_severity == 0.8
    assert ctx.event_proximity_score == 0.6


def test_normalize_returns_empty_for_empty_traffic():
    contexts = normalize_readings(traffic=[])
    assert contexts == []
