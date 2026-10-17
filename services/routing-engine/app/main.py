from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import RunMode, Settings
from app.metrics import metrics
from app.models.drift_detector import DistributionDriftDetector
from app.routing.audit_stream import AuditStreamProducer
from app.routing.priority_routing import rank_routes, route_trip
from app.routing.travel_time import enrich_routes_with_travel_time
from app.runtime import RuntimeDependencies, build_runtime_dependencies

logger = logging.getLogger("catrs.routing_engine")
settings = Settings.from_env()

_drift_detector = DistributionDriftDetector()
_audit_producer = AuditStreamProducer()


class RouteOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str = Field(min_length=1)
    travel_time_s: float = Field(gt=0.0)
    priority_score: float = Field(default=1.0, ge=0.0)
    distance_m: float | None = Field(default=None, gt=0.0)
    predicted_speed_5m: float | None = Field(default=None, gt=0.0)

    @field_validator("travel_time_s", "priority_score", "distance_m", "predicted_speed_5m")
    @classmethod
    def check_finite(cls, v: float | None) -> float | None:
        if v is not None and (math.isnan(v) or math.isinf(v)):
            raise ValueError("Numeric values must be finite (not NaN or Inf)")
        return v


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_category: str = Field(min_length=1)
    routes: list[RouteOption] = Field(min_length=1)
    request_count: int = Field(default=1, ge=1)
    current_counts: dict[str, int] = Field(default_factory=dict)
    cap_fraction: float = Field(default=1.0, gt=0.0, le=1.0)
    weight_schedule: dict[str, Any] | None = None
    weight_schedule_version: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_node: str = Field(min_length=1, description="Origin node identifier (e.g. N1)")
    destination_node: str = Field(min_length=1, description="Destination node identifier (e.g. N9)")
    trip_category: str = Field(default="commuter_general", min_length=1)
    request_count: int = Field(default=1, ge=1)
    cap_fraction: float = Field(default=1.0, gt=0.0, le=1.0)
    k_alternatives: int = Field(default=3, ge=1, le=10)
    weight_schedule_version: str | None = None


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(min_length=1)
    current_speed: float = Field(gt=0.0, le=300.0)
    current_volume: int = Field(ge=0, le=100000)
    historical_baseline_speed: float = Field(gt=0.0, le=300.0)
    weather_severity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    active_incident_flag: bool = False
    event_proximity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    upstream_segment_congestion: float = Field(default=0.0, ge=0.0, le=1.0)
    time_of_day: int = Field(default=0, ge=0, le=23)
    day_of_week: int = Field(default=0, ge=0, le=6)

    @field_validator(
        "current_speed",
        "historical_baseline_speed",
        "weather_severity_score",
        "event_proximity_score",
        "upstream_segment_congestion",
    )
    @classmethod
    def check_finite(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Numeric values must be finite (not NaN or Inf)")
        return v


class DatasetSelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str = Field(description="Dataset mode to switch to: synthetic, metr_la, or pems_bay")


# Global active dataset state
_active_dataset = "synthetic"

app = FastAPI(title="Routing Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
admin_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


def verify_routing_api_key(api_key: str | None = Security(api_key_header)) -> bool:
    current_settings = Settings.from_env()
    if current_settings.api_key:
        if not api_key or api_key != current_settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key (X-API-Key)")
    return True


def verify_admin_api_key(admin_key: str | None = Security(admin_key_header)) -> bool:
    current_settings = Settings.from_env()
    if current_settings.admin_api_key:
        if not admin_key or admin_key != current_settings.admin_api_key:
            raise HTTPException(status_code=403, detail="Invalid or missing Admin API key (X-Admin-API-Key)")
    return True


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.error(
        "Unhandled exception in routing engine on %s %s: %s",
        request.method,
        request.url.path,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred while processing routing request. Sensitive details have been redacted.",
        },
    )


@app.get("/health")
def health(
    full: bool = False,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if full:
        current_settings = Settings.from_env()
        db_status = (
            "connected"
            if (dependencies is not None and dependencies.database_connection is not None)
            else ("unavailable" if current_settings.mode == RunMode.PRODUCTION else "synthetic_memory")
        )
        redis_status = (
            "connected"
            if (dependencies is not None and dependencies.route_counter is not None and dependencies.route_counter.is_available)
            else "process_local_fallback"
        )
        model_status = (
            "loaded"
            if dependencies is not None and dependencies.prediction_service.has_model
            else "heuristic_fallback"
        )
        model_health = (
            dependencies.prediction_service.model_health_status
            if dependencies is not None
            else "uninitialized"
        )

        node_map = {"synthetic": 100, "metr_la": 207, "pems_bay": 325}
        label_map = {"synthetic": "SYNTHETIC", "metr_la": "METR-LA", "pems_bay": "PEMS-BAY"}
        version_map = {"synthetic": "stgnn-synthetic-v1", "metr_la": "stgnn-metrla-v1", "pems_bay": "stgnn-pemsbay-v1"}

        ds_key = _active_dataset.lower()
        metrics.set_dataset_info(ds_key, version_map.get(ds_key, "stgnn-v1"))

        overall_status = "healthy"
        if current_settings.mode == RunMode.PRODUCTION:
            if db_status == "unavailable" or redis_status == "process_local_fallback":
                overall_status = "degraded"

        return {
            "status": overall_status,
            "mode": current_settings.mode.value,
            "database": db_status,
            "redis": redis_status,
            "predictor": model_status,
            "predictor_health": model_health,
            "dataset": label_map.get(ds_key, "SYNTHETIC"),
            "dataset_mode": ds_key,
            "num_nodes": node_map.get(ds_key, 100),
            "sampling_interval": "5 min",
            "model": "ST-GNN" if model_status == "loaded" else "Heuristic",
            "model_version": version_map.get(ds_key, "stgnn-v1"),
            "horizons": ["5m", "15m", "30m"],
            "is_synthetic": current_settings.mode == RunMode.SYNTHETIC,
            "data_freshness": "live" if current_settings.mode != RunMode.SYNTHETIC else "simulated",
            "data_drift": _drift_detector.evaluate_sample([]).to_dict(),
            "audit_stream": {
                "published_count": _audit_producer.published_count,
                "buffered_count": _audit_producer.buffered_count,
            },
        }
    return {"status": "ok"}


@app.get("/models/drift")
def get_model_drift(
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_routing_api_key),
) -> dict[str, Any]:
    """Evaluate distribution drift on current sensor speed predictions vs training baseline."""
    sample: list[float] = []
    if dependencies is not None and dependencies.prediction_service is not None:
        try:
            pred = dependencies.prediction_service.predict(horizon=5)
            sample = [float(x) for x in pred.get("predictions", []) if x is not None]
        except Exception:
            pass
    report = _drift_detector.evaluate_sample(sample)
    return report.to_dict()


@app.get("/ready")
def ready(
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    """Readiness probe distinguishing a running process from one ready to serve traffic."""
    current_settings = Settings.from_env()
    if current_settings.mode == RunMode.PRODUCTION:
        if dependencies is None or dependencies.database_connection is None:
            raise HTTPException(status_code=503, detail="Database connection not ready")
    return {"status": "ready"}


@app.get("/dataset/info")
def dataset_info(
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    """Return active dataset details, node counts, sampling intervals, and model version."""
    node_map = {"synthetic": 100, "metr_la": 207, "pems_bay": 325}
    label_map = {"synthetic": "SYNTHETIC", "metr_la": "METR-LA", "pems_bay": "PEMS-BAY"}
    version_map = {"synthetic": "stgnn-synthetic-v1", "metr_la": "stgnn-metrla-v1", "pems_bay": "stgnn-pemsbay-v1"}

    ds_key = _active_dataset.lower()
    model_loaded = dependencies is not None and dependencies.prediction_service.has_model

    return {
        "dataset": label_map.get(ds_key, "SYNTHETIC"),
        "dataset_mode": ds_key,
        "num_nodes": node_map.get(ds_key, 100),
        "sampling_interval": "5 min",
        "model": "ST-GNN" if model_loaded else "Heuristic",
        "model_version": version_map.get(ds_key, "stgnn-v1"),
        "horizons": ["5m", "15m", "30m"],
        "available_datasets": ["synthetic", "metr_la", "pems_bay"],
    }


@app.post("/dataset/select")
def dataset_select(
    request: DatasetSelectRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _admin_authorized: bool = Depends(verify_admin_api_key),
) -> dict[str, Any]:
    """Select active dataset mode (synthetic, metr_la, pems_bay). Requires admin privileges when key configured."""
    global _active_dataset
    choice = request.dataset.lower()
    if choice not in ("synthetic", "metr_la", "pems_bay"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dataset '{choice}'. Must be 'synthetic', 'metr_la', or 'pems_bay'.",
        )

    _active_dataset = choice
    metrics.record_dataset_load(choice)
    version_map = {"synthetic": "stgnn-synthetic-v1", "metr_la": "stgnn-metrla-v1", "pems_bay": "stgnn-pemsbay-v1"}
    metrics.set_dataset_info(choice, version_map.get(choice, "stgnn-v1"))

    return {
        "status": "success",
        "selected_dataset": choice,
        "message": f"Active dataset set to {choice.upper()}",
    }


@app.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> str:
    """Return Prometheus formatted metrics exposition."""
    return metrics.generate_metrics_text()


@app.post("/predict")
def predict(
    request: PredictRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_routing_api_key),
) -> dict[str, Any]:
    """Return multi-horizon speed predictions for a single segment.

    Uses the ST-GNN model when loaded, otherwise gracefully falls back to the heuristic.
    """
    prediction_service = (
        dependencies.prediction_service
        if dependencies is not None
        else None
    )
    fallback_inputs = {
        "current_speed": request.current_speed,
        "current_volume": request.current_volume,
        "historical_baseline_speed": request.historical_baseline_speed,
        "weather_severity_score": request.weather_severity_score,
        "active_incident_flag": request.active_incident_flag,
        "event_proximity_score": request.event_proximity_score,
        "upstream_segment_congestion": request.upstream_segment_congestion,
        "time_of_day": request.time_of_day,
        "day_of_week": request.day_of_week,
    }
    model_used = "heuristic"
    result = None

    if prediction_service is not None and prediction_service.has_model:
        try:
            model_input = prediction_service.build_single_segment_tensor(
                current_speed=request.current_speed,
                current_volume=request.current_volume,
                historical_baseline_speed=request.historical_baseline_speed,
                weather_severity_score=request.weather_severity_score,
                active_incident_flag=request.active_incident_flag,
                event_proximity_score=request.event_proximity_score,
                upstream_segment_congestion=request.upstream_segment_congestion,
                time_of_day=request.time_of_day,
                day_of_week=request.day_of_week,
            )
            result = prediction_service.predict(
                model_input=model_input,
                fallback_inputs=fallback_inputs,
            )
            model_used = "st_gnn"
        except Exception:
            result = None

    if result is None:
        from app.models.pipeline import compute_prediction
        result = compute_prediction(**fallback_inputs)
        model_used = "heuristic"

    metrics.record_prediction(model_used=model_used, status="success")
    return {
        "segment_id": request.segment_id,
        "predicted_speed_5m": round(float(result["predicted_speed_5m"]), 3),
        "predicted_speed_15m": round(float(result["predicted_speed_15m"]), 3),
        "predicted_speed_30m": round(float(result["predicted_speed_30m"]), 3),
        "model_used": model_used,
    }


@app.post("/route")
def route(
    request: RouteRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_routing_api_key),
) -> dict[str, Any]:
    if request.weight_schedule is None:
        if dependencies is None or dependencies.weight_schedules is None or request.weight_schedule_version is None:
            metrics.record_route_request(request.trip_category, status="error")
            raise HTTPException(
                status_code=422,
                detail="weight_schedule_version is required when no weight_schedule is provided",
            )
        request.weight_schedule = dependencies.weight_schedules.get_version(
            version=request.weight_schedule_version,
        )
        if request.weight_schedule is None:
            metrics.record_route_request(request.trip_category, status="error")
            raise HTTPException(
                status_code=404,
                detail=f"Weight schedule version {request.weight_schedule_version!r} not found",
            )
    elif dependencies is not None and dependencies.weight_schedules is not None and request.weight_schedule_version is not None:
        loaded = dependencies.weight_schedules.get_version(version=request.weight_schedule_version)
        if loaded:
            request.weight_schedule = loaded

    # Derive travel times from predicted speed
    routes = enrich_routes_with_travel_time(
        [option.model_dump() for option in request.routes]
    )

    # 1. Compute assignments and diversification status
    assignments, div_info = route_trip(
        trip_category=request.trip_category,
        route_options=routes,
        request_count=request.request_count,
        current_counts=request.current_counts,
        cap_fraction=request.cap_fraction,
        counter=None if dependencies is None else dependencies.route_counter,
        weight_schedule=request.weight_schedule,
        return_diversification_info=True,
    )

    # 2. Rank routes and emit explanation matching actual assignment variables
    ranked = rank_routes(
        trip_category=request.trip_category,
        routes=routes,
        weight_schedule=request.weight_schedule,
        include_explanation=True,
        diversification_context=div_info,
    )

    if div_info.get("applied"):
        metrics.record_diversification_event()

    result = {
        "ranked_routes": ranked["ranked_routes"],
        "assignments": assignments,
        "explanation": ranked["explanation"],
    }

    if dependencies is not None and dependencies.route_outcomes is not None and dependencies.database_connection is not None:
        try:
            recommended = ranked["ranked_routes"][0]
            dependencies.route_outcomes.insert({
                "route_id": recommended["route_id"],
                "trip_category": request.trip_category,
                "weight_schedule_version": request.weight_schedule["version"],
                "weight_applied": recommended["weight_applied"],
                "predicted_travel_time_s": recommended["travel_time_s"],
                "observed_at": request.observed_at,
            })
            dependencies.database_connection.commit()
        except Exception:
            pass

    # Asynchronously publish routing outcome to audit stream
    try:
        _audit_producer.publish_outcome({
            "event_type": "route_allocation",
            "trip_category": request.trip_category,
            "recommended_route": result.get("explanation", {}).get("route_id"),
            "assignments": result.get("assignments", {}),
            "diversification": result.get("diversification", {}),
        })
    except Exception:
        pass

    metrics.record_route_request(request.trip_category, status="success")
    return result


@app.post("/route/plan")
def plan_route(
    request: PlanRouteRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_routing_api_key),
) -> dict[str, Any]:
    """Plan realistic graph-based route between origin and destination nodes.

    Uses topological RoadGraph with Dijkstra/A* algorithms,
    BPR congestion-aware travel times, and rolling diversification.
    """
    from app.routing.road_network import UnreachableDestinationError

    route_service = (
        dependencies.network_route_service
        if dependencies is not None and dependencies.network_route_service is not None
        else None
    )
    if route_service is None:
        from app.routing.route_generator import NetworkRouteService
        route_service = NetworkRouteService()

    weight_schedule = None
    if request.weight_schedule_version and dependencies is not None and dependencies.weight_schedules is not None:
        weight_schedule = dependencies.weight_schedules.get_version(version=request.weight_schedule_version)

    counter = dependencies.route_counter if dependencies is not None else None

    # Retrieve live ML speed predictions if model service is active
    predicted_speeds = None
    if dependencies is not None and dependencies.prediction_service is not None:
        try:
            pred_res = dependencies.prediction_service.predict(horizon=5)
            predicted_speeds = pred_res.get("predictions")
        except Exception:
            predicted_speeds = None

    try:
        plan = route_service.plan_trip(
            origin_node=request.origin_node,
            destination_node=request.destination_node,
            trip_category=request.trip_category,
            request_count=request.request_count,
            cap_fraction=request.cap_fraction,
            k_alternatives=request.k_alternatives,
            counter=counter,
            weight_schedule=weight_schedule,
            predicted_speeds=predicted_speeds,
        )
    except Exception as exc:
        if type(exc).__name__ == "UnreachableDestinationError" or isinstance(exc, UnreachableDestinationError):
            raise HTTPException(status_code=404, detail=str(exc))
        raise

    # Asynchronously publish plan outcome to audit stream
    try:
        _audit_producer.publish_outcome({
            "event_type": "graph_route_plan",
            "origin": request.origin_node,
            "destination": request.destination_node,
            "trip_category": request.trip_category,
            "assignments": plan.get("assignments", {}),
            "explanation": plan.get("explanation", {}),
        })
    except Exception:
        pass

    metrics.record_route_request(request.trip_category, status="success")
    return plan
