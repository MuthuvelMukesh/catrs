from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from app.routing.priority_routing import rank_routes, route_trip


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
    weight_schedule: dict[str, Any]

app = FastAPI(title="Routing Engine")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/route")
def route(request: RouteRequest) -> dict[str, Any]:
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
    )
    return {
        "ranked_routes": ranked["ranked_routes"],
        "assignments": assignments,
        "explanation": ranked["explanation"],
    }
