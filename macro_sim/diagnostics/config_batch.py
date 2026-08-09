"""Resumable native Config screening batches.

One native simulation already uses eight workers, so this runner executes arms
sequentially and caches shared control runs.  It never launches concurrent
worlds that would oversubscribe the host.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from macro_sim import native_backend
from macro_sim.diagnostics.config_contracts import TreatmentContract
from macro_sim.diagnostics.config_experiment import (
    DEFAULT_POPULATION,
    DEFAULT_WORKERS,
    PATHWISE_MATERIAL_RELATIVE_THRESHOLD,
    apply_native_activation_scenario,
    changed_metrics,
    effect_scales,
    native_nested_treatment_spec,
    native_treatment_spec,
    native_world_treatment_spec,
    population_scaled_new_game,
    run_native_spec_case,
    summarize_paired_runs,
    summarize_time_responses,
)


PATHWISE_MATERIAL_SHARE_THRESHOLD = 0.75


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _load_cached(path: Path, *, signature: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("run_signature") != signature:
        return None
    return dict(payload["result"])


def _run_or_load(
    *,
    path: Path,
    signature_payload: Mapping[str, Any],
    native_spec: Any,
    days: int,
    workers: int,
    burn_in_days: int,
    primary_metrics: Sequence[str],
    resume: bool,
) -> tuple[dict[str, Any], bool]:
    signature = _canonical_hash(signature_payload)
    if resume:
        cached = _load_cached(path, signature=signature)
        if cached is not None:
            return cached, True
    result = run_native_spec_case(
        native_spec,
        days=days,
        workers=workers,
        burn_in_days=burn_in_days,
        series_metric_ids=primary_metrics,
    )
    _atomic_json(
        path,
        {
            "schema_version": "config-native-run-cache-v1",
            "run_signature": signature,
            "signature": dict(signature_payload),
            "result": result,
        },
    )
    return result, False


def _direction_result(
    *,
    expected: str,
    effect: Mapping[str, Any],
    baseline_value: Any,
    treatment_value: Any,
    time_response: Mapping[str, Any] | None,
) -> str:
    difference = float(effect["mean_difference"])
    tolerance = 1.0e-12
    confidence_low = effect.get("confidence_low")
    confidence_high = effect.get("confidence_high")
    interval_unresolved = (
        confidence_low is None
        or confidence_high is None
        or float(confidence_low) <= 0.0 <= float(confidence_high)
    )
    if expected == "ambiguous":
        return "not_directional"
    if expected == "nonzero":
        mean_absolute = float(effect.get("mean_absolute_difference", abs(difference)))
        if abs(difference) <= tolerance and mean_absolute <= tolerance:
            return "fail"
        if not interval_unresolved:
            return "pass"
        pathwise_share = effect.get("pathwise_material_share")
        if (
            pathwise_share is not None
            and float(pathwise_share) >= PATHWISE_MATERIAL_SHARE_THRESHOLD
        ):
            return "pass_heterogeneous"
        return "inconclusive"
    if expected == "washout":
        if time_response is None:
            return "missing_time_path"
        peak = abs(float(time_response["peak_effect"]))
        terminal = abs(float(time_response["terminal_effect"]))
        if peak <= tolerance:
            return "fail"
        if (
            time_response.get("half_decay_tick") is not None
            and terminal <= peak / 2.0
        ):
            return "pass"
        return "inconclusive" if terminal < peak else "fail"
    if expected == "invariance":
        return (
            "requires_equivalence_bound"
            if abs(difference) > tolerance
            else "exact_invariance"
        )
    desired_sign = 1.0 if expected == "increase" else -1.0
    if (
        isinstance(baseline_value, (int, float))
        and not isinstance(baseline_value, bool)
        and isinstance(treatment_value, (int, float))
        and not isinstance(treatment_value, bool)
        and float(treatment_value) < float(baseline_value)
    ):
        desired_sign *= -1.0
    if abs(difference) <= tolerance:
        return "fail"
    observed_direction = difference * desired_sign
    if interval_unresolved:
        return "inconclusive"
    return "pass" if observed_direction > 0.0 else "fail"


def _arm_report(
    *,
    contract: TreatmentContract,
    treatment_value: Any,
    control_runs: Sequence[Mapping[str, Any]],
    treatment_runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    effects = summarize_paired_runs(control_runs, treatment_runs)
    responses = summarize_time_responses(control_runs, treatment_runs)
    changed = changed_metrics(effects)
    direction_checks: dict[str, dict[str, str]] = {}
    resolved_expected: list[str] = []
    for metric_id, expected in contract.expected_directions.items():
        if metric_id not in effects:
            direction_checks[metric_id] = {
                "statistic": contract.direction_statistics.get(
                    metric_id, "post_burnin_mean"
                ),
                "result": "missing_metric",
            }
            continue
        statistic = contract.direction_statistics.get(
            metric_id, "post_burnin_mean"
        )
        if statistic not in effects[metric_id]:
            direction_checks[metric_id] = {
                "statistic": statistic,
                "result": "missing_statistic",
            }
            continue
        result = _direction_result(
            expected=expected,
            effect=effects[metric_id][statistic],
            baseline_value=contract.baseline_value,
            treatment_value=treatment_value,
            time_response=responses.get(metric_id),
        )
        direction_checks[metric_id] = {
            "statistic": statistic,
            "result": result,
        }
        if result in {"pass", "pass_heterogeneous"}:
            resolved_expected.append(metric_id)
    changed_primary = sorted(set(changed) & set(contract.primary_metrics))
    resolved_primary = sorted(
        metric_id
        for metric_id in contract.primary_metrics
        if metric_id in effects
        and effects[metric_id]["post_burnin_mean"]["confidence_low"] is not None
        and not (
            float(effects[metric_id]["post_burnin_mean"]["confidence_low"])
            <= 0.0
            <= float(effects[metric_id]["post_burnin_mean"]["confidence_high"])
        )
    )
    return {
        "treatment_value": treatment_value,
        "effects": effects,
        "effect_scales": effect_scales(
            effects,
            control_value=contract.baseline_value,
            treatment_value=treatment_value,
        ),
        "time_responses": responses,
        "changed_metric_count": len(changed),
        "changed_metrics": changed,
        "changed_primary_metrics": changed_primary,
        "causally_resolved_primary_metrics": resolved_primary,
        "mechanism_silent": not changed,
        "primary_observable_silent": not changed_primary,
        "primary_effect_inconclusive": not resolved_primary,
        "direction_checks": direction_checks,
        "causally_resolved_expected_metrics": sorted(resolved_expected),
    }


def run_contract_batch(
    contracts: Sequence[TreatmentContract],
    *,
    seeds: Iterable[int],
    artifact_dir: Path,
    source_revision: str,
    stage: str,
    population: int = DEFAULT_POPULATION,
    days_override: int | None = None,
    workers: int = DEFAULT_WORKERS,
    burn_in_days: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    if not contracts:
        raise ValueError("at least one treatment contract is required")
    executable_statuses = {
        "screening_ready",
        "activation_scenario_required",
        "invariance_activation_required",
    }
    if any(contract.status not in executable_statuses for contract in contracts):
        raise ValueError("batch contains an unreviewed treatment contract")
    seed_values = tuple(seeds)
    if not seed_values:
        raise ValueError("at least one seed is required")
    if population < 100_000:
        raise ValueError("Config audit batches require at least 100,000 persons")

    run_metadata = {
        "source_revision": source_revision,
        "stage": stage,
        "population_per_country": population,
        "workers": workers,
        "seeds": list(seed_values),
    }
    grouped: dict[tuple[int, int, str], list[TreatmentContract]] = {}
    for contract in contracts:
        days = days_override or contract.horizon_days
        grouped.setdefault(
            (days, contract.countries, contract.activation_scenario), []
        ).append(contract)

    reports: list[dict[str, Any]] = []
    cache_hits = 0
    executed_runs = 0
    for (days, countries, activation_scenario), group in sorted(grouped.items()):
        resolved_burn_in = (
            min(90, max(1, days // 4), days - 1)
            if burn_in_days is None and days > 1
            else (burn_in_days or 0)
        )
        primary_metrics = tuple(
            sorted(
                set().union(
                    *(set(contract.primary_metrics) for contract in group)
                )
            )
        )
        controls: dict[int, dict[str, Any]] = {}
        baselines: dict[int, Any] = {}
        group_key = _canonical_hash(
            {
                **run_metadata,
                "days": days,
                "countries": countries,
                "activation_scenario": activation_scenario,
                "burn_in_days": resolved_burn_in,
                "metrics": primary_metrics,
            }
        )[:16]
        for seed in seed_values:
            baseline = population_scaled_new_game(
                population=population,
                days=days,
                seed=seed,
                countries=countries,
            )
            baselines[seed] = baseline
            signature = {
                **run_metadata,
                "case": "control",
                "seed": seed,
                "days": days,
                "countries": countries,
                "activation_scenario": activation_scenario,
                "burn_in_days": resolved_burn_in,
                "primary_metrics": primary_metrics,
            }
            control_spec = native_backend.build_native_new_game_spec(baseline)
            apply_native_activation_scenario(
                control_spec, scenario=activation_scenario
            )
            result, cached = _run_or_load(
                path=artifact_dir / "runs" / group_key / "control" / f"{seed}.json",
                signature_payload=signature,
                native_spec=control_spec,
                days=days,
                workers=workers,
                burn_in_days=resolved_burn_in,
                primary_metrics=primary_metrics,
                resume=resume,
            )
            controls[seed] = result
            cache_hits += int(cached)
            executed_runs += int(not cached)

        for contract in group:
            arms: list[dict[str, Any]] = []
            for value in contract.treatment_values:
                treatment_runs: list[dict[str, Any]] = []
                failures: list[dict[str, Any]] = []
                value_key = _canonical_hash(value)[:16]
                for seed in seed_values:
                    baseline = baselines[seed]
                    if contract.scope == "world":
                        treated = native_world_treatment_spec(
                            baseline, field=contract.field_name, value=value
                        )
                    elif contract.scope in {"relationship", "social"}:
                        treated = native_nested_treatment_spec(
                            baseline,
                            scope=contract.scope,
                            field=contract.field_name,
                            value=value,
                        )
                    else:
                        treated = native_treatment_spec(
                            baseline, field=contract.field_name, value=value
                        )
                    apply_native_activation_scenario(
                        treated, scenario=activation_scenario
                    )
                    signature = {
                        **run_metadata,
                        "case": "treatment",
                        "field_id": contract.field_id,
                        "value": value,
                        "seed": seed,
                        "days": days,
                        "countries": countries,
                        "activation_scenario": activation_scenario,
                        "burn_in_days": resolved_burn_in,
                        "primary_metrics": primary_metrics,
                    }
                    try:
                        result, cached = _run_or_load(
                            path=(
                                artifact_dir
                                / "runs"
                                / group_key
                                / contract.field_name
                                / value_key
                                / f"{seed}.json"
                            ),
                            signature_payload=signature,
                            native_spec=treated,
                            days=days,
                            workers=workers,
                            burn_in_days=resolved_burn_in,
                            primary_metrics=primary_metrics,
                            resume=resume,
                        )
                    except Exception as error:  # native stability is an estimand
                        failures.append(
                            {
                                "seed": seed,
                                "error_type": type(error).__name__,
                                "error": str(error),
                            }
                        )
                        executed_runs += 1
                        continue
                    treatment_runs.append(result)
                    cache_hits += int(cached)
                    executed_runs += int(not cached)
                if failures:
                    arms.append(
                        {
                            "treatment_value": value,
                            "stability_failure": True,
                            "completed_seed_count": len(treatment_runs),
                            "failures": failures,
                        }
                    )
                else:
                    arms.append(
                        _arm_report(
                            contract=contract,
                            treatment_value=value,
                            control_runs=[controls[seed] for seed in seed_values],
                            treatment_runs=treatment_runs,
                        )
                    )
            reports.append(
                {
                    "contract": asdict(contract),
                    "days": days,
                    "burn_in_days": resolved_burn_in,
                    "arms": arms,
                }
            )

    payload = {
        "schema_version": "config-causality-batch-v1",
        **run_metadata,
        "decision_thresholds": {
            "pathwise_material_relative": PATHWISE_MATERIAL_RELATIVE_THRESHOLD,
            "pathwise_material_share": PATHWISE_MATERIAL_SHARE_THRESHOLD,
        },
        "cache_hits": cache_hits,
        "executed_runs": executed_runs,
        "contract_count": len(contracts),
        "reports": reports,
    }
    _atomic_json(artifact_dir / "batch_report.json", payload)
    return payload
