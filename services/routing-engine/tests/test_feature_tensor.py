from __future__ import annotations

from datetime import datetime

import pytest

torch = pytest.importorskip("torch")

from app.data.normalizer import SegmentContext
from app.models.feature_tensor import build_segment_tensor, get_feature_count


def _make_contexts(segment_id: str, count: int = 12) -> list[SegmentContext]:
    """Create a list of minimal SegmentContext records."""
    return [
        SegmentContext(
            segment_id=segment_id,
            timestamp=datetime(2026, 1, 5, 8, i * 5),  # Monday, 08:00-08:55
            avg_speed=45.0 + i,
            vehicle_count=80,
            weather_severity_score=0.3,
            active_incident=False,
            event_proximity_score=0.0,
        )
        for i in range(count)
    ]


def test_tensor_shape_matches_stgnn_expectation():
    segments = ["s1", "s2", "s3"]
    contexts_by_segment = {seg: _make_contexts(seg) for seg in segments}
    baseline_lookup = {
        (seg, 0, 8): 50.0 for seg in segments
    }

    tensor = build_segment_tensor(
        contexts_by_segment=contexts_by_segment,
        segment_order=segments,
        baseline_lookup=baseline_lookup,
        window_steps=12,
    )

    assert tensor.shape == (1, 12, 3, get_feature_count())
    assert tensor.dtype == torch.float32


def test_tensor_values_are_finite():
    segments = ["s1"]
    contexts_by_segment = {seg: _make_contexts(seg) for seg in segments}
    baseline_lookup = {("s1", 0, 8): 50.0}

    tensor = build_segment_tensor(
        contexts_by_segment=contexts_by_segment,
        segment_order=segments,
        baseline_lookup=baseline_lookup,
    )

    assert torch.isfinite(tensor).all()


def test_tensor_rejects_insufficient_context_window():
    segments = ["s1"]
    contexts_by_segment = {"s1": _make_contexts("s1", count=5)}

    with pytest.raises(ValueError, match="5 contexts"):
        build_segment_tensor(
            contexts_by_segment=contexts_by_segment,
            segment_order=segments,
            baseline_lookup={},
            window_steps=12,
        )


def test_tensor_uses_baseline_lookup():
    segments = ["s1"]
    contexts = _make_contexts("s1")
    baseline_lookup = {("s1", 0, 8): 99.0}

    tensor = build_segment_tensor(
        contexts_by_segment={"s1": contexts},
        segment_order=segments,
        baseline_lookup=baseline_lookup,
    )

    # Feature index 2 is historical_baseline_speed
    assert tensor[0, 0, 0, 2].item() == 99.0


def test_feature_count_returns_correct_value():
    assert get_feature_count() == 9
