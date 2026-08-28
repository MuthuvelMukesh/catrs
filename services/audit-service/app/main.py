from datetime import date, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.batch_auditor import BatchAuditor
from app.metrics import metrics
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


class BatchAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcomes: list[RouteOutcome] = Field(min_length=1)
    schedules: dict[str, WeightSchedule] = Field(default_factory=dict)


app = FastAPI(title="Audit Service")


@app.get("/health")
def health(
    full: bool = False,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if full:
        db_status = "connected" if dependencies is not None else "unavailable"
        return {"status": "ok", "database": db_status}
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> str:
    """Return Prometheus formatted metrics exposition."""
    return metrics.generate_metrics_text()


@app.post("/audit/outcome")
def audit_outcome(
    outcome: RouteOutcome,
    weight_schedule: WeightSchedule | None = None,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    if weight_schedule is None:
        if dependencies is None:
            metrics.record_policy_lookup(hit=False)
            raise HTTPException(status_code=503, detail="audit database is unavailable")
        policy = dependencies.policies.get_version(
            version=outcome.weight_schedule_version,
        )
        if policy is None:
            metrics.record_policy_lookup(hit=False)
            raise HTTPException(status_code=404, detail="weight schedule version was not found")
        metrics.record_policy_lookup(hit=True)
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

    metrics.record_audit(outcome.trip_category, result["valid"])
    return result


@app.post("/audit/batch")
def audit_batch(
    request: BatchAuditRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    """Audit multiple route outcomes in a single request.

    Inline schedules from the request body take priority; any version
    not present in the inline map is looked up via the DB when available.
    """
    default_schedules = {
        version: schedule.model_dump(mode="json")
        for version, schedule in request.schedules.items()
    }
    auditor = BatchAuditor(
        policies=None if dependencies is None else dependencies.policies,
    )
    batch_result = auditor.audit_batch(
        [outcome.model_dump(exclude_none=True) for outcome in request.outcomes],
        default_schedules=default_schedules,
    )

    if dependencies is not None:
        for item in batch_result.results:
            if item.get("valid") and item["outcome"].get("route_id") and item["outcome"].get("outcome_at"):
                dependencies.audit_results.insert({
                    "route_id": item["outcome"]["route_id"],
                    "outcome_at": item["outcome"]["outcome_at"],
                    "valid": item["valid"],
                    "failures": item["failures"],
                    "weight_schedule_version": item["weight_schedule_version"],
                })
        dependencies.database_connection.commit()

    metrics.record_batch_audit()
    for item in batch_result.results:
        cat = item["outcome"].get("trip_category", "default")
        metrics.record_audit(cat, item.get("valid", False))

    return batch_result.to_dict()


@app.post("/audit/summary")
def audit_summary(
    request: BatchAuditRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    """Return a compact summary without per-outcome detail."""
    default_schedules = {
        version: schedule.model_dump(mode="json")
        for version, schedule in request.schedules.items()
    }
    auditor = BatchAuditor(
        policies=None if dependencies is None else dependencies.policies,
    )
    batch_result = auditor.audit_batch(
        [outcome.model_dump(exclude_none=True) for outcome in request.outcomes],
        default_schedules=default_schedules,
    )
    metrics.record_batch_audit()
    return batch_result.summary()
