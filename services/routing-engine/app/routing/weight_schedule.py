from __future__ import annotations

from datetime import date


class WeightSchedule:
    """Append-only versioned schedule for routing priorities."""

    def __init__(self) -> None:
        self._versions: dict[str, dict[str, object]] = {}

    def insert_version(self, row: dict[str, object]) -> dict[str, object]:
        version = str(row["version"])
        if version in self._versions:
            raise ValueError(f"Weight version {version} already exists and is append-only.")
        effective_date = str(row["effective_date"])
        if any(existing["effective_date"] == effective_date for existing in self._versions.values()):
            raise ValueError("Effective date must be unique for a new weight version.")
        self._versions[version] = row
        return row

    def get_weight(self, trip_category: str, version: str | None = None) -> float:
        selected = self._versions[version] if version else next(reversed(self._versions.values()))
        weights = selected["weights"]
        return float(weights.get(trip_category, 1.0))
