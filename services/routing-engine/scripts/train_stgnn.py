"""ST-GNN model training script for CATRS.

Generates temporal sequences from deterministic synthetic traffic history,
trains the PyTorch GRU ST-GNN architecture, computes evaluation metrics,
and exports model state dict checkpoints.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import math
import os
import sys
from typing import Any

# Ensure services/routing-engine is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(SCRIPT_DIR)
if ENGINE_ROOT not in sys.path:
    sys.path.insert(0, ENGINE_ROOT)

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from app.data.synthetic_world import (
    build_historical_baseline,
    generate_grid_graph,
    generate_synthetic_history,
)
from app.models.pipeline import build_feature_vector
from app.models.st_gnn import STGNNPredictor


def generate_training_data(
    days: int = 14,
    interval_minutes: int = 5,
    window_steps: int = 12,
    num_nodes: int = 100,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Generate training tensors (X, Y) from synthetic traffic patterns.

    Parameters
    ----------
    days:
        Number of synthetic history days to generate.
    interval_minutes:
        Time delta between timesteps.
    window_steps:
        Length of input temporal sequence (default 12).
    num_nodes:
        Number of nodes to slice for model input dimension (default 100).

    Returns
    -------
    X:
        Tensor of shape [samples, 12, num_nodes, 9]
    Y:
        Tensor of shape [samples, 3] representing target speeds at 5m, 15m, 30m
    """
    rows = generate_synthetic_history(days=days, interval_minutes=interval_minutes)
    baseline = build_historical_baseline(rows)

    # Group readings by timestamp
    by_time: dict[datetime, dict[str, dict[str, Any]]] = {}
    for r in rows:
        t = r["timestamp"]
        by_time.setdefault(t, {})[r["segment_id"]] = r

    sorted_times = sorted(by_time.keys())
    graph = generate_grid_graph()
    all_segments = [e["segment_id"] for e in graph["edges"]][:num_nodes]
    actual_nodes = len(all_segments)

    # If fewer segments than num_nodes, pad segment list
    while len(all_segments) < num_nodes:
        all_segments.append(all_segments[len(all_segments) % actual_nodes])

    # Slices: 12 steps input, future steps: +1 (5m), +3 (15m), +6 (30m)
    horizon_offsets = [1, 3, 6]
    max_offset = max(horizon_offsets)

    samples_x: list[list[list[list[float]]]] = []
    samples_y: list[list[float]] = []

    for i in range(len(sorted_times) - window_steps - max_offset):
        window_times = sorted_times[i : i + window_steps]
        t_5m = sorted_times[i + window_steps - 1 + horizon_offsets[0]]
        t_15m = sorted_times[i + window_steps - 1 + horizon_offsets[1]]
        t_30m = sorted_times[i + window_steps - 1 + horizon_offsets[2]]

        # Build 12-step feature window
        window_data: list[list[list[float]]] = []
        for t in window_times:
            step_nodes: list[list[float]] = []
            time_dict = by_time[t]
            for seg in all_segments:
                reading = time_dict.get(seg)
                avg_speed = reading["avg_speed"] if reading else 50.0
                vol = reading["vehicle_count"] if reading else 40
                bl = baseline.get((seg, t.weekday(), t.hour), avg_speed)

                vec = build_feature_vector(
                    current_speed=avg_speed,
                    current_volume=vol,
                    historical_baseline_speed=bl,
                    weather_severity_score=0.0,
                    active_incident_flag=False,
                    event_proximity_score=0.0,
                    upstream_segment_congestion=0.0,
                    time_of_day=t.hour,
                    day_of_week=t.weekday(),
                )
                step_nodes.append([
                    float(vec["current_speed"]),
                    float(vec["current_volume"]),
                    float(vec["historical_baseline_speed"]),
                    float(vec["weather_severity_score"]),
                    1.0 if vec["active_incident_flag"] else 0.0,
                    float(vec["event_proximity_score"]),
                    float(vec["upstream_segment_congestion"]),
                    float(vec["time_of_day_sin"]),
                    float(vec["time_of_day_cos"]),
                ])
            window_data.append(step_nodes)

        # Compute average target speed across segments for horizons
        target_5m = sum(by_time[t_5m][s]["avg_speed"] for s in all_segments if s in by_time[t_5m]) / len(all_segments)
        target_15m = sum(by_time[t_15m][s]["avg_speed"] for s in all_segments if s in by_time[t_15m]) / len(all_segments)
        target_30m = sum(by_time[t_30m][s]["avg_speed"] for s in all_segments if s in by_time[t_30m]) / len(all_segments)

        samples_x.append(window_data)
        samples_y.append([target_5m, target_15m, target_30m])

    return torch.tensor(samples_x, dtype=torch.float32), torch.tensor(samples_y, dtype=torch.float32)


