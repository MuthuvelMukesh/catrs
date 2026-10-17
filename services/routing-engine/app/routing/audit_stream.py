"""Asynchronous Redis Stream producer decoupling route execution from audit verification."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import logging
import threading
from typing import Any

logger = logging.getLogger("catrs.audit_stream")


class AuditStreamProducer:
    """Non-blocking event publisher for routing outcomes using Redis Streams with in-memory buffer fallback."""

    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        stream_key: str = "{catrs:audit}:stream",
        max_buffer_size: int = 5000,
        stream_maxlen: int = 50000,
    ) -> None:
        self._redis = redis_client
        self._stream_key = stream_key
        self._stream_maxlen = stream_maxlen
        self._buffer: deque[dict[str, Any]] = deque(maxlen=max_buffer_size)
        self._lock = threading.Lock()
        self.published_count: int = 0
        self.buffered_count: int = 0

    @property
    def is_available(self) -> bool:
        if self._redis is None:
            return False
        if not hasattr(self._redis, "ping"):
            return True
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def publish_outcome(self, outcome: dict[str, Any]) -> bool:
        """Publish a routing outcome event asynchronously. Never raises or blocks caller."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": json.dumps(outcome),
        }

        if self.is_available:
            try:
                # Redis XADD with automatic stream length capping
                self._redis.xadd(
                    self._stream_key,
                    event,
                    maxlen=self._stream_maxlen,
                    approximate=True,
                )
                self.published_count += 1
                return True
            except Exception as exc:
                logger.warning("Failed to publish to Redis stream %s (%s); buffering locally", self._stream_key, exc)

        # Fallback to bounded local buffer
        with self._lock:
            self._buffer.append(outcome)
            self.buffered_count = len(self._buffer)
        return True

    def drain_buffer(self, max_items: int = 100) -> list[dict[str, Any]]:
        """Drain events from local buffer for delayed ingestion."""
        with self._lock:
            items: list[dict[str, Any]] = []
            while self._buffer and len(items) < max_items:
                items.append(self._buffer.popleft())
            self.buffered_count = len(self._buffer)
            return items

    def flush_buffer_to_redis(self) -> int:
        """Attempt to flush buffered items to Redis stream once connection recovers."""
        if not self.is_available:
            return 0

        flushed = 0
        with self._lock:
            while self._buffer:
                item = self._buffer[0]
                try:
                    self._redis.xadd(
                        self._stream_key,
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "payload": json.dumps(item),
                        },
                        maxlen=self._stream_maxlen,
                        approximate=True,
                    )
                    self._buffer.popleft()
                    flushed += 1
                    self.published_count += 1
                except Exception:
                    break
            self.buffered_count = len(self._buffer)
        return flushed
