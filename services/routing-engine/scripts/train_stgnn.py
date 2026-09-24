"""ST-GNN model training script for CATRS.

Supports training on:
- Synthetic traffic world (100 nodes, 9 features)
- METR-LA benchmark (207 nodes, 4 features)
- PEMS-BAY benchmark (325 nodes, 4 features)

Performs genuine spatial graph convolution (GCN) + recurrent temporal dynamics (GRU)
with node-level multi-horizon forecasting (5m, 15m, 30m).
Saves model checkpoints and machine-readable metadata JSON for full reproducibility.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
import random
import subprocess
import sys
from typing import Any

# Ensure both repo root and services/routing-engine are in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(ENGINE_ROOT))

for p in (REPO_ROOT, ENGINE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from app.models.st_gnn import SpatioTemporalGNN, STGNNPredictor
from data.datasets import DatasetMode, get_dataset


def get_git_commit() -> str:
    """Safely obtain current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def train_stgnn(
    dataset_name: str = "synthetic",
    epochs: int = 15,
    batch_size: int = 32,
    lr: float = 0.005,
    lookback: int = 12,
    hidden_size: int = 32,
    gcn_hidden: int = 32,
    dropout: float = 0.1,
    checkpoint_path: str | None = None,
    seed: int = 42,
    days: int = 14,
    max_samples: int | None = None,
) -> dict[str, Any]:
    """Train ST-GNN on specified dataset with genuine GCN and GRU spatial-temporal modeling."""
    # Deterministic seeding
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    mode = DatasetMode(dataset_name.lower())
    print(f"\n=======================================================")
    print(f"CATRS ST-GNN Training Pipeline | Dataset: {mode.value.upper()}")
    print(f"=======================================================")
    print(f"Hyperparameters: epochs={epochs}, batch_size={batch_size}, lr={lr}, "
          f"lookback={lookback}, hidden_size={hidden_size}, gcn_hidden={gcn_hidden}, seed={seed}")

    # 1. Load dataset
    raw_dir = os.path.join(REPO_ROOT, "data")
    ds = get_dataset(mode, data_dir=raw_dir)

    print(f"Loading/processing dataset '{mode.value}' (lookback={lookback})...")
    if mode == DatasetMode.SYNTHETIC:
        data_dict = ds.load_or_process(lookback=lookback, days=days)
    else:
        data_dict = ds.load_or_process(lookback=lookback)

    X_train_np = data_dict["X_train"]
    Y_train_np = data_dict["Y_train"]
    X_val_np = data_dict["X_val"]
    Y_val_np = data_dict["Y_val"]
    adj_mx = data_dict["adj_mx"]
    sensor_ids = data_dict["sensor_ids"]
    feature_names = data_dict.get("feature_names", [])

    if max_samples is not None and max_samples > 0:
        print(f"Limiting dataset to first {max_samples} samples for fast execution...")
        X_train_np = X_train_np[:max_samples]
        Y_train_np = Y_train_np[:max_samples]
        val_samples = max(10, max_samples // 5)
        X_val_np = X_val_np[:val_samples]
        Y_val_np = Y_val_np[:val_samples]

    num_samples, T, num_nodes, feature_count = X_train_np.shape
    print(f"Train samples: {num_samples}, Val samples: {len(X_val_np)}")
    print(f"Input shape: [B, {T}, {num_nodes}, {feature_count}], Target shape: {Y_train_np.shape}")
    print(f"Graph nodes: {len(sensor_ids)}, Adjacency shape: {adj_mx.shape}")

    # 2. Build PyTorch tensors and DataLoaders
    X_train = torch.from_numpy(X_train_np).float()
    Y_train = torch.from_numpy(Y_train_np).float()
    X_val = torch.from_numpy(X_val_np).float()
    Y_val = torch.from_numpy(Y_val_np).float()

    train_dataset = TensorDataset(X_train, Y_train)
    val_dataset = TensorDataset(X_val, Y_val)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # 3. Model construction
    model = SpatioTemporalGNN(
        num_nodes=num_nodes,
        feature_count=feature_count,
        hidden_size=hidden_size,
        gcn_hidden=gcn_hidden,
        num_horizons=3,
        dropout=dropout,
        adj_mx=adj_mx,
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    print(f"Model parameters: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")
    print("Beginning training on CPU...\n")

    train_loss = 0.0
    val_loss = 0.0
    val_mae = 0.0
    val_rmse = 0.0
    mae_5m = 0.0
    mae_15m = 0.0
    mae_30m = 0.0

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
        err_sum = 0.0
        err_5m = 0.0
        err_15m = 0.0
        err_30m = 0.0
        total_eval_points = len(val_dataset) * num_nodes

        with torch.no_grad():
            for bx, by in val_loader:
                pred = model(bx)
                val_loss += criterion(pred, by).item() * len(bx)
                abs_diff = torch.abs(pred - by)  # [B, N, 3]
                err_sum += abs_diff.sum().item()
                err_5m += abs_diff[:, :, 0].sum().item()
                err_15m += abs_diff[:, :, 1].sum().item()
                err_30m += abs_diff[:, :, 2].sum().item()

        val_loss /= len(val_dataset)
        val_mae = err_sum / (total_eval_points * 3)
        val_rmse = math.sqrt(val_loss)
        mae_5m = err_5m / total_eval_points
        mae_15m = err_15m / total_eval_points
        mae_30m = err_30m / total_eval_points

        if epoch % 5 == 0 or epoch == epochs or epoch == 1:
            print(
                f"Epoch {epoch:2d}/{epochs:2d} | "
                f"Train MSE: {train_loss:.3f} | "
                f"Val MSE: {val_loss:.3f} | "
                f"Val MAE: {val_mae:.2f} | "
                f"Val RMSE: {val_rmse:.2f} | "
                f"MAE [5m={mae_5m:.2f}, 15m={mae_15m:.2f}, 30m={mae_30m:.2f}]"
            )

    # 4. Resolve checkpoint path
    if checkpoint_path is None:
        checkpoints_dir = os.path.join(ENGINE_ROOT, "checkpoints")
        if mode == DatasetMode.SYNTHETIC:
            checkpoint_path = os.path.join(checkpoints_dir, "synthetic_stgnn.pt")
        elif mode == DatasetMode.METR_LA:
            checkpoint_path = os.path.join(checkpoints_dir, "metr_la_stgnn.pt")
        else:
            checkpoint_path = os.path.join(checkpoints_dir, "pems_bay_stgnn.pt")

    os.makedirs(os.path.dirname(os.path.abspath(checkpoint_path)), exist_ok=True)
    torch.save(model.state_dict(), checkpoint_path)
    print(f"\nModel checkpoint saved successfully to: {checkpoint_path}")

    # Also save to default synthetic checkpoint if training synthetic
    if mode == DatasetMode.SYNTHETIC:
        default_pt = os.path.join(os.path.dirname(checkpoint_path), "stgnn_default.pt")
        torch.save(model.state_dict(), default_pt)
        print(f"Default synthetic fallback checkpoint updated: {default_pt}")

    # 5. Save machine-readable metadata JSON (Phase 13)
    meta_path = os.path.splitext(checkpoint_path)[0] + "_metadata.json"
    metadata: dict[str, Any] = {
        "dataset": mode.value,
        "dataset_version": "1.0",
        "random_seed": seed,
        "model_architecture": "SpatioTemporalGNN",
        "hyperparameters": {
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": lr,
            "lookback": lookback,
            "hidden_size": hidden_size,
            "gcn_hidden": gcn_hidden,
            "dropout": dropout,
            "num_nodes": num_nodes,
            "feature_count": feature_count,
            "num_horizons": 3,
        },
        "feature_configuration": feature_names,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "evaluation_metrics": {
            "train_mse": round(train_loss, 4),
            "val_mse": round(val_loss, 4),
            "val_mae": round(val_mae, 4),
            "val_rmse": round(val_rmse, 4),
            "per_horizon_mae": {
                "5m": round(mae_5m, 4),
                "15m": round(mae_15m, 4),
                "30m": round(mae_30m, 4),
            },
        },
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Reproducibility metadata saved successfully to: {meta_path}")

    # 6. Post-training CPU inference verification
    print("Verifying checkpoint loading and CPU inference...")
    verify_model = SpatioTemporalGNN(
        num_nodes=num_nodes,
        feature_count=feature_count,
        hidden_size=hidden_size,
        gcn_hidden=gcn_hidden,
        num_horizons=3,
        dropout=dropout,
        adj_mx=adj_mx,
    )
    loaded_state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    verify_model.load_state_dict(loaded_state)
    verify_model.eval()

    sample_x = X_val[:1]
    with torch.no_grad():
        out = verify_model(sample_x)
    print(f"Checkpoint verification PASSED! Output shape: {out.shape} (expected [1, {num_nodes}, 3])")
    print(f"Sample node 0 predictions: 5m={out[0, 0, 0]:.1f}, 15m={out[0, 0, 1]:.1f}, 30m={out[0, 0, 2]:.1f}\n")

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ST-GNN model for CATRS")
    parser.add_argument(
        "--dataset",
        type=str,
        default="synthetic",
        choices=["synthetic", "metr_la", "pems_bay"],
        help="Dataset to train on (synthetic, metr_la, pems_bay)",
    )
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", "--learning-rate", dest="lr", type=float, default=0.005, help="Learning rate")
    parser.add_argument("--lookback", "--window-steps", dest="lookback", type=int, default=12, help="Temporal window steps")
    parser.add_argument("--hidden-size", type=int, default=32, help="Hidden size for GRU")
    parser.add_argument("--gcn-hidden", "--graph-layers", dest="gcn_hidden", type=int, default=32, help="Hidden size for GCN")
    parser.add_argument("--dropout", type=float, default=0.1, help="Dropout probability")
    parser.add_argument("--seed", "--random-seed", dest="seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--days", type=int, default=14, help="Number of history days for synthetic data generation")
    parser.add_argument("--max-samples", type=int, default=None, help="Optional max training samples for quick runs")
    parser.add_argument(
        "--output",
        "--checkpoint",
        "--checkpoint-path",
        dest="checkpoint",
        type=str,
        default=None,
        help="Path to save PyTorch checkpoint",
    )
    args = parser.parse_args()

    train_stgnn(
        dataset_name=args.dataset,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        lookback=args.lookback,
        hidden_size=args.hidden_size,
        gcn_hidden=args.gcn_hidden,
        dropout=args.dropout,
        checkpoint_path=args.checkpoint,
        seed=args.seed,
        days=args.days,
        max_samples=args.max_samples,
    )


if __name__ == "__main__":
    main()
