"""Batch auditor for verifying multiple route outcomes in a single call.

Processes a list of outcome records against their corresponding policy
versions, returning per-outcome results and a summary.
"""
from __future__ import annotations

from typing import Any

from app.policy_verifier import verify_route_outcome


class BatchAuditor:
    """Verify a batch of route outcomes against independently supplied policies.

    Parameters
    ----------
    policies:
        A repository implementing ``get_version(version=...)`` to look up
        weight schedule rows.  May be ``None`` for offline / test use when
        all outcomes carry an inline ``weight_schedule``.
    """

    def __init__(self, policies: Any | None = None) -> None:
        self._policies = policies

    def audit_batch(
        self,
        outcomes: list[dict[str, Any]],
        *,
        default_schedules: dict[str, dict[str, Any]] | None = None,
    ) -> "BatchAuditResult":
        """Audit a list of outcome dicts.

        For each outcome:
        - If ``default_schedules`` contains the outcome's version, that
          schedule is used.
        - Otherwise, the repository is queried by version.
        - Outcomes whose version cannot be resolved are recorded as failures.

        Parameters
        ----------
        outcomes:
            List of outcome dicts with at least ``weight_schedule_version``,
            ``trip_category``, and ``weight_applied``.
        default_schedules:
            Optional pre-loaded schedules keyed by version string.

        Returns
        -------
        BatchAuditResult
        """
        results: list[dict[str, Any]] = []
        valid_count = 0
        invalid_count = 0
        unresolved_count = 0

        for outcome in outcomes:
            version = outcome.get("weight_schedule_version", "")
            schedule = None
            if default_schedules and version in default_schedules:
                schedule = default_schedules[version]
            elif self._policies is not None:
                try:
                    schedule = self._policies.get_version(version=version)
                except Exception:
                    schedule = None

            if schedule is None:
                result = {
                    "outcome": outcome,
                    "valid": False,
                    "failures": [f"weight schedule version {version!r} could not be resolved"],
                    "weight_schedule_version": version,
                }
                unresolved_count += 1
            else:
                verification = verify_route_outcome(
                    outcome=outcome,
                    weight_schedule=schedule,
                )
                result = {"outcome": outcome, **verification}
                if verification["valid"]:
                    valid_count += 1
                else:
                    invalid_count += 1

            results.append(result)

        return BatchAuditResult(
            results=results,
            valid_count=valid_count,
            invalid_count=invalid_count,
            unresolved_count=unresolved_count,
        )


class BatchAuditResult:
    """Summary of a batch audit run."""

    def __init__(
        self,
        *,
        results: list[dict[str, Any]],
        valid_count: int,
        invalid_count: int,
        unresolved_count: int,
    ) -> None:
        self.results = results
        self.valid_count = valid_count
        self.invalid_count = invalid_count
        self.unresolved_count = unresolved_count
        self.total = len(results)

    @property
    def all_valid(self) -> bool:
        return self.invalid_count == 0 and self.unresolved_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "unresolved_count": self.unresolved_count,
            "all_valid": self.all_valid,
            "results": self.results,
        }

    def summary(self) -> dict[str, Any]:
        """Return a compact summary without per-result detail."""
        return {
            "total": self.total,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "unresolved_count": self.unresolved_count,
            "all_valid": self.all_valid,
        }
