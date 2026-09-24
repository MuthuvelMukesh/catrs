from __future__ import annotations

import logging
import os
from typing import Any

from app.models.pipeline import build_feature_vector, compute_prediction

logger = logging.getLogger("catrs.prediction")


class PredictionService:
    """Use the model when available and retain a deterministic fallback."""

    def __init__(self, model: Any | None = None, node_count: int = 100) -> None:
        self._model = model
        self._node_count = node_count

    @classmethod
    def from_config(cls, config: Any) -> PredictionService:
        """Build a PredictionService from application configuration.

        When ``config.stgnn_enabled`` is ``True`` and PyTorch is
        available, an :class:`STGNNPredictor` is constructed. Otherwise
        the service operates in fallback-only mode.
        """
        model = None
        node_count = getattr(config, "stgnn_node_count", 100)
        if getattr(config, "stgnn_enabled", False):
            try:
                from app.models.st_gnn import STGNNPredictor

                model = STGNNPredictor(
                    feature_count=getattr(config, "stgnn_feature_count", 9),
                    node_count=node_count,
                    hidden_size=getattr(config, "stgnn_hidden_size", 32),
                )
                checkpoint_path = getattr(config, "stgnn_checkpoint_path", None)
                if checkpoint_path and not os.path.exists(checkpoint_path):
                    alt_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        checkpoint_path,
                    )
                    if os.path.exists(alt_path):
                        checkpoint_path = alt_path

                if checkpoint_path and os.path.exists(checkpoint_path):
                    import torch

                    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
                    model._model.load_state_dict(state)
                    logger.info("Loaded ST-GNN checkpoint from %s", checkpoint_path)
                elif checkpoint_path:
                    logger.warning("Checkpoint %s not found; ST-GNN fallback active", checkpoint_path)
                    model = None
            except Exception as exc:
                logger.warning("Failed to initialize ST-GNN (%s); falling back to heuristic", exc)
                model = None
        return cls(model=model, node_count=node_count)

    def build_single_segment_tensor(
        self,
        *,
        current_speed: float,
        current_volume: int,
        historical_baseline_speed: float,
        weather_severity_score: float = 0.0,
        active_incident_flag: bool = False,
        event_proximity_score: float = 0.0,
        upstream_segment_congestion: float = 0.0,
        time_of_day: int = 0,
        day_of_week: int = 0,
        window_steps: int = 12,
    ) -> Any:
        """Construct a 4D tensor [1, window_steps, node_count, 9] for ST-GNN inference from segment features."""
        import torch

        vec = build_feature_vector(
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
        flat_feats = [
            float(vec["current_speed"]),
            float(vec["current_volume"]),
            float(vec["historical_baseline_speed"]),
            float(vec["weather_severity_score"]),
            1.0 if vec["active_incident_flag"] else 0.0,
            float(vec["event_proximity_score"]),
            float(vec["upstream_segment_congestion"]),
            float(vec["time_of_day_sin"]),
            float(vec["time_of_day_cos"]),
        ]
        # Shape [1, window_steps, node_count, 9]
        node_slice = [flat_feats for _ in range(self._node_count)]
        window_slice = [node_slice for _ in range(window_steps)]
        return torch.tensor([window_slice], dtype=torch.float32)

    def predict(
        self,
        *,
        model_input: Any | None = None,
        fallback_inputs: dict[str, Any],
    ) -> dict[str, float]:
        if self._model is not None and model_input is not None:
            try:
                return self._model.predict(model_input)
            except Exception as exc:
                logger.warning("ST-GNN model inference failed (%s); falling back to heuristic", exc)
        return compute_prediction(**fallback_inputs)

    def predict_from_contexts(
        self,
        *,
        tensor: Any | None = None,
        fallback_inputs: dict[str, Any],
    ) -> dict[str, float]:
        """Predict using a pre-built tensor or fall back to heuristic."""
        return self.predict(model_input=tensor, fallback_inputs=fallback_inputs)

    @property
    def has_model(self) -> bool:
        """Whether a trained ML model is loaded."""
        return self._model is not None
