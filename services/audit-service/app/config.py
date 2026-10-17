from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class RunMode(str, Enum):
    """Operating mode for the audit service."""

    SYNTHETIC = "synthetic"
    PRODUCTION = "production"


@dataclass(frozen=True)
class Settings:
    """Typed configuration for the audit service.

    All values can be set through environment variables.  When
    ``mode`` is ``synthetic`` the service operates without a database
    and accepts policy data inline with each request.
    """

    mode: RunMode = RunMode.SYNTHETIC
    database_url: str | None = None
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])
    api_key: str | None = None
    admin_api_key: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables."""
        mode_raw = os.environ.get("AUDIT_MODE", "synthetic").lower()
        mode = RunMode(mode_raw) if mode_raw in RunMode.__members__.values() else RunMode.SYNTHETIC

        cors_str = os.environ.get("CORS_ORIGINS")
        cors_origins = [o.strip() for o in cors_str.split(",") if o.strip()] if cors_str else ["http://localhost:3000", "http://127.0.0.1:3000"]

        return cls(
            mode=mode,
            database_url=os.environ.get("DATABASE_URL"),
            cors_origins=cors_origins,
            api_key=os.environ.get("AUDIT_API_KEY"),
            admin_api_key=os.environ.get("ADMIN_API_KEY"),
        )
