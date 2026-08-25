from __future__ import annotations

import math


def build_feature_vector(
    *,
    current_speed: float,
    current_volume: int,
    historical_baseline_speed: float,
    weather_severity_score: float,
    active_incident_flag: bool,
    event_proximity_score: float,
    upstream_segment_congestion: float,
    time_of_day: int,
    day_of_week: int,
) -> dict[str, float | int | bool | dict[str, float]]:
    """Build a simplified spatio-temporal feature vector for the prototype."""
    time_of_day_sin = math.sin((time_of_day / 24.0) * 2 * math.pi)
    time_of_day_cos = math.cos((time_of_day / 24.0) * 2 * math.pi)
    day_onehot = {
        "mon": 1.0 if day_of_week == 0 else 0.0,
        "tue": 1.0 if day_of_week == 1 else 0.0,
        "wed": 1.0 if day_of_week == 2 else 0.0,
        "thu": 1.0 if day_of_week == 3 else 0.0,
        "fri": 1.0 if day_of_week == 4 else 0.0,
        "sat": 1.0 if day_of_week == 5 else 0.0,
        "sun": 1.0 if day_of_week == 6 else 0.0,
    }
    return {
        "current_speed": current_speed,
        "current_volume": current_volume,
        "historical_baseline_speed": historical_baseline_speed,
        "weather_severity_score": weather_severity_score,
        "active_incident_flag": active_incident_flag,
        "event_proximity_score": event_proximity_score,
        "upstream_segment_congestion": upstream_segment_congestion,
        "time_of_day_sin": time_of_day_sin,
        "time_of_day_cos": time_of_day_cos,
        "day_of_week_onehot": day_onehot,
    }


def compute_prediction(
    *,
    current_speed: float,
    current_volume: int,
    historical_baseline_speed: float,
    weather_severity_score: float,
    active_incident_flag: bool,
    event_proximity_score: float,
    upstream_segment_congestion: float,
    time_of_day: int,
    day_of_week: int,
) -> dict[str, float]:
    """Return a lightweight multi-horizon prediction output for the prototype."""
    vector = build_feature_vector(
        current_speed=current_speed,
        current_volume=current_volume,
        historical_baseline_speed=historical_baseline_speed,
        weather_severity_score=weather_severity_score,
        active_incident_flag=active_incident_flag,
        event_proximity_score=event_proximity_score,
        upstream_segment_congestion=upstream_segment_congestion,
        time_of_day=time_of_day,
        day_of_week=day_of_week,
    )

    baseline = float(vector["historical_baseline_speed"])
    speed_delta = float(vector["current_speed"]) - baseline
    weather_penalty = float(vector["weather_severity_score"]) * 8.0
    incident_penalty = 10.0 if bool(vector["active_incident_flag"]) else 0.0
    event_penalty = float(vector["event_proximity_score"]) * 6.0
    congestion_penalty = float(vector["upstream_segment_congestion"]) * 12.0
    time_penalty = (1.0 - float(vector["time_of_day_cos"])) * 3.0

    base_prediction = max(5.0, baseline + speed_delta * 0.5 - weather_penalty - incident_penalty - event_penalty - congestion_penalty - time_penalty)
    return {
        "predicted_speed_5m": round(base_prediction, 3),
        "predicted_speed_15m": round(max(3.0, base_prediction * 0.92), 3),
        "predicted_speed_30m": round(max(2.0, base_prediction * 0.85), 3),
    }
