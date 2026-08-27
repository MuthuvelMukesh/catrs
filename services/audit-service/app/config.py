from __future__ import annotations

import os
from dataclasses import dataclass
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

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables."""
        mode_raw = os.environ.get("AUDIT_MODE", "synthetic").lower()
        mode = RunMode(mode_raw) if mode_raw in RunMode.__members__.values() else RunMode.SYNTHETIC

        return cls(
            mode=mode,
            database_url=os.environ.get("DATABASE_URL"),
        )
