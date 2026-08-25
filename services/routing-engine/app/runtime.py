from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import psycopg
import redis

from app.data.repositories import RouteOutcomeRepository, WeightScheduleRepository
from app.routing.redis_counter import RedisDiversificationCounter


@dataclass
class RuntimeDependencies:
    weight_schedules: WeightScheduleRepository
    route_outcomes: RouteOutcomeRepository
    route_counter: RedisDiversificationCounter
    database_connection: Any


def build_runtime_dependencies() -> RuntimeDependencies | None:
    database_url = os.environ.get("DATABASE_URL")
    redis_url = os.environ.get("REDIS_URL")
    if not database_url or not redis_url:
        return None

    database_connection = psycopg.connect(database_url)
    redis_client = redis.Redis.from_url(redis_url)
    return RuntimeDependencies(
        weight_schedules=WeightScheduleRepository(database_connection),
        route_outcomes=RouteOutcomeRepository(database_connection),
        route_counter=RedisDiversificationCounter(redis_client),
        database_connection=database_connection,
    )
