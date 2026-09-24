"""Sliding-window sequence generation for multi-horizon spatio-temporal forecasting."""
from __future__ import annotations

import numpy as np


def generate_sliding_windows(
    features: np.ndarray,
    target_channel: int = 0,
    lookback: int = 12,
    horizon_offsets: list[int] | tuple[int, ...] = (0, 2, 5),
) -> tuple[np.ndarray, np.ndarray]:
    """Generate historical lookback sequences and multi-horizon target speeds.

    Args:
        features: Array of shape [T, N, F] (timesteps, nodes, features).
                  If shape is [T, N], it will be reshaped to [T, N, 1].
        target_channel: Feature index containing the ground truth speed (usually 0).
        lookback: Number of past timesteps (default 12 = 60 minutes @ 5-min intervals).
        horizon_offsets: Offsets for future prediction targets relative to sequence end:
                         0 = +5 min (next step)
                         2 = +15 min (3 steps ahead)
                         5 = +30 min (6 steps ahead)

    Returns:
        X: Sequence tensor of shape [B, lookback, N, F].
        Y: Multi-horizon target speeds of shape [B, N, len(horizon_offsets)].
    """
    if features.ndim == 2:
        features = features[:, :, np.newaxis]

    T, N, F = features.shape
    max_offset = max(horizon_offsets)
    num_samples = T - lookback - max_offset

    if num_samples <= 0:
        raise ValueError(
            f"Not enough timesteps ({T}) for lookback={lookback} and max_offset={max_offset}"
        )

    X_list = []
    Y_list = []

    for t in range(lookback, T - max_offset):
        # Lookback window [t - lookback, ..., t - 1]
        x_window = features[t - lookback : t]  # [lookback, N, F]

        # Multi-horizon targets at future steps
        y_horizons = [features[t + offset, :, target_channel] for offset in horizon_offsets]  # list of [N]
        y_target = np.stack(y_horizons, axis=-1)  # [N, 3]

        X_list.append(x_window)
        Y_list.append(y_target)

    X = np.ascontiguousarray(np.array(X_list, dtype=np.float32))
    Y = np.ascontiguousarray(np.array(Y_list, dtype=np.float32))

    return X, Y
