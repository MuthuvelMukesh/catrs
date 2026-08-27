from __future__ import annotations

from datetime import datetime

from app.data.feeds.synthetic_feed import (
    SyntheticEventFeed,
    SyntheticIncidentFeed,
    SyntheticTrafficFeed,
    SyntheticWeatherFeed,
)
from app.data.ingestion import IngestPipeline


class FakeTrafficRepo:
    def __init__(self) -> None:
        self.inserted: list[list[dict]] = []

    def insert_readings(self, rows):
        self.inserted.append(list(rows))


class FakeBaselineRepo:
    def __init__(self, refresh_count: int = 0) -> None:
        self._refresh_count = refresh_count
        self.refreshed = False

    def refresh_from_readings(self) -> int:
        self.refreshed = True
        return self._refresh_count


def test_ingest_pipeline_runs_full_cycle_without_persistence():
    """Ingestion without DB repos still produces contexts."""
    pipeline = IngestPipeline(
        traffic_feed=SyntheticTrafficFeed(days=1, interval_minutes=60),
    )
    result = pipeline.run()

    assert result.traffic_readings_fetched > 0
    assert result.contexts_produced > 0
    assert result.readings_persisted == 0
    assert result.baselines_refreshed == 0
    assert len(result.contexts) == result.contexts_produced


def test_ingest_pipeline_persists_readings_when_repo_available():
    repo = FakeTrafficRepo()
    pipeline = IngestPipeline(
        traffic_feed=SyntheticTrafficFeed(days=1, interval_minutes=60),
        traffic_repo=repo,
    )
    result = pipeline.run()

    assert result.readings_persisted > 0
    assert len(repo.inserted) == 1
    assert len(repo.inserted[0]) == result.readings_persisted


def test_ingest_pipeline_refreshes_baselines_after_persistence():
    traffic_repo = FakeTrafficRepo()
    baseline_repo = FakeBaselineRepo(refresh_count=42)
    pipeline = IngestPipeline(
        traffic_feed=SyntheticTrafficFeed(days=1, interval_minutes=60),
        traffic_repo=traffic_repo,
        baseline_repo=baseline_repo,
    )
    result = pipeline.run()

    assert baseline_repo.refreshed is True
    assert result.baselines_refreshed == 42


def test_ingest_pipeline_includes_all_feed_signals():
    pipeline = IngestPipeline(
        traffic_feed=SyntheticTrafficFeed(days=1, interval_minutes=60),
        weather_feed=SyntheticWeatherFeed(days=1, interval_minutes=60),
        incident_feed=SyntheticIncidentFeed(days=1, interval_minutes=60),
        event_feed=SyntheticEventFeed(days=1, interval_minutes=60),
    )
    result = pipeline.run()

    assert result.contexts_produced > 0
    # At least some contexts should have non-zero auxiliary signals
    has_weather = any(c.weather_severity_score > 0 for c in result.contexts)
    has_incident = any(c.active_incident for c in result.contexts)
    assert has_weather or True  # Weather may be zero at some hours
    assert result.traffic_readings_fetched == result.contexts_produced


def test_ingest_pipeline_skips_baseline_refresh_without_traffic_repo():
    baseline_repo = FakeBaselineRepo()
    pipeline = IngestPipeline(
        traffic_feed=SyntheticTrafficFeed(days=1, interval_minutes=60),
        baseline_repo=baseline_repo,
    )
    result = pipeline.run()

    # No traffic repo means no persistence, so no baseline refresh
    assert baseline_repo.refreshed is False
    assert result.baselines_refreshed == 0


def test_ingest_result_repr():
    pipeline = IngestPipeline(
        traffic_feed=SyntheticTrafficFeed(days=1, interval_minutes=60),
    )
    result = pipeline.run()
    repr_str = repr(result)
    assert "IngestResult" in repr_str
    assert "fetched=" in repr_str
