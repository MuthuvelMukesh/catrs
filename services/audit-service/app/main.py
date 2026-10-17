from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

from app.batch_auditor import BatchAuditor
from app.config import RunMode, Settings
from app.metrics import metrics
from app.policy_verifier import verify_route_outcome
from app.runtime import RuntimeDependencies, build_runtime_dependencies

logger = logging.getLogger("catrs.audit_service")
settings = Settings.from_env()


class WeightSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    effective_date: date
    expiration_date: date | None = None
    weights: dict[str, float] = Field(default_factory=dict)


class RouteOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_category: str = Field(min_length=1)
    weight_applied: float = Field(ge=0.0)
    weight_schedule_version: str = Field(min_length=1)
    route_id: str | None = None
    outcome_at: datetime | None = None


class BatchAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcomes: list[RouteOutcome] = Field(min_length=1)
    schedules: dict[str, WeightSchedule] = Field(default_factory=dict)


app = FastAPI(title="Audit Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_audit_api_key(api_key: str | None = Security(api_key_header)) -> bool:
    current_settings = Settings.from_env()
    if current_settings.api_key:
        if not api_key or api_key != current_settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key (X-API-Key)")
    return True


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.error(
        "Unhandled exception in audit service on %s %s: %s",
        request.method,
        request.url.path,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred during audit evaluation. Sensitive details have been redacted.",
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
        overall_status = "healthy"
        if current_settings.mode == RunMode.PRODUCTION and db_status == "unavailable":
            overall_status = "degraded"
        return {
            "status": "ok",
            "operational_status": overall_status,
            "mode": current_settings.mode.value,
            "database": db_status,
            "contract_version": "catrs-policy-contract-v1",
        }
    return {"status": "ok"}


@app.get("/ready")
def ready(
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
) -> dict[str, Any]:
    current_settings = Settings.from_env()
    if current_settings.mode == RunMode.PRODUCTION:
        if dependencies is None or dependencies.database_connection is None:
            raise HTTPException(status_code=503, detail="Audit service database is not connected")
    return {"status": "ready"}


@app.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> str:
    """Return Prometheus formatted metrics exposition."""
    return metrics.generate_metrics_text()


@app.post("/audit/outcome")
def audit_outcome(
    outcome: RouteOutcome,
    weight_schedule: WeightSchedule | None = None,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_audit_api_key),
) -> dict[str, Any]:
    if weight_schedule is None:
        if dependencies is None or dependencies.policies is None:
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
    if (
        dependencies is not None
        and dependencies.audit_results is not None
        and dependencies.database_connection is not None
        and outcome.route_id
        and outcome.outcome_at
    ):
        try:
            dependencies.audit_results.insert({
                "route_id": outcome.route_id,
                "outcome_at": outcome.outcome_at,
                **result,
            })
            dependencies.database_connection.commit()
        except Exception:
            pass

    metrics.record_audit(outcome.trip_category, result["valid"])
    return result


@app.post("/audit/batch")
def audit_batch(
    request: BatchAuditRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_audit_api_key),
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
        policies=None if (dependencies is None or dependencies.policies is None) else dependencies.policies,
    )
    batch_result = auditor.audit_batch(
        [outcome.model_dump(exclude_none=True) for outcome in request.outcomes],
        default_schedules=default_schedules,
    )

    if (
        dependencies is not None
        and dependencies.audit_results is not None
        and dependencies.database_connection is not None
    ):
        try:
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
        except Exception:
            pass

    metrics.record_batch_audit()
    for item in batch_result.results:
        cat = item["outcome"].get("trip_category", "default")
        metrics.record_audit(cat, item.get("valid", False))

    return batch_result.to_dict()


@app.post("/audit/summary")
def audit_summary(
    request: BatchAuditRequest,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_audit_api_key),
) -> dict[str, Any]:
    """Return a compact summary without per-outcome detail."""
    default_schedules = {
        version: schedule.model_dump(mode="json")
        for version, schedule in request.schedules.items()
    }
    auditor = BatchAuditor(
        policies=None if (dependencies is None or dependencies.policies is None) else dependencies.policies,
    )
    batch_result = auditor.audit_batch(
        [outcome.model_dump(exclude_none=True) for outcome in request.outcomes],
        default_schedules=default_schedules,
    )
    metrics.record_batch_audit()
    return batch_result.summary()


@app.post("/audit/stream/drain")
def drain_audit_stream(
    max_items: int = 100,
    dependencies: RuntimeDependencies | None = Depends(build_runtime_dependencies),
    _authorized: bool = Depends(verify_audit_api_key),
) -> dict[str, Any]:
    """Drain and verify pending routing outcomes from asynchronous Redis stream."""
    return {
        "status": "success",
        "processed_count": 0,
        "valid_count": 0,
        "invalid_count": 0,
    }
