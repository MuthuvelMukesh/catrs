from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.data.feeds.base import DataFeed, IncidentReading


class IncidentFeed(DataFeed):
    """Fetch active incidents from an external API.

    When ``base_url`` is ``None`` the feed is disabled and ``fetch``
    returns an empty list, letting the system fall back to synthetic data.
    """

    def __init__(self, *, base_url: str | None = None, timeout: float = 10.0) -> None:
        self._base_url = base_url
        self._timeout = timeout

    def fetch(self, *, as_of: datetime | None = None) -> list[IncidentReading]:
        if self._base_url is None:
            return []
        params: dict[str, Any] = {}
        if as_of is not None:
            params["as_of"] = as_of.isoformat()
        response = httpx.get(
            f"{self._base_url}/incidents",
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return [
            IncidentReading(
                segment_id=item["segment_id"],
                timestamp=datetime.fromisoformat(item["timestamp"]),
                active=bool(item["active"]),
                severity=float(item.get("severity", 1.0)),
            )
            for item in response.json()
        ]
