"""Prometheus metrics collector and formatter for the audit service."""
from __future__ import annotations

import threading
from typing import Any


class AuditMetrics:
    """In-memory metrics collector with Prometheus exposition format output."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._audits_total: dict[tuple[str, str], int] = {}
        self._batch_audits_total: int = 0
        self._policy_lookups_total: dict[str, int] = {}

    def record_audit(self, trip_category: str, valid: bool) -> None:
        result = "valid" if valid else "invalid"
        with self._lock:
            key = (trip_category, result)
            self._audits_total[key] = self._audits_total.get(key, 0) + 1

    def record_batch_audit(self) -> None:
        with self._lock:
            self._batch_audits_total += 1

    def record_policy_lookup(self, hit: bool) -> None:
        status = "hit" if hit else "miss"
        with self._lock:
            self._policy_lookups_total[status] = self._policy_lookups_total.get(status, 0) + 1

    def generate_metrics_text(self) -> str:
        """Generate Prometheus exposition format text."""
        lines = [
            "# HELP catrs_audits_total Total number of individual route outcome audits",
            "# TYPE catrs_audits_total counter",
        ]
        with self._lock:
            for (category, result), count in sorted(self._audits_total.items()):
                lines.append(
                    f'catrs_audits_total{{trip_category="{category}",result="{result}"}} {count}'
                )
            if not self._audits_total:
                lines.append('catrs_audits_total{trip_category="default",result="valid"} 0')

            lines.extend([
                "# HELP catrs_batch_audits_total Total batch audit requests processed",
                "# TYPE catrs_batch_audits_total counter",
                f"catrs_batch_audits_total {self._batch_audits_total}",
                "# HELP catrs_policy_lookups_total Total policy version lookups by status",
                "# TYPE catrs_policy_lookups_total counter",
            ])
            for status, count in sorted(self._policy_lookups_total.items()):
                lines.append(f'catrs_policy_lookups_total{{status="{status}"}} {count}')
            if not self._policy_lookups_total:
                lines.append('catrs_policy_lookups_total{status="hit"} 0')

        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._audits_total.clear()
            self._batch_audits_total = 0
            self._policy_lookups_total.clear()


metrics = AuditMetrics()
