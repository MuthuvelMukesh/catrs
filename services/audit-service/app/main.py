from datetime import date
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from app.policy_verifier import verify_route_outcome


class WeightSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    effective_date: date
    weights: dict[str, float] = Field(default_factory=dict)


class RouteOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_category: str
    weight_applied: float
    weight_schedule_version: str

app = FastAPI(title="Audit Service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/audit/outcome")
def audit_outcome(outcome: RouteOutcome, weight_schedule: WeightSchedule) -> dict[str, Any]:
    return verify_route_outcome(
        outcome=outcome.model_dump(),
        weight_schedule=weight_schedule.model_dump(mode="json"),
    )
