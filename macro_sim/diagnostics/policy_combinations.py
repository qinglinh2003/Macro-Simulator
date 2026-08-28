"""Native policy-package experiments for causality-audit milestone P5.

P5 consumes frozen P2 mechanism dispositions, P3 scenario acceptance, and P4
single-policy evidence.  It does not repair an upstream defect or admit an
excluded crisis.  Eligible packages use a preregistered five-factor regular
fraction, component ablations, one isolated two-factor follow-up, severity and
accepted-state robustness, and an explicit withdrawal branch.

Python only builds immutable inputs, schedules native actions and shocks, and
reduces maintained C++ metrics.  Every simulated day remains in the native
engine.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
from statistics import fmean
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from macro_sim.diagnostics.config_experiment import (
    paired_effect,
    summarize_metric_series,
    summarize_paired_runs,
)
from macro_sim.diagnostics.policy_catalog import METRIC_MATERIALITY
from macro_sim.diagnostics.policy_contracts import build_contracts, build_p0_payload
from macro_sim.diagnostics.policy_crisis_effects import (
    ACCOUNTING_METRICS,
    P4_PRIMARY_OUTCOMES,
    _atomic_json,
    _cache_result,
    _canonical_hash,
    _effect_floor,
    _jsonable,
)
from macro_sim.diagnostics.policy_effects import _actions, _capture_window
from macro_sim.diagnostics.policy_scenarios import (
    CRISIS_MANIFESTS,
    DEFAULT_P3_SEEDS,
    STATE_MANIFESTS,
    _crisis_native_spec,
    _integrity,
    _schedule_tape,
    _state_native_spec,
)
from macro_sim.native_backend import NativeSimulationSession


P5_SCHEMA_VERSION = "policy-causality-p5-v1"
P5_CRISIS_ID = "CR_DEMAND_RECESSION"
P5_MAIN_SEVERITY = "moderate"
P5_SEVERITIES = ("mild", "moderate", "severe")
# Alternative-state branches must preserve the exact P3 checkpoint identity.
# P3 freezes state sessions with horizon_days + 4 history frames, so the P5
# evaluation window must fit in that retained history rather than silently
# changing checkpoint state by enlarging the buffer.
P5_EVALUATION_DAYS = 90
P5_FACTOR_MASKS = (0b0001, 0b0010, 0b0100, 0b1000, 0b0111)
ACCEPTED_P2_PREFIX = "accepted"


@dataclass(frozen=True, slots=True)
class PackageBlueprint:
    package_id: str
    title: str
    scenario_id: str
    required_levers: tuple[str, ...]
    factor_levers: tuple[str, ...] = ()
    alternative_state: str | None = None
    primary_outcomes: tuple[tuple[str, int], ...] = ()
    guardrails: tuple[tuple[str, int], ...] = ()
    isolated_pair: tuple[str, str] | None = None


PACKAGE_BLUEPRINTS: tuple[PackageBlueprint, ...] = (
    PackageBlueprint(
        "recession_response",
        "Recession response",
        P5_CRISIS_ID,
        (
            "manual_policy_rate",
            "gov_consumption_share",
            "gov_deficit_target",
            "benefit_income_floor",
            "job_guarantee",
        ),
        factor_levers=(
            "manual_policy_rate",
            "gov_consumption_share",
            "gov_deficit_target",
            "benefit_income_floor",
            "job_guarantee",
        ),
        alternative_state="BASE_SLACK",
        primary_outcomes=tuple(P4_PRIMARY_OUTCOMES.items()),
        guardrails=(
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
            ("metric.economy.inflation", -1),
            ("metric.economy.income_gini", -1),
        ),
        isolated_pair=("manual_policy_rate", "gov_consumption_share"),
    ),
    PackageBlueprint(
        "anti_inflation",
        "Anti-inflation",
        "CR_SUPPLY_STAGFLATION",
        (
            "inflation_target",
            "taylor_phi_pi",
            "gov_deficit_target",
            "energy_subsidy_rate",
            "gov_investment_share",
        ),
    ),
    PackageBlueprint(
        "bank_liquidity",
        "Bank liquidity",
        "CR_BANK_RUN",
        ("omo", "reserve_floor_frac", "lolr", "deposit_rate_floor"),
    ),
    PackageBlueprint(
        "bank_solvency",
        "Bank solvency",
        "CR_BANK_RUN",
        (
            "bank_capital_constraint",
            "bank_leverage_cap",
            "bank_exposure_limit",
            "bank_migrate_on_failure",
            "bank_resolution_fund",
        ),
    ),
    PackageBlueprint(
        "housing_cycle",
        "Housing cycle",
        "CR_HOUSING_BUST",
        (
            "mortgage_underwriting",
            "mortgage_ltv_cap",
            "mortgage_dsti_cap",
            "mortgage_min_capital_ratio",
            "housing_permits",
            "housing_transfer_tax",
        ),
    ),
    PackageBlueprint(
        "energy_emergency",
        "Energy emergency",
        "CR_ENERGY_EMBARGO",
        (
            "spr_target_units",
            "energy_rationing",
            "energy_price_cap",
            "energy_cap_compensation",
            "energy_subsidy_rate",
            "tax_energy_windfall",
        ),
    ),
    PackageBlueprint(
        "external_crisis",
        "External crisis",
        "CR_PEG_PRESSURE",
        (
            "fx_regime",
            "peg_reserve_scale",
            "manual_policy_rate",
            "capital_control",
            "tariff",
            "external_interest_settlement_fraction",
        ),
    ),
    PackageBlueprint(
        "poverty_and_employment",
        "Poverty and employment",
        P5_CRISIS_ID,
        (
            "tax_income_rate",
            "benefit_income_floor",
            "min_wage",
            "benefit_replacement",
            "job_guarantee",
        ),
        factor_levers=(
            "tax_income_rate",
            "benefit_income_floor",
            "min_wage",
            "benefit_replacement",
            "job_guarantee",
        ),
        alternative_state="STRUCT_HIGH_POVERTY",
        primary_outcomes=(
            ("metric.economy.poverty_rate", -1),
            ("metric.economy.income_gini", -1),
            ("metric.economy.unemployment_rate", -1),
        ),
        guardrails=(
            ("metric.economy.real_output", 1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
            ("metric.economy.inflation", -1),
        ),
        isolated_pair=("tax_income_rate", "benefit_income_floor"),
    ),
    PackageBlueprint(
        "debt_sustainability",
        "Debt sustainability",
        "CR_SOVEREIGN_STRESS",
        (
            "gov_deficit_target",
            "bond_finance_frac",
            "bond_coupon",
            "bond_maturity",
            "omo",
        ),
    ),
)


def _reports_by_lever(payload: Mapping[str, Any], *, phase: str) -> dict[str, Any]:
    reports = payload.get("reports")
    if not isinstance(reports, list):
        raise ValueError(f"{phase} payload has no report ledger")
    output = {str(item["lever"]): item for item in reports}
    if len(output) != len(reports):
        raise ValueError(f"{phase} report ledger contains duplicate levers")
    return output


def _p3_crises(payload: Mapping[str, Any]) -> dict[str, Any]:
    reports = payload.get("reports", {}).get("crises", ())
    return {str(item["scenario_id"]): item for item in reports}


def _p3_states(payload: Mapping[str, Any]) -> dict[str, Any]:
    reports = payload.get("reports", {}).get("states", ())
    return {str(item["scenario_id"]): item for item in reports}


def _selected_p4_arm(report: Mapping[str, Any]) -> Mapping[str, Any]:
    preferred = ("meaningful", "transition")
    for dose_class in preferred:
        arm = next(
            (item for item in report.get("arms", ()) if item["dose_class"] == dose_class),
            None,
        )
        if arm is not None:
            return arm
    raise ValueError(f"{report['lever']}: P4 has no meaningful or transition arm")


def _factor_payload(
    lever: str,
    *,
    p4_reports: Mapping[str, Mapping[str, Any]],
    baselines: Mapping[str, Any],
) -> dict[str, Any]:
    arm = _selected_p4_arm(p4_reports[lever])
    high = [dict(item) for item in arm["actions"]]
    low = [
        {"lever": str(item["lever"]), "value": baselines[str(item["lever"])]}
        for item in high
    ]
    return {
        "factor_id": lever,
        "p4_disposition": p4_reports[lever]["disposition"],
        "p4_arm": arm["label"],
        "dose_class": arm["dose_class"],
        "low_actions": low,
        "high_actions": high,
    }


def build_p5_manifest(
    *,
    p2_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
    p4_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze all nine packages without bypassing an upstream exclusion."""
    p0 = build_p0_payload()
    expected_root = p0["hashes"]["p0_root"]
    for name, payload in (("P2", p2_payload), ("P3", p3_payload), ("P4", p4_payload)):
        if payload.get("p0_root_hash") != expected_root:
            raise ValueError(f"{name} P0 root does not match the current contract")
    if p4_payload.get("status") not in {"accepted", "accepted_with_explicit_defects"}:
        raise ValueError("P4 is not accepted")

    contracts = {item.lever: item for item in build_contracts()}
    p2 = _reports_by_lever(p2_payload, phase="P2")
    p4 = _reports_by_lever(p4_payload, phase="P4")
    if set(p2) != set(contracts) or set(p4) != set(contracts):
        raise ValueError("P2/P4 ledgers do not exactly cover the current Registry")
    baselines = {name: item.reference_baseline for name, item in contracts.items()}
    crises = _p3_crises(p3_payload)
    states = _p3_states(p3_payload)

    packages: list[dict[str, Any]] = []
    for blueprint in PACKAGE_BLUEPRINTS:
        unknown = sorted(set(blueprint.required_levers) - set(contracts))
        if unknown:
            raise ValueError(f"{blueprint.package_id}: unknown levers {unknown}")
        scenario = crises.get(blueprint.scenario_id)
        scenario_blocked = scenario is None or not bool(scenario.get("accepted"))
        component_blockers = [
            {
                "lever": lever,
                "p2_disposition": p2[lever]["disposition"],
                "reason": p2[lever]["reason"],
            }
            for lever in blueprint.required_levers
            if not str(p2[lever]["disposition"]).startswith(ACCEPTED_P2_PREFIX)
        ]
        state_blocked = (
            blueprint.alternative_state is not None
            and not bool(states.get(blueprint.alternative_state, {}).get("accepted"))
        )
        runnable = not scenario_blocked and not component_blockers and not state_blocked
        blockers: list[dict[str, Any]] = []
        if scenario_blocked:
            blockers.append({
                "layer": "P3",
                "scenario_id": blueprint.scenario_id,
                "disposition": None if scenario is None else scenario.get("disposition"),
                "reason": "The required crisis did not pass the frozen P3 gate.",
            })
        if state_blocked:
            blockers.append({
                "layer": "P3",
                "scenario_id": blueprint.alternative_state,
                "disposition": states.get(blueprint.alternative_state, {}).get("disposition"),
                "reason": "The required alternative state did not pass P3.",
            })
        blockers.extend({"layer": "P2", **item} for item in component_blockers)
        factors = [
            _factor_payload(lever, p4_reports=p4, baselines=baselines)
            for lever in blueprint.factor_levers
        ] if runnable else []
        action_owners: dict[str, str] = {}
        for factor in factors:
            for action in factor["high_actions"]:
                action_lever = str(action["lever"])
                previous = action_owners.setdefault(action_lever, factor["factor_id"])
                if previous != factor["factor_id"]:
                    raise ValueError(
                        f"{blueprint.package_id}: {action_lever} belongs to two factors"
                    )
        if runnable and len(factors) != 5:
            raise ValueError(f"{blueprint.package_id}: runnable P5 packages require five factors")
        packages.append({
            **asdict(blueprint),
            "runnable": runnable,
            "blockers": blockers,
            "factors": factors,
            "design": (
                {
                    "kind": "regular_fraction",
                    "runs": 16,
                    "resolution": "IV",
                    "isolated_pair_followup": list(blueprint.isolated_pair or ()),
                }
                if runnable else None
            ),
        })
    if len(packages) != 9 or len({item["package_id"] for item in packages}) != 9:
        raise ValueError("P5 package ledger must contain exactly nine packages")
    return {
        "schema_version": P5_SCHEMA_VERSION,
        "p0_root_hash": expected_root,
        "p2_acceptance_hash": p2_payload["hashes"]["p2_acceptance"],
        "p3_acceptance_hash": p3_payload["hashes"]["p3_acceptance"],
        "p4_acceptance_hash": p4_payload["hashes"]["p4_acceptance"],
        "main_severity": P5_MAIN_SEVERITY,
        "robustness_severities": list(P5_SEVERITIES),
        "packages": packages,
    }


