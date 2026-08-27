from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.models.pipeline import compute_prediction


class PredictionService:
    """Use the model when available and retain a deterministic fallback."""

    def __init__(self, model: Any | None = None) -> None:
        self._model = model

    @classmethod
    def from_config(cls, config: Any) -> PredictionService:
        """Build a PredictionService from application configuration.

        When ``config.stgnn_enabled`` is ``True`` and PyTorch is
        available, an :class:`STGNNPredictor` is constructed.  Otherwise
        the service operates in fallback-only mode.
        """
        model = None
        if getattr(config, "stgnn_enabled", False):
            try:
                from app.models.st_gnn import STGNNPredictor

                model = STGNNPredictor(
                    feature_count=config.stgnn_feature_count,
                    node_count=config.stgnn_node_count,
                    hidden_size=config.stgnn_hidden_size,
                )
                checkpoint_path = getattr(config, "stgnn_checkpoint_path", None)
                if checkpoint_path is not None:
                    import torch

                    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
                    model._model.load_state_dict(state)
            except (ImportError, RuntimeError, FileNotFoundError):
                model = None
        return cls(model=model)

    def predict(
        self,
        *,
        model_input: Any | None = None,
        fallback_inputs: dict[str, Any],
    ) -> dict[str, float]:
        if self._model is not None and model_input is not None:
            try:
                return self._model.predict(model_input)
            except (RuntimeError, ValueError):
                pass
        return compute_prediction(**fallback_inputs)

    def predict_from_contexts(
        self,
        *,
        tensor: Any | None = None,
        fallback_inputs: dict[str, Any],
    ) -> dict[str, float]:
        """Predict using a pre-built tensor or fall back to heuristic.

        This method is the preferred entry point for the full pipeline
        path where :func:`build_segment_tensor` has already produced a
        tensor from ingested :class:`SegmentContext` records.
        """
        return self.predict(model_input=tensor, fallback_inputs=fallback_inputs)

    @property
    def has_model(self) -> bool:
        """Whether a trained ML model is loaded."""
        return self._model is not None

