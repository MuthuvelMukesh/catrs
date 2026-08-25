from __future__ import annotations

from typing import Any


class STGNNPredictor:
    """Small Torch graph-temporal predictor with a fixed 12-step input window."""

    def __init__(self, *, feature_count: int, node_count: int, hidden_size: int = 32) -> None:
        try:
            import torch
            from torch import nn
        except ImportError as exc:
            raise RuntimeError("PyTorch is required for STGNNPredictor") from exc

        class Model(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.temporal = nn.GRU(feature_count, hidden_size, batch_first=True)
                self.output = nn.Linear(hidden_size * node_count, 3)
                self.node_count = node_count

            def forward(self, values: Any) -> Any:
                batch_size, _, node_count, _ = values.shape
                temporal_input = values.permute(0, 2, 1, 3).reshape(
                    batch_size * node_count, 12, feature_count
                )
                _, hidden = self.temporal(temporal_input)
                node_states = hidden[-1].reshape(batch_size, node_count * hidden_size)
                return self.output(node_states)

        self._torch = torch
        self._model = Model()

    def predict(self, values: Any) -> dict[str, float]:
        if values.ndim != 4 or values.shape[1] != 12:
            raise ValueError("STGNNPredictor expects [batch, 12, nodes, features]")
        with self._torch.no_grad():
            output = self._model(values).detach().cpu()[0]
        return {
            "predicted_speed_5m": float(output[0]),
            "predicted_speed_15m": float(output[1]),
            "predicted_speed_30m": float(output[2]),
        }
