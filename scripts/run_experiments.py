"""Master experiment reproducibility orchestrator for CATRS research evaluation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
AUDIT_DIR = str(ROOT_DIR / "services" / "audit-service")
for p in (str(ROOT_DIR), ROUTING_DIR, AUDIT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib.util

from scripts.evaluate_audit import evaluate_audit_system
from scripts.evaluate_models import evaluate as evaluate_models
from scripts.evaluate_routing import evaluate_routing_policies

_train_script = ROOT_DIR / "services" / "routing-engine" / "scripts" / "train_stgnn.py"
_spec = importlib.util.spec_from_file_location("train_stgnn_mod", _train_script)
_train_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_train_module)
train_model = _train_module.train_model


def run_all_experiments(
    *,
    seed: int = 42,
    epochs: int = 5,
    days: int = 3,
    output_dir: str = str(ROOT_DIR / "experiments"),
) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    exp_timestamp = datetime.now(timezone.utc).isoformat()
    checkpoint_path = str(ROOT_DIR / "services" / "routing-engine" / "checkpoints" / f"stgnn_exp_{seed}.pt")

    print("\n" + "#" * 80)
    print(f"       CATRS RESEARCH EXPERIMENTAL REPRODUCIBILITY HARNESS")
    print(f"       Timestamp: {exp_timestamp} | Seed: {seed}")
    print("#" * 80 + "\n")

    # Step 1: Train ST-GNN Model
    print(">>> [Phase 1/4] Training Spatio-Temporal GNN Model...")
    train_results = train_model(
        days=days,
        epochs=epochs,
        checkpoint_path=checkpoint_path,
        seed=seed,
    )

    # Step 2: Model Prediction Evaluation
    print("\n>>> [Phase 2/4] Evaluating ST-GNN vs Fallback Heuristic...")
    model_eval = evaluate_models(
        checkpoint_path=checkpoint_path,
        days=days,
        seed=seed + 100,  # Separate holdout test seed
    )

    # Step 3: Routing Policy Evaluation
    print("\n>>> [Phase 3/4] Evaluating Routing Policies & Diversification Caps...")
    routing_eval = evaluate_routing_policies(total_trips=250, cap_fraction=0.35)

    # Step 4: Audit Verification & Throughput Evaluation
    print("\n>>> [Phase 4/4] Evaluating Audit Policy Verification & Throughput...")
    audit_eval = evaluate_audit_system(batch_size=2000)

    # Compile Experiment Manifest
    manifest = {
        "experiment_id": f"catrs-exp-{seed}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "timestamp": exp_timestamp,
        "parameters": {
            "seed": seed,
            "training_epochs": epochs,
            "training_days": days,
            "checkpoint_path": checkpoint_path,
        },
        "results": {
            "training": train_results,
            "model_evaluation": model_eval,
            "routing_evaluation": routing_eval,
            "audit_evaluation": audit_eval,
        },
    }

    manifest_file = os.path.join(output_dir, f"experiment_results_{seed}.json")
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 80)
    print(f"EXPERIMENTS COMPLETED! Comprehensive manifest written to:")
    print(f"  {manifest_file}")
    print("=" * 80 + "\n")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run complete reproducible CATRS experiments")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    parser.add_argument("--epochs", type=int, default=5, help="ST-GNN training epochs")
    parser.add_argument("--days", type=int, default=3, help="Synthetic history duration in days")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(ROOT_DIR / "experiments"),
        help="Directory to save experiment results",
    )
    args = parser.parse_args()

    run_all_experiments(
        seed=args.seed,
        epochs=args.epochs,
        days=args.days,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
