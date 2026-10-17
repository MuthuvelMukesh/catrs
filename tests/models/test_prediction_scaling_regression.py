"""Regression tests for ML pipeline inverse scaling, bounds checking, and baseline normalization."""
from __future__ import annotations

import math
import numpy as np
import pytest
import torch

from app.models.baselines import (
    HistoricalMeanModel,
    LinearRegressionModel,
    PersistenceModel,
)
from app.models.prediction_service import PredictionService
from app.models.st_gnn import STGNNPredictor
from data.preprocessing.normalize import StandardScaler
from scripts.evaluate_models import compute_metrics


def test_baseline_inverse_scaling_matches_physical_units():
    """Verify that Persistence and Historical Mean predict in true physical speed units when scaler is provided."""
    # Training speeds around 60 mph, std 10 mph
    train_speeds = np.array([50.0, 55.0, 60.0, 65.0, 70.0], dtype=np.float32)
    scaler = StandardScaler().fit(train_speeds, mask_zeros=False)

    # Input tensor [B=1, T=12, N=1, F=4]
    # speed channel 0 is normalized (e.g. z-score = 0.0 corresponds to 60.0 mph)
    X = np.zeros((1, 12, 1, 4), dtype=np.float32)
    X[0, -1, 0, 0] = scaler.transform(np.array([62.0], dtype=np.float32))[0]
    X[0, -1, 0, 3] = scaler.transform(np.array([58.0], dtype=np.float32))[0]

    pers_model = PersistenceModel(speed_channel_idx=0, scaler=scaler)
    y_pers = pers_model.predict(X)
    assert y_pers.shape == (1, 1, 3)
    # Output should be unnormalized physical speed (~62.0 mph), NOT normalized ~0.2
    assert abs(y_pers[0, 0, 0] - 62.0) < 1e-3

    hist_model = HistoricalMeanModel(baseline_channel_idx=3, scaler=scaler)
    y_hist = hist_model.predict(X)
    assert abs(y_hist[0, 0, 0] - 58.0) < 1e-3


def test_stgnn_predictor_enforces_physical_bounds():
    """Verify STGNNPredictor clamps predictions to valid range [1.0, 150.0] and rejects NaNs."""
    predictor = STGNNPredictor(feature_count=4, node_count=5)

    # Valid input
    x_valid = torch.randn(1, 12, 5, 4)
    out = predictor.predict(x_valid, node_index=0)
    assert "predicted_speed_5m" in out
    assert 1.0 <= out["predicted_speed_5m"] <= 150.0
    assert 1.0 <= out["predicted_speed_15m"] <= 150.0
    assert 1.0 <= out["predicted_speed_30m"] <= 150.0

    # Input containing NaN must raise ValueError
    x_nan = x_valid.clone()
    x_nan[0, 0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="Input tensor contains non-finite"):
        predictor.predict(x_nan)


def test_prediction_service_health_status_and_fallback():
    """Verify PredictionService reports health status and safely falls back on invalid model outputs."""
    # Fallback-only service
    svc = PredictionService(model=None, node_count=10)
    assert svc.model_health_status == "fallback"
    assert not svc.has_model

    fallback_inputs = {
        "current_speed": 45.0,
        "current_volume": 120,
        "historical_baseline_speed": 50.0,
        "weather_severity_score": 0.0,
        "active_incident_flag": False,
        "event_proximity_score": 0.0,
        "upstream_segment_congestion": 0.0,
        "time_of_day": 8,
        "day_of_week": 1,
    }
    pred = svc.predict(fallback_inputs=fallback_inputs)
    assert pred["predicted_speed_5m"] > 0.0


def test_compute_metrics_handles_near_zero_without_explosion():
    """Verify MAPE calculation handles near-zero speeds gracefully."""
    y_true = np.array([0.0, 0.05, 50.0, 60.0])
    y_pred = np.array([2.0, 2.0, 52.0, 58.0])

    metrics = compute_metrics(y_true, y_pred, mape_threshold=5.0)
    assert metrics["mae"] > 0.0
    assert metrics["rmse"] > 0.0
    assert math.isfinite(metrics["mape"])
    assert metrics["mape"] < 100.0  # Should NOT explode to thousands of percent
