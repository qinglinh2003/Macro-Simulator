"""Matched native policy experiments for causality-audit milestone P4.

P4 evaluates one Policy lever at a time against a crisis that already passed
the independent P3 acceptance gate.  It never repairs or retunes the crisis
after opening a policy result.  Every treatment branches from the same native
pre-crisis checkpoint and receives the same immutable moderate shock tape.

The raw run cache deliberately separates orchestration from conclusions:
Python schedules Policy and Shock Engine inputs and reduces maintained metrics;
every simulated day and every policy read remains in the C++ engine.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean, stdev
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from macro_sim.diagnostics.config_experiment import (
    summarize_metric_series,
    summarize_paired_runs,
    summarize_time_responses,
)
from macro_sim.diagnostics.policy_catalog import METRIC_MATERIALITY, SCENARIOS
from macro_sim.diagnostics.policy_contracts import (
    PolicyCausalContract,
    build_contracts,
    build_p0_payload,
)
from macro_sim.diagnostics.policy_effects import (
    ExperimentArm,
    _actions,
    _capture_window,
    select_experiment_arms,
)
from macro_sim.diagnostics.policy_scenarios import (
    CRISIS_MANIFESTS,
    DEFAULT_P3_SEEDS,
    CrisisManifest,
    _crisis_native_spec,
    _integrity,
    _schedule_tape,
)
from macro_sim.native_backend import NativeSimulationSession


P4_SCHEMA_VERSION = "policy-causality-p4-v1"
P4_SCENARIO_ID = "CR_DEMAND_RECESSION"
P4_SEVERITY = "moderate"
P4_TIMINGS: Mapping[str, int] = {
    "immediate": 0,
    "delayed_7": 7,
    "late_30": 30,
}
P4_PRIMARY_OUTCOMES: Mapping[str, int] = {
    "metric.economy.real_output": 1,
    "metric.economy.unemployment_rate": -1,
    "metric.economy.poverty_rate": -1,
}
ACCOUNTING_METRICS = (
    "metric.source.m4.conservation_drift",
    "metric.source.m6.clearing_residual",
    "metric.economy.na.production_reconciliation_residual",
)
ACCEPTED_P2_PREFIX = "accepted"


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
    return hashlib.sha256(
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


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


def _p2_reports(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    reports = payload.get("reports")
    if not isinstance(reports, list):
        raise ValueError("P2 payload has no report ledger")
    output = {str(item["lever"]): item for item in reports}
    if len(output) != len(reports):
        raise ValueError("P2 report ledger contains duplicate levers")
    return output


def _accepted_p3_report(
    payload: Mapping[str, Any],
    *,
    scenario_id: str = P4_SCENARIO_ID,
) -> Mapping[str, Any]:
    accepted = payload.get("accepted_crises_for_p4")
    if not isinstance(accepted, list) or scenario_id not in accepted:
        raise ValueError(f"P3 did not accept {scenario_id} for P4")
    reports = payload.get("reports", {}).get("crises", ())
    report = next(
        (item for item in reports if item.get("scenario_id") == scenario_id),
        None,
    )
    if report is None or not report.get("accepted"):
        raise ValueError(f"P3 acceptance evidence is missing for {scenario_id}")
    return report


def _arm_payload(arm: ExperimentArm, *, role: str) -> dict[str, Any]:
    timings = ["immediate"]
    if role == "primary" and arm.dose_class in {"meaningful", "transition"}:
        timings.extend(("delayed_7", "late_30"))
    return {
        **arm.to_dict(),
        "timings": timings,
    }


def build_p4_matrix(
    *,
    p2_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Close the frozen 102-row matrix without inventing missing evidence."""
    p0 = build_p0_payload()
    if p0["status"] != "accepted":
        raise ValueError("current P0 contract is not accepted")
    expected_root = p0["hashes"]["p0_root"]
    for name, payload in (("P2", p2_payload), ("P3", p3_payload)):
        if payload.get("p0_root_hash") != expected_root:
            raise ValueError(f"{name} P0 root does not match the current contract")
    p3_report = _accepted_p3_report(p3_payload)
    p2 = _p2_reports(p2_payload)
    contracts = build_contracts()
    if set(p2) != {contract.lever for contract in contracts}:
        raise ValueError("P2 report ledger does not exactly cover P0 contracts")

    manifest = CRISIS_MANIFESTS[P4_SCENARIO_ID]
    rows: list[dict[str, Any]] = []
    for contract in contracts:
        role = contract.crisis_roles[P4_SCENARIO_ID]
        p2_report = p2[contract.lever]
        row: dict[str, Any] = {
            "lever": contract.lever,
            "owner_role": contract.owner_role,
            "decision_group": contract.decision_group,
            "scope": contract.scope,
            "scenario_id": P4_SCENARIO_ID,
            "scenario_role": role,
            "p2_disposition": p2_report["disposition"],
            "p2_reason": p2_report["reason"],
            "mechanism_proximal_metrics": list(contract.mechanism_proximal_metrics),
            "tradeoff_metrics": list(contract.tradeoff_metrics),
            "runnable": False,
            "pre_experiment_disposition": None,
            "pre_experiment_reason": None,
            "arms": [],
        }
        if role == "not_applicable":
            row["pre_experiment_disposition"] = "not_applicable"
            row["pre_experiment_reason"] = (
                "The frozen P0 matrix declares no demand-recession role."
            )
        elif not str(p2_report["disposition"]).startswith(ACCEPTED_P2_PREFIX):
            row["pre_experiment_disposition"] = "blocked_by_p2_defect"
            row["pre_experiment_reason"] = (
                f"P2 disposition {p2_report['disposition']}: {p2_report['reason']}"
            )
        elif contract.scope == "external" and manifest.countries < 2:
            row["pre_experiment_disposition"] = "blocked_by_scenario_topology"
            row["pre_experiment_reason"] = (
                "The only accepted P3 crisis has one economy, while this external "
                "lever requires a multi-economy counterparty and spillover path."
            )
        else:
            row["runnable"] = True
            row["arms"] = [
                _arm_payload(arm, role=role)
                for arm in select_experiment_arms(contract, phase="activation")
            ]
            if not row["arms"]:
                raise ValueError(f"{contract.lever}: runnable P4 cell has no dose arm")
        rows.append(row)

    if len(rows) != len(contracts) or len({row["lever"] for row in rows}) != len(rows):
        raise ValueError("P4 matrix does not exactly cover P0 contracts")
    if any(
        row["scenario_role"] in {"primary", "secondary", "safety"}
        and not (row["runnable"] or row["pre_experiment_disposition"])
        for row in rows
    ):
        raise ValueError("P4 matrix contains an unresolved scenario cell")
    if p3_report.get("disposition") != "accepted":
        raise ValueError("P4 may use only a fully accepted P3 crisis")
    return tuple(rows)


