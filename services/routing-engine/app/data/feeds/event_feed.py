from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.data.feeds.base import DataFeed, EventReading


class EventFeed(DataFeed):
    """Fetch event proximity scores from an external API.

    When ``base_url`` is ``None`` the feed is disabled and ``fetch``
    returns an empty list, letting the system fall back to synthetic data.
    """

    def __init__(self, *, base_url: str | None = None, timeout: float = 10.0) -> None:
        self._base_url = base_url
        self._timeout = timeout

    def fetch(self, *, as_of: datetime | None = None) -> list[EventReading]:
        if self._base_url is None:
            return []
        params: dict[str, Any] = {}
        if as_of is not None:
            params["as_of"] = as_of.isoformat()
        response = httpx.get(
            f"{self._base_url}/events",
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return [
            EventReading(
                segment_id=item["segment_id"],
                timestamp=datetime.fromisoformat(item["timestamp"]),
                proximity_score=float(item["proximity_score"]),
            )
            for item in response.json()
        ]
