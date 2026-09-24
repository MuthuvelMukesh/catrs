"""Temporal dataset splitting routines ensuring chronological order."""
from __future__ import annotations

from typing import TypeVar
import numpy as np

T = TypeVar("T", np.ndarray, list)


def temporal_split(
    data: np.ndarray,
    train_ratio: float = 0.7,
    val_ratio: float = 0.1,
    test_ratio: float = 0.2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split time-series data chronologically into train, validation, and test subsets.

    Guarantees no temporal leakage (shuffling is strictly prohibited).
    """
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-5:
        raise ValueError(f"Ratios must sum to 1.0, got {total}")

    n_samples = len(data)
    train_end = int(n_samples * train_ratio)
    val_end = int(n_samples * (train_ratio + val_ratio))

    train_data = data[:train_end]
    val_data = data[train_end:val_end]
    test_data = data[val_end:]

    return train_data, val_data, test_data
