from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Any


@dataclass(frozen=True)
class SegmentReading:
    segment_id: str
    timestamp: datetime
    avg_speed: float
    vehicle_count: int


def generate_grid_graph() -> dict[str, Any]:
    """Create a synthetic 10x10 grid graph for the prototype."""
    nodes = []
    edges = []
    for row in range(10):
        for col in range(10):
            node_id = f"n{row}_{col}"
            nodes.append({"id": node_id, "row": row, "col": col})
            if col < 9:
                right_id = f"n{row}_{col + 1}"
                edges.append({
                    "segment_id": f"s{row}_{col}_{row}_{col + 1}",
                    "from_node": node_id,
                    "to_node": right_id,
                    "length_m": 150.0,
                })
            if row < 9:
                down_id = f"n{row + 1}_{col}"
                edges.append({
                    "segment_id": f"s{row}_{col}_{row + 1}_{col}",
                    "from_node": node_id,
                    "to_node": down_id,
                    "length_m": 150.0,
                })
    return {"grid_size": (10, 10), "nodes": nodes, "edges": edges}


def generate_synthetic_history(days: int = 7, interval_minutes: int = 5) -> list[dict[str, Any]]:
    """Generate synthetic traffic observations with daily/weekly seasonality."""
    graph = generate_grid_graph()
    start = datetime(2026, 1, 1, 0, 0)
    rows: list[dict[str, Any]] = []
    for day_index in range(days):
        for step in range((24 * 60) // interval_minutes):
            timestamp = start + timedelta(days=day_index, minutes=step * interval_minutes)
            for edge in graph["edges"]:
                segment_id = edge["segment_id"]
                hour = timestamp.hour
                weekday = timestamp.weekday()
                base_speed = 55.0
                rush_factor = 1.0 if hour not in {7, 8, 17, 18} else 0.72
                weekend_factor = 0.9 if weekday >= 5 else 1.0
                seasonality = 1.0 + 0.12 * math.sin((timestamp.hour / 24.0) * 2 * math.pi)
                speed = base_speed * rush_factor * weekend_factor * seasonality
                if (hour in {7, 8, 17, 18}) and (weekday < 5):
                    speed *= 0.82
                if hour in {2, 3, 4}:
                    speed *= 1.08
                vehicle_count = max(20, int((90 - speed) * 2.2 + 35))
                rows.append({
                    "segment_id": segment_id,
                    "timestamp": timestamp,
                    "avg_speed": round(speed, 3),
                    "vehicle_count": vehicle_count,
                })
    return rows


def build_historical_baseline(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int], float]:
    """Compute a baseline by segment + weekday + hour."""
    grouped: dict[tuple[str, int, int], list[float]] = {}
    for row in rows:
        key = (row["segment_id"], row["timestamp"].weekday(), row["timestamp"].hour)
        grouped.setdefault(key, []).append(float(row["avg_speed"]))
    return {key: sum(values) / len(values) for key, values in grouped.items()}
