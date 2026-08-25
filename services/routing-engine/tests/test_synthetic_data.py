from datetime import datetime, timedelta

from app.data.synthetic_world import (
    build_historical_baseline,
    generate_grid_graph,
    generate_synthetic_history,
)


def test_rush_hour_average_speed_is_lower_than_off_peak():
    rows = generate_synthetic_history(days=7, interval_minutes=5)

    rush_hours = [row for row in rows if row["timestamp"].hour in {7, 8, 17, 18}]
    off_peak = [row for row in rows if row["timestamp"].hour in {2, 3, 4}]

    rush_avg = sum(r["avg_speed"] for r in rush_hours) / len(rush_hours)
    off_avg = sum(r["avg_speed"] for r in off_peak) / len(off_peak)

    assert rush_avg < off_avg


def test_active_incident_reduces_speed_on_its_segment():
    rows = generate_synthetic_history(days=7, interval_minutes=5)
    segment_ids = sorted({row["segment_id"] for row in rows})
    target_segment = segment_ids[0]

    incident_window = [
        row for row in rows
        if row["segment_id"] == target_segment and row["timestamp"].hour in {9, 10}
    ]
    non_incident_window = [
        row for row in rows
        if row["segment_id"] == target_segment and row["timestamp"].hour in {2, 3}
    ]

    incident_avg = sum(r["avg_speed"] for r in incident_window) / len(incident_window)
    non_incident_avg = sum(r["avg_speed"] for r in non_incident_window) / len(non_incident_window)

    assert incident_avg < non_incident_avg


def test_historical_baseline_matches_manual_groupby():
    rows = generate_synthetic_history(days=7, interval_minutes=5)
    baseline = build_historical_baseline(rows)

    manual = {}
    for row in rows:
        key = (row["segment_id"], row["timestamp"].weekday(), row["timestamp"].hour)
        manual.setdefault(key, []).append(row["avg_speed"])

    expected = {
        key: sum(values) / len(values)
        for key, values in manual.items()
    }

    assert baseline == expected


def test_generate_grid_graph_has_10_by_10_grid_shape():
    graph = generate_grid_graph()
    assert len(graph["nodes"]) == 100
    assert len(graph["edges"]) > 0
    assert graph["grid_size"] == (10, 10)
