"""METR-LA Los Angeles County traffic speed dataset implementation."""
from __future__ import annotations

from pathlib import Path
from data.datasets.real_dataset import RealTrafficDataset


class MetrLaDataset(RealTrafficDataset):
    """METR-LA benchmark traffic dataset (~207 sensors, 5-min intervals)."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        super().__init__(
            name="METR_LA",
            csv_filename="METR-LA.csv",
            pkl_filename="adj_mx_METR-LA.pkl",
            data_dir=data_dir,
        )
