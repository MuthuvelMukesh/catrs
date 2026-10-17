from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

logger = logging.getLogger("catrs.redis_counter")

_RESERVE_SCRIPT = """
local cutoff = tonumber(ARGV[1]) - tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)
local current = redis.call('ZCARD', KEYS[1])
local amount = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
if current + amount > limit then
    return 0
end
local window_secs = tonumber(ARGV[4])
for i = 1, amount do
    local sequence = redis.call('INCR', KEYS[2])
    local member = ARGV[1] .. ':' .. sequence
    redis.call('ZADD', KEYS[1], ARGV[1], member)
end
redis.call('EXPIRE', KEYS[1], window_secs)
redis.call('EXPIRE', KEYS[2], window_secs)
return 1
"""


import threading

class RedisDiversificationCounter:
    """Reserve route assignments against an atomic rolling-window cap.

    Supports atomic Lua execution on Redis when available, with a thread-safe
    process-local sliding window fallback when operating in degraded mode.
    Exposes explicit degraded indicators so consistency limitations are not masked.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        key_prefix: str = "routing",
        allow_degraded_fallback: bool = True,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._allow_degraded_fallback = allow_degraded_fallback
        self._local_lock = threading.Lock()
        self._local_assignments: dict[str, list[float]] = {}
        self.is_degraded: bool = False
        self.last_reservation_mode: str = "redis_atomic"

    @property
    def is_available(self) -> bool:
        """Check if Redis connection is active and responding."""
        if self._redis is None:
            return False
        if not hasattr(self._redis, "ping"):
            return True
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def reserve(
        self,
        *,
        route_id: str,
        amount: int,
        limit: int,
        window_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        if amount < 1 or limit < 1 or amount > limit:
            return False
        timestamp = (now or datetime.now(timezone.utc)).timestamp()
        route_key = f"{self._key_prefix}:route:{route_id}:assignments"
        sequence_key = f"{route_key}:sequence"

        if self.is_available:
            try:
                result = self._redis.eval(
                    _RESERVE_SCRIPT,
                    2,
                    route_key,
                    sequence_key,
                    timestamp,
                    amount,
                    limit,
                    window_seconds,
                )
                self.is_degraded = False
                self.last_reservation_mode = "redis_atomic"
                return bool(int(result))
            except Exception as exc:
                logger.warning("Redis reservation failed (%s); switching to degraded mode", exc)
                self.is_degraded = True

        if not self._allow_degraded_fallback:
            return False

        # Thread-safe process-local fallback
        self.is_degraded = True
        self.last_reservation_mode = "degraded_process_local"
        with self._local_lock:
            cutoff = timestamp - window_seconds
            existing = [t for t in self._local_assignments.get(route_id, []) if t > cutoff]
            if len(existing) + amount > limit:
                self._local_assignments[route_id] = existing
                return False
            existing.extend([timestamp] * amount)
            self._local_assignments[route_id] = existing
            return True

    def count(self, *, route_id: str, window_seconds: int, now: datetime | None = None) -> int:
        timestamp = (now or datetime.now(timezone.utc)).timestamp()
        route_key = f"{self._key_prefix}:route:{route_id}:assignments"
        if self.is_available:
            try:
                self._redis.zremrangebyscore(route_key, "-inf", timestamp - window_seconds)
                return int(self._redis.zcard(route_key))
            except Exception as exc:
                logger.warning("Redis count failed (%s); falling back to local count", exc)

        with self._local_lock:
            cutoff = timestamp - window_seconds
            existing = [t for t in self._local_assignments.get(route_id, []) if t > cutoff]
            self._local_assignments[route_id] = existing
            return len(existing)

    def reset(self, route_id: str) -> None:
        """Reset counters for a specific route."""
        route_key = f"{self._key_prefix}:route:{route_id}:assignments"
        sequence_key = f"{route_key}:sequence"
        try:
            self._redis.delete(route_key, sequence_key)
        except Exception as exc:
            logger.warning("Redis reset failed (%s)", exc)

    def reset_all(self) -> None:
        """Reset all routing counters."""
        try:
            keys = self._redis.keys(f"{self._key_prefix}:*")
            if keys:
                self._redis.delete(*keys)
        except Exception as exc:
            logger.warning("Redis reset_all failed (%s)", exc)
