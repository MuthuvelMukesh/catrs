"""Evaluation script for ST-GNN vs Heuristic Fallback prediction accuracy."""
from __future__ import annotations

import argparse
from datetime import datetime
import math
import os
from pathlib import Path
import sys
from typing import Any

# Ensure routing engine is at front of sys.path
ROOT_DIR = Path(__file__).parent.parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
while ROUTING_DIR in sys.path:
    sys.path.remove(ROUTING_DIR)
sys.path.insert(0, ROUTING_DIR)
if "app" in sys.modules and not hasattr(sys.modules["app"], "models"):
    for m in list(sys.modules.keys()):
        if m == "app" or m.startswith("app."):
            del sys.modules[m]

import importlib.util
import torch

from app.models.pipeline import compute_prediction
from app.models.st_gnn import STGNNPredictor

_train_script = ROOT_DIR / "services" / "routing-engine" / "scripts" / "train_stgnn.py"
_spec = importlib.util.spec_from_file_location("train_stgnn_mod", _train_script)
_train_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_train_mod)
generate_training_data = _train_mod.generate_training_data


def compute_metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    """Calculate MAE, RMSE, and MAPE metrics."""
    n = len(actual)
    if n == 0:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}

    mae = sum(abs(a - p) for a, p in zip(actual, predicted)) / n
    mse = sum((a - p) ** 2 for a, p in zip(actual, predicted)) / n
    rmse = math.sqrt(mse)
    mape = (sum(abs(a - p) / max(1.0, a) for a, p in zip(actual, predicted)) / n) * 100.0

    return {
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "mape": round(mape, 2),
    }


