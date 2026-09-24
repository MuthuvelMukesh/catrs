"""Abstract base class and contract for all CATRS traffic datasets."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import numpy as np
import torch


class TrafficDataset(ABC):
    """Abstract interface defining operations for traffic datasets."""

    def __init__(self, name: str, data_dir: str | Path) -> None:
        self.name = name
        self.data_dir = Path(data_dir)

    @property
    @abstractmethod
    def num_nodes(self) -> int:
        """Total number of nodes (sensors) in the road network."""
        pass

    @property
    @abstractmethod
    def feature_count(self) -> int:
        """Number of feature dimensions per node per timestep."""
        pass

    @abstractmethod
    def get_graph(self) -> tuple[list[str], np.ndarray]:
        """Load and return sensor IDs and raw adjacency matrix."""
        pass

    @abstractmethod
    def load_or_process(
        self,
        lookback: int = 12,
        horizon_offsets: tuple[int, ...] = (0, 2, 5),
        train_ratio: float = 0.7,
        val_ratio: float = 0.1,
        test_ratio: float = 0.2,
        force_reprocess: bool = False,
    ) -> dict[str, Any]:
        """Load processed sequence arrays or run preprocessing pipeline.

        Returns dictionary with keys:
            X_train: [B_train, lookback, N, F]
            Y_train: [B_train, N, 3] (horizons: 5m, 15m, 30m)
            X_val:   [B_val, lookback, N, F]
            Y_val:   [B_val, N, 3]
            X_test:  [B_test, lookback, N, F]
            Y_test:  [B_test, N, 3]
            scaler:  StandardScaler instance fit on training data
            sensor_ids: list[str]
            adj_mx:  np.ndarray [N, N]
            feature_names: list[str]
        """
        pass

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return dataset metadata summary."""
        pass
