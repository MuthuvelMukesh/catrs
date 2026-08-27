from __future__ import annotations

from datetime import datetime

from app.data.feeds.base import (
    EventReading,
    IncidentReading,
    TrafficReading,
    WeatherReading,
)
from app.data.feeds.event_feed import EventFeed
from app.data.feeds.incident_feed import IncidentFeed
from app.data.feeds.synthetic_feed import (
    SyntheticEventFeed,
    SyntheticIncidentFeed,
    SyntheticTrafficFeed,
    SyntheticWeatherFeed,
)
from app.data.feeds.traffic_feed import TrafficFeed
from app.data.feeds.weather_feed import WeatherFeed


# --- Disabled-feed tests (no URL configured → empty list) ---


def test_traffic_feed_returns_empty_when_url_not_configured():
    feed = TrafficFeed(base_url=None)
    assert feed.fetch() == []


def test_weather_feed_returns_empty_when_url_not_configured():
    feed = WeatherFeed(base_url=None)
    assert feed.fetch() == []


def test_incident_feed_returns_empty_when_url_not_configured():
    feed = IncidentFeed(base_url=None)
    assert feed.fetch() == []


def test_event_feed_returns_empty_when_url_not_configured():
    feed = EventFeed(base_url=None)
    assert feed.fetch() == []


# --- Synthetic feed tests ---


def test_synthetic_traffic_feed_returns_traffic_readings():
    feed = SyntheticTrafficFeed(days=1, interval_minutes=60)
    readings = feed.fetch()

    assert len(readings) > 0
    assert all(isinstance(r, TrafficReading) for r in readings)
    assert all(r.avg_speed > 0 for r in readings)
    assert all(r.vehicle_count >= 0 for r in readings)


def test_synthetic_weather_feed_returns_weather_readings():
    feed = SyntheticWeatherFeed(days=1, interval_minutes=60)
    readings = feed.fetch()

    assert len(readings) > 0
    assert all(isinstance(r, WeatherReading) for r in readings)
    assert all(0.0 <= r.severity_score <= 1.0 for r in readings)


def test_synthetic_incident_feed_returns_incident_readings():
    feed = SyntheticIncidentFeed(days=1, interval_minutes=60)
    readings = feed.fetch()

    assert len(readings) > 0
    assert all(isinstance(r, IncidentReading) for r in readings)
    # Some should be active during rush hours
    active_count = sum(1 for r in readings if r.active)
    inactive_count = sum(1 for r in readings if not r.active)
    assert active_count > 0
    assert inactive_count > 0


def test_synthetic_event_feed_returns_event_readings():
    feed = SyntheticEventFeed(days=7, interval_minutes=60)
    readings = feed.fetch()

    assert len(readings) > 0
    assert all(isinstance(r, EventReading) for r in readings)
    # Some should have non-zero proximity on weekends
    has_events = any(r.proximity_score > 0 for r in readings)
    assert has_events


def test_synthetic_traffic_feed_matches_deterministic_world():
    """Two calls with the same parameters produce identical results."""
    feed = SyntheticTrafficFeed(days=1, interval_minutes=60)
    first = feed.fetch()
    second = feed.fetch()

    assert len(first) == len(second)
    for a, b in zip(first, second):
        assert a.segment_id == b.segment_id
        assert a.timestamp == b.timestamp
        assert a.avg_speed == b.avg_speed
        assert a.vehicle_count == b.vehicle_count
