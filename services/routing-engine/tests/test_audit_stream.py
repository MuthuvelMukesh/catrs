"""Unit tests for asynchronous AuditStreamProducer."""
from __future__ import annotations

from app.routing.audit_stream import AuditStreamProducer


class FakeRedisStream:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.stream_entries: list[tuple[str, dict]] = []

    def ping(self) -> bool:
        return not self.should_fail

    def xadd(self, name: str, fields: dict, maxlen: int | None = None, approximate: bool = False) -> str:
        if self.should_fail:
            raise ConnectionError("Redis cluster connection refused")
        self.stream_entries.append((name, fields))
        return f"1000-{len(self.stream_entries)}"


def test_audit_stream_publishes_to_redis():
    """Verify events are published to Redis stream when available."""
    redis = FakeRedisStream()
    producer = AuditStreamProducer(redis_client=redis, stream_key="{catrs:audit}:stream")

    success = producer.publish_outcome({"route_id": "r1", "allocated": 5})
    assert success is True
    assert producer.published_count == 1
    assert len(redis.stream_entries) == 1
    assert redis.stream_entries[0][0] == "{catrs:audit}:stream"


def test_audit_stream_buffers_locally_when_redis_unavailable():
    """Verify non-blocking fallback to local buffer when Redis fails."""
    failing_redis = FakeRedisStream(should_fail=True)
    producer = AuditStreamProducer(redis_client=failing_redis)

    success = producer.publish_outcome({"route_id": "r_fail", "allocated": 10})
    assert success is True
    assert producer.buffered_count == 1

    drained = producer.drain_buffer(max_items=10)
    assert len(drained) == 1
    assert drained[0]["route_id"] == "r_fail"
    assert producer.buffered_count == 0
