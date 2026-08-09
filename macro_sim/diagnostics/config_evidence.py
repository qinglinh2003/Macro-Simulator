"""Build a field-level evidence ledger from native Config batch reports."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


ACCEPTED_DIRECTION_RESULTS = {
    "exact_invariance",
    "not_directional",
    "pass",
    "pass_heterogeneous",
}


def _direction_results(arm: Mapping[str, Any]) -> tuple[str, ...]:
    results = []
    checks = arm.get("direction_checks")
    if not isinstance(checks, Mapping):
        return ()
    for check in checks.values():
        if isinstance(check, Mapping):
            result = check.get("result")
        else:
            result = check
        if isinstance(result, str):
            results.append(result)
    return tuple(results)


def _arm_resolved(arm: Mapping[str, Any]) -> bool:
    results = _direction_results(arm)
    return (
        not bool(arm.get("mechanism_silent", True))
        and bool(results)
        and all(result in ACCEPTED_DIRECTION_RESULTS for result in results)
    )


def _report_evidence(
    payload: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    source: str,
    formal_seed_count: int,
) -> dict[str, Any]:
    arms = tuple(report.get("arms", ()))
    resolved = tuple(_arm_resolved(arm) for arm in arms)
    direction_results = tuple(_direction_results(arm) for arm in arms)
    seed_count = len(payload.get("seeds", ()))
    if arms and all(resolved):
        strength = "formal_complete" if seed_count >= formal_seed_count else "pilot_complete"
    elif any(resolved):
        strength = "formal_partial" if seed_count >= formal_seed_count else "pilot_partial"
    elif arms:
        strength = (
            "formal_unresolved"
            if seed_count >= formal_seed_count
            else "pilot_unresolved"
        )
    else:
        strength = "no_evidence"
    return {
        "status": strength,
        "source": source,
        "population_per_country": int(payload.get("population_per_country", 0)),
        "seed_count": seed_count,
        "days": int(report.get("days", 0)),
        "stage": payload.get("stage"),
        "arm_count": len(arms),
        "resolved_arm_count": sum(resolved),
        "silent_arm_count": sum(
            arm.get("mechanism_silent") is True for arm in arms
        ),
        "inconclusive_arm_count": sum(
            "inconclusive" in results for results in direction_results
        ),
        "direction_failure_arm_count": sum(
            "fail" in results for results in direction_results
        ),
        "stability_failure_arm_count": sum(
            bool(arm.get("stability_failure")) for arm in arms
        ),
        "unjudged_arm_count": sum(not results for results in direction_results),
    }


def build_evidence_ledger(
    contracts: Iterable[Mapping[str, Any]],
    batch_reports: Iterable[tuple[str, Mapping[str, Any]]],
    *,
    minimum_population: int = 100_000,
    formal_seed_count: int = 4,
) -> dict[str, Any]:
    """Return the strongest native evidence found for every Config contract."""

    candidates: dict[str, list[dict[str, Any]]] = {}
    for source, payload in batch_reports:
        if int(payload.get("population_per_country", 0)) < minimum_population:
            continue
        for report in payload.get("reports", ()):
            field_name = report.get("contract", {}).get("field_name")
            if not isinstance(field_name, str):
                continue
            candidates.setdefault(field_name, []).append(
                _report_evidence(
                    payload,
                    report,
                    source=source,
                    formal_seed_count=formal_seed_count,
                )
            )

    rank = {
        "no_evidence": 0,
        "pilot_unresolved": 1,
        "formal_unresolved": 2,
        "pilot_partial": 3,
        "pilot_complete": 4,
        "formal_partial": 5,
        "formal_complete": 6,
    }
    rows = []
    for contract in contracts:
        role = str(contract["experiment_role"])
        field_name = str(contract["field_name"])
        if role != "causal_treatment":
            evidence = {
                "status": role,
                "source": None,
                "population_per_country": None,
                "seed_count": None,
                "days": None,
                "stage": None,
                "arm_count": 0,
                "resolved_arm_count": 0,
                "silent_arm_count": 0,
                "inconclusive_arm_count": 0,
                "direction_failure_arm_count": 0,
                "stability_failure_arm_count": 0,
                "unjudged_arm_count": 0,
            }
        else:
            field_candidates = candidates.get(field_name, ())
            evidence = max(
                field_candidates,
                key=lambda item: (
                    rank[item["status"]],
                    item["seed_count"],
                    item["population_per_country"],
                    item["days"],
                    item["source"],
                ),
                default={
                    "status": "no_evidence",
                    "source": None,
                    "population_per_country": None,
                    "seed_count": None,
                    "days": None,
                    "stage": None,
                    "arm_count": 0,
                    "resolved_arm_count": 0,
                    "silent_arm_count": 0,
                    "inconclusive_arm_count": 0,
                    "direction_failure_arm_count": 0,
                    "stability_failure_arm_count": 0,
                    "unjudged_arm_count": 0,
                },
            )
        rows.append(
            {
                "field_id": contract["field_id"],
                "field_name": field_name,
                "module": contract["module"],
                "experiment_role": role,
                **evidence,
            }
        )

    counts = Counter(row["status"] for row in rows)
    return {
        "schema_version": "config-causality-evidence-v1",
        "minimum_population": minimum_population,
        "formal_seed_count": formal_seed_count,
        "field_count": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "rows": rows,
    }
