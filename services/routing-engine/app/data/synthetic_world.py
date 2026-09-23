from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import math
import random
from typing import Any


class TrafficScenario(str, Enum):
    """Pre-configured synthetic traffic world simulation scenarios."""

    NORMAL = "normal"
    RUSH_HOUR = "rush_hour"
    SEVERE_CONGESTION = "severe_congestion"
    WEATHER_DEGRADATION = "weather_degradation"
    TRAFFIC_INCIDENT = "traffic_incident"
    MAJOR_EVENT = "major_event"
    INCIDENT_WEATHER = "incident_weather"
    EVENT_INCIDENT = "event_incident"
    SENSOR_DEGRADATION = "sensor_degradation"


@dataclass(frozen=True)
class SegmentReading:
    segment_id: str
    timestamp: datetime
    avg_speed: float
    vehicle_count: int


def generate_grid_graph(rows: int = 10, cols: int = 10, segment_length_m: float = 150.0) -> dict[str, Any]:
    """Create a synthetic NxM grid graph for the prototype (default 10x10 = 100 nodes)."""
    nodes = []
    edges = []
    for r in range(rows):
        for c in range(cols):
            node_id = f"n{r}_{c}"
            nodes.append({"id": node_id, "row": r, "col": c})
            if c < cols - 1:
                right_id = f"n{r}_{c + 1}"
                edges.append({
                    "segment_id": f"s{r}_{c}_{r}_{c + 1}",
                    "from_node": node_id,
                    "to_node": right_id,
                    "length_m": segment_length_m,
                })
            if r < rows - 1:
                down_id = f"n{r + 1}_{c}"
                edges.append({
                    "segment_id": f"s{r}_{c}_{r + 1}_{c}",
                    "from_node": node_id,
                    "to_node": down_id,
                    "length_m": segment_length_m,
                })
    return {"grid_size": (rows, cols), "nodes": nodes, "edges": edges}