def build_p4_manifest(
    *,
    p2_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
) -> dict[str, Any]:
    matrix = build_p4_matrix(p2_payload=p2_payload, p3_payload=p3_payload)
    manifest = CRISIS_MANIFESTS[P4_SCENARIO_ID]
    return {
        "schema_version": P4_SCHEMA_VERSION,
        "scenario": manifest.to_dict(),
        "severity": P4_SEVERITY,
        "primary_outcomes": dict(P4_PRIMARY_OUTCOMES),
        "timing_offsets_days": dict(P4_TIMINGS),
        "design": {
            "policy_only_negative_control": True,
            "crisis_no_policy_control": True,
            "immediate_all_runnable_arms": True,
            "delayed_and_late_for_primary_meaningful_or_transition_arms": True,
            "common_checkpoint": True,
            "immutable_shock_tape": True,
        },
        "p0_root_hash": p3_payload["p0_root_hash"],
        "p2_acceptance_hash": p2_payload["hashes"]["p2_acceptance"],
        "p3_manifest_hash": p3_payload["hashes"]["p3_manifest"],
        "p3_acceptance_hash": p3_payload["hashes"]["p3_acceptance"],
        "matrix": list(matrix),
    }


def _contract_metrics(
    contract: PolicyCausalContract,
    *,
    scenario_id: str = P4_SCENARIO_ID,
    primary_outcomes: Mapping[str, int] = P4_PRIMARY_OUTCOMES,
) -> tuple[str, ...]:
    scenario = SCENARIOS[scenario_id]
    return tuple(sorted(set(
        contract.mechanism_proximal_metrics
        + contract.tradeoff_metrics
        + scenario.entry_metrics
        + scenario.damage_metrics
        + tuple(primary_outcomes)
        + ACCOUNTING_METRICS
        + ("metric.shock.active_count",)
    )))


def _series_for_integrity(run: Mapping[str, Any]) -> dict[str, list[float]]:
    return {
        metric_id: [float(value) for value in series["values"]]
        for metric_id, series in run.get("metric_series", {}).items()
    }


def _capture(
    session: NativeSimulationSession,
    *,
    t0: int,
    manifest: CrisisManifest,
    metric_ids: Sequence[str],
) -> dict[str, Any]:
    captured = _capture_window(
        session,
        t0=t0,
        days=manifest.horizon_days,
        metric_ids=metric_ids,
        countries=manifest.countries,
        target_economy=0,
    )
    captured["integrity"] = _integrity(_series_for_integrity(captured))
    return captured


def _cache_result(
    *,
    cache_path: Path,
    signature_payload: Mapping[str, Any],
    resume: bool,
    compute: Callable[[], Mapping[str, Any]],
) -> tuple[dict[str, Any], bool]:
    signature = _canonical_hash(signature_payload)
    if resume and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("run_signature") == signature:
            return dict(cached["result"]), True
    result = dict(compute())
    _atomic_json(cache_path, {
        "schema_version": "policy-p4-native-run-cache-v1",
        "run_signature": signature,
        "signature": signature_payload,
        "result": result,
    })
    return result, False


