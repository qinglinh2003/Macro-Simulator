"""Matched finite-size comparisons for native Config screening batches."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping


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
                    ratio = (
                        large_difference / small_difference
                        if small_difference != 0.0
                        else None
                    )
                    status = "matched"
                metrics.append(
                    {
                        "metric_id": metric_id,
                        "statistic": statistic,
                        "status": status,
                        "reference_mean_difference": small_difference,
                        "confirmation_mean_difference": large_difference,
                        "confirmation_to_reference_ratio": ratio,
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

    return {
        "schema_version": "config-finite-size-confirmation-v1",
        "reference_population_per_country": small_population,
        "confirmation_population_per_country": large_population,
        "seeds": list(large.get("seeds", ())),
        "fields": compared_fields,
    }
