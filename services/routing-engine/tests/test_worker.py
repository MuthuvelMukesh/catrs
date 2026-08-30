from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.config import RunMode, Settings
from app.data.ingestion import IngestPipeline, IngestResult
from app.worker import IngestionWorker, build_pipeline_from_config


def test_ingestion_worker_run_once():
    """Verify that run_once executes the pipeline."""
    mock_pipeline = MagicMock(spec=IngestPipeline)
    mock_result = IngestResult(
        traffic_readings_fetched=10,
        contexts_produced=10,
        readings_persisted=10,
        baselines_refreshed=5,
        contexts=[],
    )
    mock_pipeline.run.return_value = mock_result

    worker = IngestionWorker(mock_pipeline, interval_seconds=1)
    res = worker.run_once()

    assert mock_pipeline.run.called
    assert res.traffic_readings_fetched == 10
    assert res.baselines_refreshed == 5


def test_ingestion_worker_loop_and_stop():
    """Verify that the worker runs periodically and stops on stop signal."""
    mock_pipeline = MagicMock(spec=IngestPipeline)
    mock_pipeline.run.return_value = IngestResult(
        traffic_readings_fetched=5,
        contexts_produced=5,
        readings_persisted=0,
        baselines_refreshed=0,
        contexts=[],
    )

    worker = IngestionWorker(mock_pipeline, interval_seconds=1)

    t = threading.Thread(target=worker.start)
    t.daemon = True
    t.start()

    time.sleep(0.1)
    assert worker.is_running is True

    worker.stop()
    t.join(timeout=2.0)
    assert worker.is_running is False
    assert mock_pipeline.run.call_count >= 1


def test_build_pipeline_from_config_synthetic():
    """Verify pipeline construction from synthetic config settings."""
    config = Settings(mode=RunMode.SYNTHETIC)
    pipeline = build_pipeline_from_config(config, db_conn=None)
    assert pipeline is not None
    assert pipeline._traffic_repo is None
    assert pipeline._baseline_repo is None
