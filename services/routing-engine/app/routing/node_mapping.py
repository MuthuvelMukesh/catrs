"""Node-to-road mapping layer for CATRS.

Bridges sensor/node-level ST-GNN speed predictions with the routing engine:
1. Translates physical sensor IDs (e.g., METR-LA '773869', PEMS-BAY '400001')
   or synthetic node indices (0..99) into routing graph segments.
2. Constructs candidate route segments and converts predicted speeds (5m, 15m, 30m)
   into dynamic edge traversal times:
       travel_time_seconds = (segment_length_km / predicted_speed_kmh) * 3600
3. Enforces architectural separation between forecasting benchmarks and routing simulation:
   - Real benchmark datasets (METR-LA, PEMS-BAY) provide verified sensor speed forecasts.
   - Synthetic data provides controlled routing topology, stress testing, and scenario simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np


@dataclass(frozen=True)
class MappedRoadSegment:
    """Represents a navigable road edge derived from sensor topology."""

    segment_id: str
    source_sensor: str
    target_sensor: str
    length_km: float
    free_flow_speed: float
    predicted_speed_5m: float
    predicted_speed_15m: float
    predicted_speed_30m: float
    travel_time_5m_seconds: float
    travel_time_15m_seconds: float
    travel_time_30m_seconds: float


class SensorToRouteMapper:
    """Explicit mapping layer connecting sensor forecasts to routing graph edges."""

    def __init__(
        self,
        sensor_ids: list[str],
        adj_mx: np.ndarray,
        default_segment_length_km: float = 1.5,
        default_free_flow_speed: float = 65.0,
    ) -> None:
        self.sensor_ids = sensor_ids
        self.sensor_to_idx = {sid: i for i, sid in enumerate(sensor_ids)}
        self.adj_mx = adj_mx
        self.default_segment_length_km = default_segment_length_km
        self.default_free_flow_speed = default_free_flow_speed

        # Build topology of connected road segments from non-zero adjacency weights
        self.segments: dict[str, tuple[str, str, float]] = {}
        N = len(sensor_ids)
        for i in range(N):
            for j in range(N):
                if i != j and adj_mx[i, j] > 0.05:
                    u = sensor_ids[i]
                    v = sensor_ids[j]
                    seg_id = f"seg_{u}_{v}"
                    # Distance proxy or calibrated length
                    self.segments[seg_id] = (u, v, default_segment_length_km)

    def map_predictions_to_routes(
        self,
        node_predictions: np.ndarray | dict[str, dict[str, float]],
    ) -> dict[str, MappedRoadSegment]:
        """Convert multi-horizon node predictions into routing graph segment weights.

        Args:
            node_predictions: Either array [N, 3] of speeds for each sensor,
                              or dict mapping sensor_id to {"5m": ..., "15m": ..., "30m": ...}.

        Returns:
            Dictionary mapping segment_id to MappedRoadSegment with computed travel times.
        """
        mapped: dict[str, MappedRoadSegment] = {}

        for seg_id, (src, dst, length_km) in self.segments.items():
            src_idx = self.sensor_to_idx.get(src, 0)
            dst_idx = self.sensor_to_idx.get(dst, 0)

            if isinstance(node_predictions, np.ndarray):
                # Target sensor speed dictates bottleneck edge flow
                speed_5m = max(5.0, float(node_predictions[dst_idx, 0]))
                speed_15m = max(5.0, float(node_predictions[dst_idx, 1]))
                speed_30m = max(5.0, float(node_predictions[dst_idx, 2]))
            else:
                preds = node_predictions.get(dst, {"5m": 50.0, "15m": 50.0, "30m": 50.0})
                speed_5m = max(5.0, float(preds.get("5m", 50.0)))
                speed_15m = max(5.0, float(preds.get("15m", 50.0)))
                speed_30m = max(5.0, float(preds.get("30m", 50.0)))

            tt_5m = (length_km / speed_5m) * 3600.0
            tt_15m = (length_km / speed_15m) * 3600.0
            tt_30m = (length_km / speed_30m) * 3600.0

            mapped[seg_id] = MappedRoadSegment(
                segment_id=seg_id,
                source_sensor=src,
                target_sensor=dst,
                length_km=length_km,
                free_flow_speed=self.default_free_flow_speed,
                predicted_speed_5m=round(speed_5m, 2),
                predicted_speed_15m=round(speed_15m, 2),
                predicted_speed_30m=round(speed_30m, 2),
                travel_time_5m_seconds=round(tt_5m, 2),
                travel_time_15m_seconds=round(tt_15m, 2),
                travel_time_30m_seconds=round(tt_30m, 2),
            )

        return mapped
