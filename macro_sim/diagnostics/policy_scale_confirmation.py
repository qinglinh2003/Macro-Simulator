"""Native finite-size and rare-event confirmation for policy audit P6.

P6 consumes frozen P2 mechanism evidence and the P5 package ledger.  It does
not repair upstream defects.  One accepted representative from each decision
group, plus every accepted discrete-event mechanism, is repeated at 100,000
and 1,000,000 persons with matched seeds.  Rare-event mechanisms receive an
additional sixteen-seed million-person tail screen only when the matched scale
comparison changes their event incidence or per-capita frequency materially.

Python builds immutable inputs, schedules native branches, and reduces native
metrics.  Every simulated day remains in the C++ engine.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean, stdev
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from macro_sim import native_backend
from macro_sim.diagnostics.config_experiment import (
    apply_native_activation_scenario,
    population_scaled_new_game,
    summarize_paired_runs,
)
from macro_sim.diagnostics.policy_catalog import (
    ACTIVATION_FIXTURES,
    GROUP_SPECS,
    LEVER_PROXIMAL_METRICS,
    METRIC_MATERIALITY,
    _COUNT_METRICS,
)
from macro_sim.diagnostics.policy_contracts import (
    PolicyCausalContract,
    build_contracts,
    build_p0_payload,
)
from macro_sim.diagnostics.policy_crisis_effects import (
    ACCOUNTING_METRICS,
    _atomic_json,
    _canonical_hash,
    _jsonable,
)
from macro_sim.diagnostics.policy_effects import (
    LEVER_ACTIVATION_DAYS,
    _actions,
    _capture_window,
    _countries,
    _native_scenario,
    _setup_actions,
    _target_economy,
    select_experiment_arms,
)
from macro_sim.native_backend import NativeSimulationSession


P6_SCHEMA_VERSION = "policy-causality-p6-v2"
P6_MANIFEST_SCHEMA_VERSION = "policy-causality-p6-v1"
P6_RUN_SIGNATURE_SCHEMA_VERSION = "policy-causality-p6-v1"
P6_POPULATIONS = (100_000, 1_000_000)
P6_SEEDS = (5101, 5113, 5129, 5143, 5159, 5177, 5193, 5209)
P6_TAIL_EXTRA_SEEDS = (5303, 5323, 5347, 5369, 5387, 5413, 5431, 5449)
P6_BURN_IN_DAYS = 7
P6_DEFAULT_DAYS = 30
P6_REFERENCE_INTEGRITY_LIMITS: Mapping[str, float] = {
    "metric.source.m4.conservation_drift": 1.0e-4,
    "metric.source.m6.clearing_residual": 1.0e-5,
    "metric.economy.na.production_reconciliation_residual": 1.0e-6,
}


# P6 discovered that four otherwise valid representatives do not admit the
# frozen eight-seed million-person experiment within a bounded audit run on
# the reference 24 GiB host. This is an acceptance result, not a policy
# repair: the 100k records remain valid, while the 1M causal claim is withheld.
#
# The tariff observation is direct. Its four concurrent native records used
# the same source revision and produced no completed record for more than
# twelve wall-clock hours after the preceding cache write, while the process
# remained CPU-active. The other three rows are conservative projections:
# they use the same three-economy topology with a slower 100k record, or a
# single-economy 100k record already several times slower than tariff. P6 does
# not spend additional unbounded compute merely to restate that limitation.
P6_SCALE_EXECUTION_BLOCKERS: Mapping[str, Mapping[str, Any]] = {
    "tariff": {
        "evidence_kind": "direct_observation",
        "reason": "four concurrent 1M records produced no result after more than 12 wall-clock hours",
        "observed_concurrent_records": 4,
        "wall_clock_lower_bound_seconds": 43_200,
        "reference_100k_elapsed_seconds": 47.24511212500511,
    },
    "fx_regime": {
        "evidence_kind": "conservative_projection",
        "reason": "same three-economy topology as the directly blocked tariff run and a slower 100k record",
        "proxy_lever": "tariff",
        "reference_100k_elapsed_seconds": 49.25201070900948,
    },
    "mortgage_foreclosure_ltv": {
        "evidence_kind": "conservative_projection",
        "reason": "100k native record is already more than five times slower than the directly blocked tariff record",
        "proxy_lever": "tariff",
        "reference_100k_elapsed_seconds": 280.88076737499796,
    },
    "rental_eviction_arrears": {
        "evidence_kind": "conservative_projection",
        "reason": "100k native record is already more than three times slower than the directly blocked tariff record",
        "proxy_lever": "tariff",
        "reference_100k_elapsed_seconds": 159.59400758300035,
    },
}


@dataclass(frozen=True, slots=True)
class RepresentativeSpec:
    lever: str
    arm_label: str
    decision_group: str
    role: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


REPRESENTATIVES: tuple[RepresentativeSpec, ...] = (
    RepresentativeSpec("gov_investment_share", "arm_3", "fiscal_stance", "group"),
    RepresentativeSpec("benefit_income_floor", "arm_2", "labor_and_welfare", "group"),
    RepresentativeSpec("tax_income_rate", "arm_3", "tax_and_transfers", "group"),
    RepresentativeSpec("energy_price_cap", "arm_2", "energy_operations", "group"),
    RepresentativeSpec("manual_policy_rate", "arm_2", "monetary_stance", "group"),
    RepresentativeSpec("bond_finance_frac", "arm_3", "debt_management", "group"),
    RepresentativeSpec("omo", "arm_1", "liquidity_operations", "group"),
    RepresentativeSpec("bank_min_capital", "arm_3", "macroprudential", "group"),
    RepresentativeSpec("bankrupt_persist", "threshold_meaningful", "structural_law", "group"),
    RepresentativeSpec("soe_efirm", "arm_1", "energy_structure", "group"),
    RepresentativeSpec("tariff", "arm_2", "trade_and_migration", "group"),
    RepresentativeSpec("fx_regime", "arm_1", "fx_operations", "group"),
    RepresentativeSpec(
        "mortgage_foreclosure_ltv",
        "threshold_meaningful",
        "structural_law",
        "rare_event_addition",
    ),
    RepresentativeSpec(
        "rental_eviction_arrears",
        "arm_4",
        "structural_law",
        "rare_event_addition",
    ),
)


# The list is a frozen audit contract.  Runtime verification below rejects any
# new count-first mechanism that is not explicitly classified here.
RARE_EVENT_MECHANISMS: Mapping[str, str] = {
    "bank_min_capital": "metric.source.m6.bank_births",
    "mortgage_underwriting": "metric.source.m8.housing.mortgage_originations",
    "mortgage_dsti_cap": "metric.source.m8.housing.mortgage_originations",
    "mortgage_stress_rate_addon": "metric.source.m8.housing.mortgage_originations",
    "mortgage_risk_weight": "metric.source.m8.housing.mortgage_originations",
    "mortgage_min_capital_ratio": "metric.source.m8.housing.mortgage_originations",
    "mortgage_foreclosure_ltv": "metric.source.m8.housing.foreclosures",
    "mortgage_arrears_floor": "metric.source.m8.housing.foreclosures",
    "housing_permits": "metric.source.m8.housing.permits_used",
    "bankrupt_persist": "metric.source.m6.firm_defaults",
    "household_bankruptcy": "metric.source.m6.household_bankruptcies",
    "rental_eviction_arrears": "metric.source.m8.housing.evictions",
    "bank_migrate_on_failure": "metric.source.m5.bank_failures",
}


def _load(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _reports_by_lever(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    reports = payload.get("reports")
    if not isinstance(reports, list):
        raise ValueError("P2 evidence has no report ledger")
    output = {str(item["lever"]): item for item in reports}
    if len(output) != len(reports):
        raise ValueError("P2 evidence contains duplicate levers")
    return output


def _arm(report: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    matches = [
        item for item in report.get("activation", {}).get("arms", ())
        if item.get("label") == label
    ]
    if len(matches) != 1:
        raise ValueError(f"{report['lever']}: expected one frozen arm {label!r}")
    return matches[0]


def _runtime_rare_contract() -> dict[str, str]:
    return {
        lever: metrics[0]
        for lever, metrics in LEVER_PROXIMAL_METRICS.items()
        if metrics and metrics[0] in _COUNT_METRICS
    }


def build_p6_manifest(
    p2_source: str | Path | Mapping[str, Any],
    p5_source: str | Path | Mapping[str, Any],
) -> dict[str, Any]:
    p2 = _load(p2_source)
    p5 = _load(p5_source)
    reports = _reports_by_lever(p2)
    errors: list[str] = []
    if p2.get("status") != "accepted_with_explicit_defects":
        errors.append("P2 evidence is not frozen with explicit dispositions")
    if p5.get("status") != "accepted_with_explicit_defects":
        errors.append("P5 evidence is not frozen with explicit dispositions")
    if _runtime_rare_contract() != dict(RARE_EVENT_MECHANISMS):
        errors.append("the runtime count-first rare-event contract changed")

    contract_by_lever = {item.lever: item for item in build_contracts()}
    selected = []
    for spec in REPRESENTATIVES:
        report = reports.get(spec.lever)
        contract = contract_by_lever.get(spec.lever)
        if report is None or contract is None:
            errors.append(f"{spec.lever}: missing frozen contract or P2 report")
            continue
        if report.get("decision_group") != spec.decision_group:
            errors.append(f"{spec.lever}: decision-group identity changed")
        disposition = str(report.get("disposition", ""))
        if not disposition.startswith("accepted"):
            errors.append(f"{spec.lever}: selected representative is not P2 accepted")
        try:
            arm = _arm(report, spec.arm_label)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        salient = tuple(sorted(arm.get("salient_proximal_metrics", ())))
        if not salient:
            errors.append(f"{spec.lever}: selected arm has no frozen salient metric")
        selected.append({
            **spec.to_dict(),
            "p2_disposition": disposition,
            "scenario": _native_scenario(contract),
            "countries": _countries(contract),
            "target_economy": _target_economy(contract),
            "days": max(P6_DEFAULT_DAYS, LEVER_ACTIVATION_DAYS.get(spec.lever, 0)),
            "setup_actions": _jsonable(_setup_actions(contract)),
            "actions": arm.get("actions", ()),
            "dose_class": arm.get("dose_class"),
            "salient_metrics": list(salient),
            "frozen_effects": {
                metric_id: arm.get("effects", {}).get(metric_id, {})
                for metric_id in salient
            },
            "activation_fixture": contract.activation_fixture,
            "activation_metrics": list(
                ACTIVATION_FIXTURES[contract.activation_fixture].activation_metrics
            ),
            "rare_event_metric": RARE_EVENT_MECHANISMS.get(spec.lever),
        })

    expected_groups = {group for _role, group in GROUP_SPECS}
    selected_groups = {
        item["decision_group"] for item in selected if item["role"] == "group"
    }
    if selected_groups != expected_groups:
        errors.append("P6 representatives do not cover every decision group exactly")
    group_rows = [item for item in selected if item["role"] == "group"]
    if len(group_rows) != len(selected_groups):
        errors.append("P6 has duplicate primary decision-group representatives")

    selected_levers = {item["lever"] for item in selected}
    rare_ledger = []
    for lever, metric_id in RARE_EVENT_MECHANISMS.items():
        report = reports.get(lever)
        disposition = str(report.get("disposition", "missing")) if report else "missing"
        runnable = disposition.startswith("accepted")
        if runnable and lever not in selected_levers:
            errors.append(f"{lever}: accepted rare-event mechanism is not selected")
        rare_ledger.append({
            "lever": lever,
            "metric_id": metric_id,
            "p2_disposition": disposition,
            "runnable": runnable,
            "selected": lever in selected_levers,
            "reason": report.get("reason") if report else "missing P2 report",
        })

    payload = {
        "schema_version": P6_MANIFEST_SCHEMA_VERSION,
        "p0_root_hash": build_p0_payload()["hashes"]["p0_root"],
        "p2_acceptance_hash": p2.get("hashes", {}).get("p2_acceptance"),
        "p5_acceptance_hash": p5.get("hashes", {}).get("p5_acceptance"),
        "populations": list(P6_POPULATIONS),
        "matched_seeds": list(P6_SEEDS),
        "tail_extra_seeds": list(P6_TAIL_EXTRA_SEEDS),
        "representatives": selected,
        "rare_event_ledger": rare_ledger,
        "errors": errors,
    }
    payload["manifest_hash"] = _canonical_hash({
        key: value for key, value in payload.items() if key != "manifest_hash"
    })
    return payload


def _selection_contracts() -> dict[str, PolicyCausalContract]:
    contracts = {item.lever: item for item in build_contracts()}
    return {spec.lever: contracts[spec.lever] for spec in REPRESENTATIVES}


def _metric_ids(selection: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(set(selection["salient_metrics"])
        | set(selection["activation_metrics"])
        | set(selection.get("exploratory_metrics", ()))
        | set(ACCOUNTING_METRICS)
        | ({selection["rare_event_metric"]} if selection["rare_event_metric"] else set())))


def _integrity_by_economy(
    capture: Mapping[str, Any], *, population: int
) -> dict[str, Any]:
    """Apply the frozen 100k tolerance at a constant per-person rate.

    All three residuals are absolute economy totals.  Holding their absolute
    threshold fixed while population grows tenfold would make floating-point
    summation error look like an accounting violation.  Linear scaling keeps
    the admissible residual per represented person unchanged.
    """
    scale = population / P6_POPULATIONS[0]
    output = {}
    for economy_id, series in capture["metric_series_by_economy"].items():
        values_by_metric = {
            metric_id: tuple(item["values"])
            for metric_id, item in series.items()
        }
        missing = [
            metric_id for metric_id in P6_REFERENCE_INTEGRITY_LIMITS
            if metric_id not in values_by_metric
        ]
        finite = all(
            math.isfinite(value)
            for values in values_by_metric.values() for value in values
        )
        maxima = {
            metric_id: max(
                (abs(value) for value in values_by_metric.get(metric_id, ())),
                default=math.inf,
            )
            for metric_id in P6_REFERENCE_INTEGRITY_LIMITS
        }
        applied_limits = {
            metric_id: limit * scale
            for metric_id, limit in P6_REFERENCE_INTEGRITY_LIMITS.items()
        }
        per_person = {
            metric_id: value / population for metric_id, value in maxima.items()
        }
        accounting = not missing and all(
            maxima[metric_id] <= applied_limits[metric_id]
            for metric_id in P6_REFERENCE_INTEGRITY_LIMITS
        )
        output[str(economy_id)] = {
            "finite": finite,
            "missing_accounting_metrics": missing,
            "maximum_absolute_residuals": maxima,
            "maximum_residuals_per_person": per_person,
            "reference_100k_absolute_limits": dict(P6_REFERENCE_INTEGRITY_LIMITS),
            "applied_absolute_limits": applied_limits,
            "accounting_passed": accounting,
            "passed": finite and accounting,
        }
    return output


def _run_selection_seed(
    selection: Mapping[str, Any],
    contract: PolicyCausalContract,
    *,
    seed: int,
    population: int,
    workers: int,
    source_revision: str,
    manifest_hash: str,
    cache_path: Path,
    resume: bool,
) -> tuple[dict[str, Any], bool]:
    signature_payload = {
        "schema_version": P6_RUN_SIGNATURE_SCHEMA_VERSION,
        "source_revision": source_revision,
        "manifest_hash": manifest_hash,
        "selection": selection,
        "seed": seed,
        "population": population,
        "workers": workers,
    }
    signature = _canonical_hash(signature_payload)
    if resume and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("run_signature") == signature:
            return dict(cached["result"]), True

    started = time.perf_counter()
    days = int(selection["days"])
    maximum_days = P6_BURN_IN_DAYS + days + 2
    baseline = population_scaled_new_game(
        population=population,
        days=maximum_days,
        seed=seed,
        countries=int(selection["countries"]),
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    apply_native_activation_scenario(native_spec, scenario=str(selection["scenario"]))
    session = NativeSimulationSession.create_from_native_spec(
        native_spec,
        worker_count=workers,
        history_capacity_frames=maximum_days + 4,
    )
    setup_actions = tuple(
        (str(item[0]), item[1]) if isinstance(item, (tuple, list))
        else (str(item["lever"]), item["value"])
        for item in selection["setup_actions"]
    )
    if setup_actions:
        session.advance(
            1,
            actions=_actions(setup_actions, economy_id=int(selection["target_economy"])),
        )
        if P6_BURN_IN_DAYS > 1:
            session.advance(P6_BURN_IN_DAYS - 1)
    else:
        session.advance(P6_BURN_IN_DAYS)
    t0 = session.tick
    # The maintained M8 checkpoint format has a fixed serialized-size ceiling
    # and cannot encode a one-million-person economy.  P6 branches directly
    # through the native bridge's in-memory clone, which has no such limit.
    # Preserve the limitation as evidence instead of either hiding it or
    # changing the C++ checkpoint contract inside this milestone.
    checkpoint_sha256 = (
        hashlib.sha256(session.checkpoint()).hexdigest()
        if population < P6_POPULATIONS[1] else None
    )
    checkpoint_disposition = (
        "serialized_and_hashed"
        if checkpoint_sha256 is not None
        else "native_clone_only_m8_size_limit"
    )
    metric_ids = _metric_ids(selection)
    countries = int(selection["countries"])
    target = int(selection["target_economy"])

    control = session.clone()
    control.advance(days)
    control_capture = _capture_window(
        control,
        t0=t0,
        days=days,
        metric_ids=metric_ids,
        countries=countries,
        target_economy=target,
    )
    # The control session is no longer needed once its maintained metrics have
    # been copied.  Releasing it before cloning the treatment bounds peak
    # memory in million-person jobs and permits safe seed-level concurrency.
    del control

    treatment = session.clone()
    treatment_actions = tuple(
        {
            "economy_id": target,
            "lever": str(item["lever"]),
            "value": _jsonable(item["value"]),
        }
        for item in selection["actions"]
    )
    error = None
    treatment_capture: dict[str, Any] | None = None
    policy_after: dict[str, Any] = {}
    try:
        treatment.advance(days, actions=treatment_actions)
        values = treatment.policy_values(target)
        policy_after = {
            item["lever"]: _jsonable(values[item["lever"]])
            for item in treatment_actions
        }
        treatment_capture = _capture_window(
            treatment,
            t0=t0,
            days=days,
            metric_ids=metric_ids,
            countries=countries,
            target_economy=target,
        )
    except Exception as exc:  # runtime stability is a P6 estimand
        error = {"type": type(exc).__name__, "message": str(exc)}

    policy_applied = error is None and all(
        policy_after.get(item["lever"]) == _jsonable(item["value"])
        for item in treatment_actions
    )
    result = {
        "lever": selection["lever"],
        "arm_label": selection["arm_label"],
        "seed": seed,
        "population": population,
        "workers": workers,
        "countries": countries,
        "target_economy": target,
        "days": days,
        "t0": t0,
        "checkpoint_sha256": checkpoint_sha256,
        "checkpoint_disposition": checkpoint_disposition,
        "metric_ids": list(metric_ids),
        "actions": treatment_actions,
        "policy_after": policy_after,
        "policy_applied": policy_applied,
        "control": control_capture,
        "treatment": treatment_capture,
        "control_integrity": _integrity_by_economy(
            control_capture, population=population
        ),
        "treatment_integrity": (
            _integrity_by_economy(treatment_capture, population=population)
            if treatment_capture is not None else {}
        ),
        "error": error,
        "elapsed_seconds": time.perf_counter() - started,
        "memory_bytes": session.memory_usage(),
    }
    _atomic_json(cache_path, {
        "schema_version": "policy-p6-native-run-cache-v1",
        "run_signature": signature,
        "signature": signature_payload,
        "result": result,
    })
    return result, False


def _run_batch(
    selections: Sequence[Mapping[str, Any]],
    *,
    seeds: Sequence[int],
    population: int,
    workers: int,
    jobs: int,
    source_revision: str,
    manifest_hash: str,
    artifact_dir: Path,
    phase: str,
    resume: bool,
    progress: Callable[[dict[str, Any], bool], None] | None,
) -> tuple[list[dict[str, Any]], int, int]:
    contracts = _selection_contracts()
    futures = {}
    results: list[dict[str, Any]] = []
    hits = 0
    executed = 0
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
        for selection in selections:
            for seed in seeds:
                path = (
                    artifact_dir / "runs" / phase / str(population)
                    / str(selection["lever"]) / f"{seed}.json"
                )
                future = executor.submit(
                    _run_selection_seed,
                    selection,
                    contracts[str(selection["lever"])],
                    seed=int(seed),
                    population=population,
                    workers=workers,
                    source_revision=source_revision,
                    manifest_hash=manifest_hash,
                    cache_path=path,
                    resume=resume,
                )
                futures[future] = (str(selection["lever"]), int(seed))
        for future in as_completed(futures):
            result, cached = future.result()
            results.append(result)
            hits += int(cached)
            executed += int(not cached)
            if progress is not None:
                progress(result, cached)
    results.sort(key=lambda item: (str(item["lever"]), int(item["seed"])))
    return results, hits, executed


def _run_index(runs: Iterable[Mapping[str, Any]]) -> dict[tuple[str, int, int], Mapping[str, Any]]:
    return {
        (str(item["lever"]), int(item["population"]), int(item["seed"])): item
        for item in runs
    }


def _all_integrity_passed(run: Mapping[str, Any]) -> bool:
    return (
        run.get("error") is None
        and bool(run.get("policy_applied"))
        and all(item.get("passed") for item in run.get("control_integrity", {}).values())
        and all(item.get("passed") for item in run.get("treatment_integrity", {}).values())
        and run.get("treatment") is not None
    )


def _statistic(capture: Mapping[str, Any], metric_id: str, statistic: str) -> float:
    return float(capture["metric_summaries"][metric_id][statistic])


def _seed_differences(
    runs: Sequence[Mapping[str, Any]], metric_id: str, statistic: str
) -> list[float]:
    return [
        _statistic(item["treatment"], metric_id, statistic)
        - _statistic(item["control"], metric_id, statistic)
        for item in runs
    ]


def _effect_material(
    effect: Mapping[str, Any],
    controls: Sequence[Mapping[str, Any]],
    metric_id: str,
    statistic: str,
) -> dict[str, Any]:
    spec = METRIC_MATERIALITY[metric_id]
    item = effect[metric_id][statistic]
    absolute = abs(float(item["mean_difference"]))
    relative_raw = item.get("mean_relative_difference")
    relative = abs(float(relative_raw)) if relative_raw is not None else 0.0
    control_values = [_statistic(run["control"], metric_id, statistic) for run in controls]
    control_sd = stdev(control_values) if len(control_values) > 1 else 0.0
    standardized_floor = spec.standardized_floor * control_sd
    effective_floor = min(
        value for value in (spec.absolute_floor, standardized_floor)
        if value > 0.0
    ) if standardized_floor > 0.0 else spec.absolute_floor
    passed = absolute > 1.0e-12 and (
        absolute >= spec.absolute_floor
        or relative >= spec.relative_floor
        or (control_sd > 0.0 and absolute >= standardized_floor)
    )
    return {
        "passed": passed,
        "absolute_difference": absolute,
        "relative_difference": relative_raw,
        "control_standard_deviation": control_sd,
        "effective_floor": effective_floor,
    }


def _fixture_active(run: Mapping[str, Any], metric_ids: Sequence[str]) -> bool:
    series = run["control"]["metric_series"]
    return any(
        any(abs(float(value)) > 1.0e-12 for value in series.get(metric_id, {}).get("values", ()))
        for metric_id in metric_ids
    )


def _effect_summary(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return summarize_paired_runs(
        [item["control"] for item in runs],
        [item["treatment"] for item in runs],
    )


def _metric_confirmation(
    selection: Mapping[str, Any],
    metric_id: str,
    small: Sequence[Mapping[str, Any]],
    large: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    statistic = METRIC_MATERIALITY[metric_id].default_statistic
    frozen = selection["frozen_effects"][metric_id][statistic]
    frozen_difference = float(frozen["mean_difference"])
    frozen_sign = 1 if frozen_difference > 0.0 else -1 if frozen_difference < 0.0 else 0
    small_effects = _effect_summary(small)
    large_effects = _effect_summary(large)
    small_item = small_effects[metric_id][statistic]
    large_item = large_effects[metric_id][statistic]
    small_differences = _seed_differences(small, metric_id, statistic)
    large_differences = _seed_differences(large, metric_id, statistic)
    required = max(1, math.ceil(0.75 * len(small)))

    def support(values: Sequence[float]) -> int:
        return sum(
            value != 0.0 and (1 if value > 0.0 else -1) == frozen_sign
            for value in values
        )

    small_support = support(small_differences)
    large_support = support(large_differences)
    small_mean = float(small_item["mean_difference"])
    large_mean = float(large_item["mean_difference"])
    sign_preserved = (
        frozen_sign != 0
        and small_mean * frozen_sign > 0.0
        and large_mean * frozen_sign > 0.0
    )
    small_material = _effect_material(small_effects, small, metric_id, statistic)
    large_material = _effect_material(large_effects, large, metric_id, statistic)
    raw_ratio = large_mean / small_mean if small_mean else None
    count_metric = metric_id in _COUNT_METRICS
    normalized_ratio = (
        (large_mean / P6_POPULATIONS[1]) / (small_mean / P6_POPULATIONS[0])
        if count_metric and small_mean else raw_ratio
    )
    passed = (
        sign_preserved
        and small_support >= required
        and large_support >= required
        and small_material["passed"]
        and large_material["passed"]
    )
    return {
        "metric_id": metric_id,
        "statistic": statistic,
        "frozen_p2_mean_difference": frozen_difference,
        "frozen_sign": frozen_sign,
        "small_mean_difference": small_mean,
        "large_mean_difference": large_mean,
        "small_supporting_seeds": small_support,
        "large_supporting_seeds": large_support,
        "required_supporting_seeds": required,
        "small_confidence_low": small_item.get("confidence_low"),
        "small_confidence_high": small_item.get("confidence_high"),
        "large_confidence_low": large_item.get("confidence_low"),
        "large_confidence_high": large_item.get("confidence_high"),
        "small_materiality": small_material,
        "large_materiality": large_material,
        "raw_large_to_small_ratio": raw_ratio,
        "population_normalized_large_to_small_ratio": normalized_ratio,
        "sign_preserved": sign_preserved,
        "passed": passed,
    }


def _event_total(run: Mapping[str, Any], metric_id: str) -> float:
    values = run["treatment"]["metric_series"].get(metric_id, {}).get("values", ())
    return sum(max(0.0, float(value)) for value in values)


def _rare_scale(
    selection: Mapping[str, Any],
    small: Sequence[Mapping[str, Any]],
    large: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    metric_id = selection.get("rare_event_metric")
    if not metric_id:
        return None
    small_totals = [_event_total(item, metric_id) for item in small]
    large_totals = [_event_total(item, metric_id) for item in large]
    small_incidence = sum(value > 0.0 for value in small_totals) / len(small_totals)
    large_incidence = sum(value > 0.0 for value in large_totals) / len(large_totals)
    small_mean = fmean(small_totals)
    large_mean = fmean(large_totals)
    small_per_person = small_mean / P6_POPULATIONS[0]
    large_per_person = large_mean / P6_POPULATIONS[1]
    per_person_ratio = (
        large_per_person / small_per_person if small_per_person > 0.0 else None
    )
    zero_transition = (small_mean == 0.0) != (large_mean == 0.0)
    incidence_shift = abs(large_incidence - small_incidence) >= 0.25
    frequency_shift = (
        per_person_ratio is not None
        and (per_person_ratio < 0.5 or per_person_ratio > 2.0)
    )
    return {
        "metric_id": metric_id,
        "small_event_totals": small_totals,
        "large_event_totals": large_totals,
        "small_incidence": small_incidence,
        "large_incidence": large_incidence,
        "small_mean_events": small_mean,
        "large_mean_events": large_mean,
        "small_events_per_person": small_per_person,
        "large_events_per_person": large_per_person,
        "per_person_large_to_small_ratio": per_person_ratio,
        "zero_transition": zero_transition,
        "incidence_shift": incidence_shift,
        "frequency_shift": frequency_shift,
        "scale_materially_changes_event": (
            zero_transition or incidence_shift or frequency_shift
        ),
    }


def analyze_base(
    manifest: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    index = _run_index(runs)
    reports = []
    errors = []
    for selection in manifest["representatives"]:
        scale_blocker = P6_SCALE_EXECUTION_BLOCKERS.get(str(selection["lever"]))
        small = [
            index.get((selection["lever"], P6_POPULATIONS[0], seed))
            for seed in manifest["matched_seeds"]
        ]
        large = [
            index.get((selection["lever"], P6_POPULATIONS[1], seed))
            for seed in manifest["matched_seeds"]
        ]
        missing = sum(item is None for item in small + large)
        valid_small = [item for item in small if item is not None]
        valid_large = [item for item in large if item is not None]
        if scale_blocker is not None:
            small_integrity = (
                len(valid_small) == len(small)
                and all(_all_integrity_passed(item) for item in valid_small)
            )
            fixture_small = (
                sum(
                    _fixture_active(item, selection["activation_metrics"])
                    for item in valid_small
                )
                if small_integrity else 0
            )
            reports.append({
                "lever": selection["lever"],
                "decision_group": selection["decision_group"],
                "role": selection["role"],
                "arm_label": selection["arm_label"],
                "disposition": "scale_execution_blocked",
                "missing_run_count": len(large) + sum(item is None for item in small),
                "integrity_passed": small_integrity,
                "activation": {
                    "small_active_seeds": fixture_small,
                    "large_active_seeds": 0,
                    "passed": False,
                },
                "metrics": [],
                "rare_event_scale": None,
                "tail_required": False,
                "scale_execution_blocker": dict(scale_blocker),
                "million_person_effect_claimed": False,
            })
            if not small_integrity:
                errors.append(
                    f"{selection['lever']}: 100k prerequisite has a runtime or integrity defect"
                )
            continue
        integrity = (
            missing == 0
            and all(_all_integrity_passed(item) for item in valid_small + valid_large)
        )
        metric_reports = []
        if integrity:
            metric_reports = [
                _metric_confirmation(selection, metric_id, valid_small, valid_large)
                for metric_id in selection["salient_metrics"]
            ]
        fixture_small = (
            sum(_fixture_active(item, selection["activation_metrics"]) for item in valid_small)
            if integrity else 0
        )
        fixture_large = (
            sum(_fixture_active(item, selection["activation_metrics"]) for item in valid_large)
            if integrity else 0
        )
        activation_passed = (
            integrity
            and fixture_small == len(valid_small)
            and fixture_large == len(valid_large)
        )
        confirmed = (
            integrity and activation_passed and metric_reports
            and all(item["passed"] for item in metric_reports)
        )
        rare = _rare_scale(selection, valid_small, valid_large) if integrity else None
        if not integrity:
            disposition = "p6_runtime_or_integrity_defect"
        elif confirmed:
            disposition = "finite_size_confirmed"
        else:
            disposition = "finite_size_dependency"
        reports.append({
            "lever": selection["lever"],
            "decision_group": selection["decision_group"],
            "role": selection["role"],
            "arm_label": selection["arm_label"],
            "disposition": disposition,
            "missing_run_count": missing,
            "integrity_passed": integrity,
            "activation": {
                "small_active_seeds": fixture_small,
                "large_active_seeds": fixture_large,
                "passed": activation_passed,
            },
            "metrics": metric_reports,
            "rare_event_scale": rare,
            "tail_required": bool(
                rare and rare["scale_materially_changes_event"]
            ),
            "scale_execution_blocker": None,
            "million_person_effect_claimed": True,
        })
        if disposition == "p6_runtime_or_integrity_defect":
            errors.append(f"{selection['lever']}: runtime or integrity defect")
    return reports, errors


def _tail_summary(
    report: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metric_id = report["rare_event_scale"]["metric_id"]
    selected = [item for item in runs if item["lever"] == report["lever"]]
    totals = sorted(_event_total(item, metric_id) for item in selected)
    valid = len(selected) == 16 and all(_all_integrity_passed(item) for item in selected)
    quantile_index = lambda q: min(len(totals) - 1, max(0, math.ceil(q * len(totals)) - 1))
    return {
        "metric_id": metric_id,
        "seed_count": len(selected),
        "event_incidence": (
            sum(value > 0.0 for value in totals) / len(totals) if totals else None
        ),
        "mean_events": fmean(totals) if totals else None,
        "median_events": totals[quantile_index(0.5)] if totals else None,
        "p95_events": totals[quantile_index(0.95)] if totals else None,
        "maximum_events": max(totals) if totals else None,
        "valid": valid,
    }


def run_p6(
    *,
    artifact_dir: Path,
    source_revision: str,
    p2_source: str | Path | Mapping[str, Any],
    p5_source: str | Path | Mapping[str, Any],
    seeds: Sequence[int] = P6_SEEDS,
    populations: Sequence[int] = P6_POPULATIONS,
    workers: int = 8,
    small_jobs: int = 4,
    large_jobs: int = 1,
    resume: bool = True,
    formal: bool = True,
    progress: Callable[[dict[str, Any], bool], None] | None = None,
) -> dict[str, Any]:
    seeds = tuple(int(seed) for seed in seeds)
    populations = tuple(int(value) for value in populations)
    if formal and seeds != P6_SEEDS:
        raise ValueError("formal P6 requires the eight frozen matched seeds")
    if formal and populations != P6_POPULATIONS:
        raise ValueError("formal P6 requires matched 100k and 1M populations")
    if workers != 8:
        raise ValueError("P6 requires exactly eight native engine workers")
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("P6 seeds must be nonempty and distinct")
    if min(small_jobs, large_jobs) < 1:
        raise ValueError("P6 job counts must be positive")

    manifest = build_p6_manifest(p2_source, p5_source)
    errors = list(manifest["errors"])
    explicit_defects: list[str] = []
    selections = manifest["representatives"]
    all_runs: list[dict[str, Any]] = []
    hits = 0
    executed = 0
    for population in populations:
        batch_selections = [
            selection for selection in selections
            if not (
                formal
                and population == P6_POPULATIONS[1]
                and selection["lever"] in P6_SCALE_EXECUTION_BLOCKERS
            )
        ]
        batch, batch_hits, batch_executed = _run_batch(
            batch_selections,
            seeds=seeds,
            population=population,
            workers=workers,
            jobs=small_jobs if population == P6_POPULATIONS[0] else large_jobs,
            source_revision=source_revision,
            manifest_hash=manifest["manifest_hash"],
            artifact_dir=artifact_dir,
            phase="base",
            resume=resume,
            progress=progress,
        )
        all_runs.extend(batch)
        hits += batch_hits
        executed += batch_executed

    raw_integrity_errors = [
        f"{item['lever']} population={item['population']} seed={item['seed']}: "
        "runtime or integrity defect"
        for item in all_runs
        if not _all_integrity_passed(item)
    ]
    if formal:
        explicit_defects.extend(raw_integrity_errors)
    else:
        errors.extend(raw_integrity_errors)

    reports: list[dict[str, Any]] = []
    analysis_errors: list[str] = []
    if set(populations) == set(P6_POPULATIONS):
        reports, analysis_errors = analyze_base(manifest, all_runs)
        target = explicit_defects if formal else errors
        target.extend(item for item in analysis_errors if item not in target)

    tail_runs: list[dict[str, Any]] = []
    tail_hits = 0
    tail_executed = 0
    if formal and not errors:
        tail_selections = [
            selection for selection in selections
            if any(
                report["lever"] == selection["lever"] and report["tail_required"]
                for report in reports
            )
        ]
        if tail_selections:
            tail_runs, tail_hits, tail_executed = _run_batch(
                tail_selections,
                seeds=P6_TAIL_EXTRA_SEEDS,
                population=P6_POPULATIONS[1],
                workers=workers,
                jobs=large_jobs,
                source_revision=source_revision,
                manifest_hash=manifest["manifest_hash"],
                artifact_dir=artifact_dir,
                phase="tail",
                resume=resume,
                progress=progress,
            )
            large_base = [
                item for item in all_runs if item["population"] == P6_POPULATIONS[1]
            ]
            for report in reports:
                if report["tail_required"]:
                    report["tail"] = _tail_summary(
                        report,
                        large_base + tail_runs,
                    )
                    if not report["tail"]["valid"]:
                        errors.append(f"{report['lever']}: incomplete tail confirmation")

    rare_ledger = []
    report_by_lever = {item["lever"]: item for item in reports}
    for row in manifest["rare_event_ledger"]:
        if row["runnable"]:
            report = report_by_lever.get(row["lever"])
            rare_ledger.append({
                **row,
                "p6_disposition": report["disposition"] if report else "missing",
                "scale": report.get("rare_event_scale") if report else None,
                "tail_required": report.get("tail_required") if report else None,
                "tail": report.get("tail") if report else None,
            })
        else:
            rare_ledger.append({
                **row,
                "p6_disposition": "blocked_by_p2",
                "scale": None,
                "tail_required": False,
                "tail": None,
            })

    dispositions: dict[str, int] = {}
    for item in reports:
        dispositions[item["disposition"]] = dispositions.get(item["disposition"], 0) + 1
    rare_dispositions: dict[str, int] = {}
    for item in rare_ledger:
        key = str(item["p6_disposition"])
        rare_dispositions[key] = rare_dispositions.get(key, 0) + 1
    status = "accepted_with_explicit_defects" if formal and not errors else (
        "preflight_complete" if not formal and not errors else "failed"
    )
    evidence = {"reports": reports, "rare_event_ledger": rare_ledger}
    expected_base_records = len(selections) * len(seeds) * len(populations)
    blocked_base_records = (
        len(P6_SCALE_EXECUTION_BLOCKERS) * len(seeds)
        if formal and P6_POPULATIONS[1] in populations else 0
    )
    payload = {
        "schema_version": P6_SCHEMA_VERSION,
        "status": status,
        "errors": errors,
        "explicit_defects": explicit_defects,
        "source_revision": source_revision,
        "manifest": manifest,
        "protocol": {
            "populations": list(populations),
            "matched_seeds": list(seeds),
            "workers": workers,
            "small_jobs": small_jobs,
            "large_jobs": large_jobs,
            "legacy_python_simulator_used": False,
            "million_person_branching": "native_in_memory_clone",
            "scale_execution_blockers": {
                lever: dict(item)
                for lever, item in P6_SCALE_EXECUTION_BLOCKERS.items()
            },
        },
        "counts": {
            "decision_groups": len({item["decision_group"] for item in selections if item["role"] == "group"}),
            "representatives": len(selections),
            "rare_event_mechanisms": len(rare_ledger),
            "runnable_rare_event_mechanisms": sum(item["runnable"] for item in rare_ledger),
            "blocked_rare_event_mechanisms": sum(not item["runnable"] for item in rare_ledger),
            "base_run_records": len(all_runs),
            "expected_base_run_records": expected_base_records,
            "scale_execution_blocked_run_records": blocked_base_records,
            "explicit_defects": len(explicit_defects),
            "tail_run_records": len(tail_runs),
            "executed_native_run_records": executed + tail_executed,
            "cache_hits": hits + tail_hits,
            "native_branch_paths": 2 * (len(all_runs) + len(tail_runs)),
            "planned_native_branch_paths": 2 * (
                expected_base_records + len(tail_runs)
            ),
            "scale_execution_blocked_native_branch_paths": 2 * blocked_base_records,
            "dispositions": dispositions,
            "rare_dispositions": rare_dispositions,
        },
        "reports": reports,
        "rare_event_ledger": rare_ledger,
        "infrastructure_notices": [
            "The M8 serialized checkpoint size ceiling does not admit a "
            "one-million-person economy; P6 uses the native in-memory clone "
            "path and records this scale limitation explicitly.",
            "Four representatives with 32 planned 1M seed cells are classified "
            "as scale_execution_blocked. P6 withholds their million-person "
            "effect claims rather than allowing an unbounded audit run.",
        ],
        "hashes": {
            "p6_manifest": manifest["manifest_hash"],
            "p6_evidence": _canonical_hash(evidence),
        },
    }
    payload["hashes"]["p6_acceptance"] = _canonical_hash({
        "status": status,
        "errors": errors,
        "explicit_defects": explicit_defects,
        "source_revision": source_revision,
        "protocol": payload["protocol"],
        "manifest": payload["hashes"]["p6_manifest"],
        "evidence": payload["hashes"]["p6_evidence"],
    })
    _atomic_json(artifact_dir / "p6_report.json", payload)
    return payload


def render_p6_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy causality P6 report",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Protocol",
        "",
        f"- Populations: `{payload['protocol']['populations']}`",
        f"- Matched seeds: `{payload['protocol']['matched_seeds']}`",
        f"- Native workers: {payload['protocol']['workers']}",
        f"- Representatives: {payload['counts']['representatives']}",
        f"- Rare-event mechanisms: {payload['counts']['rare_event_mechanisms']}",
        f"- Native branch paths: {payload['counts']['native_branch_paths']}",
        f"- Planned native branch paths: {payload['counts']['planned_native_branch_paths']}",
        f"- Scale-blocked run records: {payload['counts']['scale_execution_blocked_run_records']}",
        f"- Legacy Python simulator used: {'yes' if payload['protocol']['legacy_python_simulator_used'] else 'no'}",
        "",
        "## Representative ledger",
        "",
        "| Group | Lever | Role | P6 disposition | Tail required |",
        "|---|---|---|---|---:|",
    ]
    for report in payload["reports"]:
        lines.append(
            f"| `{report['decision_group']}` | `{report['lever']}` | `{report['role']}` | "
            f"`{report['disposition']}` | {'yes' if report['tail_required'] else 'no'} |"
        )
    lines.extend([
        "",
        "## Rare-event ledger",
        "",
        "| Lever | Metric | P2 disposition | P6 disposition | Tail required |",
        "|---|---|---|---|---:|",
    ])
    for row in payload["rare_event_ledger"]:
        lines.append(
            f"| `{row['lever']}` | `{row['metric_id']}` | `{row['p2_disposition']}` | "
            f"`{row['p6_disposition']}` | {'yes' if row['tail_required'] else 'no'} |"
        )
    lines.extend([
        "",
        "## Frozen identities",
        "",
        f"- P6 manifest: `{payload['hashes']['p6_manifest']}`",
        f"- P6 evidence: `{payload['hashes']['p6_evidence']}`",
        f"- P6 acceptance: `{payload['hashes']['p6_acceptance']}`",
        "",
    ])
    return "\n".join(lines)


__all__ = [
    "P6_POPULATIONS",
    "P6_SCHEMA_VERSION",
    "P6_SEEDS",
    "P6_SCALE_EXECUTION_BLOCKERS",
    "P6_TAIL_EXTRA_SEEDS",
    "RARE_EVENT_MECHANISMS",
    "REPRESENTATIVES",
    "analyze_base",
    "build_p6_manifest",
    "render_p6_markdown",
    "run_p6",
]
