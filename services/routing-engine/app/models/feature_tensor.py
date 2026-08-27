from __future__ import annotations

import math
from typing import Any

from app.data.normalizer import SegmentContext
from app.models.pipeline import build_feature_vector


def build_segment_tensor(
    *,
    contexts_by_segment: dict[str, list[SegmentContext]],
    segment_order: list[str],
    baseline_lookup: dict[tuple[str, int, int], float],
    window_steps: int = 12,
) -> Any:
    """Convert a window of SegmentContext records into a tensor for STGNNPredictor.

    Produces a tensor of shape ``[1, window_steps, num_nodes, num_features]``
    by mapping each segment's context window through
    :func:`build_feature_vector` and flattening the result into a numeric
    feature vector.

    Parameters
    ----------
    contexts_by_segment:
        Mapping from segment_id to a list of at least ``window_steps``
        :class:`SegmentContext` records, ordered oldest-first.
    segment_order:
        Ordered list of segment_ids defining the node ordering in the
        tensor's node dimension.
    baseline_lookup:
        Mapping from ``(segment_id, weekday, hour)`` to historical
        baseline speed.  Used to populate the feature vector.
    window_steps:
        Number of temporal steps (default 12, matching the ST-GNN's
        expected input width).

    Returns
    -------
    torch.Tensor
        Shape ``[1, window_steps, len(segment_order), feature_count]``.

    Raises
    ------
    ValueError
        If any segment has fewer than ``window_steps`` context records.
    """
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required for tensor construction") from exc

    num_nodes = len(segment_order)
    feature_count = _FEATURE_COUNT

    tensor_data: list[list[list[float]]] = []
    for step_idx in range(window_steps):
        step_nodes: list[list[float]] = []
        for segment_id in segment_order:
            segment_contexts = contexts_by_segment.get(segment_id, [])
            if len(segment_contexts) < window_steps:
                raise ValueError(
                    f"Segment {segment_id} has {len(segment_contexts)} contexts, "
                    f"need at least {window_steps}"
                )
            ctx = segment_contexts[step_idx]
            baseline = baseline_lookup.get(
                (segment_id, ctx.timestamp.weekday(), ctx.timestamp.hour),
                ctx.avg_speed,
            )
            features = _context_to_feature_list(ctx, baseline)
            step_nodes.append(features)
        tensor_data.append(step_nodes)

    return torch.tensor([tensor_data], dtype=torch.float32)


# The feature vector has 9 scalar features after flattening:
# current_speed, current_volume, historical_baseline_speed,
# weather_severity_score, active_incident_flag, event_proximity_score,
# upstream_segment_congestion, time_of_day_sin, time_of_day_cos
_FEATURE_COUNT = 9


def _context_to_feature_list(ctx: SegmentContext, baseline: float) -> list[float]:
    """Convert a single context into a flat numeric feature list."""
    vector = build_feature_vector(
        current_speed=ctx.avg_speed,
        current_volume=ctx.vehicle_count,
        historical_baseline_speed=baseline,
        weather_severity_score=ctx.weather_severity_score,
        active_incident_flag=ctx.active_incident,
        event_proximity_score=ctx.event_proximity_score,
        upstream_segment_congestion=ctx.incident_severity,
        time_of_day=ctx.timestamp.hour,
        day_of_week=ctx.timestamp.weekday(),
    )
    return [
        float(vector["current_speed"]),
        float(vector["current_volume"]),
        float(vector["historical_baseline_speed"]),
        float(vector["weather_severity_score"]),
        1.0 if vector["active_incident_flag"] else 0.0,
        float(vector["event_proximity_score"]),
        float(vector["upstream_segment_congestion"]),
        float(vector["time_of_day_sin"]),
        float(vector["time_of_day_cos"]),
    ]


def get_feature_count() -> int:
    """Return the number of features per node per timestep."""
    return _FEATURE_COUNT
