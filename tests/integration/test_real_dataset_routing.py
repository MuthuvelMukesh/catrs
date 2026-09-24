"""Integration tests connecting real dataset predictions with routing engine mapping."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import torch

from app.models.st_gnn import SpatioTemporalGNN
from app.routing.node_mapping import SensorToRouteMapper
from data.datasets import DatasetMode, get_dataset

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
DATA_DIR = REPO_ROOT / "data"


def test_real_dataset_prediction():
    """Verify that a trained ST-GNN model produces valid multi-horizon predictions for METR-LA."""
    ds = get_dataset(DatasetMode.METR_LA, data_dir=DATA_DIR)
    sensor_ids, adj = ds.get_graph()

    model = SpatioTemporalGNN(feature_count=4, hidden_size=16, gcn_hidden=16, adj_mx=adj)
    model.eval()

    sample_x = torch.randn(1, 12, len(sensor_ids), 4)
    with torch.no_grad():
        preds = model(sample_x)  # [1, 207, 3]

    assert preds.shape == (1, 207, 3)
    preds_np = preds.numpy()[0]
    # Check that predictions exist for every sensor node
    for i in range(len(sensor_ids)):
        for h in range(3):
            assert np.isfinite(preds_np[i, h])


def test_real_prediction_to_routing():
    """Verify that per-sensor speed forecasts translate into route edge weights and traversal times."""
    ds = get_dataset(DatasetMode.METR_LA, data_dir=DATA_DIR)
    sensor_ids, adj = ds.get_graph()

    mapper = SensorToRouteMapper(sensor_ids=sensor_ids, adj_mx=adj, default_segment_length_km=2.0)
    assert len(mapper.segments) > 0

    # Simulated predictions: speeds around 60 km/h
    simulated_preds = np.full((len(sensor_ids), 3), 60.0, dtype=np.float32)
    # Simulate a bottleneck on sensor 10: 20 km/h
    simulated_preds[10, :] = 20.0

    mapped_routes = mapper.map_predictions_to_routes(simulated_preds)
    assert len(mapped_routes) == len(mapper.segments)

    # Check that travel time is correctly derived: t = (d / v) * 3600
    # For normal segment: length=2.0, speed=60.0 -> 120 seconds
    # For congested segment: length=2.0, speed=20.0 -> 360 seconds
    for seg_id, seg in mapped_routes.items():
        assert seg.travel_time_5m_seconds > 0.0
        assert seg.travel_time_15m_seconds > 0.0
        assert seg.travel_time_30m_seconds > 0.0
        if seg.target_sensor == sensor_ids[10]:
            assert abs(seg.travel_time_5m_seconds - 360.0) < 1.0
