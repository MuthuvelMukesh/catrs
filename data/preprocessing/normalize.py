"""Normalization utilities for traffic data ensuring zero train/test leakage."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np


class StandardScaler:
    """Standardize features by removing the mean and scaling to unit variance.

    Fitted strictly on training data to prevent temporal lookahead leakage.
    Supports 2D [T, N], 3D [B, N, F], or 4D [B, T, N, F] tensors.
    """

    def __init__(self, mean: float | np.ndarray | None = None, std: float | np.ndarray | None = None) -> None:
        self.mean = mean
        self.std = std

    def fit(self, data: np.ndarray, mask_zeros: bool = True) -> StandardScaler:
        """Fit scaler parameters on training data.

        Args:
            data: Training traffic data array.
            mask_zeros: If True, zero values (missing sensor readings in METR-LA)
                        are excluded from mean/std computation.
        """
        if mask_zeros:
            valid_mask = data > 0
            if np.any(valid_mask):
                self.mean = float(np.mean(data[valid_mask]))
                self.std = float(np.std(data[valid_mask]))
            else:
                self.mean = float(np.mean(data))
                self.std = float(np.std(data))
        else:
            self.mean = float(np.mean(data))
            self.std = float(np.std(data))

        if abs(self.std) < 1e-6:
            self.std = 1.0

        return self

    def transform(self, data: np.ndarray) -> np.ndarray:
        """Standardize data using previously fitted training mean and std."""
        if self.mean is None or self.std is None:
            raise RuntimeError("StandardScaler must be fitted before transform")
        return (data - self.mean) / self.std

    def inverse_transform(self, data: np.ndarray) -> np.ndarray:
        """Transform standardized data back to original traffic speed scale."""
        if self.mean is None or self.std is None:
            raise RuntimeError("StandardScaler must be fitted before inverse_transform")
        return (data * self.std) + self.mean

    def to_dict(self) -> dict[str, float]:
        """Serialize parameters for model checkpoint metadata."""
        return {
            "mean": float(self.mean) if self.mean is not None else 0.0,
            "std": float(self.std) if self.std is not None else 1.0,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StandardScaler:
        """Reconstruct scaler from dictionary."""
        return cls(mean=float(data.get("mean", 0.0)), std=float(data.get("std", 1.0)))

    def save(self, filepath: str | Path) -> None:
        """Save scaler parameters as JSON."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str | Path) -> StandardScaler:
        """Load scaler parameters from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
