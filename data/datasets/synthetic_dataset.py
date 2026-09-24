"""Synthetic grid traffic dataset implementation wrapping DeterministicSyntheticWorld."""
from __future__ import annotations

import math
from pathlib import Path
import sys
from typing import Any
import numpy as np

# Ensure routing engine is in sys.path to import synthetic_world
ROOT_DIR = Path(__file__).parent.parent.parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
if ROUTING_DIR not in sys.path:
    sys.path.insert(0, ROUTING_DIR)

from app.data.synthetic_world import DeterministicSyntheticWorld, TrafficScenario, generate_grid_graph
from data.datasets.base_dataset import TrafficDataset
from data.preprocessing.normalize import StandardScaler
from data.preprocessing.split import temporal_split
from data.preprocessing.window import generate_sliding_windows


class SyntheticTrafficDataset(TrafficDataset):
    """10x10 Planar Grid synthetic world dataset with 9 distinct scenarios."""

    FEATURE_NAMES = [
        "current_speed",
        "current_volume",
        "historical_baseline_speed",
        "weather_severity_score",
        "active_incident_flag",
        "event_proximity_score",
        "upstream_segment_congestion",
        "sin_hour",
        "cos_hour",
    ]

    def __init__(
        self,
        grid_size: int = 10,
        scenario: str | TrafficScenario = TrafficScenario.NORMAL,
        seed: int = 42,
        data_dir: str | Path | None = None,
    ) -> None:
        if data_dir is None:
            data_dir = ROOT_DIR / "data"
        super().__init__(name="SYNTHETIC", data_dir=data_dir)
        self.grid_size = grid_size
        self._num_nodes = grid_size * grid_size
        if isinstance(scenario, str):
            val = scenario.lower()
            if val == "baseline":
                val = "normal"
            try:
                scenario = TrafficScenario(val)
            except Exception:
                scenario = TrafficScenario.NORMAL
        self.scenario = scenario
        self.seed = seed
        self.world = DeterministicSyntheticWorld(scenario=self.scenario, seed=seed)

        # Graph nodes
        graph = generate_grid_graph(rows=grid_size, cols=grid_size)
        all_segments = [e["segment_id"] for e in graph["edges"]][:self._num_nodes]
        actual_nodes = len(all_segments)
        while len(all_segments) < self._num_nodes:
            all_segments.append(all_segments[len(all_segments) % actual_nodes])
        self._sensor_ids = all_segments
        self._adj_mx = self._build_grid_adjacency()

    @property
    def num_nodes(self) -> int:
        return self._num_nodes

    @property
    def feature_count(self) -> int:
        return len(self.FEATURE_NAMES)

    def _build_grid_adjacency(self) -> np.ndarray:
        """Construct planar grid bidirectional adjacency matrix."""
        N = self._num_nodes
        adj = np.eye(N, dtype=np.float32)  # self-loops
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                idx = r * self.grid_size + c
                if c + 1 < self.grid_size:
                    adj[idx, idx + 1] = 1.0
                    adj[idx + 1, idx] = 1.0
                if r + 1 < self.grid_size:
                    adj[idx, idx + self.grid_size] = 1.0
                    adj[idx + self.grid_size, idx] = 1.0
        return adj

    def get_graph(self) -> tuple[list[str], np.ndarray]:
        return self._sensor_ids, self._adj_mx

    def generate_raw_series(self, days: int = 7, interval_minutes: int = 5) -> np.ndarray:
        """Generate time-series feature matrix of shape [T, N, 9]."""
        from app.models.pipeline import build_feature_vector

        world = DeterministicSyntheticWorld(scenario=self.scenario, seed=self.seed, days=days, interval_minutes=interval_minutes)
        rows = world.generate_readings()
        baseline = world.generate_baseline()

        by_time: dict[Any, dict[str, Any]] = {}
        for r in rows:
            by_time.setdefault(r["timestamp"], {})[r["segment_id"]] = r

        sorted_times = sorted(by_time.keys())
        T = len(sorted_times)
        N = self._num_nodes
        F = self.feature_count
        series = np.zeros((T, N, F), dtype=np.float32)

        for step, t in enumerate(sorted_times):
            time_dict = by_time[t]
            for node_idx, seg in enumerate(self._sensor_ids):
                reading = time_dict.get(seg)
                avg_speed = reading["avg_speed"] if reading else 50.0
                vol = reading["vehicle_count"] if reading else 40
                bl = baseline.get((seg, t.weekday(), t.hour), avg_speed)

                vec = build_feature_vector(
                    current_speed=avg_speed,
                    current_volume=vol,
                    historical_baseline_speed=bl,
                    weather_severity_score=0.0,
                    active_incident_flag=False,
                    event_proximity_score=0.0,
                    upstream_segment_congestion=0.0,
                    time_of_day=t.hour,
                    day_of_week=t.weekday(),
                )
                series[step, node_idx] = [
                    float(vec["current_speed"]),
                    float(vec["current_volume"]),
                    float(vec["historical_baseline_speed"]),
                    float(vec["weather_severity_score"]),
                    1.0 if vec["active_incident_flag"] else 0.0,
                    float(vec["event_proximity_score"]),
                    float(vec["upstream_segment_congestion"]),
                    float(vec["time_of_day_sin"]),
                    float(vec["time_of_day_cos"]),
                ]

        return series

    def load_or_process(
        self,
        lookback: int = 12,
        horizon_offsets: tuple[int, ...] = (0, 2, 5),
        train_ratio: float = 0.7,
        val_ratio: float = 0.1,
        test_ratio: float = 0.2,
        force_reprocess: bool = False,
        days: int = 7,
    ) -> dict[str, Any]:
        """Generate synthetic sequences and multi-horizon target speeds."""
        raw_series = self.generate_raw_series(days=days)

        train_feat, val_feat, test_feat = temporal_split(
            raw_series, train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=test_ratio
        )

        scaler = StandardScaler()
        scaler.fit(train_feat[:, :, 0], mask_zeros=False)

        # Standardize speed channel
        train_norm = np.copy(train_feat)
        val_norm = np.copy(val_feat)
        test_norm = np.copy(test_feat)

        for arr in (train_norm, val_norm, test_norm):
            arr[:, :, 0] = scaler.transform(arr[:, :, 0])
            arr[:, :, 2] = scaler.transform(arr[:, :, 2])  # baseline

        X_train, _ = generate_sliding_windows(train_norm, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets)
        _, Y_train = generate_sliding_windows(train_feat, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets)

        X_val, _ = generate_sliding_windows(val_norm, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets)
        _, Y_val = generate_sliding_windows(val_feat, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets)

        X_test, _ = generate_sliding_windows(test_norm, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets)
        _, Y_test = generate_sliding_windows(test_feat, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets)

        return {
            "X_train": X_train,
            "Y_train": Y_train,
            "X_val": X_val,
            "Y_val": Y_val,
            "X_test": X_test,
            "Y_test": Y_test,
            "scaler": scaler,
            "sensor_ids": self._sensor_ids,
            "adj_mx": self._adj_mx,
            "feature_names": self.FEATURE_NAMES,
        }

    def get_metadata(self) -> dict[str, Any]:
        return {
            "dataset": "SYNTHETIC",
            "grid_size": self.grid_size,
            "num_nodes": self._num_nodes,
            "features": self.FEATURE_NAMES,
            "scenario": self.scenario.value if hasattr(self.scenario, "value") else str(self.scenario),
            "seed": self.seed,
            "graph_shape": list(self._adj_mx.shape),
        }


def pd_timedelta(minutes: int):
    from datetime import timedelta
    return timedelta(minutes=minutes)
