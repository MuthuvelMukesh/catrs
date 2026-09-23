from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from app.data.feeds.base import DataFeed, TrafficReading
from app.data.normalizer import SegmentContext, normalize_readings

logger = logging.getLogger("catrs.ingestion")


class IngestPipeline:
    """Orchestrate the feed → normalize → persist → baseline-refresh cycle.

    This class coordinates data ingestion from one or more feeds through
    normalization and into the database layer. It handles feed failures
    gracefully by logging degradation and falling back to synthetic signals
    without terminating the whole process.
    """

    def __init__(
        self,
        *,
        traffic_feed: DataFeed,
        weather_feed: DataFeed | None = None,
        incident_feed: DataFeed | None = None,
        event_feed: DataFeed | None = None,
        fallback_traffic_feed: DataFeed | None = None,
        traffic_repo: Any | None = None,
        baseline_repo: Any | None = None,
    ) -> None:
        self._traffic_feed = traffic_feed
        self._weather_feed = weather_feed
        self._incident_feed = incident_feed
        self._event_feed = event_feed
        self._fallback_traffic_feed = fallback_traffic_feed
        self._traffic_repo = traffic_repo
        self._baseline_repo = baseline_repo

    def run(self, *, as_of: datetime | None = None) -> IngestResult:
        """Execute one ingestion cycle with fault tolerance."""
        feed_statuses: dict[str, str] = {}
        is_degraded = False

        # 1. Fetch Traffic
        traffic_readings: list[TrafficReading] = []
        try:
            traffic_readings = self._traffic_feed.fetch(as_of=as_of)
            feed_statuses["traffic"] = "healthy"
        except Exception as exc:
            logger.warning("Traffic feed fetch failed: %s; attempting fallback", exc)
            feed_statuses["traffic"] = f"degraded: {exc}"
            is_degraded = True
            if self._fallback_traffic_feed is not None:
                try:
                    traffic_readings = self._fallback_traffic_feed.fetch(as_of=as_of)
                    logger.info("Fell back to synthetic traffic feed successfully")
                except Exception as fb_exc:
                    logger.error("Fallback traffic feed also failed: %s", fb_exc)

        # 2. Fetch Weather
        weather_readings = None
        if self._weather_feed is not None:
            try:
                weather_readings = self._weather_feed.fetch(as_of=as_of)
                feed_statuses["weather"] = "healthy"
            except Exception as exc:
                logger.warning("Weather feed fetch failed: %s", exc)
                feed_statuses["weather"] = f"degraded: {exc}"
                is_degraded = True

        # 3. Fetch Incidents
        incident_readings = None
        if self._incident_feed is not None:
            try:
                incident_readings = self._incident_feed.fetch(as_of=as_of)
                feed_statuses["incidents"] = "healthy"
            except Exception as exc:
                logger.warning("Incident feed fetch failed: %s", exc)
                feed_statuses["incidents"] = f"degraded: {exc}"
                is_degraded = True

        # 4. Fetch Events
        event_readings = None
        if self._event_feed is not None:
            try:
                event_readings = self._event_feed.fetch(as_of=as_of)
                feed_statuses["events"] = "healthy"
            except Exception as exc:
                logger.warning("Event feed fetch failed: %s", exc)
                feed_statuses["events"] = f"degraded: {exc}"
                is_degraded = True

        # 5. Normalize
        contexts = normalize_readings(
            traffic=traffic_readings,
            weather=weather_readings,
            incidents=incident_readings,
            events=event_readings,
        )

        # 6. Persist
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
            try:
                self._traffic_repo.insert_readings(rows)
                readings_persisted = len(rows)
            except Exception as exc:
                logger.error("Failed to persist traffic readings to repository: %s", exc)

        # 7. Baseline refresh
        baselines_refreshed = 0
        if self._baseline_repo is not None and readings_persisted > 0:
            try:
                baselines_refreshed = self._baseline_repo.refresh_from_readings()
            except Exception as exc:
                logger.error("Failed to refresh historical baselines: %s", exc)

        return IngestResult(
            traffic_readings_fetched=len(traffic_readings),
            contexts_produced=len(contexts),
            readings_persisted=readings_persisted,
            baselines_refreshed=baselines_refreshed,
            contexts=contexts,
            feed_statuses=feed_statuses,
            is_degraded=is_degraded,
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
        feed_statuses: dict[str, str] | None = None,
        is_degraded: bool = False,
    ) -> None:
        self.traffic_readings_fetched = traffic_readings_fetched
        self.contexts_produced = contexts_produced
        self.readings_persisted = readings_persisted
        self.baselines_refreshed = baselines_refreshed
        self.contexts = contexts
        self.feed_statuses = feed_statuses or {}
        self.is_degraded = is_degraded

    def __repr__(self) -> str:
        return (
            f"IngestResult(fetched={self.traffic_readings_fetched}, "
            f"contexts={self.contexts_produced}, "
            f"persisted={self.readings_persisted}, "
            f"baselines={self.baselines_refreshed}, "
            f"degraded={self.is_degraded})"
        )
