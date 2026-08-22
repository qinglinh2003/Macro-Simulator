"""Matched native experiments for Policy causality audit milestone P2.

P2 is deliberately narrower than crisis efficacy.  It asks whether every
registered Policy lever is safe in an ordinary state and whether its declared
mechanism can be activated at a clean runtime boundary.  Python only builds
the experiment, branches native checkpoints, and reduces maintained metrics;
all simulated days and policy reads remain in the C++ engine.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean, stdev
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

from macro_sim import native_backend
from macro_sim.core.native_policy_routes import (
    ENGINE_ROUTE_DEFECT,
    NATIVE_POLICY_ROUTES,
)
from macro_sim.core.policy_registry import (
    Bool,
    Choices,
    EconomyId,
    EconomySet,
    NullableRange,
    Range,
    REGISTRY,
)
from macro_sim.diagnostics.config_experiment import (
    apply_native_activation_scenario,
    derive_analysis_metrics,
    population_scaled_new_game,
    summarize_metric_series,
    summarize_paired_runs,
    summarize_time_responses,
)
from macro_sim.diagnostics.policy_catalog import (
    ACTIVATION_FIXTURES,
    METRIC_MATERIALITY,
)
from macro_sim.diagnostics.policy_contracts import (
    PolicyCausalContract,
    TreatmentBatch,
    build_contracts,
    build_p0_payload,
)
from macro_sim.native_backend import NativeSimulationSession


P2_SCHEMA_VERSION = "policy-causality-p2-v1"
DEFAULT_SEEDS = (4_201, 4_213, 4_231, 4_253)
FINAL_DISPOSITIONS = frozenset({
    "accepted",
    "accepted_activation_only",
    "accepted_structural_long_horizon",
    "accepted_expert_only",
    "redundant_merge",
    "engine_route_defect",
    "mechanism_defect",
    "observable_defect",
    "unsupported_by_current_engine",
    "remove_from_player_surface",
})


# P0 fixture identifiers are economic contracts.  The names below select the
# smallest already-audited native state builder that realizes each contract.
FIXTURE_NATIVE_SCENARIOS: Mapping[str, str] = {
    "ACT_FISCAL_RESOURCE_SLACK": "labor_demand_contraction",
    "ACT_TAX_BASES": "wealth_dispersion",
    "ACT_PENSION_ELIGIBILITY": "neutral_baseline",
    "ACT_DEBT_ISSUANCE": "active_job_guarantee_public_works",
    "ACT_TAYLOR_INTERIOR": "monetary_tightening_pressure",
    "ACT_BANK_LIQUIDITY": "bank_run_pressure",
    "ACT_DEPOSIT_PRICING": "positive_deposit_carry",
    "ACT_BANK_SOLVENCY": "binding_bank_capital",
    "ACT_BANK_ENTRY": "bank_entry_cap_pressure",
    "ACT_HOUSEHOLD_CREDIT": "household_arrears_pressure",
    "ACT_FIRM_CREDIT": "firm_debt_service_pressure",
    "ACT_MORTGAGE_CREDIT": "housing_joint_pressure",
    "ACT_HOUSING_TRANSACTIONS": "housing_liquid_market",
    "ACT_MARKET_MARGIN": "active_chartist_demand",
    "ACT_TRADE_FLOWS": "world_trade_integration",
    "ACT_MIGRATION_FLOWS": "world_migration_wage_gap",
    "ACT_PEG_PRESSURE": "world_peg_pressure",
    "ACT_ENERGY_SHORTAGE": "energy_joint_pressure",
    "ACT_INSOLVENCY_ARREARS": "credit_joint_pressure",
    "ACT_OWNERSHIP_TRANSITION": "energy_joint_pressure",
    "ACT_FISCAL_ACCOUNTING_DIVERGENCE": "neutral_baseline",
}


LEVER_NATIVE_SCENARIOS: Mapping[str, str] = {
    "tax_energy_rate": "energy_rising_price",
    "tax_energy_windfall": "energy_rising_price",
    "energy_cap_compensation": "energy_rising_price",
    "energy_subsidy_rate": "energy_rising_price",
    "energy_subsidy_threshold": "energy_rising_price",
    "bank_resolution_fund": "bank_run_pressure",
    "mortgage_foreclosure_ltv": "housing_distressed_market",
    "mortgage_arrears_floor": "housing_distressed_market",
    "rental_eviction_arrears": "housing_rental_pressure",
    "unified_bank_rwa": "binding_bank_capital",
    # A peg transition must begin from a float.  The treatment itself creates
    # the peg; using world_peg_pressure here would make that action a no-op.
    "fx_regime": "world_trade_integration",
    "peg_anchor": "world_trade_integration",
}


@dataclass(frozen=True, slots=True)
class ExperimentArm:
    label: str
    dose_class: str
    actions: tuple[tuple[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "dose_class": self.dose_class,
            "actions": [
                {"lever": name, "value": _jsonable(value)}
                for name, value in self.actions
            ],
        }


@dataclass(frozen=True, slots=True)
class ExperimentGroup:
    group_id: str
    phase: str
    native_scenario: str
    countries: int
    days: int
    burn_in_days: int
    withdrawal_days: int
    setup_actions: tuple[tuple[str, Any], ...]
    contracts: tuple[PolicyCausalContract, ...]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return [_jsonable(item) for item in sorted(value)]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
        json.dump(_jsonable(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _target_value(batch: TreatmentBatch, lever: str) -> Any:
    return next(value for name, value in batch.actions if name == lever)


def select_experiment_arms(
    contract: PolicyCausalContract,
    *,
    phase: str,
) -> tuple[ExperimentArm, ...]:
    """Select predeclared local and meaningful doses from the P0 contract."""
    if phase not in {"ordinary", "activation"}:
        raise ValueError(f"unknown P2 phase {phase!r}")
    lever = REGISTRY[contract.lever]
    batches = contract.treatment_batches
    validation = lever.validation
    if isinstance(validation, Range):
        baseline = contract.reference_baseline
        origin = 0.0 if baseline is None else float(baseline)
        ordered = sorted(
            batches,
            key=lambda batch: abs(float(_target_value(batch, contract.lever)) - origin),
        )
        selected = [ordered[-1]]
        labels = ["meaningful"]
        if phase == "activation" and len(ordered) > 1:
            selected.insert(0, ordered[0])
            labels.insert(0, "local")
        return tuple(
            ExperimentArm(batch.label, dose_class, batch.actions)
            for batch, dose_class in zip(selected, labels, strict=True)
        )
    # Every alternative enum/state transition is economically distinct.  The
    # same applies to booleans, sets, and economy references.
    return tuple(
        ExperimentArm(batch.label, "transition", batch.actions)
        for batch in batches
    )


def _countries(contract: PolicyCausalContract) -> int:
    return 3 if contract.scope == "external" else 1


def _native_scenario(contract: PolicyCausalContract) -> str:
    return LEVER_NATIVE_SCENARIOS.get(
        contract.lever,
        FIXTURE_NATIVE_SCENARIOS[contract.activation_fixture],
    )


def _setup_actions(contract: PolicyCausalContract) -> tuple[tuple[str, Any], ...]:
    if contract.lever == "soe_price_at_cost":
        return (("soe_efirm", True),)
    if (
        contract.activation_fixture == "ACT_TAYLOR_INTERIOR"
        and contract.lever != "r_max"
    ):
        return (("r_max", 0.02),)
    return ()


def build_experiment_groups(
    contracts: Sequence[PolicyCausalContract],
    *,
    phase: str,
    ordinary_days: int,
    activation_days: int,
    burn_in_days: int,
    withdrawal_days: int,
) -> tuple[ExperimentGroup, ...]:
    if phase not in {"ordinary", "activation"}:
        raise ValueError(f"unknown P2 phase {phase!r}")
    grouped: dict[tuple[Any, ...], list[PolicyCausalContract]] = {}
    for contract in contracts:
        if NATIVE_POLICY_ROUTES[contract.lever].disposition == ENGINE_ROUTE_DEFECT:
            continue
        scenario = "neutral_baseline" if phase == "ordinary" else _native_scenario(contract)
        setup = () if phase == "ordinary" else _setup_actions(contract)
        days = ordinary_days if phase == "ordinary" else activation_days
        key = (scenario, _countries(contract), days, setup)
        grouped.setdefault(key, []).append(contract)
    output = []
    for (scenario, countries, days, setup), members in sorted(
        grouped.items(), key=lambda item: repr(item[0])
    ):
        identity = {
            "phase": phase,
            "scenario": scenario,
            "countries": countries,
            "days": days,
            "setup": setup,
            "levers": [item.lever for item in members],
        }
        output.append(ExperimentGroup(
            group_id=_canonical_hash(identity)[:16],
            phase=phase,
            native_scenario=scenario,
            countries=countries,
            days=days,
            burn_in_days=burn_in_days,
            withdrawal_days=withdrawal_days,
            setup_actions=setup,
            contracts=tuple(members),
        ))
    return tuple(output)


def _actions(
    items: Iterable[tuple[str, Any]], *, economy_id: int = 0
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {"economy_id": economy_id, "lever": name, "value": _jsonable(value)}
        for name, value in items
    )


def _restore_actions(
    arm: ExperimentArm,
    baseline: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    names = {name for name, _value in arm.actions}
    if names & {"manual_policy_rate", "monetary_regime"}:
        names.update({"manual_policy_rate", "monetary_regime"})
    if names & {"fx_regime", "peg_anchor"}:
        names.update({"fx_regime", "peg_anchor"})
    ordered = sorted(names)
    return tuple(
        {"economy_id": 0, "lever": name, "value": _jsonable(baseline[name])}
        for name in ordered
    )


def _history_rows_after(
    session: NativeSimulationSession,
    *,
    economy_id: int,
    first_tick_exclusive: int,
    last_tick_inclusive: int,
) -> list[dict[str, Any]]:
    bounds = session.history_bounds()
    cursor = int(bounds["oldest_sequence"])
    stop = int(bounds["next_sequence"])
    rows: list[dict[str, Any]] = []
    while cursor < stop:
        page = session.maintained_history_page(cursor, min(512, stop - cursor))
        for frame in page["frames"]:
            tick = int(frame["tick"])
            if first_tick_exclusive < tick <= last_tick_inclusive:
                row = derive_analysis_metrics(frame["economies"][economy_id])
                row["_tick"] = tick
                rows.append(row)
        next_cursor = int(page["next_sequence"])
        if next_cursor <= cursor:
            raise RuntimeError("native metric history cursor did not advance")
        cursor = next_cursor
    return rows


def _capture_window(
    session: NativeSimulationSession,
    *,
    t0: int,
    days: int,
    metric_ids: Sequence[str],
    countries: int,
) -> dict[str, Any]:
    summaries_by_economy: dict[str, dict[str, Any]] = {}
    series_by_economy: dict[str, dict[str, Any]] = {}
    missing_by_economy: dict[str, list[str]] = {}
    finite = True
    for economy_id in range(countries):
        rows = _history_rows_after(
            session,
            economy_id=economy_id,
            first_tick_exclusive=t0,
            last_tick_inclusive=t0 + days,
        )
        summaries = {
            name: asdict(summary)
            for name, summary in summarize_metric_series(rows).items()
        }
        missing = sorted(set(metric_ids) - set(summaries))
        selected = tuple(metric_id for metric_id in metric_ids if metric_id in summaries)
        series = {
            metric_id: {
                "ticks": [int(row["_tick"]) for row in rows],
                "values": [float(row[metric_id]) for row in rows],
            }
            for metric_id in selected
        }
        finite = finite and all(
            math.isfinite(value)
            for item in series.values()
            for value in item["values"]
        )
        summaries_by_economy[str(economy_id)] = {
            metric_id: summaries[metric_id] for metric_id in selected
        }
        series_by_economy[str(economy_id)] = series
        missing_by_economy[str(economy_id)] = missing
    return {
        "metric_summaries": summaries_by_economy["0"],
        "metric_summaries_by_economy": summaries_by_economy,
        "metric_series": series_by_economy["0"],
        "metric_series_by_economy": series_by_economy,
        "missing_metrics_by_economy": missing_by_economy,
        "finite": finite,
    }


def _terminal_metrics(
    session: NativeSimulationSession,
    *,
    metric_ids: Sequence[str],
) -> dict[str, float]:
    row = derive_analysis_metrics(session.maintained_metrics()["economies"][0])
    return {
        metric_id: float(row[metric_id])
        for metric_id in metric_ids
        if isinstance(row.get(metric_id), (int, float))
        and not isinstance(row.get(metric_id), bool)
        and math.isfinite(float(row[metric_id]))
    }


def _run_group_seed(
    group: ExperimentGroup,
    *,
    seed: int,
    population: int,
    workers: int,
    source_revision: str,
    p0_root: str,
    cache_path: Path,
    resume: bool,
) -> tuple[dict[str, Any], bool]:
    signature_payload = {
        "schema_version": P2_SCHEMA_VERSION,
        "source_revision": source_revision,
        "p0_root": p0_root,
        "population": population,
        "workers": workers,
        "seed": seed,
        "group": {
            "phase": group.phase,
            "scenario": group.native_scenario,
            "countries": group.countries,
            "days": group.days,
            "burn_in_days": group.burn_in_days,
            "withdrawal_days": group.withdrawal_days,
            "setup_actions": group.setup_actions,
            "contracts": [item.to_dict() for item in group.contracts],
        },
    }
    signature = _canonical_hash(signature_payload)
    if resume and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("run_signature") == signature:
            return dict(cached["result"]), True

    started = time.perf_counter()
    maximum_days = group.burn_in_days + group.days + group.withdrawal_days + 2
    baseline = population_scaled_new_game(
        population=population,
        days=maximum_days,
        seed=seed,
        countries=group.countries,
    )
    native_spec = native_backend.build_native_new_game_spec(baseline)
    apply_native_activation_scenario(
        native_spec,
        scenario=group.native_scenario,
    )
    session = NativeSimulationSession.create_from_native_spec(
        native_spec,
        worker_count=workers,
        history_capacity_frames=maximum_days + 4,
    )
    if group.setup_actions:
        session.advance(1, actions=_actions(group.setup_actions))
        if group.burn_in_days > 1:
            session.advance(group.burn_in_days - 1)
    else:
        session.advance(group.burn_in_days)
    t0 = session.tick
    baseline_values = session.policy_values(0)
    metric_ids = tuple(sorted(set().union(*(
        set(contract.materiality_metrics)
        | set(ACTIVATION_FIXTURES[contract.activation_fixture].activation_metrics)
        for contract in group.contracts
    ))))

    control = session.clone()
    control.advance(group.days + group.withdrawal_days)
    control_main = _capture_window(
        control,
        t0=t0,
        days=group.days,
        metric_ids=metric_ids,
        countries=group.countries,
    )
    control_tail = _terminal_metrics(control, metric_ids=metric_ids)

    contracts: dict[str, Any] = {}
    for contract in group.contracts:
        contract_metrics = tuple(sorted(set(contract.materiality_metrics) | set(
            ACTIVATION_FIXTURES[contract.activation_fixture].activation_metrics
        )))
        arms = []
        for arm in select_experiment_arms(contract, phase=group.phase):
            branch = session.clone()
            treatment_actions = _actions(arm.actions)
            try:
                branch.advance(group.days, actions=treatment_actions)
                policy_after = branch.policy_values(0)
                treatment_main = _capture_window(
                    branch,
                    t0=t0,
                    days=group.days,
                    metric_ids=contract_metrics,
                    countries=group.countries,
                )
                withdrawal = None
                if arm.dose_class in {"meaningful", "transition"}:
                    restore = _restore_actions(arm, baseline_values)
                    branch.advance(group.withdrawal_days, actions=restore)
                    restored_values = branch.policy_values(0)
                    withdrawal = {
                        "actions": restore,
                        "policy_restored": all(
                            _jsonable(restored_values[name]) == _jsonable(baseline_values[name])
                            for name in {item["lever"] for item in restore}
                        ),
                        "terminal_metrics": _terminal_metrics(
                            branch, metric_ids=contract_metrics
                        ),
                    }
                arms.append({
                    **arm.to_dict(),
                    "actions": treatment_actions,
                    "policy_after": {
                        name: _jsonable(policy_after[name])
                        for name, _value in arm.actions
                    },
                    "policy_applied": all(
                        _jsonable(policy_after[name]) == _jsonable(value)
                        for name, value in arm.actions
                    ),
                    "run": treatment_main,
                    "withdrawal": withdrawal,
                    "error": None,
                })
            except Exception as exc:  # stability/validation is an estimand
                arms.append({
                    **arm.to_dict(),
                    "actions": treatment_actions,
                    "policy_after": {},
                    "policy_applied": False,
                    "run": None,
                    "withdrawal": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                })
        contracts[contract.lever] = {
            "metric_ids": contract_metrics,
            "arms": arms,
        }

    result = {
        "seed": seed,
        "phase": group.phase,
        "native_scenario": group.native_scenario,
        "countries": group.countries,
        "population_per_country": population,
        "workers": workers,
        "days": group.days,
        "burn_in_days": group.burn_in_days,
        "withdrawal_days": group.withdrawal_days,
        "t0": t0,
        "baseline_policy_values": _jsonable(baseline_values),
        "control": control_main,
        "control_withdrawal_terminal": control_tail,
        "contracts": contracts,
        "elapsed_seconds": time.perf_counter() - started,
        "memory_bytes": session.memory_usage(),
    }
    _atomic_json(cache_path, {
        "schema_version": "policy-p2-native-run-cache-v1",
        "run_signature": signature,
        "signature": signature_payload,
        "result": result,
    })
    return result, False


def _run_groups(
    groups: Sequence[ExperimentGroup],
    *,
    seeds: Sequence[int],
    population: int,
    workers: int,
    jobs: int,
    source_revision: str,
    p0_root: str,
    artifact_dir: Path,
    resume: bool,
    progress: Any = None,
) -> tuple[list[dict[str, Any]], int, int]:
    results: list[dict[str, Any]] = []
    cache_hits = 0
    executed = 0
    for group_index, group in enumerate(groups, start=1):
        futures = {}
        with ThreadPoolExecutor(max_workers=min(jobs, len(seeds))) as executor:
            for seed in seeds:
                path = artifact_dir / "runs" / group.phase / group.group_id / f"{seed}.json"
                future = executor.submit(
                    _run_group_seed,
                    group,
                    seed=seed,
                    population=population,
                    workers=workers,
                    source_revision=source_revision,
                    p0_root=p0_root,
                    cache_path=path,
                    resume=resume,
                )
                futures[future] = seed
            group_results = []
            for future in as_completed(futures):
                result, cached = future.result()
                group_results.append(result)
                cache_hits += int(cached)
                executed += int(not cached)
        results.extend(sorted(group_results, key=lambda item: int(item["seed"])))
        if progress is not None:
            progress(group_index, len(groups), group)
    return results, cache_hits, executed


def _contract_phase_runs(
    raw_runs: Sequence[Mapping[str, Any]],
    lever: str,
) -> tuple[list[Mapping[str, Any]], dict[str, list[Mapping[str, Any]]]]:
    controls = []
    arms: dict[str, list[Mapping[str, Any]]] = {}
    for raw in raw_runs:
        contract = raw.get("contracts", {}).get(lever)
        if contract is None:
            continue
        controls.append(raw["control"])
        for arm in contract["arms"]:
            arms.setdefault(arm["label"], []).append(arm)
    return controls, arms


def _metric_changed(
    effects: Mapping[str, Any],
    metric_ids: Iterable[str],
    *,
    tolerance: float = 1.0e-12,
) -> tuple[str, ...]:
    changed = []
    for metric_id in metric_ids:
        item = effects.get(metric_id, {}).get("post_burnin_mean")
        if item is not None and abs(float(item["mean_difference"])) > tolerance:
            changed.append(metric_id)
    return tuple(changed)


def _salient_metrics(
    effects: Mapping[str, Any],
    controls: Sequence[Mapping[str, Any]],
    metric_ids: Iterable[str],
) -> tuple[str, ...]:
    salient = []
    for metric_id in metric_ids:
        materiality = METRIC_MATERIALITY[metric_id]
        statistic = materiality.default_statistic
        item = effects.get(metric_id, {}).get(statistic)
        if item is None:
            continue
        absolute = abs(float(item["mean_difference"]))
        relative_value = item.get("mean_relative_difference")
        relative = abs(float(relative_value)) if relative_value is not None else 0.0
        control_values = [
            float(run["metric_summaries"][metric_id][statistic])
            for run in controls
            if metric_id in run.get("metric_summaries", {})
        ]
        control_sd = stdev(control_values) if len(control_values) > 1 else 0.0
        if (
            absolute >= materiality.absolute_floor
            or relative >= materiality.relative_floor
            or (control_sd > 0.0 and absolute >= materiality.standardized_floor * control_sd)
        ):
            salient.append(metric_id)
    return tuple(salient)


def _fixture_activation(
    controls: Sequence[Mapping[str, Any]],
    fixture_id: str,
) -> dict[str, Any]:
    metrics = ACTIVATION_FIXTURES[fixture_id].activation_metrics
    per_seed = []
    for run in controls:
        active_metrics = []
        for metric_id in metrics:
            series = run.get("metric_series", {}).get(metric_id, {}).get("values", ())
            if any(abs(float(value)) > 1.0e-12 for value in series):
                active_metrics.append(metric_id)
        per_seed.append(active_metrics)
    return {
        "declared_metrics": list(metrics),
        "active_metrics_by_seed": per_seed,
        "activated_seed_count": sum(bool(items) for items in per_seed),
        "passed": len(per_seed) == 4 and all(per_seed),
    }


def _arm_analysis(
    controls: Sequence[Mapping[str, Any]],
    raw_arms: Sequence[Mapping[str, Any]],
    contract: PolicyCausalContract,
) -> dict[str, Any]:
    failures = [arm["error"] for arm in raw_arms if arm.get("error")]
    complete = [arm for arm in raw_arms if not arm.get("error")]
    if failures or len(complete) != len(controls):
        return {
            "label": raw_arms[0]["label"],
            "dose_class": raw_arms[0]["dose_class"],
            "complete_seed_count": len(complete),
            "failures": failures,
            "effects": {},
            "time_responses": {},
            "changed_proximal_metrics": [],
            "changed_declared_metrics": [],
            "salient_proximal_metrics": [],
            "policy_applied_all_seeds": False,
            "withdrawal_restored_all_seeds": False,
        }
    treatments = [arm["run"] for arm in complete]
    effects = summarize_paired_runs(controls, treatments)
    responses = summarize_time_responses(controls, treatments)
    changed_proximal = _metric_changed(effects, contract.mechanism_proximal_metrics)
    changed_declared = _metric_changed(effects, contract.materiality_metrics)
    salient = _salient_metrics(
        effects, controls, contract.mechanism_proximal_metrics
    )
    withdrawals = [arm.get("withdrawal") for arm in complete]
    return {
        "label": complete[0]["label"],
        "dose_class": complete[0]["dose_class"],
        "actions": complete[0]["actions"],
        "complete_seed_count": len(complete),
        "failures": [],
        "effects": effects,
        "time_responses": responses,
        "changed_proximal_metrics": list(changed_proximal),
        "changed_declared_metrics": list(changed_declared),
        "salient_proximal_metrics": list(salient),
        "policy_applied_all_seeds": all(arm["policy_applied"] for arm in complete),
        "withdrawal_restored_all_seeds": all(
            item is None or item["policy_restored"] for item in withdrawals
        ),
    }


def _dose_ordering(arms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    local = next((item for item in arms if item["dose_class"] == "local"), None)
    meaningful = next(
        (item for item in arms if item["dose_class"] == "meaningful"), None
    )
    if local is None or meaningful is None:
        return {"tested": False, "ordered_metrics": [], "reversed_metrics": []}
    ordered = []
    reversed_metrics = []
    common = set(local["changed_proximal_metrics"]) | set(
        meaningful["changed_proximal_metrics"]
    )
    for metric_id in sorted(common):
        left = abs(float(local["effects"][metric_id]["post_burnin_mean"]["mean_difference"]))
        right = abs(float(meaningful["effects"][metric_id]["post_burnin_mean"]["mean_difference"]))
        (ordered if right >= left else reversed_metrics).append(metric_id)
    return {
        "tested": True,
        "ordered_metrics": ordered,
        "reversed_metrics": reversed_metrics,
    }


def analyze_p2(
    contracts: Sequence[PolicyCausalContract],
    ordinary_runs: Sequence[Mapping[str, Any]],
    activation_runs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    reports = []
    errors = []
    for contract in contracts:
        route = NATIVE_POLICY_ROUTES[contract.lever]
        if route.disposition == ENGINE_ROUTE_DEFECT:
            reports.append({
                "lever": contract.lever,
                "owner_role": contract.owner_role,
                "decision_group": contract.decision_group,
                "semantics": contract.semantics,
                "disposition": "engine_route_defect",
                "reason": route.defect_reason,
                "ordinary": None,
                "activation": None,
            })
            continue

        ordinary_controls, ordinary_raw_arms = _contract_phase_runs(
            ordinary_runs, contract.lever
        )
        activation_controls, activation_raw_arms = _contract_phase_runs(
            activation_runs, contract.lever
        )
        ordinary_arms = [
            _arm_analysis(ordinary_controls, items, contract)
            for _label, items in sorted(ordinary_raw_arms.items())
        ]
        activation_arms = [
            _arm_analysis(activation_controls, items, contract)
            for _label, items in sorted(activation_raw_arms.items())
        ]
        fixture = _fixture_activation(
            activation_controls, contract.activation_fixture
        )
        all_arms = ordinary_arms + activation_arms
        failed = any(item["failures"] for item in all_arms)
        applied = all(item["policy_applied_all_seeds"] for item in all_arms)
        restored = all(item["withdrawal_restored_all_seeds"] for item in all_arms)
        ordinary_changed = sorted(set().union(*(
            set(item["changed_proximal_metrics"]) for item in ordinary_arms
        ))) if ordinary_arms else []
        activation_changed = sorted(set().union(*(
            set(item["changed_proximal_metrics"]) for item in activation_arms
        ))) if activation_arms else []
        activation_declared = sorted(set().union(*(
            set(item["changed_declared_metrics"]) for item in activation_arms
        ))) if activation_arms else []
        salient = sorted(set().union(*(
            set(item["salient_proximal_metrics"]) for item in activation_arms
        ))) if activation_arms else []

        reason: str
        if failed or not applied or not restored:
            disposition = "mechanism_defect"
            reason = "runtime treatment, safety, or withdrawal validation failed"
        elif contract.semantics == "new-contracts-only":
            disposition = "observable_defect"
            reason = (
                "aggregate metrics cannot prove that legacy and new contract "
                "cohorts retained distinct terms"
            )
        elif not fixture["passed"]:
            disposition = "unsupported_by_current_engine"
            reason = "the declared activation fixture did not activate in all four seeds"
        elif not activation_changed:
            if activation_declared:
                disposition = "observable_defect"
                reason = "the trajectory changed outside the declared proximal observables"
            else:
                disposition = "mechanism_defect"
                reason = "no declared native observable changed in the binding fixture"
        elif not salient:
            disposition = "accepted_expert_only"
            reason = "the mechanism is live but below the preregistered gameplay-salience screen"
        elif contract.semantics == "state-transition" and contract.lever == "soe_efirm":
            disposition = "accepted_structural_long_horizon"
            reason = "the atomic ownership transition is live and has a proximal energy effect"
        elif ordinary_changed:
            disposition = "accepted"
            reason = "the mechanism is live and salient in both ordinary and activation states"
        else:
            disposition = "accepted_activation_only"
            reason = "the mechanism is silent in the ordinary state but live in its binding fixture"

        if disposition not in FINAL_DISPOSITIONS:
            errors.append(f"{contract.lever}: invalid disposition {disposition}")
        reports.append({
            "lever": contract.lever,
            "owner_role": contract.owner_role,
            "decision_group": contract.decision_group,
            "semantics": contract.semantics,
            "disposition": disposition,
            "reason": reason,
            "ordinary": {
                "changed_proximal_metrics": ordinary_changed,
                "arms": ordinary_arms,
            },
            "activation": {
                "fixture_id": contract.activation_fixture,
                "native_scenario": _native_scenario(contract),
                "fixture_evidence": fixture,
                "changed_proximal_metrics": activation_changed,
                "salient_proximal_metrics": salient,
                "dose_ordering": _dose_ordering(activation_arms),
                "arms": activation_arms,
            },
        })
    if len(reports) != len(contracts):
        errors.append("P2 report does not exactly cover the P0 contract set")
    if any(item["disposition"] not in FINAL_DISPOSITIONS for item in reports):
        errors.append("P2 report contains a non-final disposition")
    return reports, errors


def run_p2(
    *,
    artifact_dir: Path,
    source_revision: str,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    population: int = 100_000,
    workers: int = 8,
    jobs: int = 4,
    ordinary_days: int = 7,
    activation_days: int = 30,
    burn_in_days: int = 7,
    withdrawal_days: int = 7,
    resume: bool = True,
    progress: Any = None,
) -> dict[str, Any]:
    if population < 100_000:
        raise ValueError("P2 requires at least 100,000 persons per country")
    if len(tuple(seeds)) != 4 or len(set(seeds)) != 4:
        raise ValueError("P2 requires exactly four distinct matched seeds")
    if workers != 8:
        raise ValueError("P2 full native runs require exactly eight engine workers")
    if jobs < 1:
        raise ValueError("jobs must be positive")
    if min(ordinary_days, activation_days, burn_in_days, withdrawal_days) < 1:
        raise ValueError("P2 experiment windows must be positive")

    contracts = build_contracts()
    p0 = build_p0_payload()
    ordinary_groups = build_experiment_groups(
        contracts,
        phase="ordinary",
        ordinary_days=ordinary_days,
        activation_days=activation_days,
        burn_in_days=burn_in_days,
        withdrawal_days=withdrawal_days,
    )
    activation_groups = build_experiment_groups(
        contracts,
        phase="activation",
        ordinary_days=ordinary_days,
        activation_days=activation_days,
        burn_in_days=burn_in_days,
        withdrawal_days=withdrawal_days,
    )
    ordinary, ordinary_hits, ordinary_executed = _run_groups(
        ordinary_groups,
        seeds=tuple(seeds),
        population=population,
        workers=workers,
        jobs=jobs,
        source_revision=source_revision,
        p0_root=p0["hashes"]["p0_root"],
        artifact_dir=artifact_dir,
        resume=resume,
        progress=progress,
    )
    activation, activation_hits, activation_executed = _run_groups(
        activation_groups,
        seeds=tuple(seeds),
        population=population,
        workers=workers,
        jobs=jobs,
        source_revision=source_revision,
        p0_root=p0["hashes"]["p0_root"],
        artifact_dir=artifact_dir,
        resume=resume,
        progress=progress,
    )
    reports, errors = analyze_p2(contracts, ordinary, activation)
    counts: dict[str, int] = {name: 0 for name in sorted(FINAL_DISPOSITIONS)}
    for item in reports:
        counts[item["disposition"]] += 1
    status = "accepted_with_explicit_defects" if not errors else "failed"
    evidence_hash = _canonical_hash(reports)
    payload = {
        "schema_version": P2_SCHEMA_VERSION,
        "status": status,
        "errors": errors,
        "source_revision": source_revision,
        "p0_root_hash": p0["hashes"]["p0_root"],
        "protocol": {
            "population_per_country": population,
            "matched_seeds": list(seeds),
            "native_engine_workers": workers,
            "independent_seed_jobs": min(jobs, len(seeds)),
            "ordinary_days": ordinary_days,
            "activation_days": activation_days,
            "burn_in_days": burn_in_days,
            "withdrawal_days": withdrawal_days,
            "ordinary_group_count": len(ordinary_groups),
            "activation_group_count": len(activation_groups),
            "legacy_python_simulator_used": False,
        },
        "counts": {
            "levers": len(reports),
            "ordinary_native_runs": len(ordinary),
            "activation_native_runs": len(activation),
            "executed_native_runs": ordinary_executed + activation_executed,
            "cache_hits": ordinary_hits + activation_hits,
            "dispositions": counts,
        },
        "hashes": {
            "p2_evidence": evidence_hash,
            "p2_acceptance": _canonical_hash({
                "status": status,
                "errors": errors,
                "protocol": {
                    "population": population,
                    "seeds": list(seeds),
                    "workers": workers,
                    "ordinary_days": ordinary_days,
                    "activation_days": activation_days,
                    "burn_in_days": burn_in_days,
                    "withdrawal_days": withdrawal_days,
                },
                "evidence": evidence_hash,
            }),
        },
        "reports": reports,
    }
    _atomic_json(artifact_dir / "p2_report.json", payload)
    return payload


def render_p2_markdown(payload: Mapping[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Policy causality audit P2",
        "",
        f"- Status: `{payload['status']}`",
        f"- Population per country: {payload['protocol']['population_per_country']:,}",
        f"- Matched seeds: `{payload['protocol']['matched_seeds']}`",
        f"- Native engine workers: {payload['protocol']['native_engine_workers']}",
        f"- P2 acceptance hash: `{payload['hashes']['p2_acceptance']}`",
        "",
        "## Final dispositions",
        "",
        "| Disposition | Count |",
        "|---|---:|",
    ]
    for name, count in counts["dispositions"].items():
        if count:
            lines.append(f"| `{name}` | {count} |")
    lines.extend([
        "",
        "## Lever ledger",
        "",
        "| Lever | Group | Semantics | Disposition | Reason |",
        "|---|---|---|---|---|",
    ])
    for report in payload["reports"]:
        lines.append(
            f"| `{report['lever']}` | `{report['decision_group']}` | "
            f"`{report['semantics']}` | `{report['disposition']}` | "
            f"{report['reason']} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_SEEDS",
    "FINAL_DISPOSITIONS",
    "FIXTURE_NATIVE_SCENARIOS",
    "LEVER_NATIVE_SCENARIOS",
    "P2_SCHEMA_VERSION",
    "ExperimentArm",
    "ExperimentGroup",
    "analyze_p2",
    "build_experiment_groups",
    "render_p2_markdown",
    "run_p2",
    "select_experiment_arms",
]
