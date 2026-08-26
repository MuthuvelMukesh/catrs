from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import psycopg

from app.repositories import AuditResultRepository, PolicyRepository


@dataclass
class RuntimeDependencies:
    policies: PolicyRepository
    audit_results: AuditResultRepository
    database_connection: Any


def build_runtime_dependencies() -> RuntimeDependencies | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None

    database_connection = psycopg.connect(database_url)
    return RuntimeDependencies(
        policies=PolicyRepository(database_connection),
        audit_results=AuditResultRepository(database_connection),
        database_connection=database_connection,
    )