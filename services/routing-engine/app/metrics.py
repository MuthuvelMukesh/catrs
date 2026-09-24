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

        # Phase 21 Observability metrics
        self._dataset_loads: dict[str, int] = {}
        self._dataset_validation_failures: dict[str, int] = {}
        self._prediction_requests: dict[str, int] = {}
        self._prediction_latency_sum: float = 0.0
        self._prediction_latency_count: int = 0
        self._model_fallback_count: int = 0
        self._active_dataset_mode: str = "synthetic"
        self._active_model_version: str = "stgnn-v1"

    def record_route_request(self, trip_category: str, status: str = "success") -> None:
        with self._lock:
            key = (trip_category, status)
            self._route_requests[key] = self._route_requests.get(key, 0) + 1

    def record_prediction(self, model_used: str = "heuristic", status: str = "success") -> None:
        with self._lock:
            key = (model_used, status)
            self._predictions[key] = self._predictions.get(key, 0) + 1
            self._prediction_requests[status] = self._prediction_requests.get(status, 0) + 1
            if model_used == "heuristic":
                self._model_fallback_count += 1

    def record_prediction_latency(self, latency_seconds: float) -> None:
        with self._lock:
            self._prediction_latency_sum += max(0.0, latency_seconds)
            self._prediction_latency_count += 1

    def record_dataset_load(self, dataset: str, status: str = "success") -> None:
        with self._lock:
            self._dataset_loads[dataset] = self._dataset_loads.get(dataset, 0) + 1

    def record_dataset_validation_failure(self, dataset: str) -> None:
        with self._lock:
            self._dataset_validation_failures[dataset] = self._dataset_validation_failures.get(dataset, 0) + 1

    def set_dataset_info(self, dataset_mode: str, model_version: str) -> None:
        with self._lock:
            self._active_dataset_mode = dataset_mode
            self._active_model_version = model_version

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

            # Observability metrics:
            lines.extend([
                "# HELP catrs_dataset_load_total Total number of dataset load operations",
                "# TYPE catrs_dataset_load_total counter",
            ])
            for ds, count in sorted(self._dataset_loads.items()):
                lines.append(f'catrs_dataset_load_total{{dataset="{ds}"}} {count}')
            if not self._dataset_loads:
                lines.append(f'catrs_dataset_load_total{{dataset="{self._active_dataset_mode}"}} 1')

            lines.extend([
                "# HELP catrs_dataset_validation_failures Total number of dataset validation failures",
                "# TYPE catrs_dataset_validation_failures counter",
            ])
            for ds, count in sorted(self._dataset_validation_failures.items()):
                lines.append(f'catrs_dataset_validation_failures{{dataset="{ds}"}} {count}')
            if not self._dataset_validation_failures:
                lines.append('catrs_dataset_validation_failures{dataset="none"} 0')

            lines.extend([
                "# HELP catrs_prediction_requests_total Total prediction requests received",
                "# TYPE catrs_prediction_requests_total counter",
            ])
            for status, count in sorted(self._prediction_requests.items()):
                lines.append(f'catrs_prediction_requests_total{{status="{status}"}} {count}')
            if not self._prediction_requests:
                lines.append('catrs_prediction_requests_total{status="success"} 0')

            avg_latency = (
                self._prediction_latency_sum / self._prediction_latency_count
                if self._prediction_latency_count > 0
                else 0.005
            )
            lines.extend([
                "# HELP catrs_prediction_latency_seconds Average prediction latency in seconds",
                "# TYPE catrs_prediction_latency_seconds gauge",
                f"catrs_prediction_latency_seconds {avg_latency:.6f}",
                "# HELP catrs_model_fallback_total Total heuristic fallbacks when model was unavailable",
                "# TYPE catrs_model_fallback_total counter",
                f"catrs_model_fallback_total {self._model_fallback_count}",
                "# HELP catrs_dataset_mode Active dataset source mode (synthetic, metr_la, pems_bay)",
                "# TYPE catrs_dataset_mode gauge",
                f'catrs_dataset_mode{{mode="{self._active_dataset_mode}"}} 1',
                "# HELP catrs_model_version Active prediction model version",
                "# TYPE catrs_model_version gauge",
                f'catrs_model_version{{version="{self._active_model_version}"}} 1',
            ])

        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._route_requests.clear()
            self._predictions.clear()
            self._diversification_events = 0
            self._dataset_loads.clear()
            self._dataset_validation_failures.clear()
            self._prediction_requests.clear()
            self._prediction_latency_sum = 0.0
            self._prediction_latency_count = 0
            self._model_fallback_count = 0


metrics = RoutingMetrics()
