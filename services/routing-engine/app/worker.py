"""Background scheduled worker for periodic traffic data ingestion and baseline refresh."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Any

from app.config import RunMode, Settings
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
from app.data.ingestion import IngestPipeline, IngestResult
from app.data.repositories import (
    HistoricalBaselineRepository,
    TrafficRepository,
)

logger = logging.getLogger("catrs.worker")


class IngestionWorker:
    """Runs IngestPipeline at periodic intervals with graceful shutdown."""

    def __init__(
        self,
        pipeline: IngestPipeline,
        interval_seconds: int = 300,
    ) -> None:
        self.pipeline = pipeline
        self.interval_seconds = max(1, interval_seconds)
        self._stop_event = threading.Event()
        self._is_running = False

    def run_once(self) -> IngestResult:
        """Execute a single ingestion and baseline refresh cycle."""
        logger.info("Executing scheduled ingestion cycle...")
        result = self.pipeline.run()
        logger.info("Ingestion completed: %s", result)
        return result

    def start(self) -> None:
        """Run the ingestion loop synchronously until stopped."""
        self._stop_event.clear()
        self._is_running = True
        logger.info(
            "Starting IngestionWorker with interval=%ds",
            self.interval_seconds,
        )
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.error("Error during ingestion cycle: %s", exc, exc_info=True)

            # Wait for next interval or stop signal
            if self._stop_event.wait(timeout=self.interval_seconds):
                break

        self._is_running = False
        logger.info("IngestionWorker stopped.")

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return self._is_running


def build_pipeline_from_config(config: Settings, db_conn: Any = None) -> IngestPipeline:
    """Construct an IngestPipeline instance according to application settings."""
    if config.mode == RunMode.SYNTHETIC:
        traffic_feed = SyntheticTrafficFeed()
        weather_feed = SyntheticWeatherFeed()
        incident_feed = SyntheticIncidentFeed()
        event_feed = SyntheticEventFeed()
    else:
        traffic_feed = TrafficFeed(base_url=config.traffic_feed_url)
        weather_feed = WeatherFeed(base_url=config.weather_feed_url)
        incident_feed = IncidentFeed(base_url=config.incident_feed_url)
        event_feed = EventFeed(base_url=config.event_feed_url)

    traffic_repo = TrafficRepository(db_conn) if db_conn else None
    baseline_repo = HistoricalBaselineRepository(db_conn) if db_conn else None

    return IngestPipeline(
        traffic_feed=traffic_feed,
        weather_feed=weather_feed,
        incident_feed=incident_feed,
        event_feed=event_feed,
        traffic_repo=traffic_repo,
        baseline_repo=baseline_repo,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="CATRS Periodic Ingestion Worker")
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Polling interval in seconds (default: 300)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single cycle and exit",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = Settings.from_env()
    db_conn = None
    if config.database_url:
        try:
            import psycopg

            db_conn = psycopg.connect(config.database_url)
            logger.info("Connected to database at %s", config.database_url)
        except Exception as exc:
            logger.warning("Could not connect to database: %s", exc)

    pipeline = build_pipeline_from_config(config, db_conn=db_conn)
    worker = IngestionWorker(pipeline, interval_seconds=args.interval)

    if args.once:
        worker.run_once()
        return

    # Handle graceful exit
    def _handle_signal(signum: int, frame: Any) -> None:
        logger.info("Received signal %d, stopping worker...", signum)
        worker.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    worker.start()


if __name__ == "__main__":
    main()
