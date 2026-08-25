from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_RESERVE_SCRIPT = """
local cutoff = tonumber(ARGV[1]) - tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)
local current = redis.call('ZCARD', KEYS[1])
local amount = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
if current + amount > limit then
    return 0
end
local sequence = redis.call('INCR', KEYS[2])
local member = ARGV[1] .. ':' .. sequence
redis.call('ZADD', KEYS[1], ARGV[1], member)
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return 1
"""


class RedisDiversificationCounter:
    """Reserve route assignments against an atomic rolling-window cap."""

    def __init__(self, redis_client: Any, *, key_prefix: str = "routing") -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

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
        return bool(int(result))

    def count(self, *, route_id: str, window_seconds: int, now: datetime | None = None) -> int:
        timestamp = (now or datetime.now(timezone.utc)).timestamp()
        route_key = f"{self._key_prefix}:route:{route_id}:assignments"
        self._redis.zremrangebyscore(route_key, "-inf", timestamp - window_seconds)
        return int(self._redis.zcard(route_key))
