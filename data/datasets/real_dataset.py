"""Reusable dataset implementation for real-world traffic sensor networks (METR-LA, PEMS-BAY)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from data.datasets.base_dataset import TrafficDataset
from data.graphs.graph_loader import load_graph_pickle
from data.preprocessing.normalize import StandardScaler
from data.preprocessing.split import temporal_split
from data.preprocessing.validation import validate_raw_dataset
from data.preprocessing.window import generate_sliding_windows

logger = logging.getLogger("catrs.datasets.real")


class RealTrafficDataset(TrafficDataset):
    """Common implementation for real sensor network datasets like METR-LA and PEMS-BAY."""

    FEATURE_NAMES = [
        "traffic_speed",
        "time_of_day",
        "day_of_week",
        "historical_baseline",
    ]

    def __init__(
        self,
        name: str,
        csv_filename: str,
        pkl_filename: str,
        data_dir: str | Path | None = None,
    ) -> None:
        if data_dir is None:
            # Default to root/data
            data_dir = Path(__file__).parent.parent.resolve()
        super().__init__(name=name, data_dir=data_dir)

        self.csv_path = self.data_dir / "raw" / csv_filename
        self.pkl_path = self.data_dir / "raw" / pkl_filename
        self.processed_dir = self.data_dir / "processed"
        self.processed_path = self.processed_dir / f"{name.lower()}_processed.npz"
        self.scaler_path = self.processed_dir / f"{name.lower()}_scaler.json"

        self._sensor_ids: list[str] | None = None
        self._adj_mx: np.ndarray | None = None
        self._num_nodes: int = 0

    @property
    def num_nodes(self) -> int:
        if self._num_nodes == 0:
            self._load_graph_metadata()
        return self._num_nodes

    @property
    def feature_count(self) -> int:
        return len(self.FEATURE_NAMES)

    def _load_graph_metadata(self) -> None:
        sensor_ids, _, adj_mx = load_graph_pickle(self.pkl_path)
        self._sensor_ids = sensor_ids
        self._adj_mx = adj_mx
        self._num_nodes = len(sensor_ids)

    def get_graph(self) -> tuple[list[str], np.ndarray]:
        if self._sensor_ids is None or self._adj_mx is None:
            self._load_graph_metadata()
        return self._sensor_ids, self._adj_mx  # type: ignore

    def validate(self) -> dict[str, Any]:
        """Validate raw CSV and graph structure."""
        return validate_raw_dataset(self.csv_path, self.pkl_path)

    def load_or_process(
        self,
        lookback: int = 12,
        horizon_offsets: tuple[int, ...] = (0, 2, 5),
        train_ratio: float = 0.7,
        val_ratio: float = 0.1,
        test_ratio: float = 0.2,
        force_reprocess: bool = False,
    ) -> dict[str, Any]:
        """Load from processed cache or execute preprocessing pipeline."""
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        if not force_reprocess and self.processed_path.exists() and self.scaler_path.exists():
            logger.info("Loading cached processed dataset from %s", self.processed_path)
            cached = np.load(self.processed_path, allow_pickle=True)
            scaler = StandardScaler.load(self.scaler_path)
            sensor_ids, adj_mx = self.get_graph()

            return {
                "X_train": cached["X_train"],
                "Y_train": cached["Y_train"],
                "X_val": cached["X_val"],
                "Y_val": cached["Y_val"],
                "X_test": cached["X_test"],
                "Y_test": cached["Y_test"],
                "scaler": scaler,
                "sensor_ids": sensor_ids,
                "adj_mx": adj_mx,
                "feature_names": self.FEATURE_NAMES,
            }

        logger.info("Preprocessing raw dataset for %s...", self.name)
        # 1. Validate raw data
        self.validate()
        sensor_ids, adj_mx = self.get_graph()

        # 2. Read CSV and sort chronologically
        df = pd.read_csv(self.csv_path)
        timestamp_col = df.columns[0]
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        df = df.sort_values(timestamp_col).reset_index(drop=True)

        timestamps = df[timestamp_col]
        raw_speeds = df[sensor_ids].values.astype(np.float32)  # [T, N]
        T, N = raw_speeds.shape

        # 3. Compute temporal signals
        # time_of_day in [0, 1)
        tod = (timestamps.dt.hour * 60 + timestamps.dt.minute).values / 1440.0  # [T]
        tod_grid = np.tile(tod[:, np.newaxis, np.newaxis], (1, N, 1)).astype(np.float32)  # [T, N, 1]

        # day_of_week in [0, 1]
        dow = (timestamps.dt.dayofweek).values / 6.0  # [T]
        dow_grid = np.tile(dow[:, np.newaxis, np.newaxis], (1, N, 1)).astype(np.float32)  # [T, N, 1]

        # 4. Temporal split
        train_len = int(T * train_ratio)
        val_len = int(T * val_ratio)

        # 5. Compute historical baseline using TRAINING SET ONLY (zero leakage!)
        # Key: (dayofweek, hour, minute) -> mean speed per sensor
        train_df = df.iloc[:train_len]
        grouped = train_df.groupby([train_df[timestamp_col].dt.dayofweek, train_df[timestamp_col].dt.hour, train_df[timestamp_col].dt.minute])
        # Replace 0 values (sensor outages) with NaN for mean baseline calculation
        train_speeds_clean = train_df[sensor_ids].replace(0, np.nan)
        baseline_lookup = train_speeds_clean.groupby([train_df[timestamp_col].dt.dayofweek, train_df[timestamp_col].dt.hour, train_df[timestamp_col].dt.minute]).mean()
        overall_mean = train_speeds_clean.mean().values  # fallback if time slot missing

        # Broadcast historical baseline for entire series
        baseline_matrix = np.zeros((T, N), dtype=np.float32)
        time_tuples = list(zip(timestamps.dt.dayofweek, timestamps.dt.hour, timestamps.dt.minute))
        for i, t_tuple in enumerate(time_tuples):
            if t_tuple in baseline_lookup.index:
                val = baseline_lookup.loc[t_tuple].values
                # Replace any NaN in slot with overall mean
                val = np.where(np.isnan(val), overall_mean, val)
                baseline_matrix[i] = val
            else:
                baseline_matrix[i] = overall_mean

        baseline_grid = baseline_matrix[:, :, np.newaxis]  # [T, N, 1]

        # Assemble raw features: [T, N, 4]
        # Channel 0: speed, Channel 1: tod, Channel 2: dow, Channel 3: baseline
        raw_features = np.concatenate(
            [raw_speeds[:, :, np.newaxis], tod_grid, dow_grid, baseline_grid],
            axis=-1,
        )  # [T, N, 4]

        # 6. Chronological split of feature array
        train_feat, val_feat, test_feat = temporal_split(
            raw_features, train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=test_ratio
        )

        # 7. Normalization: Fit scaler on TRAIN ONLY (channel 0: speed)
        scaler = StandardScaler()
        scaler.fit(train_feat[:, :, 0], mask_zeros=True)

        # Standardize speed (channel 0) and baseline (channel 3)
        train_feat_norm = np.copy(train_feat)
        val_feat_norm = np.copy(val_feat)
        test_feat_norm = np.copy(test_feat)

        for feat_arr in (train_feat_norm, val_feat_norm, test_feat_norm):
            feat_arr[:, :, 0] = scaler.transform(feat_arr[:, :, 0])
            feat_arr[:, :, 3] = scaler.transform(feat_arr[:, :, 3])

        # 8. Sliding-window sequence creation
        # Y targets are in UNNORMALIZED ORIGINAL SPEED UNITS (for clean metric calculation)
        X_train, Y_train = generate_sliding_windows(
            train_feat_norm, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets
        )
        # For targets, get ground truth unnormalized speeds:
        _, Y_train_orig = generate_sliding_windows(
            train_feat, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets
        )
        X_val, _ = generate_sliding_windows(
            val_feat_norm, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets
        )
        _, Y_val_orig = generate_sliding_windows(
            val_feat, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets
        )
        X_test, _ = generate_sliding_windows(
            test_feat_norm, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets
        )
        _, Y_test_orig = generate_sliding_windows(
            test_feat, target_channel=0, lookback=lookback, horizon_offsets=horizon_offsets
        )

        # 9. Cache processed data
        logger.info("Saving processed dataset cache to %s...", self.processed_path)
        np.savez(
            self.processed_path,
            X_train=X_train,
            Y_train=Y_train_orig,
            X_val=X_val,
            Y_val=Y_val_orig,
            X_test=X_test,
            Y_test=Y_test_orig,
        )
        scaler.save(self.scaler_path)

        return {
            "X_train": X_train,
            "Y_train": Y_train_orig,
            "X_val": X_val,
            "Y_val": Y_val_orig,
            "X_test": X_test,
            "Y_test": Y_test_orig,
            "scaler": scaler,
            "sensor_ids": sensor_ids,
            "adj_mx": adj_mx,
            "feature_names": self.FEATURE_NAMES,
        }

    def get_metadata(self) -> dict[str, Any]:
        sensor_ids, adj_mx = self.get_graph()
        return {
            "dataset": self.name,
            "num_nodes": len(sensor_ids),
            "features": self.FEATURE_NAMES,
            "feature_count": len(self.FEATURE_NAMES),
            "csv_path": str(self.csv_path),
            "pkl_path": str(self.pkl_path),
            "graph_shape": list(adj_mx.shape),
        }
