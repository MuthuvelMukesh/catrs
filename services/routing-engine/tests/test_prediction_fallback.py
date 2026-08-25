from app.models.fallback import fallback_urgency_score
from app.models.pipeline import build_feature_vector, compute_prediction


def test_feature_vector_includes_required_fields():
    vector = build_feature_vector(
        current_speed=40.0,
        current_volume=80,
        historical_baseline_speed=50.0,
        weather_severity_score=0.6,
        active_incident_flag=True,
        event_proximity_score=0.8,
        upstream_segment_congestion=0.5,
        time_of_day=18,
        day_of_week=2,
    )

    assert "current_speed" in vector
    assert "current_volume" in vector
    assert "historical_baseline_speed" in vector
    assert "weather_severity_score" in vector
    assert "active_incident_flag" in vector
    assert "event_proximity_score" in vector
    assert "upstream_segment_congestion" in vector
    assert "time_of_day_sin" in vector
    assert "time_of_day_cos" in vector
    assert "day_of_week_onehot" in vector


def test_fallback_urgency_score_uses_raw_speed_ratio():
    score = fallback_urgency_score(current_speed=42.0, historical_baseline_speed=60.0)
    assert abs(score - 0.7) < 1e-9


def test_prediction_reduces_to_reasonable_numeric_output():
    pred = compute_prediction(
        current_speed=46.0,
        current_volume=95,
        historical_baseline_speed=55.0,
        weather_severity_score=0.7,
        active_incident_flag=True,
        event_proximity_score=0.9,
        upstream_segment_congestion=0.45,
        time_of_day=18,
        day_of_week=2,
    )

    assert pred["predicted_speed_5m"] >= 0
    assert pred["predicted_speed_15m"] >= 0
    assert pred["predicted_speed_30m"] >= 0
