"""Unit tests for distribution drift detector."""
from __future__ import annotations

import numpy as np
import pytest

from app.models.drift_detector import DistributionDriftDetector


def test_drift_detector_stable_distribution():
    """Verify nominal status when test sample matches baseline distribution."""
    np.random.seed(42)
    baseline = np.random.normal(loc=50.0, scale=10.0, size=500)
    detector = DistributionDriftDetector(baseline_speeds=baseline)

    # Identical distribution sample
    live_sample = np.random.normal(loc=50.0, scale=10.0, size=300)
    report = detector.evaluate_sample(live_sample)

    assert report.is_drift_detected is False
    assert report.drift_level == "nominal"
    assert report.psi < 0.10


def test_drift_detector_detects_severe_shift():
    """Verify severe drift detection when traffic shifts significantly (e.g., severe storm/gridlock)."""
    np.random.seed(42)
    baseline = np.random.normal(loc=65.0, scale=8.0, size=500)
    detector = DistributionDriftDetector(baseline_speeds=baseline)

    # Severe congestion shift: average speed drops to 15 km/h
    gridlock_sample = np.random.normal(loc=15.0, scale=4.0, size=300)
    report = detector.evaluate_sample(gridlock_sample)

    assert report.is_drift_detected is True
    assert report.drift_level == "severe"
    assert report.psi >= 0.20
    assert "retraining" in report.recommendation.lower()


def test_drift_detector_empty_sample_safety():
    """Verify detector safely handles empty sample arrays without dividing by zero."""
    detector = DistributionDriftDetector()
    report = detector.evaluate_sample([])

    assert report.is_drift_detected is False
    assert report.sample_size == 0
