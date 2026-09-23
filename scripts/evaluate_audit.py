"""Audit policy compliance verification evaluation for CATRS."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).parent.parent.resolve()
AUDIT_DIR = str(ROOT_DIR / "services" / "audit-service")
while AUDIT_DIR in sys.path:
    sys.path.remove(AUDIT_DIR)
sys.path.insert(0, AUDIT_DIR)
if "app" in sys.modules and not hasattr(sys.modules["app"], "policy_verifier"):
    for m in list(sys.modules.keys()):
        if m == "app" or m.startswith("app."):
            del sys.modules[m]

from app.batch_auditor import BatchAuditor
from app.policy_verifier import verify_route_outcome


def evaluate_audit_system(batch_size: int = 5000) -> dict[str, Any]:
    """Run compliance detection stress tests and high-volume batch throughput benchmarks."""
    schedule = {
        "version": "policy-2026-v1",
        "effective_date": "2026-08-01",
        "weights": {
            "emergency": 10.0,
            "transit": 3.0,
            "freight": 2.0,
            "commuter_general": 1.0,
        },
    }
    schedules = {"policy-2026-v1": schedule}

    # ── 1. Accuracy and Policy Detection Scenarios ──────────────────────────────
    scenarios = [
        # (Scenario Name, Outcome, Expected Valid, Expected Failure Type)
        (
            "Valid Outcome",
            {
                "trip_category": "emergency",
                "weight_applied": 10.0,
                "weight_schedule_version": "policy-2026-v1",
                "outcome_at": "2026-08-15T10:00:00Z",
            },
            True,
            None,
        ),
        (
            "Incorrect Priority Weight",
            {
                "trip_category": "emergency",
                "weight_applied": 1.0,  # tampered / wrong weight
                "weight_schedule_version": "policy-2026-v1",
                "outcome_at": "2026-08-15T10:00:00Z",
            },
            False,
            "applied priority weight does not match",
        ),
        (
            "Mismatched Policy Version",
            {
                "trip_category": "emergency",
                "weight_applied": 10.0,
                "weight_schedule_version": "policy-2025-v9",  # wrong version
                "outcome_at": "2026-08-15T10:00:00Z",
            },
            False,
            "weight schedule version does not match",
        ),
        (
            "Unknown Unresolved Policy",
            {
                "trip_category": "commuter_general",
                "weight_applied": 1.0,
                "weight_schedule_version": "non-existent-version-xyz",
                "outcome_at": "2026-08-15T10:00:00Z",
            },
            False,
            "could not be resolved",
        ),
        (
            "Missing / Empty Trip Category",
            {
                "trip_category": "",
                "weight_applied": 1.0,
                "weight_schedule_version": "policy-2026-v1",
                "outcome_at": "2026-08-15T10:00:00Z",
            },
            False,
            "trip_category is missing or empty",
        ),
        (
            "Inapplicable / Not Yet Effective Policy",
            {
                "trip_category": "emergency",
                "weight_applied": 10.0,
                "weight_schedule_version": "policy-2026-v1",
                "outcome_at": "2026-07-15T10:00:00Z",  # before effective date 2026-08-01
            },
            False,
            "was not yet effective",
        ),
    ]

    auditor = BatchAuditor()
    print("\n" + "=" * 80)
    print("           CATRS AUDIT POLICY VERIFICATION DETECTION SCENARIOS")
    print("=" * 80)

    detected_invalid = 0
    total_invalid = 0
    false_acceptances = 0

    for name, outcome, expected_valid, failure_fragment in scenarios:
        res = auditor.audit_batch([outcome], default_schedules=schedules)
        item = res.results[0]
        actual_valid = item["valid"]

        if not expected_valid:
            total_invalid += 1
            if not actual_valid:
                detected_invalid += 1
                status = "DETECTED (CORRECT)"
            else:
                false_acceptances += 1
                status = "MISSED (FALSE ACCEPTANCE)"
        else:
            status = "ACCEPTED (CORRECT)" if actual_valid else "FALSE REJECTION"

        failures_str = "; ".join(item["failures"]) if item["failures"] else "None"
        print(f"[{status:<24}] Scenario: {name}")
        print(f"   Outcome : {outcome}")
        print(f"   Failures: {failures_str}\n")

    detection_rate_pct = (detected_invalid / total_invalid) * 100.0 if total_invalid else 100.0
    false_acceptance_pct = (false_acceptances / total_invalid) * 100.0 if total_invalid else 0.0

    # ── 2. High-Volume Batch Audit Throughput Benchmark ──────────────────────────
    print("-" * 80)
    print(f"Executing Batch Audit Throughput Stress Test ({batch_size:,} records)...")
    batch_outcomes = []
    for i in range(batch_size):
        # 90% valid, 10% corrupted
        is_corrupted = (i % 10 == 0)
        batch_outcomes.append({
            "trip_category": "emergency" if i % 2 == 0 else "commuter_general",
            "weight_applied": 1.0 if is_corrupted else (10.0 if i % 2 == 0 else 1.0),
            "weight_schedule_version": "policy-2026-v1",
            "route_id": f"route_{i % 5}",
            "outcome_at": "2026-08-20T12:00:00Z",
        })

    t0 = time.perf_counter()
    batch_res = auditor.audit_batch(batch_outcomes, default_schedules=schedules)
    duration = time.perf_counter() - t0

    throughput_rps = batch_size / duration
    ms_per_thousand = (duration / batch_size) * 1000.0 * 1000.0

    print(f"Batch Processing Time : {duration * 1000.0:.2f} ms for {batch_size:,} outcomes")
    print(f"Audit Throughput      : {throughput_rps:,.0f} outcomes/second")
    print(f"Latency per 1k records: {ms_per_thousand:.2f} ms")
    print(f"Batch Summary Result  : Total={batch_res.total}, Valid={batch_res.valid_count}, Invalid={batch_res.invalid_count}, Unresolved={batch_res.unresolved_count}")
    print("=" * 80 + "\n")

    return {
        "detection_rate_pct": detection_rate_pct,
        "false_acceptance_pct": false_acceptance_pct,
        "batch_size": batch_size,
        "throughput_outcomes_per_sec": round(throughput_rps, 1),
        "latency_ms_per_1000": round(ms_per_thousand, 2),
        "total_processed": batch_res.total,
        "valid_count": batch_res.valid_count,
        "invalid_count": batch_res.invalid_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CATRS Audit Service")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch throughput stress test size")
    args = parser.parse_args()

    evaluate_audit_system(batch_size=args.batch_size)


if __name__ == "__main__":
    main()
