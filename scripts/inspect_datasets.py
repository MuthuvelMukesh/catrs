"""Programmatic dataset inspection and profiling script for CATRS.

Inspects METR-LA and PEMS-BAY CSV files and adjacency matrix pickles,
validates sensor ID alignment, sampling frequency, and value ranges,
and writes a machine-readable metadata report to data/metadata/datasets_metadata.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pickle
import sys
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).parent.parent.resolve()
DATA_RAW = ROOT_DIR / "data" / "raw"
DATA_META = ROOT_DIR / "data" / "metadata"


def inspect_dataset(name: str, csv_filename: str, pkl_filename: str) -> dict:
    csv_path = DATA_RAW / csv_filename
    pkl_path = DATA_RAW / pkl_filename

    print(f"\n=======================================================")
    print(f"       INSPECTING DATASET: {name}")
    print(f"=======================================================")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    if not pkl_path.exists():
        raise FileNotFoundError(f"Pickle file not found: {pkl_path}")

    # 1. Read CSV preview and full shape
    print(f"Reading CSV: {csv_path.name}...")
    df = pd.read_csv(csv_path)
    print(f"Loaded CSV shape: {df.shape} (rows={df.shape[0]}, cols={df.shape[1]})")

    # Detect timestamp column
    first_col = df.columns[0]
    has_datetime_first = False
    try:
        sample_ts = pd.to_datetime(df[first_col].iloc[:5])
        has_datetime_first = True
        timestamp_col = first_col
        sensor_cols = list(df.columns[1:])
    except Exception:
        timestamp_col = None
        sensor_cols = list(df.columns)

    if has_datetime_first:
        timestamps = pd.to_datetime(df[timestamp_col])
        is_monotonic = timestamps.is_monotonic_increasing
        time_diffs = timestamps.diff().dropna()
        mode_diff = time_diffs.mode()[0]
        sampling_minutes = mode_diff.total_seconds() / 60.0
        start_time = str(timestamps.min())
        end_time = str(timestamps.max())
        num_timesteps = len(timestamps)
        duplicate_timestamps = int(timestamps.duplicated().sum())
    else:
        is_monotonic = False
        sampling_minutes = None
        start_time = None
        end_time = None
        num_timesteps = len(df)
        duplicate_timestamps = 0

    # Sensor data statistics
    sensor_df = df[sensor_cols]
    num_sensors = len(sensor_cols)
    null_counts = int(sensor_df.isna().sum().sum())
    zero_counts = int((sensor_df == 0).sum().sum())
    min_val = float(sensor_df.min().min())
    max_val = float(sensor_df.max().max())
    mean_val = float(sensor_df.mean().mean())
    std_val = float(sensor_df.std().mean())

    print(f"Sensor count in CSV: {num_sensors}")
    print(f"Timestamp column: {timestamp_col}")
    print(f"Chronological ordering: {'Yes' if is_monotonic else 'No'}")
    print(f"Sampling interval: {sampling_minutes} minutes")
    print(f"Time range: {start_time} to {end_time} ({num_timesteps} steps)")
    print(f"Missing (NaN) count: {null_counts}")
    print(f"Zero values count: {zero_counts} ({zero_counts / (num_timesteps * num_sensors) * 100:.2f}%)")
    print(f"Value range: min={min_val:.2f}, max={max_val:.2f}, mean={mean_val:.2f}, avg_std={std_val:.2f}")

    # 2. Inspect Adjacency Pickle
    print(f"\nInspecting Adjacency Pickle: {pkl_path.name}...")
    with open(pkl_path, "rb") as f:
        try:
            pkl_data = pickle.load(f, encoding="latin1")
        except Exception:
            f.seek(0)
            pkl_data = pickle.load(f)

    print(f"Pickle object type: {type(pkl_data)}")
    if isinstance(pkl_data, (list, tuple)):
        print(f"Pickle length: {len(pkl_data)}")
        for idx, item in enumerate(pkl_data):
            print(f"  Item {idx}: type={type(item)}, "
                  f"shape/len={getattr(item, 'shape', len(item) if hasattr(item, '__len__') else None)}")

        sensor_ids_pkl = pkl_data[0]
        sensor_to_ind = pkl_data[1]
        adj_mx = pkl_data[2]
    elif isinstance(pkl_data, dict):
        print(f"Pickle keys: {list(pkl_data.keys())}")
        sensor_ids_pkl = pkl_data.get("sensor_ids", list(pkl_data.keys()))
        sensor_to_ind = pkl_data.get("sensor_to_ind", {})
        adj_mx = pkl_data.get("adj_mx", None)
    elif isinstance(pkl_data, np.ndarray):
        sensor_ids_pkl = None
        sensor_to_ind = None
        adj_mx = pkl_data
    else:
        raise ValueError(f"Unrecognized pickle format: {type(pkl_data)}")

    adj_shape = list(adj_mx.shape)
    adj_nonzeros = int(np.count_nonzero(adj_mx))
    adj_min = float(np.min(adj_mx))
    adj_max = float(np.max(adj_mx))
    adj_has_self_loops = bool(np.all(np.diag(adj_mx) > 0))

    print(f"Adjacency matrix shape: {adj_shape}")
    print(f"Non-zero edge count: {adj_nonzeros}")
    print(f"Adjacency values: min={adj_min:.4f}, max={adj_max:.4f}")
    print(f"Has self-loops: {adj_has_self_loops}")

    # Alignment verification
    # Convert CSV sensor columns to strings
    csv_sensor_strs = [str(c).strip() for c in sensor_cols]
    if sensor_ids_pkl is not None:
        pkl_sensor_strs = [str(s).strip() for s in sensor_ids_pkl]
        num_pkl_sensors = len(pkl_sensor_strs)
        sensor_count_match = (num_sensors == num_pkl_sensors)
        exact_order_match = (csv_sensor_strs == pkl_sensor_strs)
        set_diff = set(csv_sensor_strs).symmetric_difference(set(pkl_sensor_strs))
        print(f"Sensor count matches graph: {sensor_count_match} (CSV: {num_sensors}, Graph: {num_pkl_sensors})")
        print(f"Exact sensor ID ordering match: {exact_order_match}")
        if set_diff:
            print(f"Sensor ID symmetric difference: {len(set_diff)} IDs mismatch!")
    else:
        sensor_count_match = (num_sensors == adj_shape[0])
        exact_order_match = False
        pkl_sensor_strs = []

    report = {
        "dataset": name,
        "csv_filename": csv_filename,
        "pkl_filename": pkl_filename,
        "num_nodes": num_sensors,
        "num_timesteps": num_timesteps,
        "timestamp_col": timestamp_col,
        "sampling_minutes": sampling_minutes,
        "time_start": start_time,
        "time_end": end_time,
        "is_chronological": is_monotonic,
        "duplicate_timestamps": duplicate_timestamps,
        "missing_values_count": null_counts,
        "zero_values_count": zero_counts,
        "zero_percentage": round(zero_counts / (num_timesteps * num_sensors) * 100, 2),
        "speed_stats": {
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "mean": round(mean_val, 2),
            "std": round(std_val, 2),
        },
        "graph": {
            "shape": adj_shape,
            "non_zero_edges": adj_nonzeros,
            "min_weight": adj_min,
            "max_weight": adj_max,
            "has_self_loops": adj_has_self_loops,
            "sensor_count_match": sensor_count_match,
            "exact_sensor_order_match": exact_order_match,
        },
        "sensor_ids_sample": csv_sensor_strs[:10],
    }

    return report


def main():
    DATA_META.mkdir(parents=True, exist_ok=True)

    metr_la_report = inspect_dataset(
        name="METR_LA",
        csv_filename="METR-LA.csv",
        pkl_filename="adj_mx_METR-LA.pkl",
    )

    pems_bay_report = inspect_dataset(
        name="PEMS_BAY",
        csv_filename="PEMS-BAY.csv",
        pkl_filename="adj_mx_PEMS-BAY.pkl",
    )

    full_report = {
        "inspected_at": pd.Timestamp.now().isoformat(),
        "datasets": {
            "METR_LA": metr_la_report,
            "PEMS_BAY": pems_bay_report,
        },
    }

    out_path = DATA_META / "datasets_metadata.json"
    with open(out_path, "w") as f:
        json.dump(full_report, f, indent=2)

    print(f"\n=======================================================")
    print(f"Machine-readable metadata report saved to: {out_path}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
