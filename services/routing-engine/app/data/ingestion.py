from __future__ import annotations

from datetime import datetime
from typing import Any

from app.data.feeds.base import DataFeed
from app.data.normalizer import SegmentContext, normalize_readings


class IngestPipeline:
    """Orchestrate the feed → normalize → persist → baseline-refresh cycle.

    This class coordinates data ingestion from one or more feeds through
    normalization and into the database layer.  It can be invoked as a
    periodic task or triggered on demand.

    Parameters
    ----------
    traffic_feed:
        Primary traffic data feed.
    weather_feed:
        Optional weather feed.
    incident_feed:
        Optional incident feed.
    event_feed:
        Optional event feed.
    traffic_repo:
        Repository for persisting traffic readings.
    baseline_repo:
        Repository for persisting and refreshing historical baselines.
    """

    def __init__(
        self,
        *,
        traffic_feed: DataFeed,
        weather_feed: DataFeed | None = None,
        incident_feed: DataFeed | None = None,
        event_feed: DataFeed | None = None,
        traffic_repo: Any | None = None,
        baseline_repo: Any | None = None,
    ) -> None:
        self._traffic_feed = traffic_feed
        self._weather_feed = weather_feed
        self._incident_feed = incident_feed
        self._event_feed = event_feed
        self._traffic_repo = traffic_repo
        self._baseline_repo = baseline_repo

    def run(self, *, as_of: datetime | None = None) -> IngestResult:
        """Execute one ingestion cycle.

        1. Fetch readings from all configured feeds.
        2. Normalize into unified :class:`SegmentContext` records.
        3. Persist traffic readings (if repository available).
        4. Refresh historical baselines (if repository available).

        Returns a summary of the ingestion cycle.
        """
        # Fetch
        traffic_readings = self._traffic_feed.fetch(as_of=as_of)
        weather_readings = (
            self._weather_feed.fetch(as_of=as_of)
            if self._weather_feed is not None
            else None
        )
        incident_readings = (
            self._incident_feed.fetch(as_of=as_of)
            if self._incident_feed is not None
            else None
        )
        event_readings = (
            self._event_feed.fetch(as_of=as_of)
            if self._event_feed is not None
            else None
        )

        # Normalize
        contexts = normalize_readings(
            traffic=traffic_readings,
            weather=weather_readings,
            incidents=incident_readings,
            events=event_readings,
        )

        # Persist
        readings_persisted = 0
        if self._traffic_repo is not None and traffic_readings:
            rows = [
                {
                    "segment_id": r.segment_id,
                    "timestamp": r.timestamp,
                    "avg_speed": r.avg_speed,
                    "vehicle_count": r.vehicle_count,
                }
                for r in traffic_readings
            ]
            self._traffic_repo.insert_readings(rows)
            readings_persisted = len(rows)

        # Baseline refresh
        baselines_refreshed = 0
        if self._baseline_repo is not None and readings_persisted > 0:
            baselines_refreshed = self._baseline_repo.refresh_from_readings()

        return IngestResult(
            traffic_readings_fetched=len(traffic_readings),
            contexts_produced=len(contexts),
            readings_persisted=readings_persisted,
            baselines_refreshed=baselines_refreshed,
            contexts=contexts,
        )


class IngestResult:
    """Summary of a single ingestion cycle."""

    def __init__(
        self,
        *,
        traffic_readings_fetched: int,
        contexts_produced: int,
        readings_persisted: int,
        baselines_refreshed: int,
        contexts: list[SegmentContext],
    ) -> None:
        self.traffic_readings_fetched = traffic_readings_fetched
        self.contexts_produced = contexts_produced
        self.readings_persisted = readings_persisted
        self.baselines_refreshed = baselines_refreshed
        self.contexts = contexts

    def __repr__(self) -> str:
        return (
            f"IngestResult(fetched={self.traffic_readings_fetched}, "
            f"contexts={self.contexts_produced}, "
            f"persisted={self.readings_persisted}, "
            f"baselines={self.baselines_refreshed})"
        )
