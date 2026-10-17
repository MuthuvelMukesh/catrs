"""Concurrency, recovery, and degraded-mode tests for RedisDiversificationCounter."""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone
import pytest

from app.routing.priority_routing import route_trip
from app.routing.redis_counter import RedisDiversificationCounter


class MockRedisWithState:
    """Mock Redis tracking sorted sets in memory with simulated latency and failure modes."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.zsets: dict[str, list[tuple[float, str]]] = {}
        self.counters: dict[str, int] = {}
        self.is_connected = True

    def ping(self) -> bool:
        if self.should_fail or not self.is_connected:
            raise ConnectionError("Simulated Redis connection failure")
        return True

    def eval(self, script, key_count, route_key, sequence_key, timestamp, amount, limit, window_seconds):
        if self.should_fail or not self.is_connected:
            raise ConnectionError("Redis cluster unreachable")

        cutoff = float(timestamp) - float(window_seconds)
        items = self.zsets.setdefault(route_key, [])
        # Prune expired
        items = [item for item in items if item[0] > cutoff]
        self.zsets[route_key] = items

        current = len(items)
        amt = int(amount)
        lim = int(limit)
        if current + amt > lim:
            return 0

        seq = self.counters.setdefault(sequence_key, 0)
        for _ in range(amt):
            seq += 1
            items.append((float(timestamp), f"{timestamp}:{seq}"))
        self.counters[sequence_key] = seq
        return 1

    def zremrangebyscore(self, key, minimum, maximum):
        max_val = float(maximum)
        items = self.zsets.setdefault(key, [])
        self.zsets[key] = [it for it in items if it[0] > max_val]

    def zcard(self, key):
        return len(self.zsets.get(key, []))


def test_concurrent_reservations_strictly_enforce_cap():
    """Verify that concurrent threads never exceed the limit."""
    redis = MockRedisWithState()
    counter = RedisDiversificationCounter(redis, key_prefix="conc_test")

    limit = 20
    amount_per_req = 2
    total_workers = 20  # Total demand = 40 (2x the limit)

    accepted_count = 0
    now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)

    def worker_reserve():
        return counter.reserve(
            route_id="r_hot",
            amount=amount_per_req,
            limit=limit,
            window_seconds=60,
            now=now,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_reserve) for _ in range(total_workers)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    accepted_requests = sum(1 for r in results if r is True)
    total_reserved = accepted_requests * amount_per_req

    assert total_reserved <= limit
    assert accepted_requests == 10  # 10 requests * 2 = 20 capacity


def test_rolling_window_expiration():
    """Verify that expired timestamps free up quota for subsequent requests."""
    redis = MockRedisWithState()
    counter = RedisDiversificationCounter(redis, key_prefix="window_test")

    t0 = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    # Fill capacity at t0 (limit = 10)
    assert counter.reserve(route_id="r1", amount=10, limit=10, window_seconds=60, now=t0) is True
    # Immediate next request rejected
    assert counter.reserve(route_id="r1", amount=1, limit=10, window_seconds=60, now=t0) is False

    # At t0 + 61s, previous window has expired
    t1 = t0 + timedelta(seconds=61)
    assert counter.reserve(route_id="r1", amount=10, limit=10, window_seconds=60, now=t1) is True


def test_redis_failure_activates_degraded_process_local_fallback():
    """Verify that when Redis fails, counter operates in degraded local mode and reports warning."""
    failing_redis = MockRedisWithState(should_fail=True)
    counter = RedisDiversificationCounter(failing_redis, allow_degraded_fallback=True)

    t0 = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    # Local fallback should reserve locally up to limit
    res1 = counter.reserve(route_id="r_fallback", amount=5, limit=10, window_seconds=60, now=t0)
    assert res1 is True
    assert counter.is_degraded is True
    assert counter.last_reservation_mode == "degraded_process_local"

    # Local fallback respects limit
    res2 = counter.reserve(route_id="r_fallback", amount=6, limit=10, window_seconds=60, now=t0)
    assert res2 is False  # 5 + 6 > 10

    # Route trip transparency reflects degraded mode
    routes = [
        {"route_id": "r1", "travel_time_s": 100.0, "priority_score": 1.0},
        {"route_id": "r2", "travel_time_s": 150.0, "priority_score": 1.0},
    ]
    assignments, div_info = route_trip(
        trip_category="commuter_general",
        route_options=routes,
        request_count=10,
        current_counts={},
        cap_fraction=0.6,
        counter=counter,
        return_diversification_info=True,
    )

    assert div_info["is_degraded"] is True
    assert div_info["counter_mode"] == "degraded_process_local"
    assert "consistency_warning" in div_info
