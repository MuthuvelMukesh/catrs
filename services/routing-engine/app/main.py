from datetime import datetime, timezone
import math
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.metrics import metrics
from app.routing.priority_routing import rank_routes, route_trip
from app.routing.travel_time import enrich_routes_with_travel_time
from app.runtime import RuntimeDependencies, build_runtime_dependencies


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


app = FastAPI(title="Routing Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(
    full: bool = False,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if full:
        db_status = (
            "connected"
            if (dependencies is not None and dependencies.database_connection is not None)
            else "unavailable"
        )
        redis_status = (
            "connected"
            if (dependencies is not None and dependencies.route_counter is not None and dependencies.route_counter.is_available)
            else "unavailable"
        )
        model_status = (
            "loaded"
            if dependencies is not None and dependencies.prediction_service.has_model
            else "fallback"
        )
        return {
            "status": "ok",
            "database": db_status,
            "redis": redis_status,
            "predictor": model_status,
        }
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> str:
    """Return Prometheus formatted metrics exposition."""
    return metrics.generate_metrics_text()


@app.post("/predict")
def predict(
    request: PredictRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
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

    metrics.record_route_request(request.trip_category, status="success")
    return result
