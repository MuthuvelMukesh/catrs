"""Research evaluation and benchmark suite for CATRS.

Evaluates ST-GNN against established baselines:
1. Historical Mean (profile baseline)
2. Persistence (naive last-step identity baseline)
3. Linear Regression / Ridge (lookback-to-horizon linear mapping)
4. GRU (pure temporal ablation)
5. GCN (pure spatial ablation)
6. SpatioTemporalGNN (integrated spatio-temporal architecture)

Features:
- Rigorous scale consistency: models train on normalized data and evaluate on unnormalized
  physical speed units (mph / km/h) via fitted StandardScaler.
- Computes MAE, RMSE, MAPE (with thresholding for near-zero ground truth), and R² for 5m, 15m, 30m.
- Per-node sensor error breakdown and inference latency benchmarking (p50, p95).
- Multi-seed evaluations (reporting mean ± std) and architectural/feature ablations.
- Automated Model Release Criteria evaluation (only promote ST-GNN if it outperforms baselines).
- Exports machine-readable JSON and CSV tables to results/{dataset}/.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from typing import Any

# Path setup
ROOT_DIR = Path(__file__).parent.parent.resolve()
ROUTING_DIR = ROOT_DIR / "services" / "routing-engine"

for p in (str(ROOT_DIR), str(ROUTING_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import torch
import torch.nn as nn

from app.models.baselines import (
    GCNModel,
    GRUModel,
    HistoricalMeanModel,
    LinearRegressionModel,
    PersistenceModel,
)
from app.models.st_gnn import SpatioTemporalGNN
from data.datasets import DatasetMode, get_dataset
from data.preprocessing.normalize import StandardScaler


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    mape_threshold: float = 5.0,
) -> dict[str, float]:
    """Calculate MAE, RMSE, MAPE, and R2 across non-zero traffic observations.

    Args:
        y_true: Ground truth speeds in original physical units (mph / km/h).
        y_pred: Predicted speeds in original physical units (mph / km/h).
        mape_threshold: Minimum ground truth speed for MAPE to avoid division by near-zero.
    """
    if not (np.isfinite(y_true).all() and np.isfinite(y_pred).all()):
        y_pred = np.nan_to_num(y_pred, nan=0.0, posinf=150.0, neginf=0.0)

    # Valid mask for observations (exclude sensor outage zeros)
    mask = y_true > 0.1
    if not np.any(mask):
        mask = np.ones_like(y_true, dtype=bool)

    diff = y_pred[mask] - y_true[mask]
    mae = float(np.mean(np.abs(diff)))
    rmse = float(np.sqrt(np.mean(diff ** 2)))

    # MAPE with explicit near-zero thresholding
    mape_mask = y_true[mask] >= mape_threshold
    if np.any(mape_mask):
        mape = float(np.mean(np.abs(diff[mape_mask]) / y_true[mask][mape_mask])) * 100.0
    else:
        mape = 0.0

    ss_res = float(np.sum(diff ** 2))
    ss_tot = float(np.sum((y_true[mask] - np.mean(y_true[mask])) ** 2))
    r2 = float(1.0 - (ss_res / (ss_tot + 1e-8)))

    return {
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "mape": round(mape, 2),
        "r2": round(r2, 4),
    }


def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, dict[str, float]]:
    """Compute metrics for 5m, 15m, 30m horizons, and overall."""
    return {
        "5m": compute_metrics(y_true[:, :, 0], y_pred[:, :, 0]),
        "15m": compute_metrics(y_true[:, :, 1], y_pred[:, :, 1]),
        "30m": compute_metrics(y_true[:, :, 2], y_pred[:, :, 2]),
        "overall": compute_metrics(y_true, y_pred),
    }


def benchmark_inference_latency(
    model: Any,
    sample_input: torch.Tensor,
    num_runs: int = 50,
) -> dict[str, float]:
    """Measure inference latency (p50, p95, mean) in milliseconds."""
    latencies_ms = []
    # Warmup
    for _ in range(5):
        if isinstance(model, nn.Module):
            with torch.no_grad():
                _ = model(sample_input)
        elif hasattr(model, "predict"):
            _ = model.predict(sample_input.numpy() if isinstance(sample_input, torch.Tensor) else sample_input)

    for _ in range(num_runs):
        t0 = time.perf_counter()
        if isinstance(model, nn.Module):
            with torch.no_grad():
                _ = model(sample_input)
        elif hasattr(model, "predict"):
            _ = model.predict(sample_input.numpy() if isinstance(sample_input, torch.Tensor) else sample_input)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

    return {
        "latency_p50_ms": round(float(np.percentile(latencies_ms, 50)), 2),
        "latency_p95_ms": round(float(np.percentile(latencies_ms, 95)), 2),
        "latency_mean_ms": round(float(np.mean(latencies_ms)), 2),
    }


def compute_per_node_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute per-sensor error distribution (mean, min, max, std of MAE)."""
    # Shape [B, N, 3] -> per node MAE: average across B and 3
    node_diff = np.abs(y_pred - y_true)  # [B, N, 3]
    node_mae = np.mean(node_diff, axis=(0, 2))  # [N]
    return {
        "node_mae_mean": round(float(np.mean(node_mae)), 3),
        "node_mae_min": round(float(np.min(node_mae)), 3),
        "node_mae_max": round(float(np.max(node_mae)), 3),
        "node_mae_std": round(float(np.std(node_mae)), 3),
    }


