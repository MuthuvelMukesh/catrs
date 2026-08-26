from datetime import date, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.policy_verifier import verify_route_outcome
from app.runtime import RuntimeDependencies, build_runtime_dependencies


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
    route_id: str | None = None
    outcome_at: datetime | None = None

app = FastAPI(title="Audit Service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/audit/outcome")
def audit_outcome(
    outcome: RouteOutcome,
    weight_schedule: WeightSchedule | None = None,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if weight_schedule is None:
        if dependencies is None:
            raise HTTPException(status_code=503, detail="audit database is unavailable")
        policy = dependencies.policies.get_version(
            version=outcome.weight_schedule_version,
        )
        if policy is None:
            raise HTTPException(status_code=404, detail="weight schedule version was not found")
    else:
        policy = weight_schedule.model_dump(mode="json")

    result = verify_route_outcome(
        outcome=outcome.model_dump(exclude_none=True),
        weight_schedule=policy,
    )
    if dependencies is not None and outcome.route_id and outcome.outcome_at:
        dependencies.audit_results.insert({
            "route_id": outcome.route_id,
            "outcome_at": outcome.outcome_at,
            **result,
        })
        dependencies.database_connection.commit()
    return result
