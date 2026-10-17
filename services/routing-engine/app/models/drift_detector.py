"""Traffic speed distribution drift detector using Kolmogorov-Smirnov test and Population Stability Index (PSI)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any
import numpy as np

try:
    from scipy import stats
    HAS_SCIPY_STATS = True
except ImportError:
    stats = None
    HAS_SCIPY_STATS = False


@dataclass
class DriftReport:
    """Detailed dataset and model drift diagnostic summary."""
    metric: str
    psi: float
    ks_statistic: float
    ks_p_value: float
    is_drift_detected: bool
    drift_level: str  # "nominal", "moderate", "severe"
    sample_size: int
    baseline_size: int
    recommendation: str
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "psi": round(self.psi, 4),
            "ks_statistic": round(self.ks_statistic, 4),
            "ks_p_value": round(self.ks_p_value, 4),
            "is_drift_detected": self.is_drift_detected,
            "drift_level": self.drift_level,
            "sample_size": self.sample_size,
            "baseline_size": self.baseline_size,
            "recommendation": self.recommendation,
            "evaluated_at": self.evaluated_at,
        }


class DistributionDriftDetector:
    """Monitors live sensor distributions against training baseline using PSI & KS-test."""

    def __init__(
        self,
        baseline_speeds: np.ndarray | list[float] | None = None,
        *,
        num_bins: int = 10,
        psi_threshold: float = 0.20,
    ) -> None:
        self.num_bins = num_bins
        self.psi_threshold = psi_threshold
        # Default baseline modeled after standard urban speed limits (40-65 km/h mean)
        if baseline_speeds is None:
            np.random.seed(42)
            self.baseline = np.random.normal(loc=52.0, scale=12.0, size=500).clip(10.0, 110.0)
        else:
            self.baseline = np.asarray(baseline_speeds, dtype=float)

        self._bins = np.linspace(
            max(0.0, float(np.min(self.baseline)) - 5.0),
            float(np.max(self.baseline)) + 5.0,
            self.num_bins + 1,
        )
        self._baseline_hist, _ = np.histogram(self.baseline, bins=self._bins)
        # Add epsilon to prevent log(0)
        self._baseline_pct = (self._baseline_hist + 1e-4) / (np.sum(self._baseline_hist) + 1e-4 * self.num_bins)

    def evaluate_sample(
        self,
        live_speeds: np.ndarray | list[float],
        metric_name: str = "sensor_speed_kmh",
    ) -> DriftReport:
        """Calculate PSI and KS statistic between live observation sample and baseline."""
        sample = np.asarray(live_speeds, dtype=float).flatten()
        if len(sample) == 0:
            return DriftReport(
                metric=metric_name,
                psi=0.0,
                ks_statistic=0.0,
                ks_p_value=1.0,
                is_drift_detected=False,
                drift_level="nominal",
                sample_size=0,
                baseline_size=len(self.baseline),
                recommendation="Insufficient sample volume for drift assessment.",
            )

        # 1. Population Stability Index (PSI)
        live_hist, _ = np.histogram(sample, bins=self._bins)
        live_pct = (live_hist + 1e-4) / (np.sum(live_hist) + 1e-4 * self.num_bins)

        psi_val = float(np.sum((live_pct - self._baseline_pct) * np.log(live_pct / self._baseline_pct)))

        # 2. Two-sample Kolmogorov-Smirnov test
        if HAS_SCIPY_STATS:
            ks_res = stats.ks_2samp(self.baseline, sample)
            ks_stat = float(ks_res.statistic)
            ks_p = float(ks_res.pvalue)
        else:
            # Fallback empirical max distance between CDFs
            all_vals = np.sort(np.concatenate([self.baseline, sample]))
            cdf_base = np.searchsorted(np.sort(self.baseline), all_vals, side="right") / len(self.baseline)
            cdf_live = np.searchsorted(np.sort(sample), all_vals, side="right") / len(sample)
            ks_stat = float(np.max(np.abs(cdf_base - cdf_live)))
            ks_p = 0.05 if ks_stat > 0.2 else 0.50

        # Assess drift severity
        if psi_val >= self.psi_threshold or (ks_p < 0.01 and ks_stat > 0.25):
            drift_level = "severe"
            is_drift = True
            recommendation = "Severe distribution shift. Automated model retraining required."
        elif psi_val >= 0.10 or ks_stat > 0.15:
            drift_level = "moderate"
            is_drift = False
            recommendation = "Moderate drift observed. Monitor error residuals and candidate models."
        else:
            drift_level = "nominal"
            is_drift = False
            recommendation = "Distribution stable. Operating within expected calibration envelope."

        return DriftReport(
            metric=metric_name,
            psi=psi_val,
            ks_statistic=ks_stat,
            ks_p_value=ks_p,
            is_drift_detected=is_drift,
            drift_level=drift_level,
            sample_size=len(sample),
            baseline_size=len(self.baseline),
            recommendation=recommendation,
        )
