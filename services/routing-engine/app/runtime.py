from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.data.repositories import (
    HistoricalBaselineRepository,
    RouteOutcomeRepository,
    WeightScheduleRepository,
)
from app.models.prediction_service import PredictionService
from app.routing.redis_counter import RedisDiversificationCounter

logger = logging.getLogger("catrs.runtime")


@dataclass
class RuntimeDependencies:
    weight_schedules: WeightScheduleRepository | None
    route_outcomes: RouteOutcomeRepository | None
    route_counter: RedisDiversificationCounter | None
    prediction_service: PredictionService
    baseline_repo: HistoricalBaselineRepository | None
    database_connection: Any | None
    config: Settings | None = None


def build_runtime_dependencies() -> RuntimeDependencies | None:
    try:
        import dotenv
        env_path = dotenv.find_dotenv()
        if env_path:
            dotenv.load_dotenv(env_path)
    except Exception:
        pass

    database_url = os.environ.get("DATABASE_URL")
    redis_url = os.environ.get("REDIS_URL")
    config = Settings.from_env()

    db_conn = None
    if database_url:
        try:
            import psycopg
            db_conn = psycopg.connect(database_url)
        except Exception as exc:
            logger.warning("Database connection failed (%s): running in degraded mode", exc)
            db_conn = None

    redis_counter = None
    if redis_url:
        try:
            import redis
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=2.0)
            client.ping()
            redis_counter = RedisDiversificationCounter(client)
        except Exception as exc:
            logger.warning("Redis connection failed (%s): running without Redis counters", exc)
            redis_counter = None

    pred_service = PredictionService.from_config(config)

    # Return dependencies if any dependency exists or prediction service is configured
    return RuntimeDependencies(
        weight_schedules=WeightScheduleRepository(db_conn) if db_conn else None,
        route_outcomes=RouteOutcomeRepository(db_conn) if db_conn else None,
        route_counter=redis_counter,
        prediction_service=pred_service,
        baseline_repo=HistoricalBaselineRepository(db_conn) if db_conn else None,
        database_connection=db_conn,
        config=config,
    )
