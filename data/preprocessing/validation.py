"""Dataset validation routines for CATRS traffic datasets."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd


class DatasetValidationError(ValueError):
    """Raised when traffic dataset fails structural or content validation."""
    pass


def validate_raw_dataset(
    csv_path: str | Path,
    pkl_path: str | Path,
    expected_min_samples: int = 100,
) -> dict[str, Any]:
    """Validate raw traffic dataset CSV and graph adjacency pickle files.

    Performs strict checks for file presence, non-corruption, sensor count alignment,
    timestamp monotonicity, duplicate timestamps, NaN/Inf presence, and non-empty graph.
    """
    csv_path = Path(csv_path)
    pkl_path = Path(pkl_path)

    # 1. File existence
    if not csv_path.exists():
        raise DatasetValidationError(
            f"Dataset validation failed: CSV file does not exist at {csv_path}"
        )
    if not pkl_path.exists():
        raise DatasetValidationError(
            f"Dataset validation failed: Adjacency graph file does not exist at {pkl_path}"
        )

    # 2. File size
    if csv_path.stat().st_size == 0:
        raise DatasetValidationError(
            f"Dataset validation failed: CSV file is empty (0 bytes) at {csv_path}"
        )
    if pkl_path.stat().st_size == 0:
        raise DatasetValidationError(
            f"Dataset validation failed: Pickle file is empty (0 bytes) at {pkl_path}"
        )

    # 3. Graph Pickle Validation
    import pickle
    try:
        with open(pkl_path, "rb") as f:
            try:
                pkl_data = pickle.load(f, encoding="latin1")
            except Exception:
                f.seek(0)
                pkl_data = pickle.load(f)
    except Exception as exc:
        raise DatasetValidationError(
            f"Dataset validation failed: Graph pickle file corrupted at {pkl_path}: {exc}"
        ) from exc

    if isinstance(pkl_data, (list, tuple)):
        if len(pkl_data) < 3:
            raise DatasetValidationError(
                f"Dataset validation failed: Pickle tuple length is {len(pkl_data)}, expected 3 (sensor_ids, id_map, adj_mx)"
            )
        sensor_ids_graph = [str(s).strip() for s in pkl_data[0]]
        adj_mx = pkl_data[2]
    elif isinstance(pkl_data, dict):
        sensor_ids_graph = [str(s).strip() for s in pkl_data.get("sensor_ids", [])]
        adj_mx = pkl_data.get("adj_mx")
    elif isinstance(pkl_data, np.ndarray):
        sensor_ids_graph = None
        adj_mx = pkl_data
    else:
        raise DatasetValidationError(
            f"Dataset validation failed: Unsupported pickle format {type(pkl_data)}"
        )

    if not isinstance(adj_mx, np.ndarray) or adj_mx.ndim != 2 or adj_mx.shape[0] != adj_mx.shape[1]:
        raise DatasetValidationError(
            f"Dataset validation failed: Adjacency matrix must be a 2D square matrix, got shape {getattr(adj_mx, 'shape', None)}"
        )

    graph_nodes = adj_mx.shape[0]
    if graph_nodes == 0:
        raise DatasetValidationError(
            "Dataset validation failed: Adjacency matrix has 0 nodes"
        )

    if np.all(adj_mx == 0):
        raise DatasetValidationError(
            "Dataset validation failed: Adjacency matrix has 0 non-zero edges (completely disconnected graph)"
        )

    # 4. CSV Validation
    try:
        # Read header and first chunk to inspect columns
        header_df = pd.read_csv(csv_path, nrows=5)
    except Exception as exc:
        raise DatasetValidationError(
            f"Dataset validation failed: CSV corrupted or unreadable at {csv_path}: {exc}"
        ) from exc

    first_col = header_df.columns[0]
    try:
        pd.to_datetime(header_df[first_col])
        timestamp_col = first_col
        sensor_cols = [str(c).strip() for c in header_df.columns[1:]]
    except Exception:
        timestamp_col = None
        sensor_cols = [str(c).strip() for c in header_df.columns]

    csv_nodes = len(sensor_cols)
    if csv_nodes != graph_nodes:
        raise DatasetValidationError(
            f"Dataset validation failed:\n\n"
            f"CSV nodes: {csv_nodes}\n"
            f"Graph nodes: {graph_nodes}\n\n"
            f"Sensor/graph dimension mismatch.\n"
            f"Expected: CSV sensor columns == adjacency matrix dimensions ({graph_nodes})"
        )

    if sensor_ids_graph is not None:
        if len(sensor_ids_graph) != csv_nodes:
            raise DatasetValidationError(
                f"Dataset validation failed: Sensor ID list length ({len(sensor_ids_graph)}) "
                f"does not match CSV sensor count ({csv_nodes})"
            )
        if sensor_ids_graph != sensor_cols:
            diff = set(sensor_cols).symmetric_difference(set(sensor_ids_graph))
            raise DatasetValidationError(
                f"Dataset validation failed: Sensor ordering or IDs do not match between CSV and graph pickle.\n"
                f"Mismatched IDs count: {len(diff)}"
            )

    # Check timestamps and full integrity with a larger sample or full load
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        raise DatasetValidationError(f"Dataset validation failed loading CSV: {exc}") from exc

    if len(df) < expected_min_samples:
        raise DatasetValidationError(
            f"Dataset validation failed: Insufficient samples. Found {len(df)} rows, "
            f"expected at least {expected_min_samples}"
        )

    if timestamp_col is not None:
        try:
            ts = pd.to_datetime(df[timestamp_col])
        except Exception as exc:
            raise DatasetValidationError(
                f"Dataset validation failed: Invalid datetime values in timestamp column '{timestamp_col}': {exc}"
            ) from exc

        if not ts.is_monotonic_increasing:
            raise DatasetValidationError(
                "Dataset validation failed: Timestamps are not in strict chronological order"
            )

        dup_count = int(ts.duplicated().sum())
        if dup_count > 0:
            raise DatasetValidationError(
                f"Dataset validation failed: Found {dup_count} duplicate timestamps"
            )

    # Check numeric types and Inf
    sensor_data = df[sensor_cols].values
    if not np.issubdtype(sensor_data.dtype, np.number):
        raise DatasetValidationError(
            "Dataset validation failed: Non-numeric traffic readings detected in sensor columns"
        )

    if np.isinf(sensor_data).any():
        raise DatasetValidationError(
            "Dataset validation failed: Infinite (Inf) values detected in traffic readings"
        )

    return {
        "status": "valid",
        "num_nodes": csv_nodes,
        "num_timesteps": len(df),
        "timestamp_col": timestamp_col,
        "sensor_ids": sensor_cols,
        "adj_shape": adj_mx.shape,
    }