def _merge_factor_actions(
    factors: Sequence[Mapping[str, Any]],
    signs: Sequence[int],
) -> list[dict[str, Any]]:
    merged: dict[str, Any] = {}
    for factor, sign in zip(factors, signs, strict=True):
        key = "high_actions" if sign > 0 else "low_actions"
        for action in factor[key]:
            lever = str(action["lever"])
            if lever in merged and _jsonable(merged[lever]) != _jsonable(action["value"]):
                raise ValueError(f"conflicting package actions for {lever}")
            merged[lever] = action["value"]
    return [{"lever": lever, "value": value} for lever, value in merged.items()]


def fractional_package_design(
    factors: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    if len(factors) != 5:
        raise ValueError("P5 regular fractions require exactly five factors")
    arms: list[dict[str, Any]] = []
    for base_signs in itertools.product((-1, 1), repeat=4):
        signs = []
        for mask in P5_FACTOR_MASKS:
            sign = 1
            for index, base_sign in enumerate(base_signs):
                if mask & (1 << index):
                    sign *= base_sign
            signs.append(sign)
        bits = "".join("h" if sign > 0 else "l" for sign in signs)
        arms.append({
            "arm_id": f"arm-{bits}",
            "signs": signs,
            "actions": _merge_factor_actions(factors, signs),
        })
    return tuple(arms)


def interaction_alias_groups(
    factors: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[int, list[str]] = {}
    for left, right in itertools.combinations(range(len(factors)), 2):
        mask = P5_FACTOR_MASKS[left] ^ P5_FACTOR_MASKS[right]
        grouped.setdefault(mask, []).append(
            f"{factors[left]['factor_id']}:{factors[right]['factor_id']}"
        )
    return {
        f"{factors[left]['factor_id']}:{factors[right]['factor_id']}": tuple(
            grouped[P5_FACTOR_MASKS[left] ^ P5_FACTOR_MASKS[right]]
        )
        for left, right in itertools.combinations(range(len(factors)), 2)
    }


def _capture_period(
    session: NativeSimulationSession,
    *,
    t0: int,
    days: int,
    metric_ids: Sequence[str],
) -> dict[str, Any]:
    captured = _capture_window(
        session,
        t0=t0,
        days=days,
        metric_ids=metric_ids,
        countries=1,
        target_economy=0,
    )
    series = {
        metric_id: [float(value) for value in item["values"]]
        for metric_id, item in captured["metric_series"].items()
    }
    captured["integrity"] = _integrity(series)
    return captured


def _native_actions(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return _actions(
        ((str(item["lever"]), item["value"]) for item in items),
        economy_id=0,
    )


def _policy_matches(
    session: NativeSimulationSession,
    actions: Sequence[Mapping[str, Any]],
) -> bool:
    current = session.policy_values(0)
    return all(
        _jsonable(current[str(item["lever"])]) == _jsonable(item["value"])
        for item in actions
    )


def _run_crisis_branch(
    session: NativeSimulationSession,
    *,
    scenario_id: str = P5_CRISIS_ID,
    severity: str,
    actions: Sequence[Mapping[str, Any]],
    withdrawal_actions: Sequence[Mapping[str, Any]] | None,
    withdrawal_after_days: int | None,
    metric_ids: Sequence[str],
) -> dict[str, Any]:
    manifest = CRISIS_MANIFESTS[scenario_id]
    started = time.perf_counter()
    branch = session.clone()
    t0 = branch.tick
    try:
        tape_hash = _schedule_tape(
            branch,
            manifest,
            severity=severity,
            start_tick=t0 + 1,
        )
        treatment = _native_actions(actions) if actions else []
        withdrawal = (
            _native_actions(withdrawal_actions)
            if withdrawal_actions is not None else None
        )
        if withdrawal is not None:
            if withdrawal_after_days is None:
                raise ValueError("withdrawal branch has no withdrawal boundary")
            if not 1 <= withdrawal_after_days < manifest.horizon_days:
                raise ValueError("withdrawal boundary lies outside the crisis horizon")
            branch.advance(withdrawal_after_days, actions=treatment)
            branch.advance(
                manifest.horizon_days - withdrawal_after_days,
                actions=withdrawal,
            )
            expected_actions = withdrawal
        elif treatment:
            branch.advance(manifest.horizon_days, actions=treatment)
            expected_actions = treatment
        else:
            branch.advance(manifest.horizon_days)
            expected_actions = []
        captured = _capture_period(
            branch,
            t0=t0,
            days=manifest.horizon_days,
            metric_ids=metric_ids,
        )
        missing = sorted(set(metric_ids) & set(
            captured["missing_metrics_by_economy"].get("0", ())
        ))
        return {
            "severity": severity,
            "tape_hash": tape_hash,
            "actions": treatment,
            "withdrawal_actions": withdrawal,
            "withdrawal_after_days": withdrawal_after_days,
            "policy_applied": _policy_matches(branch, expected_actions),
            "run": captured,
            "missing_required_metrics": missing,
            "terminal_active_shocks": captured["metric_series"]
            .get("metric.shock.active_count", {"values": [math.inf]})["values"][-1],
            "elapsed_seconds": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:
        return {
            "severity": severity,
            "tape_hash": None,
            "actions": list(actions),
            "withdrawal_actions": (
                None if withdrawal_actions is None else list(withdrawal_actions)
            ),
            "withdrawal_after_days": withdrawal_after_days,
            "policy_applied": False,
            "run": None,
            "missing_required_metrics": [],
            "terminal_active_shocks": None,
            "elapsed_seconds": time.perf_counter() - started,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _run_state_branch(
    session: NativeSimulationSession,
    *,
    actions: Sequence[Mapping[str, Any]],
    metric_ids: Sequence[str],
) -> dict[str, Any]:
    started = time.perf_counter()
    branch = session.clone()
    t0 = branch.tick
    try:
        treatment = _native_actions(actions) if actions else []
        if treatment:
            branch.advance(P5_EVALUATION_DAYS, actions=treatment)
        else:
            branch.advance(P5_EVALUATION_DAYS)
        captured = _capture_period(
            branch,
            t0=t0,
            days=P5_EVALUATION_DAYS,
            metric_ids=metric_ids,
        )
        missing = sorted(set(metric_ids) & set(
            captured["missing_metrics_by_economy"].get("0", ())
        ))
        return {
            "actions": treatment,
            "policy_applied": _policy_matches(branch, treatment),
            "run": captured,
            "missing_required_metrics": missing,
            "elapsed_seconds": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:
        return {
            "actions": list(actions),
            "policy_applied": False,
            "run": None,
            "missing_required_metrics": [],
            "elapsed_seconds": time.perf_counter() - started,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _run_path(
    artifact_dir: Path,
    package_id: str,
    seed: int,
    *parts: str,
) -> Path:
    return artifact_dir / "runs" / package_id / str(seed) / Path(*parts).with_suffix(".json")


def _package_metric_ids(package: Mapping[str, Any]) -> tuple[str, ...]:
    contracts = {item.lever: item for item in build_contracts()}
    metrics = {
        *(item[0] for item in package["primary_outcomes"]),
        *(item[0] for item in package["guardrails"]),
        *ACCOUNTING_METRICS,
        "metric.shock.active_count",
    }
    for factor in package["factors"]:
        contract = contracts[factor["factor_id"]]
        metrics.update(contract.mechanism_proximal_metrics)
        metrics.update(contract.tradeoff_metrics)
    return tuple(sorted(metrics))


def _p3_crisis_report(
    payload: Mapping[str, Any],
    scenario_id: str = P5_CRISIS_ID,
) -> Mapping[str, Any]:
    report = _p3_crises(payload).get(scenario_id)
    if report is None or not report.get("accepted"):
        raise ValueError(f"P3 did not accept {scenario_id}")
    return report


def _p3_state_report(
    payload: Mapping[str, Any],
    state_id: str,
) -> Mapping[str, Any]:
    report = _p3_states(payload).get(state_id)
    if report is None or not report.get("accepted"):
        raise ValueError(f"P3 did not accept {state_id}")
    return report


def _expected_hash_by_seed(
    report: Mapping[str, Any],
    key: str,
) -> dict[int, str]:
    return {int(item["seed"]): str(item["sha256"]) for item in report[key]}


def _read_result(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8"))["result"])


def _known_memory_bytes(value: Any) -> int:
    if not isinstance(value, Mapping):
        return 0
    direct = value.get("total_known")
    if isinstance(direct, (int, float)):
        return int(direct)
    return sum(_known_memory_bytes(item) for item in value.values())


def _run_seed(
    *,
    seed: int,
    runnable_packages: Sequence[Mapping[str, Any]],
    manifest_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
    population: int,
    workers: int,
    source_revision: str,
    artifact_dir: Path,
    resume: bool,
    progress: Callable[[int, str, str, bool], None] | None,
    execution_schema_version: str = P5_SCHEMA_VERSION,
    require_frozen_checkpoints: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    cache_hits = 0
    executed = 0
    paths: list[str] = []
    crisis_checkpoints: dict[str, str] = {}
    expected_crisis_checkpoints: dict[str, str] = {}
    crisis_checkpoint_matches: dict[str, bool] = {}
    state_checkpoints: dict[str, str] = {}
    expected_state_checkpoints: dict[str, str] = {}
    state_checkpoint_matches: dict[str, bool] = {}
    peak_memory_bytes = 0
    package_runs: dict[str, list[str]] = {}
    for package in runnable_packages:
        package_id = str(package["package_id"])
        scenario_id = str(package["scenario_id"])
        crisis_manifest = CRISIS_MANIFESTS[scenario_id]
        crisis_report = _p3_crisis_report(p3_payload, scenario_id)
        crisis_session = NativeSimulationSession.create_from_native_spec(
            _crisis_native_spec(crisis_manifest, population=population, seed=seed),
            worker_count=workers,
            history_capacity_frames=(
                crisis_manifest.burn_in_days + crisis_manifest.horizon_days + 8
            ),
        )
        crisis_session.advance(crisis_manifest.burn_in_days)
        crisis_checkpoint = hashlib.sha256(crisis_session.checkpoint()).hexdigest()
        expected_crisis_checkpoint = _expected_hash_by_seed(
            crisis_report, "frozen_common_checkpoint_hashes"
        )[seed]
        checkpoint_matches = crisis_checkpoint == expected_crisis_checkpoint
        if require_frozen_checkpoints and not checkpoint_matches:
            raise RuntimeError(
                f"seed {seed}/{package_id}: crisis checkpoint "
                f"{crisis_checkpoint} != frozen R5 {expected_crisis_checkpoint}"
            )
        crisis_checkpoints[scenario_id] = crisis_checkpoint
        expected_crisis_checkpoints[scenario_id] = expected_crisis_checkpoint
        crisis_checkpoint_matches[scenario_id] = checkpoint_matches
        expected_tapes = {
            severity: str(tuple(crisis_report["frozen_tape_hashes"][severity])[0])
            for severity in P5_SEVERITIES
        }
        if any(
            len(tuple(crisis_report["frozen_tape_hashes"][severity])) != 1
            for severity in P5_SEVERITIES
        ):
            raise RuntimeError(
                f"{scenario_id}: R5 did not freeze exactly one tape per severity"
            )
        peak_memory_bytes = max(
            peak_memory_bytes,
            _known_memory_bytes(crisis_session.memory_usage()),
        )
        metric_ids = _package_metric_ids(package)
        factors = package["factors"]
        design = fractional_package_design(factors)
        full_arm = next(item for item in design if all(sign > 0 for sign in item["signs"]))
        full_actions = full_arm["actions"]
        baseline_actions = _merge_factor_actions(factors, (-1,) * len(factors))
        signature_base = {
            "schema_version": execution_schema_version,
            "source_revision": source_revision,
            "manifest_hash": _canonical_hash(manifest_payload),
            "p3_crisis_checkpoint_sha256": expected_crisis_checkpoint,
            "current_crisis_checkpoint_sha256": crisis_checkpoint,
            "p3_tape_sha256": expected_tapes,
            "seed": seed,
            "population": population,
            "workers": workers,
            "package_id": package_id,
            "metric_ids": metric_ids,
        }
        current_paths: list[str] = []

        def crisis_cached(
            path: Path,
            *,
            branch_id: str,
            severity: str,
            actions: Sequence[Mapping[str, Any]],
            withdrawal_actions: Sequence[Mapping[str, Any]] | None = None,
            withdrawal_after_days: int | None = None,
        ) -> dict[str, Any]:
            nonlocal cache_hits, executed
            result, cached = _cache_result(
                cache_path=path,
                signature_payload={
                    **signature_base,
                    "branch_id": branch_id,
                    "severity": severity,
                    "actions": actions,
                    "withdrawal_actions": withdrawal_actions,
                    "withdrawal_after_days": withdrawal_after_days,
                },
                resume=resume,
                compute=lambda: _run_crisis_branch(
                    crisis_session,
                    scenario_id=scenario_id,
                    severity=severity,
                    actions=actions,
                    withdrawal_actions=withdrawal_actions,
                    withdrawal_after_days=withdrawal_after_days,
                    metric_ids=metric_ids,
                ),
            )
            if result.get("tape_hash") != expected_tapes[severity]:
                raise RuntimeError(
                    f"seed {seed}/{package_id}/{branch_id}: shock tape drift"
                )
            cache_hits += int(cached)
            executed += int(not cached)
            current_paths.append(str(path))
            paths.append(str(path))
            if progress is not None:
                progress(seed, package_id, branch_id, cached)
            return result

        crisis_cached(
            _run_path(artifact_dir, package_id, seed, "moderate-control"),
            branch_id="moderate-control",
            severity=P5_MAIN_SEVERITY,
            actions=(),
        )
        for arm in design:
            crisis_cached(
                _run_path(artifact_dir, package_id, seed, "factorial", arm["arm_id"]),
                branch_id=f"factorial/{arm['arm_id']}",
                severity=P5_MAIN_SEVERITY,
                actions=arm["actions"],
            )
        for index, factor in enumerate(factors):
            signs = [1] * len(factors)
            signs[index] = -1
            crisis_cached(
                _run_path(
                    artifact_dir,
                    package_id,
                    seed,
                    "ablation",
                    factor["factor_id"],
                ),
                branch_id=f"ablation/{factor['factor_id']}",
                severity=P5_MAIN_SEVERITY,
                actions=_merge_factor_actions(factors, signs),
            )
        for severity in ("mild", "severe"):
            crisis_cached(
                _run_path(artifact_dir, package_id, seed, "severity", f"{severity}-control"),
                branch_id=f"severity/{severity}-control",
                severity=severity,
                actions=(),
            )
            crisis_cached(
                _run_path(artifact_dir, package_id, seed, "severity", f"{severity}-full"),
                branch_id=f"severity/{severity}-full",
                severity=severity,
                actions=full_actions,
            )
        crisis_cached(
            _run_path(artifact_dir, package_id, seed, "withdrawal"),
            branch_id="withdrawal",
            severity=P5_MAIN_SEVERITY,
            actions=full_actions,
            withdrawal_actions=baseline_actions,
            withdrawal_after_days=crisis_manifest.maximum_shock_days,
        )

        isolated_pair = tuple(package["isolated_pair"])
        pair_indexes = tuple(
            next(
                index for index, factor in enumerate(factors)
                if factor["factor_id"] == factor_id
            )
            for factor_id in isolated_pair
        )
        for pair_signs in itertools.product((-1, 1), repeat=2):
            signs = [-1] * len(factors)
            for index, sign in zip(pair_indexes, pair_signs, strict=True):
                signs[index] = sign
            bits = "".join("h" if sign > 0 else "l" for sign in pair_signs)
            crisis_cached(
                _run_path(artifact_dir, package_id, seed, "followup", bits),
                branch_id=f"followup/{bits}",
                severity=P5_MAIN_SEVERITY,
                actions=_merge_factor_actions(factors, signs),
            )

        state_id = str(package["alternative_state"])
        state_manifest = STATE_MANIFESTS[state_id]
        state_report = _p3_state_report(p3_payload, state_id)
        state_session = NativeSimulationSession.create_from_native_spec(
            _state_native_spec(state_manifest, population=population, seed=seed),
            worker_count=workers,
            history_capacity_frames=state_manifest.horizon_days + 4,
        )
        state_session.advance(state_manifest.horizon_days)
        peak_memory_bytes = max(
            peak_memory_bytes,
            _known_memory_bytes(state_session.memory_usage()),
        )
        state_checkpoint = hashlib.sha256(state_session.checkpoint()).hexdigest()
        expected_state_checkpoint = _expected_hash_by_seed(
            state_report, "frozen_checkpoint_hashes"
        )[seed]
        state_matches = state_checkpoint == expected_state_checkpoint
        if require_frozen_checkpoints and not state_matches:
            raise RuntimeError(
                f"seed {seed}/{package_id}: alternative-state checkpoint drift"
            )
        state_checkpoints[state_id] = state_checkpoint
        expected_state_checkpoints[state_id] = expected_state_checkpoint
        state_checkpoint_matches[state_id] = state_matches

        def state_cached(path: Path, *, branch_id: str, actions: Sequence[Mapping[str, Any]]) -> None:
            nonlocal cache_hits, executed
            result, cached = _cache_result(
                cache_path=path,
                signature_payload={
                    **signature_base,
                    "branch_id": branch_id,
                    "alternative_state": state_id,
                    "p3_state_checkpoint_sha256": expected_state_checkpoint,
                    "current_state_checkpoint_sha256": state_checkpoint,
                    "actions": actions,
                },
                resume=resume,
                compute=lambda: _run_state_branch(
                    state_session,
                    actions=actions,
                    metric_ids=metric_ids,
                ),
            )
            cache_hits += int(cached)
            executed += int(not cached)
            current_paths.append(str(path))
            paths.append(str(path))
            if progress is not None:
                progress(seed, package_id, branch_id, cached)

        state_cached(
            _run_path(artifact_dir, package_id, seed, "alternative-state-control"),
            branch_id="alternative-state-control",
            actions=(),
        )
        state_cached(
            _run_path(artifact_dir, package_id, seed, "alternative-state-full"),
            branch_id="alternative-state-full",
            actions=full_actions,
        )
        package_runs[package_id] = current_paths

    return {
        "seed": seed,
        "crisis_checkpoint_sha256": crisis_checkpoints,
        "expected_crisis_checkpoint_sha256": expected_crisis_checkpoints,
        "crisis_checkpoint_matches_r5": crisis_checkpoint_matches,
        "state_checkpoint_sha256": state_checkpoints,
        "expected_state_checkpoint_sha256": expected_state_checkpoints,
        "state_checkpoint_matches_r5": state_checkpoint_matches,
        "package_run_paths": package_runs,
        "all_run_paths": paths,
        "cache_hits": cache_hits,
        "executed": executed,
        "elapsed_seconds": time.perf_counter() - started,
        "estimated_peak_memory_bytes": peak_memory_bytes,
    }


def _run_is_valid(result: Mapping[str, Any], *, crisis: bool) -> bool:
    return bool(
        result.get("error") is None
        and result.get("run") is not None
        and result.get("policy_applied")
        and not result.get("missing_required_metrics")
        and result["run"]["integrity"]["passed"]
        and (
            not crisis
            or float(result.get("terminal_active_shocks", math.inf)) == 0.0
        )
    )


def _paired_zero(values: Sequence[float]) -> dict[str, Any]:
    return asdict(paired_effect([0.0] * len(values), values))


def _metric_value(run: Mapping[str, Any], metric_id: str) -> float:
    statistic = METRIC_MATERIALITY[metric_id].default_statistic
    return float(run["metric_summaries"][metric_id][statistic])


def _metric_assessment(
    *,
    metric_id: str,
    favorable_sign: int,
    effects: Mapping[str, Mapping[str, Mapping[str, Any]]],
    controls: Sequence[Mapping[str, Any]],
    treatments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    statistic = METRIC_MATERIALITY[metric_id].default_statistic
    effect = effects[metric_id][statistic]
    floors = _effect_floor(metric_id, controls, statistic=statistic)
    mean_difference = float(effect["mean_difference"])
    magnitude = abs(mean_difference)
    material = magnitude > 1.0e-12 and magnitude >= floors["effective_floor"]
    seed_benefits = [
        favorable_sign * (_metric_value(treatment, metric_id) - _metric_value(control, metric_id))
        for control, treatment in zip(controls, treatments, strict=True)
    ]
    signed_mean = favorable_sign * mean_difference
    raw_bound = (
        effect["confidence_low"] if favorable_sign > 0 else effect["confidence_high"]
    )
    # A one-seed preflight has no estimable confidence interval.  Preserve the
    # descriptive result without allowing it to pass the formal confidence gate.
    signed_bound = (
        favorable_sign * float(raw_bound) if raw_bound is not None else None
    )
    favorable = sum(value > 0.0 for value in seed_benefits)
    adverse = sum(value < 0.0 for value in seed_benefits)
    return {
        "metric_id": metric_id,
        "favorable_sign": favorable_sign,
        "statistic": statistic,
        "mean_difference": mean_difference,
        "signed_mean_benefit": signed_mean,
        "signed_confidence_bound": signed_bound,
        "favorable_seed_count": favorable,
        "adverse_seed_count": adverse,
        "seed_benefits": seed_benefits,
        **floors,
        "material": material,
        "passed": (
            material and signed_bound is not None and signed_bound > 0.0 and favorable >= 6
        ),
        "harm": material and signed_mean < 0.0 and adverse >= 6,
    }


def _effect_assessments(
    *,
    package: Mapping[str, Any],
    controls: Sequence[Mapping[str, Any]],
    treatments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    effects = summarize_paired_runs(controls, treatments)
    primary = {
        metric_id: _metric_assessment(
            metric_id=metric_id,
            favorable_sign=int(sign),
            effects=effects,
            controls=controls,
            treatments=treatments,
        )
        for metric_id, sign in package["primary_outcomes"]
    }
    guardrails = {
        metric_id: _metric_assessment(
            metric_id=metric_id,
            favorable_sign=int(sign),
            effects=effects,
            controls=controls,
            treatments=treatments,
        )
        for metric_id, sign in package["guardrails"]
    }
    return {
        "effects": effects,
        "primary": primary,
        "guardrails": guardrails,
        "supported_primary_metrics": sorted(
            metric_id for metric_id, item in primary.items() if item["passed"]
        ),
        "primary_harms": sorted(
            metric_id for metric_id, item in primary.items() if item["harm"]
        ),
        "guardrail_failures": sorted(
            metric_id for metric_id, item in guardrails.items() if item["harm"]
        ),
    }


def _factorial_analysis(
    *,
    package: Mapping[str, Any],
    design: Sequence[Mapping[str, Any]],
    by_seed: Mapping[int, Sequence[Mapping[str, Any]]],
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    factors = package["factors"]
    aliases = interaction_alias_groups(factors)
    metrics = tuple(
        dict.fromkeys(
            [item[0] for item in package["primary_outcomes"]]
            + [item[0] for item in package["guardrails"]]
        )
    )
    main_effects: dict[str, dict[str, Any]] = {}
    interactions: dict[str, dict[str, Any]] = {}
    for metric_id in metrics:
        statistic = METRIC_MATERIALITY[metric_id].default_statistic
        floors = _effect_floor(metric_id, controls, statistic=statistic)
        values_by_seed = {
            seed: [_metric_value(result, metric_id) for result in results]
            for seed, results in by_seed.items()
        }
        for index, factor in enumerate(factors):
            estimates = [
                2.0 * fmean(
                    arm["signs"][index] * value
                    for arm, value in zip(design, values_by_seed[seed], strict=True)
                )
                for seed in sorted(values_by_seed)
            ]
            summary = _paired_zero(estimates)
            main_effects.setdefault(factor["factor_id"], {})[metric_id] = {
                **summary,
                **floors,
                "material": abs(float(summary["mean_difference"])) >= floors["effective_floor"],
            }
        for left, right in itertools.combinations(range(len(factors)), 2):
            interaction_id = (
                f"{factors[left]['factor_id']}:{factors[right]['factor_id']}"
            )
            estimates = [
                4.0 * fmean(
                    arm["signs"][left] * arm["signs"][right] * value
                    for arm, value in zip(design, values_by_seed[seed], strict=True)
                )
                for seed in sorted(values_by_seed)
            ]
            summary = _paired_zero(estimates)
            interactions.setdefault(interaction_id, {})[metric_id] = {
                **summary,
                **floors,
                "material": abs(float(summary["mean_difference"])) >= floors["effective_floor"],
                "alias_group": aliases[interaction_id],
            }
    return {
        "resolution": "IV",
        "main_effects": main_effects,
        "two_factor_interactions": interactions,
    }


def _isolated_pair_analysis(
    *,
    package: Mapping[str, Any],
    by_seed: Mapping[int, Sequence[Mapping[str, Any]]],
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metrics = tuple(
        dict.fromkeys(
            [item[0] for item in package["primary_outcomes"]]
            + [item[0] for item in package["guardrails"]]
        )
    )
    output: dict[str, Any] = {}
    signs = tuple(itertools.product((-1, 1), repeat=2))
    for metric_id in metrics:
        statistic = METRIC_MATERIALITY[metric_id].default_statistic
        floors = _effect_floor(metric_id, controls, statistic=statistic)
        estimates = []
        for seed in sorted(by_seed):
            values = [_metric_value(run, metric_id) for run in by_seed[seed]]
            estimates.append(4.0 * fmean(
                left * right * value
                for (left, right), value in zip(signs, values, strict=True)
            ))
        summary = _paired_zero(estimates)
        output[metric_id] = {
            **summary,
            **floors,
            "material": abs(float(summary["mean_difference"])) >= floors["effective_floor"],
        }
    return {
        "pair": list(package["isolated_pair"]),
        "effects": output,
    }


def _dominance_analysis(
    *,
    package: Mapping[str, Any],
    full_runs: Sequence[Mapping[str, Any]],
    ablations: Mapping[str, Sequence[Mapping[str, Any]]],
    full_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}
    for factor_id, runs in ablations.items():
        factor_results: dict[str, Any] = {}
        for metric_id, outcome in full_assessment["primary"].items():
            sign = int(outcome["favorable_sign"])
            contributions = [
                sign * (_metric_value(full, metric_id) - _metric_value(without, metric_id))
                for full, without in zip(full_runs, runs, strict=True)
            ]
            summary = _paired_zero(contributions)
            full_benefit = float(outcome["signed_mean_benefit"])
            ratio = (
                float(summary["mean_difference"]) / full_benefit
                if full_benefit > 1.0e-12 else None
            )
            factor_results[metric_id] = {
                **summary,
                "share_of_full_benefit": ratio,
                "dominant": bool(
                    outcome["passed"]
                    and ratio is not None
                    and ratio >= 0.80
                    and summary["confidence_low"] is not None
                    and float(summary["confidence_low"]) > 0.0
                ),
            }
        results[factor_id] = factor_results
    dominant = sorted({
        factor_id
        for factor_id, metrics in results.items()
        if any(item["dominant"] for item in metrics.values())
    })
    return {"by_factor": results, "dominant_components": dominant}


def _package_paths(
    artifact_dir: Path,
    package_id: str,
    seed: int,
    design: Sequence[Mapping[str, Any]],
    factors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "control": _run_path(artifact_dir, package_id, seed, "moderate-control"),
        "factorial": [
            _run_path(artifact_dir, package_id, seed, "factorial", arm["arm_id"])
            for arm in design
        ],
        "ablations": {
            factor["factor_id"]: _run_path(
                artifact_dir, package_id, seed, "ablation", factor["factor_id"]
            )
            for factor in factors
        },
        "severity": {
            severity: {
                "control": (
                    _run_path(artifact_dir, package_id, seed, "moderate-control")
                    if severity == "moderate"
                    else _run_path(
                        artifact_dir, package_id, seed, "severity", f"{severity}-control"
                    )
                ),
                "full": (
                    next(
                        _run_path(
                            artifact_dir,
                            package_id,
                            seed,
                            "factorial",
                            arm["arm_id"],
                        )
                        for arm in design if all(sign > 0 for sign in arm["signs"])
                    )
                    if severity == "moderate"
                    else _run_path(
                        artifact_dir, package_id, seed, "severity", f"{severity}-full"
                    )
                ),
            }
            for severity in P5_SEVERITIES
        },
        "withdrawal": _run_path(artifact_dir, package_id, seed, "withdrawal"),
        "alternative_state": {
            "control": _run_path(
                artifact_dir, package_id, seed, "alternative-state-control"
            ),
            "full": _run_path(
                artifact_dir, package_id, seed, "alternative-state-full"
            ),
        },
        "followup": [
            _run_path(
                artifact_dir,
                package_id,
                seed,
                "followup",
                "".join("h" if sign > 0 else "l" for sign in pair_signs),
            )
            for pair_signs in itertools.product((-1, 1), repeat=2)
        ],
    }


def _analyze_runnable_package(
    *,
    package: Mapping[str, Any],
    seeds: Sequence[int],
    artifact_dir: Path,
) -> tuple[dict[str, Any], list[str]]:
    package_id = str(package["package_id"])
    factors = package["factors"]
    design = fractional_package_design(factors)
    paths = {
        seed: _package_paths(artifact_dir, package_id, seed, design, factors)
        for seed in seeds
    }
    all_records: list[tuple[str, dict[str, Any], bool]] = []
    for seed in seeds:
        item = paths[seed]
        all_records.append((f"{seed}/control", _read_result(item["control"]), True))
        all_records.extend(
            (f"{seed}/factorial/{index}", _read_result(path), True)
            for index, path in enumerate(item["factorial"])
        )
        all_records.extend(
            (f"{seed}/ablation/{factor}", _read_result(path), True)
            for factor, path in item["ablations"].items()
        )
        for severity, severity_paths in item["severity"].items():
            if severity != "moderate":
                all_records.append((
                    f"{seed}/severity/{severity}/control",
                    _read_result(severity_paths["control"]),
                    True,
                ))
                all_records.append((
                    f"{seed}/severity/{severity}/full",
                    _read_result(severity_paths["full"]),
                    True,
                ))
        all_records.append((
            f"{seed}/withdrawal", _read_result(item["withdrawal"]), True
        ))
        all_records.append((
            f"{seed}/alternative-state/control",
            _read_result(item["alternative_state"]["control"]),
            False,
        ))
        all_records.append((
            f"{seed}/alternative-state/full",
            _read_result(item["alternative_state"]["full"]),
            False,
        ))
        all_records.extend(
            (f"{seed}/followup/{index}", _read_result(path), True)
            for index, path in enumerate(item["followup"])
        )
    invalid = [
        label for label, result, crisis in all_records
        if not _run_is_valid(result, crisis=crisis)
    ]
    if invalid:
        return ({
            **dict(package),
            "disposition": "p5_runtime_or_integrity_defect",
            "reason": "At least one package branch failed runtime, application, metrics, or integrity.",
            "invalid_branches": invalid,
        }, invalid)

    controls = [_read_result(paths[seed]["control"])["run"] for seed in seeds]
    factorial_by_seed = {
        seed: [_read_result(path)["run"] for path in paths[seed]["factorial"]]
        for seed in seeds
    }
    full_index = next(
        index for index, arm in enumerate(design)
        if all(sign > 0 for sign in arm["signs"])
    )
    full_runs = [factorial_by_seed[seed][full_index] for seed in seeds]
    full_assessment = _effect_assessments(
        package=package,
        controls=controls,
        treatments=full_runs,
    )
    factorial = _factorial_analysis(
        package=package,
        design=design,
        by_seed=factorial_by_seed,
        controls=controls,
    )
    ablations = {
        factor["factor_id"]: [
            _read_result(paths[seed]["ablations"][factor["factor_id"]])["run"]
            for seed in seeds
        ]
        for factor in factors
    }
    dominance = _dominance_analysis(
        package=package,
        full_runs=full_runs,
        ablations=ablations,
        full_assessment=full_assessment,
    )

    severities: dict[str, Any] = {}
    for severity in P5_SEVERITIES:
        severity_controls = [
            _read_result(paths[seed]["severity"][severity]["control"])["run"]
            for seed in seeds
        ]
        severity_full = [
            _read_result(paths[seed]["severity"][severity]["full"])["run"]
            for seed in seeds
        ]
        severities[severity] = _effect_assessments(
            package=package,
            controls=severity_controls,
            treatments=severity_full,
        )
    moderate_supported = set(full_assessment["supported_primary_metrics"])
    severity_stable_metrics = sorted(
        metric_id for metric_id in moderate_supported
        if all(severities[severity]["primary"][metric_id]["passed"] for severity in P5_SEVERITIES)
    )
    severity_robust = bool(moderate_supported) and set(severity_stable_metrics) == moderate_supported

    state_controls = [
        _read_result(paths[seed]["alternative_state"]["control"])["run"]
        for seed in seeds
    ]
    state_full = [
        _read_result(paths[seed]["alternative_state"]["full"])["run"]
        for seed in seeds
    ]
    alternative_state = _effect_assessments(
        package=package,
        controls=state_controls,
        treatments=state_full,
    )
    alternative_state["state_id"] = package["alternative_state"]
    alternative_state["passed"] = bool(
        alternative_state["supported_primary_metrics"]
        and not alternative_state["primary_harms"]
        and not alternative_state["guardrail_failures"]
    )

    withdrawal_runs = [
        _read_result(paths[seed]["withdrawal"])["run"] for seed in seeds
    ]
    withdrawal = _effect_assessments(
        package=package,
        controls=controls,
        treatments=withdrawal_runs,
    )
    withdrawal["passed"] = not (
        withdrawal["primary_harms"] or withdrawal["guardrail_failures"]
    )

    followup_by_seed = {
        seed: [_read_result(path)["run"] for path in paths[seed]["followup"]]
        for seed in seeds
    }
    followup = _isolated_pair_analysis(
        package=package,
        by_seed=followup_by_seed,
        controls=controls,
    )
    harms = sorted(set(
        full_assessment["primary_harms"] + full_assessment["guardrail_failures"]
    ))
    if not full_assessment["supported_primary_metrics"]:
        disposition = "package_no_supported_benefit"
        reason = "The full package passed no preregistered primary benefit gate."
    elif harms:
        disposition = "package_guardrail_failure"
        reason = "The full package has a material primary or guardrail harm."
    elif dominance["dominant_components"]:
        disposition = "package_component_dominated"
        reason = "At least one disclosed component supplies 80% or more of a supported package benefit."
    elif not severity_robust or not alternative_state["passed"] or not withdrawal["passed"]:
        disposition = "package_not_robust"
        reason = "The package failed severity, alternative-state, or withdrawal robustness."
    else:
        disposition = "recommended_package"
        reason = "The package passed benefit, guardrail, dominance, severity, state, and withdrawal gates."
    return ({
        **dict(package),
        "disposition": disposition,
        "reason": reason,
        "invalid_branches": [],
        "factorial_design": list(design),
        "full_package": full_assessment,
        "factorial_analysis": factorial,
        "dominance": dominance,
        "severity_robustness": {
            "by_severity": severities,
            "stable_supported_metrics": severity_stable_metrics,
            "passed": severity_robust,
        },
        "alternative_state_robustness": alternative_state,
        "withdrawal": withdrawal,
        "isolated_pair_followup": followup,
    }, [])


def analyze_p5(
    *,
    packages: Sequence[Mapping[str, Any]],
    seeds: Sequence[int],
    artifact_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for package in packages:
        if not package["runnable"]:
            has_p3 = any(item["layer"] == "P3" for item in package["blockers"])
            disposition = (
                "blocked_by_p3_scenario" if has_p3 else "blocked_by_p2_component"
            )
            reports.append({
                **dict(package),
                "disposition": disposition,
                "reason": "The package is excluded by frozen upstream evidence.",
            })
            continue
        report, invalid = _analyze_runnable_package(
            package=package,
            seeds=seeds,
            artifact_dir=artifact_dir,
        )
        reports.append(report)
        errors.extend(f"{package['package_id']}: {item}" for item in invalid)
    if len(reports) != 9 or len({item["package_id"] for item in reports}) != 9:
        errors.append("P5 report does not exactly cover all nine packages")
    if any(not item.get("disposition") for item in reports):
        errors.append("P5 report contains an unresolved package")
    return reports, errors


def run_p5(
    *,
    artifact_dir: Path,
    p2_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
    p4_payload: Mapping[str, Any],
    source_revision: str,
    seeds: Sequence[int] = DEFAULT_P3_SEEDS,
    population: int = 100_000,
    workers: int = 8,
    jobs: int = 4,
    resume: bool = True,
    progress: Callable[[int, str, str, bool], None] | None = None,
) -> dict[str, Any]:
    if len(seeds) != 8 or len(set(seeds)) != 8:
        raise ValueError("P5 requires exactly eight unique matched seeds")
    if population < 100_000:
        raise ValueError("P5 package estimates require at least 100,000 persons")
    if workers != 8:
        raise ValueError("P5 acceptance uses exactly eight native engine workers")
    if jobs < 1:
        raise ValueError("jobs must be positive")
    manifest = build_p5_manifest(
        p2_payload=p2_payload,
        p3_payload=p3_payload,
        p4_payload=p4_payload,
    )
    runnable = [item for item in manifest["packages"] if item["runnable"]]
    seed_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(jobs, len(seeds))) as executor:
        futures = {
            executor.submit(
                _run_seed,
                seed=seed,
                runnable_packages=runnable,
                manifest_payload=manifest,
                p3_payload=p3_payload,
                population=population,
                workers=workers,
                source_revision=source_revision,
                artifact_dir=artifact_dir,
                resume=resume,
                progress=progress,
            ): seed
            for seed in seeds
        }
        for future in as_completed(futures):
            seed_results.append(future.result())
    seed_results.sort(key=lambda item: int(item["seed"]))
    reports, errors = analyze_p5(
        packages=manifest["packages"],
        seeds=tuple(seeds),
        artifact_dir=artifact_dir,
    )
    dispositions: dict[str, int] = {}
    for report in reports:
        dispositions[report["disposition"]] = dispositions.get(report["disposition"], 0) + 1
    evidence_hash = _canonical_hash(reports)
    acceptance = {
        "schema_version": P5_SCHEMA_VERSION,
        "manifest_hash": _canonical_hash(manifest),
        "evidence_hash": evidence_hash,
        "dispositions": dispositions,
        "errors": errors,
    }
    payload = {
        "schema_version": P5_SCHEMA_VERSION,
        "status": "accepted_with_explicit_defects" if not errors else "incomplete",
        "source_revision": source_revision,
        "p0_root_hash": manifest["p0_root_hash"],
        "protocol": {
            "population_per_country": population,
            "seeds": list(seeds),
            "workers": workers,
            "jobs": jobs,
            "legacy_python_simulator_used": False,
        },
        "manifest": manifest,
        "seed_runs": seed_results,
        "counts": {
            "packages": len(reports),
            "runnable_packages": len(runnable),
            "blocked_packages": len(reports) - len(runnable),
            "executed_native_branches": sum(item["executed"] for item in seed_results),
            "cache_hits": sum(item["cache_hits"] for item in seed_results),
            "dispositions": dispositions,
        },
        "reports": reports,
        "errors": errors,
        "hashes": {
            "p5_manifest": _canonical_hash(manifest),
            "p5_evidence": evidence_hash,
            "p5_acceptance": _canonical_hash(acceptance),
        },
    }
    _atomic_json(artifact_dir / "p5_report.json", payload)
    return payload


def render_p5_markdown(payload: Mapping[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Policy causality P5 report",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Protocol",
        "",
        f"- Packages: {counts['packages']}",
        f"- Runnable packages: {counts['runnable_packages']}",
        f"- Blocked packages: {counts['blocked_packages']}",
        f"- Population per country: {payload['protocol']['population_per_country']:,}",
        f"- Matched seeds: {len(payload['protocol']['seeds'])}",
        f"- Native workers per session: {payload['protocol']['workers']}",
        f"- Concurrent seed jobs: {payload['protocol']['jobs']}",
        f"- Fresh native branches: {counts['executed_native_branches']}",
        f"- Cache hits: {counts['cache_hits']}",
        "- Legacy Python simulator used: no",
        "",
        "## Dispositions",
        "",
        "| Disposition | Count |",
        "|---|---:|",
    ]
    for name, count in sorted(counts["dispositions"].items()):
        lines.append(f"| `{name}` | {count} |")
    lines.extend((
        "",
        "## Package ledger",
        "",
        "| Package | Scenario | Runnable | P5 disposition | Reason |",
        "|---|---|---:|---|---|",
    ))
    for report in payload["reports"]:
        reason = str(report["reason"]).replace("|", "\\|")
        lines.append(
            f"| `{report['package_id']}` | `{report['scenario_id']}` | "
            f"{'yes' if report['runnable'] else 'no'} | "
            f"`{report['disposition']}` | {reason} |"
        )
    lines.extend((
        "",
        "## Frozen identities",
        "",
        f"- P5 manifest: `{payload['hashes']['p5_manifest']}`",
        f"- P5 evidence: `{payload['hashes']['p5_evidence']}`",
        f"- P5 acceptance: `{payload['hashes']['p5_acceptance']}`",
    ))
    if payload["errors"]:
        lines.extend(("", "## Errors", ""))
        lines.extend(f"- {item}" for item in payload["errors"])
    return "\n".join(lines) + "\n"


__all__ = [
    "PACKAGE_BLUEPRINTS",
    "P5_SCHEMA_VERSION",
    "analyze_p5",
    "build_p5_manifest",
    "fractional_package_design",
    "interaction_alias_groups",
    "render_p5_markdown",
    "run_p5",
]
