from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TrafficReading:
    """Normalized traffic reading from any feed source."""

    segment_id: str
    timestamp: datetime
    avg_speed: float
    vehicle_count: int


@dataclass(frozen=True)
class WeatherReading:
    """Normalized weather severity for a geographic region."""

    region_id: str
    timestamp: datetime
    severity_score: float  # 0.0 = clear, 1.0 = severe


@dataclass(frozen=True)
class IncidentReading:
    """Active incident affecting a road segment."""

    segment_id: str
    timestamp: datetime
    active: bool
    severity: float  # 0.0 = minor, 1.0 = major


@dataclass(frozen=True)
class EventReading:
    """Event proximity score for a road segment."""

    segment_id: str
    timestamp: datetime
    proximity_score: float  # 0.0 = no event, 1.0 = at venue


class DataFeed(ABC):
    """Abstract interface for all data feed adapters.

    Every feed—whether backed by a live API or the synthetic world—
    implements the same ``fetch`` interface so the ingestion pipeline
    can treat them uniformly.
    """

    @abstractmethod
    def fetch(self, *, as_of: datetime | None = None) -> list[Any]:
        """Return normalized readings.

        Parameters
        ----------
        as_of:
            Optional timestamp indicating the query point.  For live
            feeds this is typically ignored or used as a cache key.
            For synthetic feeds it controls the generated window.
        """