def generate_synthetic_history(
    days: int = 7,
    interval_minutes: int = 5,
    scenario: TrafficScenario | str = TrafficScenario.NORMAL,
    seed: int = 42,
    start_time: datetime | None = None,
) -> list[dict[str, Any]]:
    """Generate synthetic traffic observations with daily/weekly seasonality and controllable scenarios.

    Parameters
    ----------
    days:
        Number of days to simulate.
    interval_minutes:
        Resolution in minutes between consecutive readings.
    scenario:
        Simulation scenario profile (e.g. normal, rush_hour, severe_congestion, etc.).
    seed:
        Deterministic pseudo-random seed for exact reproducibility.
    start_time:
        Starting datetime (defaults to 2026-01-01 00:00:00).
    """
    if isinstance(scenario, str):
        try:
            scenario = TrafficScenario(scenario.lower())
        except ValueError:
            scenario = TrafficScenario.NORMAL

    rng = random.Random(seed)
    graph = generate_grid_graph()
    edges = graph["edges"]
    start = start_time or datetime(2026, 1, 1, 0, 0)
    steps_per_day = (24 * 60) // interval_minutes
    rows: list[dict[str, Any]] = []

    # Identify bottleneck segments for incident/event scenarios
    incident_segments = {edges[i]["segment_id"] for i in range(min(10, len(edges)))}
    venue_segments = {edges[i]["segment_id"] for i in range(10, min(25, len(edges)))}

    for day_index in range(days):
        for step in range(steps_per_day):
            timestamp = start + timedelta(days=day_index, minutes=step * interval_minutes)
            hour = timestamp.hour
            weekday = timestamp.weekday()

            # Baseline speed and seasonal cycles
            base_speed = 55.0
            rush_factor = 1.0 if hour not in {7, 8, 17, 18} else 0.72
            weekend_factor = 0.9 if weekday >= 5 else 1.0
            seasonality = 1.0 + 0.12 * math.sin((hour / 24.0) * 2 * math.pi)
            speed = base_speed * rush_factor * weekend_factor * seasonality

            if (hour in {7, 8, 17, 18}) and (weekday < 5):
                speed *= 0.82
            if hour in {2, 3, 4}:
                speed *= 1.08

            # Scenario adjustments
            scenario_factor = 1.0
            volume_multiplier = 1.0

            if scenario == TrafficScenario.RUSH_HOUR:
                if hour in {7, 8, 9, 16, 17, 18, 19}:
                    scenario_factor = 0.65
                    volume_multiplier = 1.55
            elif scenario == TrafficScenario.SEVERE_CONGESTION:
                scenario_factor = 0.45
                volume_multiplier = 2.1
            elif scenario == TrafficScenario.WEATHER_DEGRADATION:
                scenario_factor = 0.70
                volume_multiplier = 0.95
            elif scenario == TrafficScenario.INCIDENT_WEATHER:
                scenario_factor = 0.55
                volume_multiplier = 1.15
            elif scenario == TrafficScenario.MAJOR_EVENT:
                if 17 <= hour <= 23:
                    volume_multiplier = 1.6

            for edge in edges:
                segment_id = edge["segment_id"]
                seg_speed = speed * scenario_factor
                seg_vol_mult = volume_multiplier

                # Localized incident effects
                if scenario in (
                    TrafficScenario.TRAFFIC_INCIDENT,
                    TrafficScenario.INCIDENT_WEATHER,
                    TrafficScenario.EVENT_INCIDENT,
                ) and segment_id in incident_segments:
                    if 7 <= hour <= 20:
                        seg_speed *= 0.35
                        seg_vol_mult *= 1.4

                # Localized event effects
                if scenario in (
                    TrafficScenario.MAJOR_EVENT,
                    TrafficScenario.EVENT_INCIDENT,
                ) and segment_id in venue_segments:
                    if 18 <= hour <= 23:
                        seg_speed *= 0.45
                        seg_vol_mult *= 1.85

                # Sensor degradation noise / jitter
                if scenario == TrafficScenario.SENSOR_DEGRADATION:
                    jitter = rng.uniform(-15.0, 15.0)
                    seg_speed = max(5.0, min(120.0, seg_speed + jitter))

                # Deterministic small variation per edge
                edge_seed_jitter = math.sin(hash(segment_id) % 1000 + step * 0.1) * 1.5
                final_speed = max(5.0, min(120.0, seg_speed + edge_seed_jitter))
                vehicle_count = max(10, int(((100 - final_speed) * 2.2 + 35) * seg_vol_mult))

                rows.append({
                    "segment_id": segment_id,
                    "timestamp": timestamp,
                    "avg_speed": round(final_speed, 3),
                    "vehicle_count": vehicle_count,
                })
    return rows


def build_historical_baseline(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int], float]:
    """Compute historical baseline speed averages grouped by (segment_id, weekday, hour)."""
    grouped: dict[tuple[str, int, int], list[float]] = {}
    for row in rows:
        key = (row["segment_id"], row["timestamp"].weekday(), row["timestamp"].hour)
        grouped.setdefault(key, []).append(float(row["avg_speed"]))
    return {key: sum(values) / len(values) for key, values in grouped.items()}


class DeterministicSyntheticWorld:
    """Configurable and reproducible synthetic environment."""

    def __init__(
        self,
        *,
        scenario: TrafficScenario | str = TrafficScenario.NORMAL,
        seed: int = 42,
        days: int = 7,
        interval_minutes: int = 5,
        start_time: datetime | None = None,
    ) -> None:
        self.scenario = (
            TrafficScenario(scenario.lower())
            if isinstance(scenario, str)
            else scenario
        )
        self.seed = seed
        self.days = days
        self.interval_minutes = interval_minutes
        self.start_time = start_time or datetime(2026, 1, 1, 0, 0)
        self.graph = generate_grid_graph()

    def generate_readings(self) -> list[dict[str, Any]]:
        return generate_synthetic_history(
            days=self.days,
            interval_minutes=self.interval_minutes,
            scenario=self.scenario,
            seed=self.seed,
            start_time=self.start_time,
        )

    def generate_baseline(self) -> dict[tuple[str, int, int], float]:
        readings = self.generate_readings()
        return build_historical_baseline(readings)
