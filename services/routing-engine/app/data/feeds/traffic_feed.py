"""Production-hardened traffic data feed adapter with retries, circuit breaker, and schema validation."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any

import httpx

from app.data.feeds.base import DataFeed, TrafficReading
from app.data.feeds.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger("catrs.feeds.traffic")


class TrafficFeed(DataFeed):
    """Fetch traffic readings from an external API with retries and circuit breaker."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        circuit_breaker: CircuitBreaker | None = None,
        source_name: str = "external_traffic_api",
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self.circuit_breaker = circuit_breaker or CircuitBreaker(name="traffic_feed_breaker")
        self.source_name = source_name

    def fetch(self, *, as_of: datetime | None = None) -> list[TrafficReading]:
        if self._base_url is None:
            return []

        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError(f"Circuit breaker {self.circuit_breaker.name!r} is OPEN; request throttled")

        params: dict[str, Any] = {}
        if as_of is not None:
            params["as_of"] = as_of.isoformat()

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = httpx.get(
                    f"{self._base_url}/readings",
                    params=params,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                data = response.json()
                self.circuit_breaker.record_success()

                now = datetime.now(timezone.utc)
                readings: list[TrafficReading] = []
                seen_keys: set[tuple[str, str]] = set()

                for item in data:
                    seg_id = str(item.get("segment_id", "")).strip()
                    ts_raw = item.get("timestamp")
                    if not seg_id or ts_raw is None:
                        continue

                    # Deduplication / idempotency
                    dedup_key = (seg_id, str(ts_raw))
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    dt = datetime.fromisoformat(ts_raw)
                    speed = max(0.0, min(250.0, float(item.get("avg_speed", 0.0))))
                    v_count = max(0, int(item.get("vehicle_count", 0)))
                    confidence = max(0.0, min(1.0, float(item.get("confidence", 1.0))))

                    readings.append(
                        TrafficReading(
                            segment_id=seg_id,
                            timestamp=dt,
                            avg_speed=speed,
                            vehicle_count=v_count,
                            source=self.source_name,
                            ingested_at=now,
                            is_synthetic=False,
                            confidence_score=confidence,
                            units=str(item.get("units", "km/h")),
                        )
                    )

                return readings
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Traffic feed fetch failed on attempt %d/%d: %s", attempt, self._max_retries, exc
                )
                if attempt < self._max_retries:
                    time.sleep(0.1 * (2 ** (attempt - 1)))

        self.circuit_breaker.record_failure()
        if last_exc:
            raise last_exc
        return []
