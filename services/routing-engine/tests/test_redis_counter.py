from datetime import datetime, timezone

from app.routing.redis_counter import RedisDiversificationCounter


class FakeRedis:
    def __init__(self, reservation_result: int) -> None:
        self.reservation_result = reservation_result
        self.eval_args = None
        self.removed = None

    def eval(self, script, key_count, route_key, sequence_key, timestamp, amount, limit, window_seconds):
        self.eval_args = (script, key_count, route_key, sequence_key, timestamp, amount, limit, window_seconds)
        return self.reservation_result

    def zremrangebyscore(self, key, minimum, maximum):
        self.removed = (key, minimum, maximum)

    def zcard(self, key):
        return 4


def test_counter_atomically_accepts_reservation_within_window_cap():
    redis = FakeRedis(1)
    counter = RedisDiversificationCounter(redis, key_prefix="test")

    reserved = counter.reserve(
        route_id="r1",
        amount=3,
        limit=10,
        window_seconds=60,
        now=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert reserved is True
    assert redis.eval_args[1] == 2
    assert redis.eval_args[2] == "test:route:r1:assignments"
    assert redis.eval_args[5:7] == (3, 10)


def test_counter_rejects_invalid_or_oversized_reservations():
    counter = RedisDiversificationCounter(FakeRedis(1))

    assert counter.reserve(route_id="r1", amount=0, limit=10, window_seconds=60) is False
    assert counter.reserve(route_id="r1", amount=11, limit=10, window_seconds=60) is False


def test_counter_reports_current_rolling_window_count():
    redis = FakeRedis(1)
    counter = RedisDiversificationCounter(redis, key_prefix="test")

    assert counter.count(
        route_id="r1",
        window_seconds=60,
        now=datetime(2026, 8, 26, tzinfo=timezone.utc),
    ) == 4
    assert redis.removed[0] == "test:route:r1:assignments"
