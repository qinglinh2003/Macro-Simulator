"""Matched finite-size comparisons for native Config screening batches."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping


REPRESENTATIVE_CONFIRMATION_FIELDS: Mapping[str, str] = {
    "banking_and_credit": "household_credit",
    "consumption_prices_and_expectations": "alpha1",
    "demography_and_households": "demographic_annual_divorce_rate_base",
    "distribution_and_welfare": "mpc_dispersion",
    "energy": "energy_intensity",
    "firms_and_industrial_dynamics": "rho",
    "government_and_public_sector": "jg_productivity",
    "housing": "builder_productivity",
    "labor_market": "job_search_intensity",
    "open_economy": "migration_rate",
    "production_and_technology": "alpha",
    "securities_and_capital_markets": "wealth_effect",
}


def _canonical_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_report(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _reports_by_field(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    reports = {}
    for report in payload.get("reports", ()):
        field_name = str(report["contract"]["field_name"])
        if field_name in reports:
            raise ValueError(f"duplicate report for field {field_name!r}")
        reports[field_name] = report
    return reports


def _arms_by_value(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _canonical_value(arm["treatment_value"]): arm
        for arm in report.get("arms", ())
    }


def _effect(
    arm: Mapping[str, Any], metric_id: str, statistic: str
) -> Mapping[str, Any] | None:
    metric = arm.get("effects", {}).get(metric_id)
    if not isinstance(metric, Mapping):
        return None
    value = metric.get(statistic)
    return value if isinstance(value, Mapping) else None


def _finite_number(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _interval_excludes_zero(effect: Mapping[str, Any]) -> bool | None:
    low = _finite_number(effect.get("confidence_low"))
    high = _finite_number(effect.get("confidence_high"))
    if low is None or high is None:
        return None
    return not (low <= 0.0 <= high)


def _direction_results(arm: Mapping[str, Any]) -> dict[str, str]:
    results: dict[str, str] = {}
    for metric_id, check in arm.get("direction_checks", {}).items():
        if isinstance(check, Mapping) and isinstance(check.get("result"), str):
            results[str(metric_id)] = str(check["result"])
    return results


def _direction_gate(results: Mapping[str, str]) -> str:
    if not results:
        return "not_applicable"
    accepted = {"pass", "pass_heterogeneous"}
    return "pass" if all(value in accepted for value in results.values()) else "fail"


def compare_batch_reports(
    reference: str | Path | Mapping[str, Any],
    confirmation: str | Path | Mapping[str, Any],
    *,
    field_name: str | None = None,
) -> dict[str, Any]:
    """Compare otherwise identical 100k and 1M batch estimands.

    The function rejects mismatched horizons, activation scenarios, treatment
    levels, and seed sets.  That makes a reported difference attributable to
    finite population size rather than to an accidental experiment change.
    """

    small = _load_report(reference)
    large = _load_report(confirmation)
    small_population = int(small["population_per_country"])
    large_population = int(large["population_per_country"])
    if small_population >= large_population:
        raise ValueError("reference population must be smaller than confirmation")
    if tuple(small.get("seeds", ())) != tuple(large.get("seeds", ())):
        raise ValueError("finite-size comparison requires identical paired seeds")

    small_reports = _reports_by_field(small)
    large_reports = _reports_by_field(large)
    fields = (
        (field_name,)
        if field_name is not None
        else tuple(sorted(set(small_reports) & set(large_reports)))
    )
    if not fields:
        raise ValueError("no common Config field reports")

    compared_fields = []
    for field in fields:
        if field not in small_reports or field not in large_reports:
            raise ValueError(f"missing matched report for field {field!r}")
        small_report = small_reports[field]
        large_report = large_reports[field]
        small_contract = small_report["contract"]
        large_contract = large_report["contract"]
        contract_keys = (
            "scope",
            "field_name",
            "activation_scenario",
            "baseline_value",
            "treatment_values",
            "primary_metrics",
            "direction_statistics",
        )
        for key in contract_keys:
            if small_contract.get(key) != large_contract.get(key):
                raise ValueError(f"field {field!r} has mismatched contract {key!r}")
        if int(small_report["days"]) != int(large_report["days"]):
            raise ValueError(f"field {field!r} has mismatched horizons")
        if int(small_report["burn_in_days"]) != int(large_report["burn_in_days"]):
            raise ValueError(f"field {field!r} has mismatched burn-in horizons")

        small_arms = _arms_by_value(small_report)
        large_arms = _arms_by_value(large_report)
        if set(small_arms) != set(large_arms):
            raise ValueError(f"field {field!r} has mismatched treatment arms")

        arm_comparisons = []
        direction_statistics = small_contract.get("direction_statistics", {})
        for value_key in sorted(small_arms):
            small_arm = small_arms[value_key]
            large_arm = large_arms[value_key]
            reference_direction_results = _direction_results(small_arm)
            confirmation_direction_results = _direction_results(large_arm)
            metrics = []
            for metric_id in small_contract.get("primary_metrics", ()):
                statistic = direction_statistics.get(metric_id, "post_burnin_mean")
                small_effect = _effect(small_arm, metric_id, statistic)
                large_effect = _effect(large_arm, metric_id, statistic)
                if small_effect is None or large_effect is None:
                    metrics.append(
                        {
                            "metric_id": metric_id,
                            "statistic": statistic,
                            "status": "missing_estimand",
                        }
                    )
                    continue
                small_difference = _finite_number(small_effect.get("mean_difference"))
                large_difference = _finite_number(large_effect.get("mean_difference"))
                if small_difference is None or large_difference is None:
                    status = "non_finite"
                    sign_preserved = None
                    ratio = None
                else:
                    sign_preserved = (
                        small_difference == 0.0 == large_difference
                        or small_difference * large_difference > 0.0
                    )
                    raw_ratio = (
                        large_difference / small_difference
                        if small_difference != 0.0
                        else None
                    )
                    reference_per_person = small_difference / small_population
                    confirmation_per_person = large_difference / large_population
                    per_person_ratio = (
                        confirmation_per_person / reference_per_person
                        if reference_per_person != 0.0
                        else None
                    )
                    status = "matched"
                if status != "matched":
                    raw_ratio = None
                    reference_per_person = None
                    confirmation_per_person = None
                    per_person_ratio = None
                metrics.append(
                    {
                        "metric_id": metric_id,
                        "statistic": statistic,
                        "status": status,
                        "reference_mean_difference": small_difference,
                        "confirmation_mean_difference": large_difference,
                        "raw_confirmation_to_reference_ratio": raw_ratio,
                        "reference_difference_per_person": reference_per_person,
                        "confirmation_difference_per_person": confirmation_per_person,
                        "per_person_confirmation_to_reference_ratio": per_person_ratio,
                        "sign_preserved": sign_preserved,
                        "reference_interval_excludes_zero": _interval_excludes_zero(
                            small_effect
                        ),
                        "confirmation_interval_excludes_zero": _interval_excludes_zero(
                            large_effect
                        ),
                    }
                )
            arm_comparisons.append(
                {
                    "treatment_value": large_arm["treatment_value"],
                    "reference_direction_results": reference_direction_results,
                    "confirmation_direction_results": confirmation_direction_results,
                    "reference_direction_gate": _direction_gate(
                        reference_direction_results
                    ),
                    "confirmation_direction_gate": _direction_gate(
                        confirmation_direction_results
                    ),
                    "confirmation_mechanism_silent": bool(
                        large_arm.get("mechanism_silent", False)
                    ),
                    "confirmation_primary_effect_inconclusive": bool(
                        large_arm.get("primary_effect_inconclusive", False)
                    ),
                    "metrics": metrics,
                }
            )
        compared_fields.append(
            {
                "field_name": field,
                "scope": large_contract["scope"],
                "days": int(large_report["days"]),
                "burn_in_days": int(large_report["burn_in_days"]),
                "arms": arm_comparisons,
            }
        )

    direction_arms = [
        arm
        for field in compared_fields
        for arm in field["arms"]
        if arm["confirmation_direction_gate"] != "not_applicable"
    ]
    acceptance = {
        "direction_arm_count": len(direction_arms),
        "direction_failure_count": sum(
            arm["confirmation_direction_gate"] != "pass" for arm in direction_arms
        ),
        "mechanism_silent_count": sum(
            arm["confirmation_mechanism_silent"]
            for field in compared_fields
            for arm in field["arms"]
        ),
        "primary_inconclusive_count": sum(
            arm["confirmation_primary_effect_inconclusive"]
            for field in compared_fields
            for arm in field["arms"]
        ),
    }
    acceptance["accepted"] = (
        acceptance["direction_arm_count"] > 0
        and acceptance["direction_failure_count"] == 0
        and acceptance["mechanism_silent_count"] == 0
        and acceptance["primary_inconclusive_count"] == 0
    )
    return {
        "schema_version": "config-finite-size-confirmation-v1",
        "reference_population_per_country": small_population,
        "confirmation_population_per_country": large_population,
        "seeds": list(large.get("seeds", ())),
        "acceptance": acceptance,
        "fields": compared_fields,
    }
