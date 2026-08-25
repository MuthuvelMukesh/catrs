from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.models.pipeline import compute_prediction


class PredictionService:
    """Use the model when available and retain a deterministic fallback."""

    def __init__(self, model: Any | None = None) -> None:
        self._model = model

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
