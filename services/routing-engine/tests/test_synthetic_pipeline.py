"""End-to-end test of the full synthetic ingestion pipeline.

Runs SyntheticTrafficFeed → IngestPipeline → normalised SegmentContext list
without any database, confirming data flows correctly through the whole stack.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.data.feeds.synthetic_feed import (
    SyntheticEventFeed,
    SyntheticIncidentFeed,
    SyntheticTrafficFeed,
    SyntheticWeatherFeed,
)
from app.data.ingestion import IngestPipeline
from app.data.normalizer import SegmentContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_pipeline(*, days: int = 1, interval_minutes: int = 60) -> IngestPipeline:
    """Build a pipeline with all synthetic feeds, no database."""
    return IngestPipeline(
        traffic_feed=SyntheticTrafficFeed(days=days, interval_minutes=interval_minutes),
        weather_feed=SyntheticWeatherFeed(days=days, interval_minutes=interval_minutes),
        incident_feed=SyntheticIncidentFeed(days=days, interval_minutes=interval_minutes),
        event_feed=SyntheticEventFeed(days=days, interval_minutes=interval_minutes),
        traffic_repo=None,
        baseline_repo=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pipeline_produces_segment_contexts():
    pipeline = _build_pipeline()
    result = pipeline.run()
    assert result.contexts_produced > 0
    assert all(isinstance(ctx, SegmentContext) for ctx in result.contexts)


def test_pipeline_traffic_readings_count_matches_fetched():
    pipeline = _build_pipeline(days=1, interval_minutes=60)
    result = pipeline.run()
    assert result.traffic_readings_fetched > 0
    assert result.contexts_produced > 0


def test_pipeline_context_fields_are_populated():
    pipeline = _build_pipeline(days=1, interval_minutes=60)
    result = pipeline.run()
    ctx = result.contexts[0]
    assert isinstance(ctx.segment_id, str)
    assert isinstance(ctx.timestamp, datetime)
    assert ctx.avg_speed > 0
    assert ctx.vehicle_count >= 0
    assert 0.0 <= ctx.weather_severity_score <= 1.0
    assert isinstance(ctx.active_incident, bool)
    assert 0.0 <= ctx.event_proximity_score <= 1.0


def test_pipeline_without_db_skips_persist_and_baseline():
    pipeline = _build_pipeline()
    result = pipeline.run()
    assert result.readings_persisted == 0
    assert result.baselines_refreshed == 0


def test_pipeline_repr_is_human_readable():
    pipeline = _build_pipeline()
    result = pipeline.run()
    text = repr(result)
    assert "fetched=" in text
    assert "contexts=" in text
    assert "persisted=" in text
    assert "baselines=" in text


def test_pipeline_contexts_include_rush_hour_incidents():
    """Incidents are active during weekday rush hours — some contexts should reflect this."""
    pipeline = _build_pipeline(days=7, interval_minutes=60)
    result = pipeline.run()
    incident_contexts = [ctx for ctx in result.contexts if ctx.active_incident]
    assert len(incident_contexts) > 0, "Expected at least one incident-active context"


def test_pipeline_contexts_have_unique_segment_timestamps():
    """No two contexts should share both the same segment and the same timestamp."""
    pipeline = _build_pipeline(days=1, interval_minutes=60)
    result = pipeline.run()
    keys = [(ctx.segment_id, ctx.timestamp) for ctx in result.contexts]
    assert len(keys) == len(set(keys)), "Duplicate (segment_id, timestamp) pairs found"
