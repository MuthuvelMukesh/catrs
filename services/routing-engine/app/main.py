from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.metrics import metrics
from app.routing.priority_routing import rank_routes, route_trip
from app.routing.travel_time import enrich_routes_with_travel_time
from app.runtime import RuntimeDependencies, build_runtime_dependencies


class RouteOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str
    travel_time_s: float
    priority_score: float = 1.0
    distance_m: float | None = Field(default=None, gt=0.0)
    predicted_speed_5m: float | None = Field(default=None, gt=0.0)


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_category: str
    routes: list[RouteOption] = Field(min_length=1)
    request_count: int = Field(default=1, ge=1)
    current_counts: dict[str, int] = Field(default_factory=dict)
    cap_fraction: float = Field(default=1.0, gt=0.0, le=1.0)
    weight_schedule: dict[str, Any] | None = None
    weight_schedule_version: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    current_speed: float = Field(gt=0.0)
    current_volume: int = Field(ge=0)
    historical_baseline_speed: float = Field(gt=0.0)
    weather_severity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    active_incident_flag: bool = False
    event_proximity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    upstream_segment_congestion: float = Field(default=0.0, ge=0.0, le=1.0)
    time_of_day: int = Field(default=0, ge=0, le=23)
    day_of_week: int = Field(default=0, ge=0, le=6)


app = FastAPI(title="Routing Engine")


@app.get("/health")
def health(
    full: bool = False,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if full:
        db_status = "connected" if dependencies is not None else "unavailable"
        redis_status = "connected" if dependencies is not None else "unavailable"
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

    Uses the ST-GNN model when loaded, otherwise falls back to the heuristic.
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
    if prediction_service is not None:
        if prediction_service.has_model:
            model_used = "st_gnn"
        result = prediction_service.predict(
            model_input=None,
            fallback_inputs=fallback_inputs,
        )
    else:
        from app.models.pipeline import compute_prediction
        result = compute_prediction(**fallback_inputs)

    metrics.record_prediction(model_used=model_used, status="success")
    return {
        "segment_id": request.segment_id,
        **result,
    }


@app.post("/route")
def route(
    request: RouteRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if request.weight_schedule is None:
        if dependencies is None or request.weight_schedule_version is None:
            metrics.record_route_request(request.trip_category, status="error")
            raise HTTPException(
                status_code=422,
                detail="weight_schedule_version is required when no weight_schedule is provided",
            )
        request.weight_schedule = dependencies.weight_schedules.get_version(
            version=request.weight_schedule_version,
        )
    elif dependencies is not None and request.weight_schedule_version is not None:
        request.weight_schedule = dependencies.weight_schedules.get_version(
            version=request.weight_schedule_version,
        )

    # Derive travel times from predicted speed (centralised via travel_time module)
    routes = enrich_routes_with_travel_time(
        [option.model_dump() for option in request.routes]
    )

    ranked = rank_routes(
        trip_category=request.trip_category,
        routes=routes,
        weight_schedule=request.weight_schedule,
        include_explanation=True,
    )
    assignments = route_trip(
        trip_category=request.trip_category,
        route_options=routes,
        request_count=request.request_count,
        current_counts=request.current_counts,
        cap_fraction=request.cap_fraction,
        counter=None if dependencies is None else dependencies.route_counter,
        weight_schedule=request.weight_schedule,
    )
    result = {
        "ranked_routes": ranked["ranked_routes"],
        "assignments": assignments,
        "explanation": ranked["explanation"],
    }
    if dependencies is not None:
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

    metrics.record_route_request(request.trip_category, status="success")
    return result
