from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class RunMode(str, Enum):
    """Operating mode for the routing engine."""

    SYNTHETIC = "synthetic"
    PRODUCTION = "production"


class DatasetMode(str, Enum):
    """Traffic dataset source mode."""

    SYNTHETIC = "synthetic"
    METR_LA = "metr_la"
    PEMS_BAY = "pems_bay"


@dataclass(frozen=True)
class FeedConfig:
    """Configuration for external data feed endpoints.

    When a URL is ``None`` the corresponding feed is disabled and the
    system falls back to synthetic data for that signal.
    """

    traffic_url: str | None = None
    weather_url: str | None = None
    incident_url: str | None = None
    event_url: str | None = None


@dataclass(frozen=True)
class Settings:
    """Typed configuration for the routing engine.

    All values can be set through environment variables.  When
    ``mode`` is ``synthetic`` every feed URL is ignored and the
    deterministic synthetic world is used for all data signals.
    """

    mode: RunMode = RunMode.SYNTHETIC
    dataset_mode: DatasetMode = DatasetMode.SYNTHETIC

    # Benchmark dataset paths
    metr_la_data_path: str = "data/raw/METR-LA.csv"
    metr_la_graph_path: str = "data/raw/adj_mx_METR-LA.pkl"
    pems_bay_data_path: str = "data/raw/PEMS-BAY.csv"
    pems_bay_graph_path: str = "data/raw/adj_mx_PEMS-BAY.pkl"

    database_url: str | None = None
    redis_url: str | None = None

    feeds: FeedConfig = field(default_factory=FeedConfig)

    # ST-GNN model settings
    stgnn_enabled: bool = False
    stgnn_checkpoint_path: str | None = None
    stgnn_feature_count: int = 9
    stgnn_node_count: int = 100
    stgnn_hidden_size: int = 32

    # Prediction defaults
    prediction_window_steps: int = 12
    prediction_interval_minutes: int = 5

    # Routing defaults
    default_cap_fraction: float = 1.0
    diversification_window_seconds: int = 60

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables."""
        mode_raw = os.environ.get("ROUTING_MODE", "synthetic").lower()
        mode = RunMode(mode_raw) if mode_raw in RunMode.__members__.values() else RunMode.SYNTHETIC

        ds_raw = os.environ.get("DATASET_MODE", "synthetic").lower()
        dataset_mode = DatasetMode(ds_raw) if ds_raw in [e.value for e in DatasetMode] else DatasetMode.SYNTHETIC

        feeds = FeedConfig(
            traffic_url=os.environ.get("TRAFFIC_FEED_URL"),
            weather_url=os.environ.get("WEATHER_FEED_URL"),
            incident_url=os.environ.get("INCIDENT_FEED_URL"),
            event_url=os.environ.get("EVENT_FEED_URL"),
        )

        return cls(
            mode=mode,
            dataset_mode=dataset_mode,
            metr_la_data_path=os.environ.get("METR_LA_DATA_PATH", "data/raw/METR-LA.csv"),
            metr_la_graph_path=os.environ.get("METR_LA_GRAPH_PATH", "data/raw/adj_mx_METR-LA.pkl"),
            pems_bay_data_path=os.environ.get("PEMS_BAY_DATA_PATH", "data/raw/PEMS-BAY.csv"),
            pems_bay_graph_path=os.environ.get("PEMS_BAY_GRAPH_PATH", "data/raw/adj_mx_PEMS-BAY.pkl"),
            database_url=os.environ.get("DATABASE_URL"),
            redis_url=os.environ.get("REDIS_URL"),
            feeds=feeds,
            stgnn_enabled=os.environ.get("STGNN_ENABLED", "").lower() in ("1", "true", "yes"),
            stgnn_checkpoint_path=os.environ.get("STGNN_CHECKPOINT_PATH"),
            stgnn_feature_count=int(os.environ.get("STGNN_FEATURE_COUNT", "9")),
            stgnn_node_count=int(os.environ.get("STGNN_NODE_COUNT", "100")),
            stgnn_hidden_size=int(os.environ.get("STGNN_HIDDEN_SIZE", "32")),
            prediction_window_steps=int(os.environ.get("PREDICTION_WINDOW_STEPS", "12")),
            prediction_interval_minutes=int(os.environ.get("PREDICTION_INTERVAL_MINUTES", "5")),
            default_cap_fraction=float(os.environ.get("DEFAULT_CAP_FRACTION", "1.0")),
            diversification_window_seconds=int(os.environ.get("DIVERSIFICATION_WINDOW_SECONDS", "60")),
        )
