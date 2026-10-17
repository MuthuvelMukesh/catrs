"""Spatial bridge mapping traffic sensors to road network edges using KD-Tree indexing."""
from __future__ import annotations

import math
from typing import Any
import numpy as np

try:
    from scipy.spatial import cKDTree
    HAS_SCIPY = True
except ImportError:
    cKDTree = None
    HAS_SCIPY = False

from app.routing.road_network import RoadGraph


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute haversine distance in meters between two lat/lon pairs."""
    r = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class SensorRoadMapper:
    """Binds traffic sensors (from ML models) to road graph segments via spatial indexing."""

    def __init__(
        self,
        sensor_locations: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        """Initialize mapper with sensor coordinates: {sensor_id: (lat, lon)}."""
        self.sensor_locations = sensor_locations or self._create_default_sensor_locations()
        self.sensor_ids: list[str] = list(self.sensor_locations.keys())
        self.sensor_coords: np.ndarray = np.array(
            [self.sensor_locations[sid] for sid in self.sensor_ids], dtype=float
        )
        self._segment_to_sensor: dict[str, str] = {}
        self._segment_distances: dict[str, float] = {}
        self._tree = cKDTree(self.sensor_coords) if HAS_SCIPY and len(self.sensor_coords) > 0 else None

    @staticmethod
    def _create_default_sensor_locations() -> dict[str, tuple[float, float]]:
        """Generate default sensor grid matching metropolitan corridor coverage."""
        sensors = {}
        # 12 primary sensor stations located along arterial intersections & expressways
        base_coords = [
            ("sensor_0", (37.780, -122.420)),
            ("sensor_1", (37.780, -122.410)),
            ("sensor_2", (37.780, -122.400)),
            ("sensor_3", (37.770, -122.420)),
            ("sensor_4", (37.770, -122.410)),
            ("sensor_5", (37.770, -122.400)),
            ("sensor_6", (37.760, -122.420)),
            ("sensor_7", (37.760, -122.410)),
            ("sensor_8", (37.760, -122.400)),
            ("sensor_hwy_w", (37.770, -122.435)),
            ("sensor_hwy_e", (37.770, -122.385)),
            ("sensor_hwy_n", (37.795, -122.410)),
        ]
        for sid, coords in base_coords:
            sensors[sid] = coords
        return sensors

    def bind_graph(self, graph: RoadGraph) -> dict[str, str]:
        """Project every road segment onto its spatially nearest sensor station."""
        self._segment_to_sensor.clear()
        self._segment_distances.clear()

        for seg_id, seg in graph.segments.items():
            from_node = graph.nodes.get(seg.from_node)
            to_node = graph.nodes.get(seg.to_node)
            if not from_node or not to_node:
                continue

            # Compute edge midpoint
            mid_lat = (from_node.lat + to_node.lat) / 2.0
            mid_lon = (from_node.lon + to_node.lon) / 2.0

            if self._tree is not None:
                dist, idx = self._tree.query([mid_lat, mid_lon], k=1)
                nearest_sid = self.sensor_ids[int(idx)]
                nearest_dist = float(dist)
            else:
                # Vectorized Euclidean fallback
                dists = np.hypot(
                    self.sensor_coords[:, 0] - mid_lat,
                    self.sensor_coords[:, 1] - mid_lon,
                )
                idx = int(np.argmin(dists))
                nearest_sid = self.sensor_ids[idx]
                nearest_dist = float(dists[idx])

            self._segment_to_sensor[seg_id] = nearest_sid
            self._segment_distances[seg_id] = nearest_dist

        return dict(self._segment_to_sensor)

    def apply_predicted_speeds(
        self,
        graph: RoadGraph,
        sensor_speeds: dict[str, float] | list[float] | np.ndarray,
    ) -> int:
        """Update road segment predicted speeds using live model sensor forecasts."""
        if not self._segment_to_sensor:
            self.bind_graph(graph)

        speed_map: dict[str, float] = {}
        if isinstance(sensor_speeds, (list, tuple, np.ndarray)):
            for i, spd in enumerate(sensor_speeds):
                sid = self.sensor_ids[i] if i < len(self.sensor_ids) else f"sensor_{i}"
                speed_map[sid] = float(spd)
        elif isinstance(sensor_speeds, dict):
            speed_map = {str(k): float(v) for k, v in sensor_speeds.items()}

        updated = 0
        for seg_id, seg in graph.segments.items():
            mapped_sensor = self._segment_to_sensor.get(seg_id)
            if mapped_sensor and mapped_sensor in speed_map:
                seg.predicted_speed_kmh = max(5.0, min(140.0, speed_map[mapped_sensor]))
                updated += 1

        return updated

    def get_segment_sensor(self, segment_id: str) -> str | None:
        """Get the mapped sensor ID for a segment."""
        return self._segment_to_sensor.get(segment_id)