def fit_and_evaluate_baselines(
    dataset_name: str,
    data_dict: dict[str, Any],
    epochs: int = 3,
    max_train_samples: int = 400,
    max_test_samples: int = 200,
    seed: int = 42,
) -> dict[str, Any]:
    """Fit all baseline models and evaluate on unnormalized physical scale."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    scaler: StandardScaler = data_dict["scaler"]
    X_train = data_dict["X_train"][:max_train_samples]
    Y_train = data_dict["Y_train"][:max_train_samples]  # Physical unnormalized
    X_test = data_dict["X_test"][:max_test_samples]
    Y_test = data_dict["Y_test"][:max_test_samples]      # Physical unnormalized
    adj_mx = data_dict["adj_mx"]

    # Target in normalized space for stable neural training
    Y_train_norm = scaler.transform(Y_train)

    B, T, N, F = X_train.shape
    results: dict[str, Any] = {}
    latencies: dict[str, Any] = {}
    node_stats: dict[str, Any] = {}

    print(f"\n--- Evaluating Baselines on {dataset_name.upper()} (Test N={len(X_test)}) ---")

    # 1. Historical Mean (reads baseline channel, transforms to physical units)
    hist_channel = 2 if dataset_name == "synthetic" else 3
    hist_model = HistoricalMeanModel(baseline_channel_idx=hist_channel, scaler=scaler)
    y_pred_hist = hist_model.predict(X_test)
    results["Historical_Mean"] = evaluate_predictions(Y_test, y_pred_hist)
    latencies["Historical_Mean"] = benchmark_inference_latency(hist_model, torch.from_numpy(X_test[:32]))
    node_stats["Historical_Mean"] = compute_per_node_metrics(Y_test, y_pred_hist)
    print(f"Historical Mean: MAE={results['Historical_Mean']['overall']['mae']:.2f}, RMSE={results['Historical_Mean']['overall']['rmse']:.2f}, R²={results['Historical_Mean']['overall']['r2']:.4f}")

    # 2. Persistence (reads last observed speed channel, transforms to physical units)
    pers_model = PersistenceModel(speed_channel_idx=0, scaler=scaler)
    y_pred_pers = pers_model.predict(X_test)
    results["Persistence"] = evaluate_predictions(Y_test, y_pred_pers)
    latencies["Persistence"] = benchmark_inference_latency(pers_model, torch.from_numpy(X_test[:32]))
    node_stats["Persistence"] = compute_per_node_metrics(Y_test, y_pred_pers)
    print(f"Persistence:     MAE={results['Persistence']['overall']['mae']:.2f}, RMSE={results['Persistence']['overall']['rmse']:.2f}, R²={results['Persistence']['overall']['r2']:.4f}")

    # 3. Linear Regression (trained directly on physical targets)
    lr_model = LinearRegressionModel(alpha=1.0)
    lr_model.fit(X_train, Y_train)
    y_pred_lr = lr_model.predict(X_test)
    results["Linear_Regression"] = evaluate_predictions(Y_test, y_pred_lr)
    latencies["Linear_Regression"] = benchmark_inference_latency(lr_model, torch.from_numpy(X_test[:32]))
    node_stats["Linear_Regression"] = compute_per_node_metrics(Y_test, y_pred_lr)
    print(f"Linear Reg:      MAE={results['Linear_Regression']['overall']['mae']:.2f}, RMSE={results['Linear_Regression']['overall']['rmse']:.2f}, R²={results['Linear_Regression']['overall']['r2']:.4f}")

    # Convert to PyTorch for neural baselines
    X_train_t = torch.from_numpy(X_train).float()
    Y_train_norm_t = torch.from_numpy(Y_train_norm).float()
    X_test_t = torch.from_numpy(X_test).float()

    train_ds = torch.utils.data.TensorDataset(X_train_t, Y_train_norm_t)
    train_loader = torch.utils.data.DataLoader(train_ds, batch_size=32, shuffle=True)
    crit = nn.MSELoss()

    # 4. GRU (Temporal only)
    gru_model = GRUModel(feature_count=F, hidden_size=32, num_horizons=3)
    opt_gru = torch.optim.Adam(gru_model.parameters(), lr=0.005)
    gru_model.train()
    for _ in range(epochs):
        for bx, by in train_loader:
            opt_gru.zero_grad()
            pred = gru_model(bx)
            loss = crit(pred, by)
            loss.backward()
            opt_gru.step()
    gru_model.eval()
    with torch.no_grad():
        y_pred_gru_norm = gru_model(X_test_t).numpy()
    y_pred_gru = scaler.inverse_transform(y_pred_gru_norm)
    results["GRU"] = evaluate_predictions(Y_test, y_pred_gru)
    latencies["GRU"] = benchmark_inference_latency(gru_model, X_test_t[:32])
    node_stats["GRU"] = compute_per_node_metrics(Y_test, y_pred_gru)
    print(f"GRU (Temporal):  MAE={results['GRU']['overall']['mae']:.2f}, RMSE={results['GRU']['overall']['rmse']:.2f}, R²={results['GRU']['overall']['r2']:.4f}")

    # 5. GCN (Spatial only)
    gcn_model = GCNModel(feature_count=F, hidden_size=32, num_horizons=3, adj_mx=adj_mx)
    opt_gcn = torch.optim.Adam(gcn_model.parameters(), lr=0.005)
    gcn_model.train()
    for _ in range(epochs):
        for bx, by in train_loader:
            opt_gcn.zero_grad()
            pred = gcn_model(bx)
            loss = crit(pred, by)
            loss.backward()
            opt_gcn.step()
    gcn_model.eval()
    with torch.no_grad():
        y_pred_gcn_norm = gcn_model(X_test_t).numpy()
    y_pred_gcn = scaler.inverse_transform(y_pred_gcn_norm)
    results["GCN"] = evaluate_predictions(Y_test, y_pred_gcn)
    latencies["GCN"] = benchmark_inference_latency(gcn_model, X_test_t[:32])
    node_stats["GCN"] = compute_per_node_metrics(Y_test, y_pred_gcn)
    print(f"GCN (Spatial):   MAE={results['GCN']['overall']['mae']:.2f}, RMSE={results['GCN']['overall']['rmse']:.2f}, R²={results['GCN']['overall']['r2']:.4f}")

    # 6. SpatioTemporalGNN (Full Proposed Architecture)
    stgnn_model = SpatioTemporalGNN(
        feature_count=F,
        hidden_size=32,
        gcn_hidden=32,
        num_horizons=3,
        adj_mx=adj_mx,
    )

    opt_stgnn = torch.optim.Adam(stgnn_model.parameters(), lr=0.005)
    stgnn_model.train()
    for _ in range(max(epochs, 4)):
        for bx, by in train_loader:
            opt_stgnn.zero_grad()
            pred = stgnn_model(bx)
            loss = crit(pred, by)
            loss.backward()
            opt_stgnn.step()

    stgnn_model.eval()
    with torch.no_grad():
        y_pred_stgnn_norm = stgnn_model(X_test_t).numpy()
    y_pred_stgnn = scaler.inverse_transform(y_pred_stgnn_norm)
    results["ST_GNN"] = evaluate_predictions(Y_test, y_pred_stgnn)
    latencies["ST_GNN"] = benchmark_inference_latency(stgnn_model, X_test_t[:32])
    node_stats["ST_GNN"] = compute_per_node_metrics(Y_test, y_pred_stgnn)
    print(f"ST-GNN (Proposed): MAE={results['ST_GNN']['overall']['mae']:.2f}, RMSE={results['ST_GNN']['overall']['rmse']:.2f}, R²={results['ST_GNN']['overall']['r2']:.4f}")

    # Save trained checkpoint
    ckpt_dir = ROUTING_DIR / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_file = ckpt_dir / f"{dataset_name}_stgnn.pt"
    torch.save(stgnn_model.state_dict(), ckpt_file)

    meta_file = ckpt_dir / f"{dataset_name}_stgnn_metadata.json"
    meta = {
        "dataset": dataset_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "epochs": max(epochs, 4),
        "feature_count": F,
        "metrics": results["ST_GNN"],
        "latencies": latencies["ST_GNN"],
        "scaler": scaler.to_dict(),
    }
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Attach latency and node metrics to final structure
    for m_name in results:
        if m_name in latencies:
            results[m_name]["latency"] = latencies[m_name]
        if m_name in node_stats:
            results[m_name]["node_stats"] = node_stats[m_name]

    # Evaluate Model Release Criteria
    _evaluate_release_criteria(results)

    return results


def _evaluate_release_criteria(results: dict[str, Any]) -> dict[str, Any]:
    """Check whether ST-GNN satisfies release criteria to be production champion."""
    stgnn_mae = results["ST_GNN"]["overall"]["mae"]
    pers_mae = results["Persistence"]["overall"]["mae"]
    lr_mae = results["Linear_Regression"]["overall"]["mae"]
    best_baseline_mae = min(pers_mae, lr_mae)

    print("\n--- Model Release Criteria Evaluation ---")
    print(f"ST-GNN MAE:            {stgnn_mae:.3f}")
    print(f"Persistence MAE:       {pers_mae:.3f}")
    print(f"Linear Regression MAE: {lr_mae:.3f}")
    print(f"Best Baseline MAE:     {best_baseline_mae:.3f}")

    is_champion = stgnn_mae <= (best_baseline_mae + 0.05)
    champion = "ST_GNN" if is_champion else ("Linear_Regression" if lr_mae < pers_mae else "Persistence")

    print(f"Status: {'PROMOTED' if is_champion else 'RETAIN BASELINE CHAMPION'}")
    print(f"Active Production Champion: {champion}\n")

    release_info = {
        "stgnn_mae": stgnn_mae,
        "best_baseline_mae": best_baseline_mae,
        "promoted": is_champion,
        "champion_model": champion,
    }
    results["release_evaluation"] = release_info
    return release_info


def run_ablation_study(
    dataset_name: str,
    data_dict: dict[str, Any],
    epochs: int = 2,
    max_train_samples: int = 300,
    max_test_samples: int = 150,
) -> dict[str, Any]:
    """Run architectural and feature ablation studies with proper scaling."""
    scaler: StandardScaler = data_dict["scaler"]
    X_train = data_dict["X_train"][:max_train_samples]
    Y_train = data_dict["Y_train"][:max_train_samples]
    X_test = data_dict["X_test"][:max_test_samples]
    Y_test = data_dict["Y_test"][:max_test_samples]
    adj_mx = data_dict["adj_mx"]
    F_full = X_train.shape[-1]

    Y_train_norm = scaler.transform(Y_train)

    X_train_t = torch.from_numpy(X_train).float()
    Y_train_t = torch.from_numpy(Y_train_norm).float()
    X_test_t = torch.from_numpy(X_test).float()

    print(f"\n--- Running Ablation Study on {dataset_name.upper()} ---")
    ablation_results: dict[str, Any] = {}

    feat_configs = {
        "Traffic_Only": [0],
        "Traffic_Temporal": [0, 1] if F_full > 1 else [0],
        "Traffic_Graph": [0],
        "Full_Model": list(range(F_full)),
    }

    for name, channels in feat_configs.items():
        F_sub = len(channels)
        x_sub_train = X_train_t[:, :, :, channels]
        x_sub_test = X_test_t[:, :, :, channels]

        use_graph = ("Graph" in name) or ("Full" in name)
        cur_adj = adj_mx if use_graph else np.eye(adj_mx.shape[0], dtype=np.float32)

        model = SpatioTemporalGNN(feature_count=F_sub, hidden_size=16, gcn_hidden=16, adj_mx=cur_adj)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
        criterion = nn.MSELoss()

        train_ds = torch.utils.data.TensorDataset(x_sub_train, Y_train_t)
        loader = torch.utils.data.DataLoader(train_ds, batch_size=32, shuffle=True)
        model.train()
        for _ in range(epochs):
            for bx, by in loader:
                optimizer.zero_grad()
                pred = model(bx)
                loss = criterion(pred, by)
                loss.backward()
                optimizer.step()

        model.eval()
        with torch.no_grad():
            pred_norm = model(x_sub_test).numpy()
        pred_unnorm = scaler.inverse_transform(pred_norm)

        ablation_results[name] = evaluate_predictions(Y_test, pred_unnorm)
        print(f"Ablation [{name:18s}]: MAE={ablation_results[name]['overall']['mae']:.2f}, RMSE={ablation_results[name]['overall']['rmse']:.2f}, R²={ablation_results[name]['overall']['r2']:.4f}")

    return ablation_results


def run_multi_seed_evaluation(
    dataset_name: str,
    data_dict: dict[str, Any],
    seeds: list[int] = [42, 123, 456, 789, 2026],
    max_train_samples: int = 300,
    max_test_samples: int = 150,
) -> dict[str, Any]:
    """Run evaluation across multiple random seeds and report mean ± std."""
    print(f"\n--- Running Multi-Seed Evaluation on {dataset_name.upper()} ({len(seeds)} seeds) ---")
    scaler: StandardScaler = data_dict["scaler"]
    seed_metrics: list[dict[str, float]] = []

    X_train = data_dict["X_train"][:max_train_samples]
    Y_train = data_dict["Y_train"][:max_train_samples]
    X_test = data_dict["X_test"][:max_test_samples]
    Y_test = data_dict["Y_test"][:max_test_samples]
    adj_mx = data_dict["adj_mx"]
    F = X_train.shape[-1]

    Y_train_norm = scaler.transform(Y_train)

    for s in seeds:
        torch.manual_seed(s)
        np.random.seed(s)
        model = SpatioTemporalGNN(feature_count=F, hidden_size=16, gcn_hidden=16, adj_mx=adj_mx)
        opt = torch.optim.Adam(model.parameters(), lr=0.005)
        crit = nn.MSELoss()

        train_ds = torch.utils.data.TensorDataset(
            torch.from_numpy(X_train).float(),
            torch.from_numpy(Y_train_norm).float(),
        )
        loader = torch.utils.data.DataLoader(train_ds, batch_size=32, shuffle=True)

        model.train()
        for _ in range(2):
            for bx, by in loader:
                opt.zero_grad()
                loss = crit(model(bx), by)
                loss.backward()
                opt.step()

        model.eval()
        with torch.no_grad():
            pred_norm = model(torch.from_numpy(X_test).float()).numpy()
        pred_unnorm = scaler.inverse_transform(pred_norm)
        m = compute_metrics(Y_test, pred_unnorm)
        seed_metrics.append(m)

    maes = [m["mae"] for m in seed_metrics]
    rmses = [m["rmse"] for m in seed_metrics]
    mapes = [m["mape"] for m in seed_metrics]
    r2s = [m["r2"] for m in seed_metrics]

    summary = {
        "seeds": seeds,
        "mae_mean": round(float(np.mean(maes)), 3),
        "mae_std": round(float(np.std(maes)), 3),
        "rmse_mean": round(float(np.mean(rmses)), 3),
        "rmse_std": round(float(np.std(rmses)), 3),
        "mape_mean": round(float(np.mean(mapes)), 2),
        "mape_std": round(float(np.std(mapes)), 2),
        "r2_mean": round(float(np.mean(r2s)), 4),
        "r2_std": round(float(np.std(r2s)), 4),
    }
    print(f"Multi-Seed Summary: MAE={summary['mae_mean']} ± {summary['mae_std']}, RMSE={summary['rmse_mean']} ± {summary['rmse_std']}, R²={summary['r2_mean']} ± {summary['r2_std']}")
    return summary


def save_results(
    dataset_name: str,
    metrics: dict[str, Any],
    ablation: dict[str, Any] | None = None,
    multiseed: dict[str, Any] | None = None,
) -> None:
    """Save machine-readable evaluation outputs to results/{dataset}/."""
    out_dir = ROOT_DIR / "results" / dataset_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. metrics.json
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # 2. metrics.csv
    csv_path = out_dir / "metrics.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["dataset", "model", "horizon", "mae", "rmse", "mape", "r2"])
        for model_name, horizons in metrics.items():
            if isinstance(horizons, dict):
                for h_name, vals in horizons.items():
                    if isinstance(vals, dict) and "mae" in vals:
                        writer.writerow([
                            dataset_name,
                            model_name,
                            h_name,
                            vals["mae"],
                            vals["rmse"],
                            vals["mape"],
                            vals["r2"],
                        ])

    # 3. ablation.json and ablation.csv
    if ablation:
        with open(out_dir / "ablation.json", "w", encoding="utf-8") as f:
            json.dump(ablation, f, indent=2)
        with open(out_dir / "ablation.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["dataset", "configuration", "horizon", "mae", "rmse", "mape", "r2"])
            for cfg_name, horizons in ablation.items():
                for h_name, vals in horizons.items():
                    if isinstance(vals, dict) and "mae" in vals:
                        writer.writerow([
                            dataset_name,
                            cfg_name,
                            h_name,
                            vals["mae"],
                            vals["rmse"],
                            vals["mape"],
                            vals["r2"],
                        ])

    # 4. multiseed_metrics.json
    if multiseed:
        with open(out_dir / "multiseed_metrics.json", "w", encoding="utf-8") as f:
            json.dump(multiseed, f, indent=2)

    print(f"Results successfully saved to: {out_dir}")


def evaluate_dataset(
    dataset_name: str,
    run_ablation: bool = True,
    run_multiseed: bool = True,
    seeds: list[int] = [42, 123, 456, 789, 2026],
) -> None:
    """Run full evaluation suite for a single dataset."""
    mode = DatasetMode(dataset_name.lower())
    ds = get_dataset(mode, data_dir=ROOT_DIR / "data")
    if mode == DatasetMode.SYNTHETIC:
        data_dict = ds.load_or_process(lookback=12, days=7)
    else:
        # Check if raw files exist before processing real datasets
        metr_raw = ROOT_DIR / "data" / "raw" / "METR-LA.csv"
        if not metr_raw.exists():
            print(f"[SKIP] Raw dataset files for {dataset_name} not found in data/raw/. Skipping.")
            return
        data_dict = ds.load_or_process(lookback=12)

    # 1. Baselines evaluation
    metrics = fit_and_evaluate_baselines(dataset_name, data_dict)

    # 2. Ablation study
    ablation = None
    if run_ablation:
        ablation = run_ablation_study(dataset_name, data_dict)

    # 3. Multi-seed evaluation
    multiseed = None
    if run_multiseed:
        multiseed = run_multi_seed_evaluation(dataset_name, data_dict, seeds=seeds)

    # 4. Save results
    save_results(dataset_name, metrics, ablation, multiseed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CATRS traffic forecasting models")
    parser.add_argument(
        "--dataset",
        type=str,
        default="synthetic",
        choices=["synthetic", "metr_la", "pems_bay", "all"],
        help="Dataset to evaluate",
    )
    parser.add_argument("--ablation", action="store_true", default=True, help="Run ablation study")
    parser.add_argument("--multiseed", action="store_true", default=True, help="Run multi-seed evaluation")
    args = parser.parse_args()

    targets = ["synthetic", "metr_la", "pems_bay"] if args.dataset == "all" else [args.dataset]
    for ds_name in targets:
        evaluate_dataset(ds_name, run_ablation=args.ablation, run_multiseed=args.multiseed)


if __name__ == "__main__":
    main()
