"""Unit tests for METR-LA, PEMS-BAY, and Graph loaders."""
from __future__ import annotations

import os
from pathlib import Path
import pytest
import numpy as np

from data.datasets import DatasetMode, get_dataset
from data.datasets.metr_la_dataset import MetrLaDataset
from data.datasets.pems_bay_dataset import PemsBayDataset
from data.graphs.graph_loader import load_graph_pickle, GraphLoadError
from data.preprocessing.validation import validate_raw_dataset, DatasetValidationError

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
DATA_DIR = REPO_ROOT / "data"


def test_graph_loader():
    """Verify loading graph adjacency pickles for METR-LA and PEMS-BAY."""
    metr_pkl = DATA_DIR / "raw" / "adj_mx_METR-LA.pkl"
    if metr_pkl.exists():
        sensor_ids, id_map, adj = load_graph_pickle(metr_pkl)
        assert len(sensor_ids) == 207
        assert len(id_map) == 207
        assert adj.shape == (207, 207)
        assert np.all(adj >= 0.0)

    pems_pkl = DATA_DIR / "raw" / "adj_mx_PEMS-BAY.pkl"
    if pems_pkl.exists():
        sensor_ids, id_map, adj = load_graph_pickle(pems_pkl)
        assert len(sensor_ids) == 325
        assert len(id_map) == 325
        assert adj.shape == (325, 325)
        assert np.all(adj >= 0.0)


def test_sensor_graph_alignment():
    """Verify that sensor IDs in the adjacency pickle match the CSV columns in order."""
    metr_csv = DATA_DIR / "raw" / "METR-LA.csv"
    metr_pkl = DATA_DIR / "raw" / "adj_mx_METR-LA.pkl"
    if metr_csv.exists() and metr_pkl.exists():
        sensor_ids, _, adj = load_graph_pickle(metr_pkl)
        # Read header only
        import pandas as pd
        df_head = pd.read_csv(metr_csv, nrows=1)
        csv_cols = [c for c in df_head.columns if c not in ("datetime", "timestamp", "Unnamed: 0")]
        assert len(csv_cols) == len(sensor_ids) == 207
        assert csv_cols == sensor_ids


def test_metr_la_loader():
    """Verify MetrLaDataset instantiation, metadata, and graph loading."""
    ds = get_dataset(DatasetMode.METR_LA, data_dir=DATA_DIR)
    assert isinstance(ds, MetrLaDataset)
    assert ds.name == "METR_LA"
    assert ds.num_nodes == 207
    assert ds.feature_count == 4

    sensor_ids, adj = ds.get_graph()
    assert len(sensor_ids) == 207
    assert adj.shape == (207, 207)


def test_pems_bay_loader():
    """Verify PemsBayDataset instantiation, metadata, and graph loading."""
    ds = get_dataset(DatasetMode.PEMS_BAY, data_dir=DATA_DIR)
    assert isinstance(ds, PemsBayDataset)
    assert ds.name == "PEMS_BAY"
    assert ds.num_nodes == 325
    assert ds.feature_count == 4

    sensor_ids, adj = ds.get_graph()
    assert len(sensor_ids) == 325
    assert adj.shape == (325, 325)


def test_dataset_validation(tmp_path):
    """Verify that malformed data raises clear DatasetValidationError without silent repair."""
    # Test missing file error
    with pytest.raises(DatasetValidationError, match="CSV file does not exist"):
        validate_raw_dataset(
            csv_path=tmp_path / "non_existent.csv",
            pkl_path=tmp_path / "non_existent.pkl",
        )

    # Test dimension mismatch error
    corrupted_csv = tmp_path / "dummy.csv"
    corrupted_csv.write_text("timestamp,s1,s2\n2026-01-01 00:00:00,50,60\n")
    corrupted_pkl = tmp_path / "dummy.pkl"
    import pickle
    with open(corrupted_pkl, "wb") as f:
        # 3 sensors in graph but 2 in CSV
        pickle.dump((["s1", "s2", "s3"], {"s1": 0, "s2": 1, "s3": 2}, np.eye(3)), f)

    with pytest.raises(DatasetValidationError, match="Sensor/graph dimension mismatch"):
        validate_raw_dataset(csv_path=corrupted_csv, pkl_path=corrupted_pkl)
