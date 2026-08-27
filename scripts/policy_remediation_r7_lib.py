"""R7 finite-size and rare-event confirmation for repaired policies.

Python only builds inputs, schedules native branches, and reduces maintained
metrics. Every simulated day is advanced by the C++ engine.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Callable, Mapping, Sequence

from macro_sim.diagnostics.config_experiment import summarize_paired_runs
from macro_sim.diagnostics.policy_catalog import (
    ACTIVATION_FIXTURES,
    METRIC_MATERIALITY,
)
from macro_sim.diagnostics.policy_contracts import (
    PolicyCausalContract,
    build_contracts,
    build_p0_payload,
)
from macro_sim.diagnostics.policy_crisis_effects import _canonical_hash
from macro_sim.diagnostics.policy_effects import (
    _countries,
    _native_scenario,
    _setup_actions,
    _target_economy,
)
from macro_sim.diagnostics.policy_scale_confirmation import (
    _all_integrity_passed,
    _effect_material,
    _run_selection_seed,
    _statistic,
)
from scripts.policy_remediation_r6_lib import assert_r6_native_build


R7_SCHEMA_VERSION = "policy-remediation-r7-v1"
R7_RUN_SIGNATURE_VERSION = "policy-remediation-r7-run-v1"
R7_CANDIDATES = (
    "mortgage_foreclosure_ltv",
    "gov_investment_share",
    "bankrupt_persist",
    "rental_eviction_arrears",
    "soe_efirm",
    "tariff",
    "fx_regime",
)
R7_POPULATIONS = (100_000, 1_000_000)
R7_SEEDS = (6203, 6221, 6247, 6271)
R7_NATIVE_WORKERS = 8
R7_SMALL_JOBS = 4
R7_LARGE_JOBS = 1
R7_MAX_RECORD_SECONDS = 1_200.0
R7_MAX_ESTIMATED_PEAK_BYTES = 16 * 1024**3

R7_ARM_LABELS: Mapping[str, str] = {
    "mortgage_foreclosure_ltv": "threshold_meaningful",
    "gov_investment_share": "arm_3",
    "bankrupt_persist": "threshold_meaningful",
    "rental_eviction_arrears": "arm_4",
    "soe_efirm": "arm_1",
    "tariff": "arm_2",
    "fx_regime": "arm_1",
}
R7_HORIZON_DAYS: Mapping[str, int] = {
    "mortgage_foreclosure_ltv": 90,
    "gov_investment_share": 30,
    "bankrupt_persist": 60,
    "rental_eviction_arrears": 60,
    "soe_efirm": 21,
    "tariff": 30,
    "fx_regime": 30,
}
R7_RARE_EVENT_METRICS: Mapping[str, str] = {
    "mortgage_foreclosure_ltv": "metric.source.m8.housing.foreclosures",
    "bankrupt_persist": "metric.source.m6.firm_defaults",
    "rental_eviction_arrears": "metric.source.m8.housing.evictions",
}
R7_SCALE_METRIC_OVERRIDES: Mapping[str, tuple[str, ...]] = {
    "rental_eviction_arrears": (
        "metric.source.m8.housing.evictions",
    ),
    # SOE ownership plus at-cost pricing has a direct, signed price channel.
    # Physical output remains an endogenous equilibrium response and did not
    # preserve one direction across the frozen R7 seeds, so retain it as an
    # exploratory side effect rather than an acceptance gate.
    "soe_efirm": (
        "metric.source.m8.energy.transaction_price",
    ),
}
R7_EXPLORATORY_METRICS: Mapping[str, tuple[str, ...]] = {
    "soe_efirm": (
        "metric.source.m8.energy.production",
    ),
}

# These are economy totals or event counts. Their first-order scale reference
# is proportionality to population. Prices and exchange rates are intensive.
R7_EXTENSIVE_METRICS = frozenset({
    "metric.source.m4.public_capital",
    "metric.source.m4.public_fixed_capital_formation",
    "metric.source.m6.firm_defaults",
    "metric.source.m6.firm_exits",
    "metric.source.m8.energy.production",
    "metric.source.m8.housing.evictions",
    "metric.source.m8.housing.foreclosures",
    "metric.source.m8.housing.rent_unpaid",
    "metric.source.m9.country.imports_volume",
    "metric.source.m9.country.peg_reserves",
    "metric.source.m9.country.tariff_revenue",
})

# Waiting hundreds of days for a legal threshold is not part of the causal
# estimand. R7 preserves the R6 three-to-one threshold ratio while placing the
# matched control and treatment near the event boundary.
R7_CONTROL_OVERRIDES: Mapping[str, tuple[tuple[str, Any], ...]] = {
    "rental_eviction_arrears": (("rental_eviction_arrears", 1),),
}
R7_ACTION_OVERRIDES: Mapping[str, tuple[Mapping[str, Any], ...]] = {
    "rental_eviction_arrears": ({
        "economy_id": 0,
        "lever": "rental_eviction_arrears",
        "value": 3,
    },),
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _reports_by_lever(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = payload.get("reports", ())
    output = {str(row["lever"]): row for row in rows}
    if len(output) != len(rows):
        raise ValueError("R6 evidence contains duplicate lever rows")
    return output


def _selected_arm(report: Mapping[str, Any], lever: str) -> Mapping[str, Any]:
    label = R7_ARM_LABELS[lever]
    matches = [
        row for row in report.get("activation", {}).get("arms", ())
        if row.get("label") == label
    ]
    if len(matches) != 1:
        raise ValueError(f"{lever}: expected one R6 activation arm {label!r}")
    arm = matches[0]
    if not arm.get("salient_proximal_metrics"):
        raise ValueError(f"{lever}: R6 arm has no salient proximal metric")
    return arm


def _contracts() -> dict[str, PolicyCausalContract]:
    contracts = {contract.lever: contract for contract in build_contracts()}
    missing = sorted(set(R7_CANDIDATES) - set(contracts))
    if missing:
        raise ValueError(f"missing R7 contracts: {missing}")
    return contracts


def build_r7_manifest(
    *,
    r6_p2: Mapping[str, Any],
    r6_acceptance: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    p0_hash = build_p0_payload()["hashes"]["p0_root"]
    if r6_p2.get("p0_root_hash") != p0_hash:
        errors.append("R6 mechanism evidence does not match the current P0 contract")
    if r6_acceptance.get("status") != "accepted":
        errors.append("R6 acceptance is not accepted")
    p2_reports = _reports_by_lever(r6_p2)
    r6_reports = _reports_by_lever(r6_acceptance)
    contracts = _contracts()
    selections: list[dict[str, Any]] = []
    for lever in R7_CANDIDATES:
        contract = contracts[lever]
        p2_report = p2_reports.get(lever)
        accepted_report = r6_reports.get(lever)
        if p2_report is None or accepted_report is None:
            errors.append(f"{lever}: missing R6 evidence")
            continue
        arm = _selected_arm(p2_report, lever)
        setup = list(_setup_actions(contract))
        setup.extend(R7_CONTROL_OVERRIDES.get(lever, ()))
        actions = R7_ACTION_OVERRIDES.get(lever, tuple(arm["actions"]))
        metrics = tuple(sorted(
            R7_SCALE_METRIC_OVERRIDES.get(
                lever, tuple(arm["salient_proximal_metrics"])
            )
        ))
        exploratory_metrics = tuple(sorted(
            R7_EXPLORATORY_METRICS.get(lever, ())
        ))
        selections.append({
            "lever": lever,
            "arm_label": R7_ARM_LABELS[lever],
            "r6_classification": accepted_report["classification"],
            "decision_group": contract.decision_group,
            "scenario": _native_scenario(contract),
            "countries": _countries(contract),
            "target_economy": _target_economy(contract),
            "days": R7_HORIZON_DAYS[lever],
            "setup_actions": _jsonable(setup),
            "actions": _jsonable(actions),
            "salient_metrics": list(metrics),
            "exploratory_metrics": list(exploratory_metrics),
            "activation_fixture": contract.activation_fixture,
            "activation_metrics": list(
                ACTIVATION_FIXTURES[contract.activation_fixture].activation_metrics
            ),
            "rare_event_metric": R7_RARE_EVENT_METRICS.get(lever),
            "r6_frozen_effects": {
                metric_id: arm["effects"][metric_id]
                for metric_id in (*metrics, *exploratory_metrics)
            },
            "time_compression": (
                {
                    "kind": "proportional_threshold_clock",
                    "r6_control": 90,
                    "r6_treatment": 270,
                    "r7_control": 1,
                    "r7_treatment": 3,
                    "ratio": 3.0,
                }
                if lever == "rental_eviction_arrears" else None
            ),
        })
    if len(selections) != len(R7_CANDIDATES):
        errors.append("R7 does not exactly cover seven candidates")
    payload = {
        "schema_version": R7_SCHEMA_VERSION,
        "p0_root_hash": p0_hash,
        "r6_p2_acceptance_hash": r6_p2.get("hashes", {}).get("p2_acceptance"),
        "r6_acceptance_hash": r6_acceptance.get("hashes", {}).get(
            "r6_acceptance"
        ),
        "populations_per_country": list(R7_POPULATIONS),
        "matched_seeds": list(R7_SEEDS),
        "native_workers": R7_NATIVE_WORKERS,
        "small_jobs": R7_SMALL_JOBS,
        "large_jobs": R7_LARGE_JOBS,
        "budgets": {
            "maximum_record_seconds": R7_MAX_RECORD_SECONDS,
            "maximum_estimated_peak_bytes": R7_MAX_ESTIMATED_PEAK_BYTES,
        },
        "selections": selections,
        "errors": errors,
    }
    payload["manifest_hash"] = _canonical_hash({
        key: value for key, value in payload.items() if key != "manifest_hash"
    })
    return payload


def _known_memory_bytes(value: Any) -> int:
    if not isinstance(value, Mapping):
        return 0
    direct = value.get("total_known")
    if isinstance(direct, (int, float)):
        return int(direct)
    return sum(_known_memory_bytes(item) for item in value.values())


def _record_budget(run: Mapping[str, Any]) -> dict[str, Any]:
    one_world = _known_memory_bytes(run.get("memory_bytes"))
    estimated_peak = math.ceil(one_world * 2.25)
    elapsed = float(run.get("elapsed_seconds", math.inf))
    return {
        "elapsed_seconds": elapsed,
        "one_world_known_bytes": one_world,
        "estimated_peak_known_bytes": estimated_peak,
        "wall_clock_passed": elapsed <= R7_MAX_RECORD_SECONDS,
        "memory_passed": estimated_peak <= R7_MAX_ESTIMATED_PEAK_BYTES,
        "passed": (
            elapsed <= R7_MAX_RECORD_SECONDS
            and estimated_peak <= R7_MAX_ESTIMATED_PEAK_BYTES
        ),
    }


def _seed_differences(
    runs: Sequence[Mapping[str, Any]], metric_id: str, statistic: str
) -> list[float]:
    return [
        _statistic(run["treatment"], metric_id, statistic)
        - _statistic(run["control"], metric_id, statistic)
        for run in runs
    ]


def _expected_sign(selection: Mapping[str, Any], metric_id: str) -> int:
    statistic = METRIC_MATERIALITY[metric_id].default_statistic
    difference = float(
        selection["r6_frozen_effects"][metric_id][statistic]["mean_difference"]
    )
    return 1 if difference > 0.0 else -1 if difference < 0.0 else 0


def _metric_scale_report(
    selection: Mapping[str, Any],
    metric_id: str,
    small: Sequence[Mapping[str, Any]],
    large: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    statistic = METRIC_MATERIALITY[metric_id].default_statistic
    small_effect = summarize_paired_runs(
        [row["control"] for row in small],
        [row["treatment"] for row in small],
    )
    large_effect = summarize_paired_runs(
        [row["control"] for row in large],
        [row["treatment"] for row in large],
    )
    small_item = small_effect[metric_id][statistic]
    large_item = large_effect[metric_id][statistic]
    small_mean = float(small_item["mean_difference"])
    large_mean = float(large_item["mean_difference"])
    expected_sign = _expected_sign(selection, metric_id)
    required = math.ceil(0.75 * len(small))

    def supporting(values: Sequence[float]) -> int:
        return sum(
            value != 0.0 and (1 if value > 0.0 else -1) == expected_sign
            for value in values
        )

    small_support = supporting(_seed_differences(small, metric_id, statistic))
    large_support = supporting(_seed_differences(large, metric_id, statistic))
    sign_passed = (
        expected_sign != 0
        and small_mean * expected_sign > 0.0
        and large_mean * expected_sign > 0.0
        and small_support >= required
        and large_support >= required
    )
    small_material = _effect_material(
        small_effect, small, metric_id, statistic
    )
    large_material = _effect_material(
        large_effect, large, metric_id, statistic
    )
    raw_ratio = large_mean / small_mean if small_mean else None
    population_ratio = R7_POPULATIONS[1] / R7_POPULATIONS[0]
    elasticity = (
        math.log(abs(raw_ratio), population_ratio)
        if raw_ratio not in (None, 0.0) and raw_ratio > 0.0 else None
    )
    expected_elasticity = 1.0 if metric_id in R7_EXTENSIVE_METRICS else 0.0
    elasticity_gap = (
        abs(elasticity - expected_elasticity)
        if elasticity is not None else None
    )
    first_order_scale = elasticity_gap is not None and elasticity_gap <= 0.35
    passed = sign_passed and small_material["passed"] and large_material["passed"]
    return {
        "metric_id": metric_id,
        "statistic": statistic,
        "r6_expected_sign": expected_sign,
        "small_mean_difference": small_mean,
        "large_mean_difference": large_mean,
        "small_supporting_seeds": small_support,
        "large_supporting_seeds": large_support,
        "required_supporting_seeds": required,
        "small_materiality": small_material,
        "large_materiality": large_material,
        "raw_large_to_small_ratio": raw_ratio,
        "expected_population_elasticity": expected_elasticity,
        "estimated_population_elasticity": elasticity,
        "elasticity_gap": elasticity_gap,
        "first_order_scale_confirmed": first_order_scale,
        "scale_model": (
            {
                "form": "absolute_effect_equals_beta_times_population_to_alpha",
                "alpha": elasticity,
                "reference_population": R7_POPULATIONS[0],
                "reference_absolute_effect": abs(small_mean),
            }
            if passed and not first_order_scale else None
        ),
        "sign_passed": sign_passed,
        "passed": passed,
    }


def _event_total(
    run: Mapping[str, Any], metric_id: str, branch: str
) -> float:
    values = run[branch]["metric_series"].get(metric_id, {}).get(
        "values", ()
    )
    return sum(max(0.0, float(value)) for value in values)


def _rare_event_report(
    selection: Mapping[str, Any],
    small: Sequence[Mapping[str, Any]],
    large: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    metric_id = selection.get("rare_event_metric")
    if not metric_id:
        return None
    small_control = [_event_total(row, metric_id, "control") for row in small]
    small_treatment = [_event_total(row, metric_id, "treatment") for row in small]
    large_control = [_event_total(row, metric_id, "control") for row in large]
    large_treatment = [_event_total(row, metric_id, "treatment") for row in large]
    # Event policies can work by creating an eligible transition or preventing
    # one. Opportunity therefore means at least one matched branch realizes
    # the event; treatment-only counting rejects successful prevention.
    small_totals = [max(a, b) for a, b in zip(small_control, small_treatment)]
    large_totals = [max(a, b) for a, b in zip(large_control, large_treatment)]
    small_mean = fmean(small_totals)
    large_mean = fmean(large_totals)
    raw_ratio = large_mean / small_mean if small_mean > 0.0 else None
    elasticity = (
        math.log(raw_ratio, R7_POPULATIONS[1] / R7_POPULATIONS[0])
        if raw_ratio is not None and raw_ratio > 0.0 else None
    )
    return {
        "metric_id": metric_id,
        "small_control_event_totals": small_control,
        "small_treatment_event_totals": small_treatment,
        "large_control_event_totals": large_control,
        "large_treatment_event_totals": large_treatment,
        "small_event_totals": small_totals,
        "large_event_totals": large_totals,
        "small_incidence": sum(value > 0.0 for value in small_totals) / len(small),
        "large_incidence": sum(value > 0.0 for value in large_totals) / len(large),
        "small_mean_events": small_mean,
        "large_mean_events": large_mean,
        "small_events_per_person": small_mean / R7_POPULATIONS[0],
        "large_events_per_person": large_mean / R7_POPULATIONS[1],
        "estimated_count_elasticity": elasticity,
        "nonzero_at_both_scales": small_mean > 0.0 and large_mean > 0.0,
    }


def _activation_present(
    run: Mapping[str, Any], selection: Mapping[str, Any]
) -> bool:
    metric_ids = list(selection["activation_metrics"])
    rare_metric = selection.get("rare_event_metric")
    if rare_metric and rare_metric not in metric_ids:
        metric_ids.append(rare_metric)
    return any(
        any(
            abs(float(value)) > 1.0e-12
            for branch in ("control", "treatment")
            for value in run[branch]["metric_series"].get(
                metric_id, {}
            ).get("values", ())
        )
        for metric_id in metric_ids
    )


def analyze_r7(
    manifest: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    index = {
        (str(row["lever"]), int(row["population"]), int(row["seed"])): row
        for row in runs
    }
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for selection in manifest["selections"]:
        lever = str(selection["lever"])
        small = [
            index.get((lever, R7_POPULATIONS[0], seed))
            for seed in R7_SEEDS
        ]
        large = [
            index.get((lever, R7_POPULATIONS[1], seed))
            for seed in R7_SEEDS
        ]
        complete = all(row is not None for row in small + large)
        valid_small = [row for row in small if row is not None]
        valid_large = [row for row in large if row is not None]
        integrity = (
            complete
            and all(_all_integrity_passed(row) for row in valid_small + valid_large)
        )
        budgets = [
            {
                "population": int(row["population"]),
                "seed": int(row["seed"]),
                **_record_budget(row),
            }
            for row in valid_small + valid_large
        ]
        budget_passed = complete and all(row["passed"] for row in budgets)
        activation = {
            "small_active_seeds": sum(
                _activation_present(run, selection)
                for run in valid_small
            ),
            "large_active_seeds": sum(
                _activation_present(run, selection)
                for run in valid_large
            ),
        }
        activation["passed"] = (
            len(valid_small) == len(R7_SEEDS)
            and len(valid_large) == len(R7_SEEDS)
            and activation["small_active_seeds"] == len(R7_SEEDS)
            and activation["large_active_seeds"] == len(R7_SEEDS)
        )
        metrics = (
            [
                _metric_scale_report(
                    selection, metric_id, valid_small, valid_large
                )
                for metric_id in selection["salient_metrics"]
            ]
            if integrity else []
        )
        exploratory_metrics = (
            [
                _metric_scale_report(
                    selection, metric_id, valid_small, valid_large
                )
                for metric_id in selection.get("exploratory_metrics", ())
            ]
            if integrity else []
        )
        rare = (
            _rare_event_report(selection, valid_small, valid_large)
            if integrity else None
        )
        effect_passed = bool(metrics) and all(row["passed"] for row in metrics)
        if not integrity:
            disposition = "runtime_or_integrity_defect"
        elif not budget_passed:
            disposition = "execution_budget_defect"
        elif not activation["passed"]:
            disposition = "activation_defect"
        elif not effect_passed:
            disposition = "scale_effect_defect"
        elif all(row["first_order_scale_confirmed"] for row in metrics):
            disposition = "finite_size_confirmed"
        else:
            disposition = "finite_size_dependency_modeled"
        if disposition not in {
            "finite_size_confirmed", "finite_size_dependency_modeled"
        }:
            errors.append(f"{lever}: {disposition}")
        reports.append({
            "lever": lever,
            "r6_classification": selection["r6_classification"],
            "disposition": disposition,
            "complete": complete,
            "integrity_passed": integrity,
            "execution_budget_passed": budget_passed,
            "activation": activation,
            "metrics": metrics,
            "exploratory_metrics": exploratory_metrics,
            "rare_event": rare,
            "time_compression": selection["time_compression"],
            "execution_records": budgets,
        })
    return reports, errors


def _run_batch(
    selections: Sequence[Mapping[str, Any]],
    contracts: Mapping[str, PolicyCausalContract],
    *,
    population: int,
    seeds: Sequence[int],
    source_revision: str,
    manifest_hash: str,
    artifact_dir: Path,
    jobs: int,
    resume: bool,
    progress: Callable[[Mapping[str, Any], bool], None] | None,
) -> tuple[list[dict[str, Any]], int, int]:
    futures = {}
    output: list[dict[str, Any]] = []
    hits = 0
    executed = 0
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for selection in selections:
            for seed in seeds:
                cache_path = (
                    artifact_dir / "runs" / str(population)
                    / str(selection["lever"]) / f"{seed}.json"
                )
                future = executor.submit(
                    _run_selection_seed,
                    selection,
                    contracts[str(selection["lever"])],
                    seed=int(seed),
                    population=population,
                    workers=R7_NATIVE_WORKERS,
                    source_revision=source_revision,
                    manifest_hash=manifest_hash,
                    cache_path=cache_path,
                    resume=resume,
                )
                futures[future] = (selection["lever"], seed)
        for future in as_completed(futures):
            result, cached = future.result()
            output.append(result)
            hits += int(cached)
            executed += int(not cached)
            if progress is not None:
                progress(result, cached)
    output.sort(key=lambda row: (str(row["lever"]), int(row["seed"])))
    return output, hits, executed


def run_r7(
    *,
    artifact_dir: Path,
    source_revision: str,
    r6_p2: Mapping[str, Any],
    r6_acceptance: Mapping[str, Any],
    seeds: Sequence[int] = R7_SEEDS,
    populations: Sequence[int] = R7_POPULATIONS,
    resume: bool = True,
    formal: bool = True,
    progress: Callable[[Mapping[str, Any], bool], None] | None = None,
) -> dict[str, Any]:
    seeds = tuple(int(seed) for seed in seeds)
    populations = tuple(int(value) for value in populations)
    if formal and seeds != R7_SEEDS:
        raise ValueError("formal R7 requires the four preregistered seeds")
    if formal and populations != R7_POPULATIONS:
        raise ValueError("formal R7 requires matched 100k and 1M populations")
    repo_root = Path(__file__).resolve().parents[1]
    native_build = assert_r6_native_build(repo_root)
    manifest = build_r7_manifest(
        r6_p2=r6_p2,
        r6_acceptance=r6_acceptance,
    )
    errors = list(manifest["errors"])
    contracts = _contracts()
    runs: list[dict[str, Any]] = []
    hits = 0
    executed = 0
    for population in populations:
        batch, batch_hits, batch_executed = _run_batch(
            manifest["selections"],
            contracts,
            population=population,
            seeds=seeds,
            source_revision=source_revision,
            manifest_hash=manifest["manifest_hash"],
            artifact_dir=artifact_dir,
            jobs=(R7_SMALL_JOBS if population == R7_POPULATIONS[0] else R7_LARGE_JOBS),
            resume=resume,
            progress=progress,
        )
        runs.extend(batch)
        hits += batch_hits
        executed += batch_executed
    reports: list[dict[str, Any]] = []
    if formal and populations == R7_POPULATIONS and seeds == R7_SEEDS:
        reports, analysis_errors = analyze_r7(manifest, runs)
        errors.extend(analysis_errors)
    status = "accepted" if formal and not errors else (
        "preflight_complete" if not formal and not errors else "failed"
    )
    evidence = {
        "reports": reports,
        "execution_identity": [
            {
                "lever": row["lever"],
                "population": row["population"],
                "seed": row["seed"],
                "days": row["days"],
                "countries": row["countries"],
                "elapsed_seconds": row["elapsed_seconds"],
                "policy_applied": row["policy_applied"],
                "error": row["error"],
            }
            for row in runs
        ],
    }
    dispositions: dict[str, int] = {}
    for report in reports:
        key = str(report["disposition"])
        dispositions[key] = dispositions.get(key, 0) + 1
    payload = {
        "schema_version": R7_SCHEMA_VERSION,
        "status": status,
        "errors": errors,
        "source_revision": source_revision,
        "manifest": manifest,
        "protocol": {
            "populations_per_country": list(populations),
            "matched_seeds": list(seeds),
            "native_engine_workers": R7_NATIVE_WORKERS,
            "small_jobs": R7_SMALL_JOBS,
            "large_jobs": R7_LARGE_JOBS,
            "native_build": native_build,
            "legacy_python_simulator_used": False,
            "million_person_branching": "native_in_memory_clone",
            "wall_clock_budget_seconds_per_record": R7_MAX_RECORD_SECONDS,
            "estimated_peak_memory_budget_bytes": R7_MAX_ESTIMATED_PEAK_BYTES,
        },
        "counts": {
            "candidates": len(manifest["selections"]),
            "run_records": len(runs),
            "planned_run_records": (
                len(manifest["selections"]) * len(seeds) * len(populations)
            ),
            "native_branch_paths": 2 * len(runs),
            "executed_native_run_records": executed,
            "cache_hits": hits,
            "previously_blocked_paths_completed": sum(
                report["lever"] in {
                    "mortgage_foreclosure_ltv",
                    "rental_eviction_arrears",
                    "tariff",
                    "fx_regime",
                }
                and report["complete"]
                for report in reports
            ),
            "dispositions": dispositions,
        },
        "reports": reports,
        "runs": runs,
        "hashes": {
            "r7_manifest": manifest["manifest_hash"],
            "r7_evidence": _canonical_hash(evidence),
        },
    }
    payload["hashes"]["r7_acceptance"] = _canonical_hash({
        "status": status,
        "errors": errors,
        "source_revision": source_revision,
        "protocol": payload["protocol"],
        "manifest": payload["hashes"]["r7_manifest"],
        "evidence": payload["hashes"]["r7_evidence"],
    })
    _atomic_json(artifact_dir / "r7_report.json", payload)
    return payload


def freeze_r7_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    frozen = {key: value for key, value in payload.items() if key != "runs"}
    return _jsonable(frozen)


def build_r7_acceptance(evidence: Mapping[str, Any]) -> dict[str, Any]:
    reports = list(evidence.get("reports", ()))
    errors = list(evidence.get("errors", ()))
    if evidence.get("status") != "accepted":
        errors.append("R7 scale evidence is not accepted")
    if {str(row.get("lever")) for row in reports} != set(R7_CANDIDATES):
        errors.append("R7 report ledger does not exactly cover seven candidates")
    if evidence.get("counts", {}).get("run_records") != 56:
        errors.append("R7 evidence does not contain 56 matched run records")
    if evidence.get("counts", {}).get("previously_blocked_paths_completed") != 4:
        errors.append("R7 did not complete every previously blocked path")
    accepted_dispositions = {
        "finite_size_confirmed", "finite_size_dependency_modeled"
    }
    if any(row.get("disposition") not in accepted_dispositions for row in reports):
        errors.append("R7 contains an unaccepted scale disposition")
    if evidence.get("protocol", {}).get("legacy_python_simulator_used") is not False:
        errors.append("R7 evidence does not prove native-only simulation")
    ledger = [
        {
            "lever": row["lever"],
            "r6_classification": row["r6_classification"],
            "scale_disposition": row["disposition"],
            "execution_budget_passed": row["execution_budget_passed"],
            "rare_event": row["rare_event"],
            "metric_models": [
                {
                    "metric_id": metric["metric_id"],
                    "estimated_population_elasticity": metric[
                        "estimated_population_elasticity"
                    ],
                    "first_order_scale_confirmed": metric[
                        "first_order_scale_confirmed"
                    ],
                    "scale_model": metric["scale_model"],
                }
                for metric in row["metrics"]
            ],
            "exploratory_metric_models": [
                {
                    "metric_id": metric["metric_id"],
                    "passed": metric["passed"],
                    "estimated_population_elasticity": metric[
                        "estimated_population_elasticity"
                    ],
                    "first_order_scale_confirmed": metric[
                        "first_order_scale_confirmed"
                    ],
                    "scale_model": metric["scale_model"],
                }
                for metric in row.get("exploratory_metrics", ())
            ],
        }
        for row in reports
    ]
    status = "accepted" if not errors else "failed"
    payload = {
        "schema_version": R7_SCHEMA_VERSION,
        "status": status,
        "errors": errors,
        "source_revision": evidence.get("source_revision"),
        "protocol": evidence.get("protocol"),
        "counts": {
            "candidates": len(ledger),
            "classifications_unchanged": sum(
                row["r6_classification"] in {
                    "effective", "conditional", "expert_only", "structural"
                }
                for row in ledger
            ),
            "finite_size_confirmed": sum(
                row["scale_disposition"] == "finite_size_confirmed"
                for row in ledger
            ),
            "finite_size_dependencies_modeled": sum(
                row["scale_disposition"] == "finite_size_dependency_modeled"
                for row in ledger
            ),
            "previously_blocked_paths_completed": evidence.get("counts", {}).get(
                "previously_blocked_paths_completed"
            ),
        },
        "reports": ledger,
        "hashes": {
            "r7_evidence": evidence.get("hashes", {}).get("r7_evidence"),
        },
    }
    payload["hashes"]["r7_acceptance"] = _canonical_hash({
        **{
            key: value for key, value in payload.items()
            if key != "hashes"
        },
        "r7_evidence": payload["hashes"]["r7_evidence"],
    })
    return payload


def validate_r7_acceptance(
    acceptance: Mapping[str, Any], evidence: Mapping[str, Any]
) -> list[str]:
    expected = build_r7_acceptance(evidence)
    return [] if _jsonable(acceptance) == _jsonable(expected) else [
        "committed R7 acceptance report does not reproduce"
    ]


def render_r7_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy remediation R7 acceptance",
        "",
        f"- Status: `{payload['status']}`",
        "- Populations per country: 100,000 and 1,000,000",
        "- Matched seeds: 4",
        "- Native workers: 8",
        "- Legacy Python simulator used: no",
        f"- Acceptance hash: `{payload['hashes']['r7_acceptance']}`",
        "",
        "## Scale ledger",
        "",
        "| Lever | R6 class | R7 scale disposition | Budget |",
        "|---|---|---|---:|",
    ]
    for row in payload["reports"]:
        lines.append(
            f"| `{row['lever']}` | `{row['r6_classification']}` | "
            f"`{row['scale_disposition']}` | "
            f"{'pass' if row['execution_budget_passed'] else 'fail'} |"
        )
    lines.extend([
        "",
        "A modeled dependency preserves the matched-seed effect direction but "
        "does not follow the preregistered first-order population elasticity. "
        "The fitted power-law exponent is retained in the machine report; it "
        "is not silently described as scale invariant.",
        "",
    ])
    return "\n".join(lines)