def evaluate(
    checkpoint_path: str = str(ROOT_DIR / "services" / "routing-engine" / "checkpoints" / "stgnn_default.pt"),
    days: int = 5,
    seed: int = 1234,
) -> dict[str, Any]:
    """Evaluate both ST-GNN and Fallback Heuristic on holdout test data."""
    print(f"Generating test evaluation data (days={days}, seed={seed})...")
    X, Y = generate_training_data(days=days, num_nodes=100, seed=seed)
    total_samples = len(X)
    print(f"Test samples available: {total_samples}")

    actual_5m = [float(Y[i, 0]) for i in range(total_samples)]
    actual_15m = [float(Y[i, 1]) for i in range(total_samples)]
    actual_30m = [float(Y[i, 2]) for i in range(total_samples)]

    # 1. Evaluate Heuristic Fallback
    heuristic_5m = []
    heuristic_15m = []
    heuristic_30m = []

    for i in range(total_samples):
        # Use average current speed from the last timestep
        last_step_speed = float(X[i, -1, :, 0].mean())
        last_step_vol = int(X[i, -1, :, 1].mean())
        last_step_bl = float(X[i, -1, :, 2].mean())

        pred = compute_prediction(
            current_speed=last_step_speed,
            current_volume=last_step_vol,
            historical_baseline_speed=last_step_bl,
            weather_severity_score=float(X[i, -1, :, 3].mean()),
            active_incident_flag=bool(X[i, -1, :, 4].mean() > 0.5),
            event_proximity_score=float(X[i, -1, :, 5].mean()),
            upstream_segment_congestion=float(X[i, -1, :, 6].mean()),
            time_of_day=int((i * 5 // 60) % 24),
            day_of_week=int((i * 5 // (60 * 24)) % 7),
        )
        heuristic_5m.append(pred["predicted_speed_5m"])
        heuristic_15m.append(pred["predicted_speed_15m"])
        heuristic_30m.append(pred["predicted_speed_30m"])

    m_h5 = compute_metrics(actual_5m, heuristic_5m)
    m_h15 = compute_metrics(actual_15m, heuristic_15m)
    m_h30 = compute_metrics(actual_30m, heuristic_30m)

    # 2. Evaluate ST-GNN (if checkpoint exists)
    stgnn_available = os.path.exists(checkpoint_path)
    if stgnn_available:
        try:
            predictor = STGNNPredictor(feature_count=9, node_count=100, hidden_size=32)
            state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            predictor._model.load_state_dict(state)
            predictor._model.eval()

            stgnn_5m = []
            stgnn_15m = []
            stgnn_30m = []

            with torch.no_grad():
                # Process in batches of 64
                batch_size = 64
                for b in range(0, total_samples, batch_size):
                    bx = X[b : b + batch_size]
                    out = predictor._model(bx).cpu()
                    for item in out:
                        stgnn_5m.append(float(item[0]))
                        stgnn_15m.append(float(item[1]))
                        stgnn_30m.append(float(item[2]))

            m_s5 = compute_metrics(actual_5m, stgnn_5m)
            m_s15 = compute_metrics(actual_15m, stgnn_15m)
            m_s30 = compute_metrics(actual_30m, stgnn_30m)
        except Exception as exc:
            print(f"Warning: Could not run ST-GNN inference ({exc})")
            stgnn_available = False
            m_s5 = m_s15 = m_s30 = {"mae": None, "rmse": None, "mape": None}
    else:
        m_s5 = m_s15 = m_s30 = {"mae": None, "rmse": None, "mape": None}

    # Print results summary table
    print("\n" + "=" * 76)
    print("           CATRS MODEL ACCURACY EVALUATION REPORT (TEST DATA)")
    print("=" * 76)
    print(f"{'Model':<20} | {'Horizon':<8} | {'MAE (km/h)':<12} | {'RMSE (km/h)':<12} | {'MAPE (%)':<10}")
    print("-" * 76)
    print(f"{'Heuristic Fallback':<20} | {'5-min':<8} | {m_h5['mae']:<12.3f} | {m_h5['rmse']:<12.3f} | {m_h5['mape']:<10.2f}")
    print(f"{'Heuristic Fallback':<20} | {'15-min':<8} | {m_h15['mae']:<12.3f} | {m_h15['rmse']:<12.3f} | {m_h15['mape']:<10.2f}")
    print(f"{'Heuristic Fallback':<20} | {'30-min':<8} | {m_h30['mae']:<12.3f} | {m_h30['rmse']:<12.3f} | {m_h30['mape']:<10.2f}")
    print("-" * 76)
    if stgnn_available:
        print(f"{'ST-GNN (Neural)':<20} | {'5-min':<8} | {m_s5['mae']:<12.3f} | {m_s5['rmse']:<12.3f} | {m_s5['mape']:<10.2f}")
        print(f"{'ST-GNN (Neural)':<20} | {'15-min':<8} | {m_s15['mae']:<12.3f} | {m_s15['rmse']:<12.3f} | {m_s15['mape']:<10.2f}")
        print(f"{'ST-GNN (Neural)':<20} | {'30-min':<8} | {m_s30['mae']:<12.3f} | {m_s30['rmse']:<12.3f} | {m_s30['mape']:<10.2f}")
    else:
        print(f"{'ST-GNN (Neural)':<20} | Checkpoint unavailable at {checkpoint_path}")
    print("=" * 76 + "\n")

    return {
        "heuristic": {"5m": m_h5, "15m": m_h15, "30m": m_h30},
        "stgnn": {"5m": m_s5, "15m": m_s15, "30m": m_s30} if stgnn_available else None,
        "sample_count": total_samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ST-GNN vs Heuristic Fallback")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=str(ROOT_DIR / "services" / "routing-engine" / "checkpoints" / "stgnn_default.pt"),
        help="Path to ST-GNN checkpoint",
    )
    parser.add_argument("--days", type=int, default=3, help="Number of test days")
    parser.add_argument("--seed", type=int, default=1234, help="Random seed for test data")
    args = parser.parse_args()

    evaluate(checkpoint_path=args.checkpoint, days=args.days, seed=args.seed)


if __name__ == "__main__":
    main()
