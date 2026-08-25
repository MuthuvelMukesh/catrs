import pytest


torch = pytest.importorskip("torch")

from app.models.st_gnn import STGNNPredictor


def test_st_gnn_predicts_three_horizons_from_twelve_steps():
    predictor = STGNNPredictor(feature_count=4, node_count=3)
    result = predictor.predict(torch.zeros((1, 12, 3, 4)))

    assert set(result) == {
        "predicted_speed_5m",
        "predicted_speed_15m",
        "predicted_speed_30m",
    }


def test_st_gnn_rejects_wrong_time_window():
    predictor = STGNNPredictor(feature_count=4, node_count=3)

    with pytest.raises(ValueError, match="12"):
        predictor.predict(torch.zeros((1, 6, 3, 4)))