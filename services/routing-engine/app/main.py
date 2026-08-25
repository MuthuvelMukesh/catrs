from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field

from app.routing.priority_routing import rank_routes, route_trip
from app.runtime import RuntimeDependencies, build_runtime_dependencies


class RouteOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str
    travel_time_s: float
    priority_score: float = 1.0


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

app = FastAPI(title="Routing Engine")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/route")
def route(
    request: RouteRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if request.weight_schedule is None:
        if dependencies is None or request.weight_schedule_version is None:
            raise ValueError("weight_schedule_version is required for live policy lookup")
        request.weight_schedule = dependencies.weight_schedules.get_version(
            version=request.weight_schedule_version,
        )
    if dependencies is not None and request.weight_schedule_version is not None:
        request.weight_schedule = dependencies.weight_schedules.get_version(
            version=request.weight_schedule_version,
        )
    routes = [option.model_dump() for option in request.routes]
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
    return result
