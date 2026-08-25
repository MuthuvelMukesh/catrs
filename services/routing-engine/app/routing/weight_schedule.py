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

    def get_version(self, *, version: str | None = None, as_of: date | str | None = None) -> dict[str, object]:
        if version is not None:
            try:
                return self._versions[version]
            except KeyError as exc:
                raise ValueError(f"Unknown weight schedule version: {version}") from exc

        target_date = date.max if as_of is None else date.fromisoformat(str(as_of))
        eligible = [
            row for row in self._versions.values()
            if date.fromisoformat(str(row["effective_date"])) <= target_date
        ]
        if not eligible:
            raise ValueError(f"No weight schedule is effective on {target_date.isoformat()}")
        return max(eligible, key=lambda row: date.fromisoformat(str(row["effective_date"])))

    def get_weight(
        self,
        trip_category: str,
        version: str | None = None,
        as_of: date | str | None = None,
    ) -> float:
        selected = self.get_version(version=version, as_of=as_of)
        weights = selected["weights"]
        return float(weights.get(trip_category, 1.0))
