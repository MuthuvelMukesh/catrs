from app.models.prediction_service import PredictionService


FALLBACK_INPUTS = {
    "current_speed": 46.0,
    "current_volume": 95,
    "historical_baseline_speed": 55.0,
    "weather_severity_score": 0.7,
    "active_incident_flag": True,
    "event_proximity_score": 0.9,
    "upstream_segment_congestion": 0.45,
    "time_of_day": 18,
    "day_of_week": 2,
}


class BrokenModel:
    def predict(self, model_input):
        raise RuntimeError("model unavailable")


def test_prediction_service_uses_fallback_when_model_fails():
    prediction = PredictionService(BrokenModel()).predict(
        model_input=object(),
        fallback_inputs=FALLBACK_INPUTS,
    )

    assert set(prediction) == {
        "predicted_speed_5m",
        "predicted_speed_15m",
        "predicted_speed_30m",
    }


def test_prediction_service_uses_model_output_when_available():
    expected = {"predicted_speed_5m": 40.0, "predicted_speed_15m": 38.0, "predicted_speed_30m": 35.0}

    class Model:
        def predict(self, model_input):
            return expected

    assert PredictionService(Model()).predict(
        model_input=object(),
        fallback_inputs=FALLBACK_INPUTS,
    ) == expected