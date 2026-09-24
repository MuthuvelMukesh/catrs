"""Unified traffic datasets module for CATRS."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from data.datasets.base_dataset import TrafficDataset
from data.datasets.metr_la_dataset import MetrLaDataset
from data.datasets.pems_bay_dataset import PemsBayDataset
from data.datasets.synthetic_dataset import SyntheticTrafficDataset


class DatasetMode(str, Enum):
    """Supported traffic dataset modes."""

    SYNTHETIC = "synthetic"
    METR_LA = "metr_la"
    PEMS_BAY = "pems_bay"


def get_dataset(
    mode: str | DatasetMode = DatasetMode.SYNTHETIC,
    data_dir: str | Path | None = None,
    **kwargs: Any,
) -> TrafficDataset:
    """Factory creating the appropriate TrafficDataset instance.

    Args:
        mode: Dataset mode ('synthetic', 'metr_la', 'pems_bay').
        data_dir: Optional root data directory.
        **kwargs: Additional dataset options (e.g. scenario, seed, grid_size).

    Returns:
        TrafficDataset instance.
    """
    if isinstance(mode, str):
        mode_str = mode.lower().replace("-", "_")
        try:
            mode = DatasetMode(mode_str)
        except ValueError:
            raise ValueError(
                f"Unknown dataset mode '{mode}'. Supported modes: {[m.value for m in DatasetMode]}"
            )

    if mode == DatasetMode.METR_LA:
        return MetrLaDataset(data_dir=data_dir)
    elif mode == DatasetMode.PEMS_BAY:
        return PemsBayDataset(data_dir=data_dir)
    elif mode == DatasetMode.SYNTHETIC:
        return SyntheticTrafficDataset(data_dir=data_dir, **kwargs)
    else:
        raise ValueError(f"Unhandled dataset mode: {mode}")


__all__ = [
    "TrafficDataset",
    "DatasetMode",
    "get_dataset",
    "MetrLaDataset",
    "PemsBayDataset",
    "SyntheticTrafficDataset",
]
