"""Prometheus metrics collector and formatter for the routing engine."""
from __future__ import annotations

import threading
from typing import Any


class RoutingMetrics:
    """In-memory metrics collector with Prometheus exposition format output."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._route_requests: dict[tuple[str, str], int] = {}
        self._predictions: dict[tuple[str, str], int] = {}
        self._diversification_events: int = 0
        self._total_travel_time_saved_s: float = 0.0

    def record_route_request(self, trip_category: str, status: str = "success") -> None:
        with self._lock:
            key = (trip_category, status)
            self._route_requests[key] = self._route_requests.get(key, 0) + 1

    def record_prediction(self, model_used: str = "heuristic", status: str = "success") -> None:
        with self._lock:
            key = (model_used, status)
            self._predictions[key] = self._predictions.get(key, 0) + 1

    def record_diversification_event(self) -> None:
        with self._lock:
            self._diversification_events += 1

    def generate_metrics_text(self) -> str:
        """Generate Prometheus exposition format text."""
        lines = [
            "# HELP catrs_route_requests_total Total number of routing requests processed",
            "# TYPE catrs_route_requests_total counter",
        ]
        with self._lock:
            for (category, status), count in sorted(self._route_requests.items()):
                lines.append(
                    f'catrs_route_requests_total{{trip_category="{category}",status="{status}"}} {count}'
                )
            if not self._route_requests:
                lines.append('catrs_route_requests_total{trip_category="default",status="success"} 0')

            lines.extend([
                "# HELP catrs_predictions_total Total segment predictions computed",
                "# TYPE catrs_predictions_total counter",
            ])
            for (model, status), count in sorted(self._predictions.items()):
                lines.append(
                    f'catrs_predictions_total{{model_used="{model}",status="{status}"}} {count}'
                )
            if not self._predictions:
                lines.append('catrs_predictions_total{model_used="heuristic",status="success"} 0')

            lines.extend([
                "# HELP catrs_diversification_events_total Total diversification events applied",
                "# TYPE catrs_diversification_events_total counter",
                f"catrs_diversification_events_total {self._diversification_events}",
            ])

        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._route_requests.clear()
            self._predictions.clear()
            self._diversification_events = 0


metrics = RoutingMetrics()
