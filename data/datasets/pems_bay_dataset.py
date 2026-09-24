"""PEMS-BAY California Bay Area traffic speed dataset implementation."""
from __future__ import annotations

from pathlib import Path
from data.datasets.real_dataset import RealTrafficDataset


class PemsBayDataset(RealTrafficDataset):
    """PEMS-BAY benchmark traffic dataset (~325 sensors, 5-min intervals)."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        super().__init__(
            name="PEMS_BAY",
            csv_filename="PEMS-BAY.csv",
            pkl_filename="adj_mx_PEMS-BAY.pkl",
            data_dir=data_dir,
        )