def _run_control_branch(
    session: NativeSimulationSession,
    *,
    manifest: CrisisManifest,
    t0: int,
    with_crisis: bool,
    metric_ids: Sequence[str],
    severity: str = P4_SEVERITY,
) -> dict[str, Any]:
    started = time.perf_counter()
    branch = session.clone()
    tape_hash = None
    if with_crisis:
        tape_hash = _schedule_tape(
            branch,
            manifest,
            severity=severity,
            start_tick=t0 + 1,
        )
    branch.advance(manifest.horizon_days)
    captured = _capture(
        branch,
        t0=t0,
        manifest=manifest,
        metric_ids=metric_ids,
    )
    return {
        "branch_kind": "crisis_control" if with_crisis else "ordinary_control",
        "tape_hash": tape_hash,
        "run": captured,
        "terminal_active_shocks": captured["metric_series"]
        .get("metric.shock.active_count", {"values": [math.inf]})["values"][-1],
        "elapsed_seconds": time.perf_counter() - started,
        "error": None,
    }


def _run_treatment_branch(
    session: NativeSimulationSession,
    *,
    manifest: CrisisManifest,
    t0: int,
    arm: Mapping[str, Any],
    timing: str,
    with_crisis: bool,
    metric_ids: Sequence[str],
    severity: str = P4_SEVERITY,
    timing_offsets: Mapping[str, int] = P4_TIMINGS,
) -> dict[str, Any]:
    started = time.perf_counter()
    branch = session.clone()
    tape_hash = None
    if with_crisis:
        tape_hash = _schedule_tape(
            branch,
            manifest,
            severity=severity,
            start_tick=t0 + 1,
        )
    delay = timing_offsets[timing]
    actions = _actions(
        ((str(item["lever"]), item["value"]) for item in arm["actions"]),
        economy_id=0,
    )
    try:
        if delay:
            branch.advance(delay)
        branch.advance(manifest.horizon_days - delay, actions=actions)
        policy_after = branch.policy_values(0)
        applied = all(
            _jsonable(policy_after[item["lever"]]) == _jsonable(item["value"])
            for item in actions
        )
        captured = _capture(
            branch,
            t0=t0,
            manifest=manifest,
            metric_ids=metric_ids,
        )
        return {
            "branch_kind": "crisis_policy" if with_crisis else "policy_only",
            "timing": timing,
            "effectiveness_tick": t0 + delay + 1,
            "actions": actions,
            "policy_applied": applied,
            "tape_hash": tape_hash,
            "run": captured,
            "terminal_active_shocks": captured["metric_series"]
            .get("metric.shock.active_count", {"values": [math.inf]})["values"][-1],
            "elapsed_seconds": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:  # validation/stability is part of the evidence
        return {
            "branch_kind": "crisis_policy" if with_crisis else "policy_only",
            "timing": timing,
            "effectiveness_tick": t0 + delay + 1,
            "actions": actions,
            "policy_applied": False,
            "tape_hash": tape_hash,
            "run": None,
            "terminal_active_shocks": None,
            "elapsed_seconds": time.perf_counter() - started,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _row_arm_lookup(row: Mapping[str, Any]) -> Iterable[tuple[Mapping[str, Any], str, bool]]:
    for arm in row["arms"]:
        if row.get("policy_only_negative_control", True):
            yield arm, "immediate", False
        for timing in arm["timings"]:
            yield arm, timing, True


def _branch_path(
    artifact_dir: Path,
    *,
    lever: str,
    arm_label: str,
    seed: int,
    timing: str,
    with_crisis: bool,
) -> Path:
    kind = "crisis" if with_crisis else "policy_only"
    return artifact_dir / "runs" / lever / arm_label / str(seed) / f"{kind}-{timing}.json"


def _run_seed(
    *,
    seed: int,
    matrix: Sequence[Mapping[str, Any]],
    manifest_payload: Mapping[str, Any],
    p3_report: Mapping[str, Any],
    population: int,
    workers: int,
    source_revision: str,
    artifact_dir: Path,
    resume: bool,
    progress: Callable[[int, str, str, str, bool], None] | None,
    scenario_id: str = P4_SCENARIO_ID,
    severity: str = P4_SEVERITY,
    primary_outcomes: Mapping[str, int] = P4_PRIMARY_OUTCOMES,
    timing_offsets: Mapping[str, int] = P4_TIMINGS,
) -> dict[str, Any]:
    manifest = CRISIS_MANIFESTS[scenario_id]
    started = time.perf_counter()
    session = NativeSimulationSession.create_from_native_spec(
        _crisis_native_spec(manifest, population=population, seed=seed),
        worker_count=workers,
        history_capacity_frames=manifest.burn_in_days + manifest.horizon_days + 8,
    )
    session.advance(manifest.burn_in_days)
    t0 = session.tick
    checkpoint_hash = hashlib.sha256(session.checkpoint()).hexdigest()
    expected = {
        int(item["seed"]): str(item["sha256"])
        for item in p3_report["frozen_common_checkpoint_hashes"]
    }[seed]
    if checkpoint_hash != expected:
        raise RuntimeError(
            f"seed {seed}: P4 common checkpoint {checkpoint_hash} != frozen P3 {expected}"
        )
    frozen_tapes = tuple(p3_report["frozen_tape_hashes"][severity])
    if len(frozen_tapes) != 1:
        raise RuntimeError("P3 did not freeze exactly one moderate shock tape hash")
    expected_tape_hash = str(frozen_tapes[0])

    contracts = {contract.lever: contract for contract in build_contracts()}
    runnable = [row for row in matrix if row["runnable"]]
    all_metrics = tuple(sorted(set().union(*(
        set(_contract_metrics(
            contracts[row["lever"]],
            scenario_id=scenario_id,
            primary_outcomes=primary_outcomes,
        )) for row in runnable
    ))))
    common_signature = {
        "schema_version": P4_SCHEMA_VERSION,
        "source_revision": source_revision,
        "manifest_hash": _canonical_hash(manifest_payload),
        "p3_checkpoint_sha256": expected,
        "p3_tape_sha256": expected_tape_hash,
        "seed": seed,
        "population": population,
        "workers": workers,
    }
    cache_hits = 0
    executed = 0

    controls: dict[str, str] = {}
    for with_crisis in (False, True):
        label = "crisis" if with_crisis else "ordinary"
        path = artifact_dir / "runs" / "controls" / str(seed) / f"{label}.json"
        result, cached = _cache_result(
            cache_path=path,
            signature_payload={
                **common_signature,
                "branch_kind": f"{label}_control",
                "metric_ids": all_metrics,
            },
            resume=resume,
            compute=lambda crisis=with_crisis: _run_control_branch(
                session,
                manifest=manifest,
                t0=t0,
                with_crisis=crisis,
                metric_ids=all_metrics,
                severity=severity,
            ),
        )
        cache_hits += int(cached)
        executed += int(not cached)
        if with_crisis and result.get("tape_hash") != expected_tape_hash:
            raise RuntimeError(
                f"seed {seed}: P4 shock tape drifted from frozen P3 evidence"
            )
        controls[label] = str(path)
        if progress is not None:
            progress(seed, "controls", label, "immediate", cached)

    paths: list[str] = []
    for row in runnable:
        contract = contracts[row["lever"]]
        metric_ids = _contract_metrics(
            contract,
            scenario_id=scenario_id,
            primary_outcomes=primary_outcomes,
        )
        for arm, timing, with_crisis in _row_arm_lookup(row):
            path = _branch_path(
                artifact_dir,
                lever=row["lever"],
                arm_label=arm["label"],
                seed=seed,
                timing=timing,
                with_crisis=with_crisis,
            )
            result, cached = _cache_result(
                cache_path=path,
                signature_payload={
                    **common_signature,
                    "branch_kind": "crisis_policy" if with_crisis else "policy_only",
                    "lever": row["lever"],
                    "role": row["scenario_role"],
                    "arm": arm,
                    "timing": timing,
                    "metric_ids": metric_ids,
                },
                resume=resume,
                compute=lambda a=arm, t=timing, crisis=with_crisis, ids=metric_ids: _run_treatment_branch(
                    session,
                    manifest=manifest,
                    t0=t0,
                    arm=a,
                    timing=t,
                    with_crisis=crisis,
                    metric_ids=ids,
                    severity=severity,
                    timing_offsets=timing_offsets,
                ),
            )
            cache_hits += int(cached)
            executed += int(not cached)
            if with_crisis and result.get("tape_hash") != expected_tape_hash:
                raise RuntimeError(
                    f"seed {seed}/{row['lever']}/{arm['label']}: "
                    "shock tape drifted from frozen P3 evidence"
                )
            paths.append(str(path))
            if progress is not None:
                progress(seed, row["lever"], arm["label"], timing, cached)

    return {
        "seed": seed,
        "t0": t0,
        "common_checkpoint_sha256": checkpoint_hash,
        "control_paths": controls,
        "treatment_paths": paths,
        "cache_hits": cache_hits,
        "executed": executed,
        "elapsed_seconds": time.perf_counter() - started,
        "memory_bytes": session.memory_usage(),
    }


def _read_result(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8"))["result"])


def _effect_floor(
    metric_id: str,
    controls: Sequence[Mapping[str, Any]],
    *,
    statistic: str,
) -> dict[str, float]:
    rule = METRIC_MATERIALITY[metric_id]
    values = [
        float(run["metric_summaries"][metric_id][statistic])
        for run in controls
    ]
    scale = max(fmean(abs(value) for value in values), 1.0e-12)
    metric_floor = max(rule.absolute_floor, rule.relative_floor * scale)
    standardized_floor = rule.standardized_floor * (
        stdev(values) if len(values) > 1 else 0.0
    )
    return {
        "metric_floor": metric_floor,
        "standardized_floor": standardized_floor,
        "effective_floor": min(metric_floor, standardized_floor)
        if standardized_floor > 0.0
        else metric_floor,
    }


def _materiality(
    metric_id: str,
    effects: Mapping[str, Mapping[str, Mapping[str, Any]]],
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rule = METRIC_MATERIALITY[metric_id]
    statistic = rule.default_statistic
    effect = effects[metric_id][statistic]
    floors = _effect_floor(metric_id, controls, statistic=statistic)
    magnitude = abs(float(effect["mean_difference"]))
    return {
        "statistic": statistic,
        "mean_difference": effect["mean_difference"],
        "confidence_low": effect["confidence_low"],
        "confidence_high": effect["confidence_high"],
        **floors,
        "material": magnitude > 1.0e-12 and magnitude >= floors["effective_floor"],
    }


def _synthetic_interaction_run(
    ordinary_control: Mapping[str, Any],
    crisis_control: Mapping[str, Any],
    policy_only: Mapping[str, Any],
    crisis_policy: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = set.intersection(*(
        set(item["metric_series"])
        for item in (ordinary_control, crisis_control, policy_only, crisis_policy)
    ))
    series: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    ticks: list[int] | None = None
    for metric_id in sorted(metrics):
        paths = [
            item["metric_series"][metric_id]
            for item in (ordinary_control, crisis_control, policy_only, crisis_policy)
        ]
        current_ticks = [int(value) for value in paths[0]["ticks"]]
        if any([int(value) for value in path["ticks"]] != current_ticks for path in paths[1:]):
            raise ValueError(f"interaction ticks differ for {metric_id}")
        values = [
            (float(cp) - float(cc)) - (float(po) - float(oc))
            for oc, cc, po, cp in zip(
                paths[0]["values"],
                paths[1]["values"],
                paths[2]["values"],
                paths[3]["values"],
                strict=True,
            )
        ]
        series[metric_id] = {"ticks": current_ticks, "values": values}
        if ticks is None:
            ticks = current_ticks
            rows = [{"_tick": tick} for tick in ticks]
        for row, value in zip(rows, values, strict=True):
            row[metric_id] = value
    summaries = {
        name: asdict(summary) for name, summary in summarize_metric_series(rows).items()
    }
    return {"metric_series": series, "metric_summaries": summaries}


def _zero_run_like(run: Mapping[str, Any]) -> dict[str, Any]:
    series = {
        metric_id: {
            "ticks": list(item["ticks"]),
            "values": [0.0] * len(item["values"]),
        }
        for metric_id, item in run["metric_series"].items()
    }
    rows = [
        {
            "_tick": tick,
            **{metric_id: 0.0 for metric_id in series},
        }
        for tick in next(iter(series.values()))["ticks"]
    ]
    return {
        "metric_series": series,
        "metric_summaries": {
            name: asdict(summary)
            for name, summary in summarize_metric_series(rows).items()
        },
    }


def _arm_analysis(
    *,
    row: Mapping[str, Any],
    arm: Mapping[str, Any],
    timing: str,
    seeds: Sequence[int],
    artifact_dir: Path,
    ordinary_controls: Mapping[int, Mapping[str, Any]],
    crisis_controls: Mapping[int, Mapping[str, Any]],
    primary_outcomes: Mapping[str, int] = P4_PRIMARY_OUTCOMES,
) -> dict[str, Any]:
    crisis_records = [
        _read_result(_branch_path(
            artifact_dir,
            lever=row["lever"],
            arm_label=arm["label"],
            seed=seed,
            timing=timing,
            with_crisis=True,
        ))
        for seed in seeds
    ]
    policy_only_negative_control = bool(
        row.get("policy_only_negative_control", True)
    )
    policy_records: list[dict[str, Any]] = []
    if timing == "immediate" and policy_only_negative_control:
        policy_records = [
            _read_result(_branch_path(
                artifact_dir,
                lever=row["lever"],
                arm_label=arm["label"],
                seed=seed,
                timing="immediate",
                with_crisis=False,
            ))
            for seed in seeds
        ]
    errors = [
        item["error"]
        for item in (*crisis_records, *policy_records)
        if item.get("error")
    ]
    required_metrics = set(
        primary_outcomes
    ) | set(row["mechanism_proximal_metrics"]) | set(row["tradeoff_metrics"])
    compared_runs = [
        *crisis_records,
        *policy_records,
        *({"run": crisis_controls[seed]} for seed in seeds),
    ]
    if timing == "immediate" and policy_only_negative_control:
        compared_runs.extend({"run": ordinary_controls[seed]} for seed in seeds)
    missing_metrics = sorted(set().union(*(
        set(item["run"]["missing_metrics_by_economy"].get("0", ()))
        for item in compared_runs
        if item.get("run") is not None
    )) & required_metrics) if crisis_records else []
    output: dict[str, Any] = {
        "label": arm["label"],
        "dose_class": arm["dose_class"],
        "actions": arm["actions"],
        "timing": timing,
        "errors": errors,
        "missing_declared_metrics": missing_metrics,
        "complete_seed_count": sum(item.get("run") is not None for item in crisis_records),
        "policy_applied_all_seeds": all(
            item.get("policy_applied")
            for item in (*crisis_records, *policy_records)
        ),
        "integrity_all_seeds": all(
            item.get("run") is not None
            and item["run"]["integrity"]["passed"]
            and float(item["terminal_active_shocks"]) == 0.0
            for item in (*crisis_records, *policy_records)
        ),
    }
    if errors or missing_metrics or output["complete_seed_count"] != len(seeds):
        output.update({
            "crisis_effects": None,
            "ordinary_effects": None,
            "crisis_interactions": None,
            "time_responses": None,
            "materiality": {},
            "primary_benefit": {},
        })
        return output

    crisis_runs = [item["run"] for item in crisis_records]
    crisis_control_runs = [crisis_controls[seed] for seed in seeds]
    crisis_effects = summarize_paired_runs(crisis_control_runs, crisis_runs)
    output["crisis_effects"] = crisis_effects
    output["time_responses"] = summarize_time_responses(
        crisis_control_runs, crisis_runs
    )
    metrics = tuple(dict.fromkeys(
        list(primary_outcomes)
        + list(row["mechanism_proximal_metrics"])
        + list(row["tradeoff_metrics"])
    ))
    output["materiality"] = {
        metric_id: _materiality(metric_id, crisis_effects, crisis_control_runs)
        for metric_id in metrics
        if metric_id in crisis_effects and metric_id in METRIC_MATERIALITY
    }

    if timing == "immediate":
        policy_runs = [item["run"] for item in policy_records]
        ordinary_control_runs = [ordinary_controls[seed] for seed in seeds]
        output["ordinary_effects"] = summarize_paired_runs(
            ordinary_control_runs, policy_runs
        )
        interactions = [
            _synthetic_interaction_run(oc, cc, po, cp)
            for oc, cc, po, cp in zip(
                ordinary_control_runs,
                crisis_control_runs,
                policy_runs,
                crisis_runs,
                strict=True,
            )
        ]
        zeros = [_zero_run_like(item) for item in interactions]
        output["crisis_interactions"] = summarize_paired_runs(zeros, interactions)
    else:
        output["ordinary_effects"] = None
        output["crisis_interactions"] = None

    primary: dict[str, Any] = {}
    for metric_id, favorable_sign in primary_outcomes.items():
        if metric_id not in crisis_effects:
            continue
        material = output["materiality"][metric_id]
        effect = crisis_effects[metric_id][material["statistic"]]
        signed_mean = favorable_sign * float(effect["mean_difference"])
        signed_low = favorable_sign * float(
            effect["confidence_low"] if favorable_sign > 0 else effect["confidence_high"]
        )
        per_seed = []
        for control, treatment in zip(crisis_control_runs, crisis_runs, strict=True):
            left = float(control["metric_summaries"][metric_id][material["statistic"]])
            right = float(treatment["metric_summaries"][metric_id][material["statistic"]])
            per_seed.append(favorable_sign * (right - left))
        primary[metric_id] = {
            "favorable_sign": favorable_sign,
            "signed_mean_benefit": signed_mean,
            "signed_confidence_bound": signed_low,
            "favorable_seed_count": sum(value > 0.0 for value in per_seed),
            "adverse_seed_count": sum(value < 0.0 for value in per_seed),
            "worst_seed_benefit": min(per_seed),
            "best_seed_benefit": max(per_seed),
            "seed_benefits": per_seed,
            "material": material["material"],
            "passed": material["material"] and signed_low > 0.0 and sum(
                value > 0.0 for value in per_seed
            ) >= 6,
        }
    output["primary_benefit"] = primary
    return output


def _dose_ordering(arms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    immediate = [item for item in arms if item["timing"] == "immediate"]
    local = next((item for item in immediate if item["dose_class"] == "local"), None)
    meaningful = next(
        (item for item in immediate if item["dose_class"] == "meaningful"), None
    )
    if local is None or meaningful is None:
        return {"tested": False, "ordered_metrics": [], "reversed_metrics": []}
    common = set(local["materiality"]) & set(meaningful["materiality"])
    ordered = []
    reversed_metrics = []
    for metric_id in sorted(common):
        left = abs(float(local["materiality"][metric_id]["mean_difference"]))
        right = abs(float(meaningful["materiality"][metric_id]["mean_difference"]))
        (ordered if right >= left else reversed_metrics).append(metric_id)
    return {
        "tested": True,
        "ordered_metrics": ordered,
        "reversed_metrics": reversed_metrics,
    }


def _timing_summary(
    arms: Sequence[Mapping[str, Any]],
    *,
    primary_outcomes: Mapping[str, int] = P4_PRIMARY_OUTCOMES,
) -> dict[str, Any]:
    candidates = [
        item for item in arms
        if item["dose_class"] in {"meaningful", "transition"}
        and item["primary_benefit"]
    ]
    if not any(item["timing"] != "immediate" for item in candidates):
        return {"tested": False, "best_timing_by_metric": {}}
    best: dict[str, dict[str, Any]] = {}
    for metric_id in primary_outcomes:
        values = [
            (float(item["primary_benefit"][metric_id]["signed_mean_benefit"]), item)
            for item in candidates
            if metric_id in item["primary_benefit"]
        ]
        if not values:
            continue
        benefit, item = max(values, key=lambda pair: pair[0])
        best[metric_id] = {
            "timing": item["timing"],
            "arm": item["label"],
            "signed_mean_benefit": benefit,
        }
    return {"tested": True, "best_timing_by_metric": best}


def analyze_p4(
    *,
    matrix: Sequence[Mapping[str, Any]],
    seeds: Sequence[int],
    artifact_dir: Path,
    primary_outcomes: Mapping[str, int] = P4_PRIMARY_OUTCOMES,
) -> tuple[list[dict[str, Any]], list[str]]:
    ordinary_control_records = {
        seed: _read_result(
            artifact_dir / "runs" / "controls" / str(seed) / "ordinary.json"
        )
        for seed in seeds
    }
    crisis_control_records = {
        seed: _read_result(
            artifact_dir / "runs" / "controls" / str(seed) / "crisis.json"
        )
        for seed in seeds
    }
    ordinary_controls = {
        seed: item["run"] for seed, item in ordinary_control_records.items()
    }
    crisis_controls = {
        seed: item["run"] for seed, item in crisis_control_records.items()
    }
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in matrix:
        if not row["runnable"]:
            reports.append({
                **dict(row),
                "disposition": row["pre_experiment_disposition"],
                "reason": row["pre_experiment_reason"],
                "arm_results": [],
            })
            continue
        arm_results = []
        for arm in row["arms"]:
            for timing in arm["timings"]:
                arm_results.append(_arm_analysis(
                    row=row,
                    arm=arm,
                    timing=timing,
                    seeds=seeds,
                    artifact_dir=artifact_dir,
                    ordinary_controls=ordinary_controls,
                    crisis_controls=crisis_controls,
                    primary_outcomes=primary_outcomes,
                ))
        runtime_failed = any(
            item["errors"]
            or item["missing_declared_metrics"]
            or not item["policy_applied_all_seeds"]
            or not item["integrity_all_seeds"]
            for item in arm_results
        )
        immediate = [item for item in arm_results if item["timing"] == "immediate"]
        any_material = any(
            evidence["material"]
            for item in immediate
            for evidence in item["materiality"].values()
        )
        any_benefit = any(
            evidence["passed"]
            for item in immediate
            for evidence in item["primary_benefit"].values()
        )
        any_harm = any(
            evidence["material"]
            and evidence["signed_mean_benefit"] < 0.0
            and evidence["adverse_seed_count"] >= 6
            for item in immediate
            for evidence in item["primary_benefit"].values()
        )
        if runtime_failed:
            disposition = "p4_runtime_or_integrity_defect"
            reason = "At least one preregistered arm failed application, runtime, or integrity."
        elif row["scenario_role"] == "primary":
            if any_benefit:
                disposition = "accepted_crisis_efficacy"
                reason = "At least one preregistered dose materially improves a primary loss with paired support."
            elif any_material:
                disposition = "primary_no_supported_benefit"
                reason = "The policy moved declared outcomes but no dose passed the crisis-benefit gate."
            else:
                disposition = "primary_nonbinding_in_crisis"
                reason = "No preregistered dose produced a material declared effect in the accepted crisis."
        elif row["scenario_role"] == "secondary":
            disposition = (
                "secondary_effect_detected" if any_material else "secondary_inactive_in_crisis"
            )
            reason = (
                "A material secondary, proximal, or trade-off effect was detected."
                if any_material
                else "No material declared effect was detected in this accepted crisis."
            )
        else:
            disposition = "safety_concern" if any_harm else "safety_passed"
            reason = (
                "A tested dose materially worsened a primary crisis loss in at least six seeds."
                if any_harm
                else "No tested dose met the preregistered material-worsening screen."
            )
        reports.append({
            **dict(row),
            "disposition": disposition,
            "reason": reason,
            "arm_results": arm_results,
            "dose_ordering": _dose_ordering(arm_results),
            "timing_summary": _timing_summary(
                arm_results,
                primary_outcomes=primary_outcomes,
            ),
        })

    if len(reports) != len(matrix):
        errors.append("P4 report does not exactly cover the frozen matrix")
    unresolved = [
        item["lever"] for item in reports
        if item["scenario_role"] in {"primary", "secondary", "safety"}
        and not item.get("disposition")
    ]
    if unresolved:
        errors.append("unresolved P4 cells: " + ", ".join(unresolved))
    for seed, record in ordinary_control_records.items():
        if record.get("error") or not record["run"]["integrity"]["passed"]:
            errors.append(f"seed {seed}: ordinary control failed integrity")
    for seed, record in crisis_control_records.items():
        if (
            record.get("error")
            or not record["run"]["integrity"]["passed"]
            or float(record["terminal_active_shocks"]) != 0.0
        ):
            errors.append(f"seed {seed}: crisis control failed integrity")
    return reports, errors


def run_p4(
    *,
    artifact_dir: Path,
    p2_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
    source_revision: str,
    seeds: Sequence[int] = DEFAULT_P3_SEEDS,
    population: int = 100_000,
    workers: int = 8,
    jobs: int = 4,
    resume: bool = True,
    progress: Callable[[int, str, str, str, bool], None] | None = None,
) -> dict[str, Any]:
    if len(seeds) != 8 or len(set(seeds)) != 8:
        raise ValueError("P4 requires exactly eight unique matched seeds")
    if population < 100_000:
        raise ValueError("P4 crisis estimates require at least 100,000 persons per country")
    if workers != 8:
        raise ValueError("P4 acceptance uses exactly eight native engine workers")
    if jobs < 1:
        raise ValueError("jobs must be positive")
    manifest_payload = build_p4_manifest(
        p2_payload=p2_payload,
        p3_payload=p3_payload,
    )
    matrix = tuple(manifest_payload["matrix"])
    p3_report = _accepted_p3_report(p3_payload)
    seed_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(jobs, len(seeds))) as executor:
        futures = {
            executor.submit(
                _run_seed,
                seed=seed,
                matrix=matrix,
                manifest_payload=manifest_payload,
                p3_report=p3_report,
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
    reports, errors = analyze_p4(
        matrix=matrix,
        seeds=tuple(seeds),
        artifact_dir=artifact_dir,
    )
    counts: dict[str, int] = {}
    for report in reports:
        counts[report["disposition"]] = counts.get(report["disposition"], 0) + 1
    evidence_hash = _canonical_hash(reports)
    acceptance = {
        "schema_version": P4_SCHEMA_VERSION,
        "matrix_hash": _canonical_hash(matrix),
        "evidence_hash": evidence_hash,
        "counts": counts,
        "errors": errors,
    }
    payload = {
        "schema_version": P4_SCHEMA_VERSION,
        "status": "accepted_with_explicit_defects" if not errors else "incomplete",
        "source_revision": source_revision,
        "p0_root_hash": manifest_payload["p0_root_hash"],
        "protocol": {
            "population_per_country": population,
            "seeds": list(seeds),
            "workers": workers,
            "jobs": jobs,
            "legacy_python_simulator_used": False,
        },
        "manifest": manifest_payload,
        "seed_runs": seed_results,
        "counts": {
            "matrix_cells": len(matrix),
            "runnable_cells": sum(row["runnable"] for row in matrix),
            "executed_native_branches": sum(item["executed"] for item in seed_results),
            "cache_hits": sum(item["cache_hits"] for item in seed_results),
            "dispositions": counts,
        },
        "reports": reports,
        "errors": errors,
        "hashes": {
            "p4_manifest": _canonical_hash(manifest_payload),
            "p4_evidence": evidence_hash,
            "p4_acceptance": _canonical_hash(acceptance),
        },
    }
    _atomic_json(artifact_dir / "p4_report.json", payload)
    return payload


def render_p4_markdown(payload: Mapping[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Policy causality P4 report",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Protocol",
        "",
        f"- Scenario: `{P4_SCENARIO_ID}` (`{P4_SEVERITY}` frozen tape)",
        f"- Population per country: {payload['protocol']['population_per_country']:,}",
        f"- Matched seeds: {len(payload['protocol']['seeds'])}",
        f"- Native engine workers per session: {payload['protocol']['workers']}",
        f"- Concurrent seed jobs: {payload['protocol']['jobs']}",
        f"- Matrix cells: {counts['matrix_cells']}",
        f"- Runnable cells: {counts['runnable_cells']}",
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
        "## Frozen identities",
        "",
        f"- P4 manifest: `{payload['hashes']['p4_manifest']}`",
        f"- P4 evidence: `{payload['hashes']['p4_evidence']}`",
        f"- P4 acceptance: `{payload['hashes']['p4_acceptance']}`",
        "",
        "## Cell ledger",
        "",
        "| Lever | Role | P2 | P4 disposition | Reason |",
        "|---|---|---|---|---|",
    ))
    for report in payload["reports"]:
        reason = str(report["reason"]).replace("|", "\\|")
        lines.append(
            f"| `{report['lever']}` | `{report['scenario_role']}` | "
            f"`{report['p2_disposition']}` | `{report['disposition']}` | {reason} |"
        )
    if payload["errors"]:
        lines.extend(("", "## Errors", ""))
        lines.extend(f"- {error}" for error in payload["errors"])
    return "\n".join(lines) + "\n"


__all__ = [
    "P4_PRIMARY_OUTCOMES",
    "P4_SCHEMA_VERSION",
    "P4_SCENARIO_ID",
    "P4_SEVERITY",
    "P4_TIMINGS",
    "analyze_p4",
    "build_p4_manifest",
    "build_p4_matrix",
    "render_p4_markdown",
    "run_p4",
]
