from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
import torch

from app.models.prediction_service import PredictionService
from app.models.st_gnn import STGNNPredictor


def test_st_gnn_checkpoint_save_and_load(tmp_path):
    """Verify that an ST-GNN model state dict can be saved and loaded."""
    checkpoint_file = str(tmp_path / "model.pt")

    # Create predictor and save weights
    predictor = STGNNPredictor(feature_count=9, node_count=10, hidden_size=16)
    torch.save(predictor._model.state_dict(), checkpoint_file)
    assert os.path.exists(checkpoint_file)

    # Load via PredictionService.from_config
    config = SimpleNamespace(
        stgnn_enabled=True,
        stgnn_feature_count=9,
        stgnn_node_count=10,
        stgnn_hidden_size=16,
        stgnn_checkpoint_path=checkpoint_file,
    )
    svc = PredictionService.from_config(config)
    assert svc.has_model is True

    # Test prediction through service
    dummy_input = torch.randn(1, 12, 10, 9)
    result = svc.predict(
        model_input=dummy_input,
        fallback_inputs={
            "current_speed": 45.0,
            "current_volume": 80,
            "historical_baseline_speed": 55.0,
        },
    )
    assert "predicted_speed_5m" in result
    assert "predicted_speed_15m" in result
    assert "predicted_speed_30m" in result
    assert all(isinstance(v, float) for v in result.values())


def test_prediction_service_handles_missing_checkpoint_gracefully(tmp_path):
    """When checkpoint path does not exist, service gracefully falls back."""
    config = SimpleNamespace(
        stgnn_enabled=True,
        stgnn_feature_count=9,
        stgnn_node_count=10,
        stgnn_hidden_size=16,
        stgnn_checkpoint_path=str(tmp_path / "non_existent.pt"),
    )
    svc = PredictionService.from_config(config)
    assert svc.has_model is False