def train_model(
    epochs: int = 15,
    batch_size: int = 32,
    lr: float = 0.005,
    num_nodes: int = 100,
    hidden_size: int = 32,
    checkpoint_path: str = "checkpoints/stgnn_default.pt",
) -> dict[str, float]:
    """Train STGNN on synthetic traffic data and save checkpoint."""
    print(f"Generating synthetic training dataset (nodes={num_nodes})...")
    X, Y = generate_training_data(days=14, num_nodes=num_nodes)
    print(f"Dataset generated: X shape = {X.shape}, Y shape = {Y.shape}")

    # Train / validation split (80 / 20)
    total_samples = len(X)
    split_idx = int(total_samples * 0.8)
    train_dataset = TensorDataset(X[:split_idx], Y[:split_idx])
    val_dataset = TensorDataset(X[split_idx:], Y[split_idx:])

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    predictor = STGNNPredictor(
        feature_count=9,
        node_count=num_nodes,
        hidden_size=hidden_size,
    )
    model = predictor._model

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    print(f"Starting training for {epochs} epochs...")
    best_val_loss = float("inf")

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for bx, by in train_loader:
            optimizer.zero_grad()
            pred = model(bx)
            loss = criterion(pred, by)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(bx)
        train_loss /= len(train_dataset)

        # Validation
        model.eval()
        val_loss = 0.0
        val_mae = 0.0
        with torch.no_grad():
            for bx, by in val_loader:
                pred = model(bx)
                val_loss += criterion(pred, by).item() * len(bx)
                val_mae += torch.abs(pred - by).sum().item()
        val_loss /= len(val_dataset)
        val_mae /= (len(val_dataset) * 3)
        val_rmse = math.sqrt(val_loss)

        if epoch % 5 == 0 or epoch == epochs or epoch == 1:
            print(f"Epoch {epoch:2d}/{epochs:2d} | Train MSE: {train_loss:.4f} | Val MSE: {val_loss:.4f} | Val MAE: {val_mae:.2f} km/h | Val RMSE: {val_rmse:.2f} km/h")

    # Save checkpoint
    os.makedirs(os.path.dirname(os.path.abspath(checkpoint_path)), exist_ok=True)
    torch.save(model.state_dict(), checkpoint_path)
    print(f"Model checkpoint saved successfully to: {checkpoint_path}")

    return {
        "final_train_loss": train_loss,
        "final_val_loss": val_loss,
        "final_val_mae": val_mae,
        "final_val_rmse": val_rmse,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ST-GNN model for CATRS")
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.005, help="Learning rate")
    parser.add_argument("--nodes", type=int, default=100, help="Number of graph nodes")
    parser.add_argument("--hidden-size", type=int, default=32, help="Hidden size for GRU")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=os.path.join(ENGINE_ROOT, "checkpoints", "stgnn_default.pt"),
        help="Path to save PyTorch checkpoint",
    )
    args = parser.parse_args()

    train_model(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        num_nodes=args.nodes,
        hidden_size=args.hidden_size,
        checkpoint_path=args.checkpoint,
    )


if __name__ == "__main__":
    main()
