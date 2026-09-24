"""Unit tests for preprocessing, sliding windows, and zero-leakage normalization."""
from __future__ import annotations

import numpy as np
import pytest

from data.preprocessing.normalize import StandardScaler
from data.preprocessing.split import temporal_split
from data.preprocessing.window import generate_sliding_windows


def test_temporal_window():
    """Verify temporal sliding window dimensions [B, T=12, N, F] and targets [B, N, 3]."""
    T, N, F = 50, 10, 4
    # Dummy data where speed at timestep t equals t
    data = np.zeros((T, N, F), dtype=np.float32)
    for t in range(T):
        data[t, :, 0] = float(t)

    lookback = 12
    horizon_offsets = (0, 2, 5)  # +5m (+1 step), +15m (+3 steps), +30m (+6 steps)
    X, Y = generate_sliding_windows(
        data,
        target_channel=0,
        lookback=lookback,
        horizon_offsets=horizon_offsets,
    )

    max_offset = max(horizon_offsets)
    expected_samples = T - lookback - max_offset
    assert X.shape == (expected_samples, lookback, N, F)
    assert Y.shape == (expected_samples, N, 3)

    # Verify lookback indexing
    # For first sample (t = 12): lookback is steps 0..11, targets are steps 12, 14, 17
    assert np.allclose(X[0, -1, :, 0], 11.0)
    assert np.allclose(Y[0, :, 0], 12.0)
    assert np.allclose(Y[0, :, 1], 14.0)
    assert np.allclose(Y[0, :, 2], 17.0)


def test_normalization_no_leakage():
    """Verify that scaler parameters are computed strictly on training data without test leakage."""
    np.random.seed(42)
    train_data = np.random.normal(loc=50.0, scale=10.0, size=(100, 20)).astype(np.float32)
    test_data = np.random.normal(loc=70.0, scale=15.0, size=(50, 20)).astype(np.float32)

    scaler = StandardScaler()
    scaler.fit(train_data, mask_zeros=False)

    # Train mean should match train_data statistics
    assert abs(scaler.mean - float(np.mean(train_data))) < 1e-4
    assert abs(scaler.std - float(np.std(train_data))) < 1e-4

    # Standardize train and test
    norm_train = scaler.transform(train_data)
    norm_test = scaler.transform(test_data)

    # norm_train has mean ~0, std ~1
    assert abs(float(np.mean(norm_train))) < 0.05
    assert abs(float(np.std(norm_train)) - 1.0) < 0.05

    # Inverse transform recovers original data exactly
    recovered_train = scaler.inverse_transform(norm_train)
    assert np.allclose(recovered_train, train_data, atol=1e-5)

    recovered_test = scaler.inverse_transform(norm_test)
    assert np.allclose(recovered_test, test_data, atol=1e-5)


def test_train_val_test_split():
    """Verify strictly chronological temporal splitting into 70/10/20 fractions."""
    T = 100
    data = np.arange(T)[:, np.newaxis, np.newaxis]  # shape [100, 1, 1]
    train, val, test = temporal_split(data, train_ratio=0.7, val_ratio=0.1, test_ratio=0.2)

    assert len(train) == 70
    assert len(val) == 10
    assert len(test) == 20

    # Ensure strictly chronological ordering (no future leakage)
    assert train[-1, 0, 0] < val[0, 0, 0]
    assert val[-1, 0, 0] < test[0, 0, 0]


def test_missing_values():
    """Verify that zero values (sensor outages) are masked from baseline and normalization."""
    # Data with 20% zeros
    data = np.array([0.0, 0.0, 50.0, 60.0, 70.0], dtype=np.float32)
    scaler = StandardScaler()
    scaler.fit(data, mask_zeros=True)

    # Mean should be of non-zero values (50, 60, 70) = 60.0
    assert abs(scaler.mean - 60.0) < 1e-5
    # Std of (50, 60, 70) with N=3 is sqrt(200/3) = 8.16496
    expected_std = float(np.std([50.0, 60.0, 70.0]))
    assert abs(scaler.std - expected_std) < 1e-4
