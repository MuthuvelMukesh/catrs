"""Deterministic synthetic dataset generation CLI for CATRS research reproducibility."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

# Ensure routing engine is in path
ROOT_DIR = Path(__file__).parent.parent.resolve()
ROUTING_DIR = str(ROOT_DIR / "services" / "routing-engine")
if ROUTING_DIR not in sys.path:
    sys.path.insert(0, ROUTING_DIR)

from app.data.synthetic_world import (
    TrafficScenario,
    build_historical_baseline,
    generate_grid_graph,
    generate_synthetic_history,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic traffic dataset for CATRS")
    parser.add_argument(
        "--scenario",
        type=str,
        default="normal",
        choices=[s.value for s in TrafficScenario],
        help="Simulation scenario",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    parser.add_argument("--days", type=int, default=7, help="Simulation duration in days")
    parser.add_argument("--interval", type=int, default=5, help="Interval in minutes")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / "scripts" / "synthetic_data.json"),
        help="Output file path",
    )
    args = parser.parse_args()

    print(f"Generating synthetic history (scenario={args.scenario}, seed={args.seed}, days={args.days})...")
    start_time = datetime(2026, 1, 1, 0, 0)
    rows = generate_synthetic_history(
        days=args.days,
        interval_minutes=args.interval,
        scenario=args.scenario,
        seed=args.seed,
        start_time=start_time,
    )
    baseline = build_historical_baseline(rows)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    serializable_rows = [
        {
            "segment_id": r["segment_id"],
            "timestamp": r["timestamp"].isoformat(),
            "avg_speed": r["avg_speed"],
            "vehicle_count": r["vehicle_count"],
        }
        for r in rows
    ]

    metadata = {
        "scenario": args.scenario,
        "seed": args.seed,
        "days": args.days,
        "interval_minutes": args.interval,
        "start_time": start_time.isoformat(),
        "total_readings": len(rows),
        "total_baseline_cells": len(baseline),
        "generated_at": datetime.now().isoformat(),
    }

    output_payload = {
        "metadata": metadata,
        "readings": serializable_rows,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)

    print(f"Dataset successfully exported to {args.output}")
    print(f"Total readings: {len(rows)} | Total baseline cells: {len(baseline)}")


if __name__ == "__main__":
    main()
