from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from app.repositories import AuditResultRepository, PolicyRepository

logger = logging.getLogger("catrs.audit.runtime")


@dataclass
class RuntimeDependencies:
    policies: PolicyRepository | None
    audit_results: AuditResultRepository | None
    database_connection: Any | None


def build_runtime_dependencies() -> RuntimeDependencies | None:
    try:
        import dotenv
        env_path = dotenv.find_dotenv()
        if env_path:
            dotenv.load_dotenv(env_path)
    except Exception:
        pass

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None

    try:
        import psycopg
        database_connection = psycopg.connect(database_url)
        return RuntimeDependencies(
            policies=PolicyRepository(database_connection),
            audit_results=AuditResultRepository(database_connection),
            database_connection=database_connection,
        )
    except Exception as exc:
        logger.warning("Audit database connection failed (%s): operating in memory-only mode", exc)
        return None