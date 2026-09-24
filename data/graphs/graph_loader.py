"""Graph loader with safe structure validation for traffic sensor adjacency matrices."""
from __future__ import annotations

from pathlib import Path
import pickle
from typing import Any
import numpy as np


class GraphLoadError(ValueError):
    """Raised when adjacency pickle cannot be safely loaded or verified."""
    pass


def load_graph_pickle(
    pkl_path: str | Path,
) -> tuple[list[str], dict[str, int], np.ndarray]:
    """Load and validate traffic network adjacency matrix from pickle artifact.

    Args:
        pkl_path: Path to pickle file.

    Returns:
        sensor_ids: List of sensor ID strings.
        sensor_id_to_ind: Dict mapping sensor ID string to 0-indexed position.
        adj_mx: Symmetric or directed adjacency matrix of shape [N, N].

    Raises:
        GraphLoadError: If file is missing, corrupted, or structure is invalid.
    """
    path = Path(pkl_path)
    if not path.exists():
        raise GraphLoadError(f"Adjacency graph file not found at {path}")

    try:
        with open(path, "rb") as f:
            try:
                data = pickle.load(f, encoding="latin1")
            except Exception:
                f.seek(0)
                data = pickle.load(f)
    except Exception as exc:
        raise GraphLoadError(f"Failed to unpickle graph file at {path}: {exc}") from exc

    if isinstance(data, (list, tuple)) and len(data) >= 3:
        sensor_ids = [str(s).strip() for s in data[0]]
        sensor_id_to_ind = {str(k).strip(): int(v) for k, v in data[1].items()}
        adj_mx = data[2]
    elif isinstance(data, dict):
        sensor_ids = [str(s).strip() for s in data.get("sensor_ids", [])]
        sensor_id_to_ind = {str(k).strip(): int(v) for k, v in data.get("sensor_id_to_ind", {}).items()}
        adj_mx = data.get("adj_mx")
    elif isinstance(data, np.ndarray):
        adj_mx = data
        sensor_ids = [f"sensor_{i}" for i in range(adj_mx.shape[0])]
        sensor_id_to_ind = {sid: i for i, sid in enumerate(sensor_ids)}
    else:
        raise GraphLoadError(f"Unsupported adjacency pickle structure: {type(data)}")

    if not isinstance(adj_mx, np.ndarray) or adj_mx.ndim != 2 or adj_mx.shape[0] != adj_mx.shape[1]:
        raise GraphLoadError(
            f"Adjacency matrix must be a 2D square numpy array, got {getattr(adj_mx, 'shape', None)}"
        )

    N = adj_mx.shape[0]
    if len(sensor_ids) != N:
        raise GraphLoadError(
            f"Sensor ID list count ({len(sensor_ids)}) does not match adjacency dimension ({N})"
        )

    # Ensure dtype is float32
    adj_mx = np.ascontiguousarray(adj_mx, dtype=np.float32)

    return sensor_ids, sensor_id_to_ind, adj_mx
