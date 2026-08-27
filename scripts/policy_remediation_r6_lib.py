"""R6 single-policy calibration and player-surface classification.

The orchestration in this module never advances the legacy Python economy.
It reuses the maintained native P2 matched-state experiment and the generic
native P4 checkpoint/branch runner against the independently accepted R5
crisis library.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from macro_sim.diagnostics.policy_catalog import METRIC_MATERIALITY
from macro_sim.diagnostics.policy_contracts import (
    PolicyCausalContract,
    build_contracts,
    build_p0_payload,
)
from macro_sim.diagnostics.policy_crisis_effects import (
    P4_SEVERITY,
    P4_TIMINGS,
    _accepted_p3_report,
    _canonical_hash,
    _run_seed,
    analyze_p4,
)
from macro_sim.diagnostics.policy_effects import (
    ExperimentArm,
    run_p2,
    select_experiment_arms,
)
from macro_sim.diagnostics.policy_scenarios import (
    CRISIS_MANIFESTS,
    DEFAULT_P3_SEEDS,
)


R6_SCHEMA_VERSION = "policy-remediation-r6-v1"
R6_CANDIDATES = (
    "gov_consumption_share",
    "gov_deficit_target",
    "deficit_u_ref",
    "benefit_replacement",
    "benefit_income_floor",
    "pension_replacement",
    "tax_income_rate",
    "energy_price_cap",
    "energy_rationing",
    "min_wage",
    "job_guarantee",
    "jg_wage_ratio",
    "inflation_target",
    "taylor_phi_pi",
    "taylor_phi_u",
    "rate_inertia",
    "manual_policy_rate",
    "monetary_regime",
    "r_neutral",
    "u_natural",
    "r_max",
    "infl_ema_lambda",
    "cb_core_inflation",
    "cb_uses_fixed_basket_cpi",
    "cb_log_inflation",
    "omo",
    "bank_min_capital",
    "mortgage_ltv_cap",
    "mortgage_foreclosure_ltv",
    "jg_public_works_share",
    "gov_investment_share",
    "bankrupt_persist",
    "rental_eviction_arrears",
    "soe_efirm",
    "tariff",
    "fx_regime",
)
R6_SCALE_PENDING = frozenset({
    "mortgage_foreclosure_ltv",
    "gov_investment_share",
    "bankrupt_persist",
    "rental_eviction_arrears",
    "soe_efirm",
    "tariff",
    "fx_regime",
})
R6_ACTIVATION_ONLY_CRISIS_EXCLUSIONS = frozenset({
    "jg_wage_ratio",
    "jg_public_works_share",
})
R6_CLASSIFICATIONS = frozenset({
    "effective",
    "conditional",
    "expert_only",
    "structural",
    "removed",
})


# Frozen before R6 treatment results are opened.  The anchor is the state in
# which the lever is expected to help.  The adverse state tests the most
# important policy trade-off or a second mechanism-relevant crisis.
R6_STATE_DESIGN: Mapping[tuple[str, str], tuple[str, str]] = {
    ("treasury", "fiscal_stance"): (
        "CR_DEMAND_RECESSION", "CR_SUPPLY_STAGFLATION",
    ),
    ("treasury", "tax_and_transfers"): (
        "CR_DEMAND_RECESSION", "CR_CREDIT_CRUNCH",
    ),
    ("labor_social", "labor_and_welfare"): (
        "CR_DEMAND_RECESSION", "CR_SUPPLY_STAGFLATION",
    ),
    ("central_bank", "monetary_stance"): (
        "CR_DEMAND_RECESSION", "CR_ENERGY_EMBARGO",
    ),
    ("central_bank", "liquidity_operations"): (
        "CR_BANK_RUN", "CR_DEMAND_RECESSION",
    ),
    ("central_bank", "fx_operations"): (
        "CR_PEG_PRESSURE", "CR_TRADE_INTERRUPTION",
    ),
    ("regulator", "macroprudential"): (
        "CR_CREDIT_CRUNCH", "CR_SUPPLY_STAGFLATION",
    ),
    ("regulator", "structural_law"): (
        "CR_HOUSING_BUST", "CR_DEMAND_RECESSION",
    ),
    ("energy", "energy_operations"): (
        "CR_ENERGY_EMBARGO", "CR_DEMAND_RECESSION",
    ),
    ("energy", "energy_structure"): (
        "CR_ENERGY_EMBARGO", "CR_SUPPLY_STAGFLATION",
    ),
    ("external_affairs", "trade_and_migration"): (
        "CR_TRADE_INTERRUPTION", "CR_ENERGY_EMBARGO",
    ),
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (set, frozenset, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
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


def _contracts() -> dict[str, PolicyCausalContract]:
    by_lever = {contract.lever: contract for contract in build_contracts()}
    missing = sorted(set(R6_CANDIDATES) - set(by_lever))
    if missing or len(R6_CANDIDATES) != 36 or len(set(R6_CANDIDATES)) != 36:
        raise ValueError(f"invalid R6 candidate inventory; missing={missing}")
    return by_lever


def _scenario_outcomes(scenario_id: str) -> dict[str, int]:
    manifest = CRISIS_MANIFESTS[scenario_id]
    outcomes: dict[str, int] = {}
    for rule in (manifest.primary_damage, *manifest.propagation_rules):
        if rule.metric_id not in METRIC_MATERIALITY:
            continue
        sign = -1 if rule.direction == "increase" else 1
        previous = outcomes.get(rule.metric_id)
        if previous is not None and previous != sign:
            raise ValueError(
                f"{scenario_id}: inconsistent outcome direction for {rule.metric_id}"
            )
        outcomes[rule.metric_id] = sign
    if not outcomes:
        raise ValueError(f"{scenario_id}: no materiality-backed crisis outcomes")
    return outcomes


def _selected_crisis_arms(
    contract: PolicyCausalContract,
    *,
    scenario_id: str,
) -> tuple[ExperimentArm, ...]:
    if contract.lever == "fx_regime" and scenario_id == "CR_PEG_PRESSURE":
        return (ExperimentArm(
            "transition_to_float",
            "transition",
            (("fx_regime", "float"),),
        ),)
    arms = select_experiment_arms(contract, phase="activation")
    meaningful = tuple(
        arm for arm in arms if arm.dose_class in {"meaningful", "transition"}
    )
    if not meaningful:
        raise ValueError(f"{contract.lever}: no meaningful R6 crisis dose")
    return meaningful


def build_r6_design(
    *,
    p3_payload: Mapping[str, Any],
    p2_payload: Mapping[str, Any],
) -> dict[str, Any]:
    p0 = build_p0_payload()
    if p3_payload.get("p0_root_hash") != p0["hashes"]["p0_root"]:
        raise ValueError("R5 crisis evidence does not match the current P0 contract")
    if p2_payload.get("p0_root_hash") != p0["hashes"]["p0_root"]:
        raise ValueError("R6 mechanism evidence does not match the current P0 contract")
    accepted_crises = set(p3_payload.get("accepted_crises_for_p4", ()))
    if accepted_crises != set(CRISIS_MANIFESTS):
        raise ValueError("R6 requires the complete accepted R5 crisis library")
    p2_by = {str(row["lever"]): row for row in p2_payload.get("reports", ())}
    if set(p2_by) != set(R6_CANDIDATES):
        raise ValueError("R6 mechanism report does not exactly cover 36 candidates")

    by_lever = _contracts()
    rows: list[dict[str, Any]] = []
    for lever in R6_CANDIDATES:
        contract = by_lever[lever]
        state_pair = R6_STATE_DESIGN.get(
            (contract.owner_role, contract.decision_group)
        )
        if state_pair is None:
            raise ValueError(f"{lever}: no preregistered R6 state pair")
        for state_kind, scenario_id in zip(
            ("anchor", "adverse"), state_pair, strict=True
        ):
            role = contract.crisis_roles[scenario_id]
            if lever in R6_ACTIVATION_ONLY_CRISIS_EXCLUSIONS:
                rows.append({
                    "lever": lever,
                    "state_kind": state_kind,
                    "scenario_id": scenario_id,
                    "scenario_role": role,
                    "runnable": False,
                    "reason": (
                        "The lever is meaningful only with job_guarantee enabled; "
                        "R6 uses its matched activation fixture instead of changing "
                        "a second policy in a single-policy crisis branch."
                    ),
                    "arms": [],
                })
                continue
            manifest = CRISIS_MANIFESTS[scenario_id]
            if contract.scope == "external" and manifest.countries < 2:
                raise ValueError(
                    f"{lever}/{scenario_id}: external policy needs multiple economies"
                )
            rows.append({
                "lever": lever,
                "owner_role": contract.owner_role,
                "decision_group": contract.decision_group,
                "scope": contract.scope,
                "state_kind": state_kind,
                "scenario_id": scenario_id,
                "scenario_role": role,
                "p2_disposition": p2_by[lever]["disposition"],
                "p2_reason": p2_by[lever]["reason"],
                "mechanism_proximal_metrics": list(
                    contract.mechanism_proximal_metrics
                ),
                "tradeoff_metrics": list(contract.tradeoff_metrics),
                "runnable": True,
                "pre_experiment_disposition": None,
                "pre_experiment_reason": None,
                "policy_only_negative_control": False,
                "arms": [
                    {**arm.to_dict(), "timings": ["immediate"]}
                    for arm in _selected_crisis_arms(
                        contract, scenario_id=scenario_id
                    )
                ],
            })
    if len(rows) != 72:
        raise ValueError("R6 design must contain exactly two states per candidate")
    return {
        "schema_version": R6_SCHEMA_VERSION,
        "p0_root_hash": p0["hashes"]["p0_root"],
        "p2_acceptance_hash": p2_payload["hashes"]["p2_acceptance"],
        "p3_acceptance_hash": p3_payload["hashes"]["p3_acceptance"],
        "population_per_country": 100_000,
        "mechanism_seeds": p2_payload["protocol"]["matched_seeds"],
        "crisis_seeds": list(DEFAULT_P3_SEEDS),
        "native_engine_workers": 8,
        "independent_seed_jobs": 8,
        "severity": P4_SEVERITY,
        "policy_only_negative_control": False,
        "rows": rows,
    }


def run_r6_mechanism(
    *,
    artifact_dir: Path,
    source_revision: str,
    resume: bool = True,
    progress: Any = None,
) -> dict[str, Any]:
    return run_p2(
        artifact_dir=artifact_dir,
        source_revision=source_revision,
        levers=R6_CANDIDATES,
        population=100_000,
        workers=8,
        jobs=8,
        resume=resume,
        progress=progress,
    )


def run_r6_crises(
    *,
    artifact_dir: Path,
    p2_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
    source_revision: str,
    resume: bool = True,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    design = build_r6_design(p3_payload=p3_payload, p2_payload=p2_payload)
    rows = tuple(row for row in design["rows"] if row["runnable"])
    scenario_ids = tuple(sorted({str(row["scenario_id"]) for row in rows}))
    scenario_reports: list[dict[str, Any]] = []
    seed_runs: list[dict[str, Any]] = []
    errors: list[str] = []
    for scenario_index, scenario_id in enumerate(scenario_ids, start=1):
        matrix = tuple(row for row in rows if row["scenario_id"] == scenario_id)
        outcomes = _scenario_outcomes(scenario_id)
        scenario_dir = artifact_dir / "scenarios" / scenario_id
        p3_report = _accepted_p3_report(
            p3_payload, scenario_id=scenario_id
        )
        manifest_payload = {
            "schema_version": R6_SCHEMA_VERSION,
            "scenario": CRISIS_MANIFESTS[scenario_id].to_dict(),
            "severity": P4_SEVERITY,
            "primary_outcomes": outcomes,
            "timing_offsets_days": dict(P4_TIMINGS),
            "design_hash": _canonical_hash(design),
            "matrix": list(matrix),
        }
        current_runs: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(
                    _run_seed,
                    seed=seed,
                    matrix=matrix,
                    manifest_payload=manifest_payload,
                    p3_report=p3_report,
                    population=100_000,
                    workers=8,
                    source_revision=source_revision,
                    artifact_dir=scenario_dir,
                    resume=resume,
                    progress=None,
                    scenario_id=scenario_id,
                    severity=P4_SEVERITY,
                    primary_outcomes=outcomes,
                    timing_offsets=P4_TIMINGS,
                ): seed
                for seed in DEFAULT_P3_SEEDS
            }
            for future in as_completed(futures):
                current_runs.append(future.result())
        current_runs.sort(key=lambda item: int(item["seed"]))
        analyzed, scenario_errors = analyze_p4(
            matrix=matrix,
            seeds=DEFAULT_P3_SEEDS,
            artifact_dir=scenario_dir,
            primary_outcomes=outcomes,
        )
        for report in analyzed:
            scenario_reports.append({
                **report,
                "scenario_id": scenario_id,
                "state_kind": next(
                    row["state_kind"]
                    for row in matrix
                    if row["lever"] == report["lever"]
                ),
            })
        errors.extend(f"{scenario_id}: {item}" for item in scenario_errors)
        seed_runs.extend(
            {**item, "scenario_id": scenario_id} for item in current_runs
        )
        if progress is not None:
            progress(scenario_id, scenario_index, len(scenario_ids))

    excluded = [row for row in design["rows"] if not row["runnable"]]
    payload = {
        "schema_version": R6_SCHEMA_VERSION,
        "status": "accepted" if not errors else "failed",
        "source_revision": source_revision,
        "p0_root_hash": design["p0_root_hash"],
        "design": design,
        "scenario_outcomes": {
            scenario_id: _scenario_outcomes(scenario_id)
            for scenario_id in scenario_ids
        },
        "reports": scenario_reports,
        "excluded_state_rows": excluded,
        "seed_runs": seed_runs,
        "errors": errors,
        "counts": {
            "candidates": len(R6_CANDIDATES),
            "designed_state_rows": len(design["rows"]),
            "runnable_state_rows": len(rows),
            "excluded_state_rows": len(excluded),
            "scenarios": len(scenario_ids),
            "native_seed_sessions": len(seed_runs),
            "executed_native_branches": sum(
                int(item["executed"]) for item in seed_runs
            ),
            "cache_hits": sum(int(item["cache_hits"]) for item in seed_runs),
        },
        "hashes": {
            "r6_design": _canonical_hash(design),
            "r6_crisis_evidence": _canonical_hash(scenario_reports),
        },
    }
    _atomic_json(artifact_dir / "r6_crisis_report.json", payload)
    return payload


def _mechanism_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    activation = report.get("activation") or {}
    arms = activation.get("arms") or []
    meaningful = [
        arm for arm in arms
        if arm.get("dose_class") in {"meaningful", "transition"}
    ]
    timing: dict[str, Any] = {}
    for arm in meaningful:
        for metric_id in report.get("activation", {}).get(
            "changed_proximal_metrics", ()
        ):
            response = arm.get("time_responses", {}).get(metric_id)
            if response is not None:
                timing.setdefault(metric_id, []).append({
                    "arm": arm["label"],
                    "first_difference_tick": response["first_difference_tick"],
                    "peak_tick": response["peak_tick"],
                    "half_decay_tick": response["half_decay_tick"],
                    "terminal_effect": response["terminal_effect"],
                })
    return {
        "disposition": report["disposition"],
        "reason": report["reason"],
        "ordinary_changed_proximal_metrics": (
            report.get("ordinary") or {}
        ).get("changed_proximal_metrics", []),
        "activation_fixture": activation.get("fixture_id"),
        "activation_state": activation.get("native_scenario"),
        "changed_proximal_metrics": activation.get(
            "changed_proximal_metrics", []
        ),
        "salient_proximal_metrics": activation.get(
            "salient_proximal_metrics", []
        ),
        "dose_ordering": activation.get("dose_ordering", {}),
        "timing": timing,
    }


def _crisis_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    states: list[dict[str, Any]] = []
    for row in rows:
        arms: list[dict[str, Any]] = []
        for arm in row.get("arm_results", ()):
            outcomes = []
            for metric_id, evidence in arm.get("primary_benefit", {}).items():
                materiality = arm.get("materiality", {}).get(metric_id, {})
                floor = max(float(materiality.get("effective_floor", 0.0)), 1.0e-12)
                outcomes.append({
                    "metric_id": metric_id,
                    "mean_difference": materiality.get("mean_difference"),
                    "effect_to_floor": (
                        abs(float(materiality.get("mean_difference", 0.0))) / floor
                    ),
                    "material": bool(evidence.get("material")),
                    "signed_mean_benefit": evidence.get("signed_mean_benefit"),
                    "favorable_seed_count": evidence.get("favorable_seed_count"),
                    "adverse_seed_count": evidence.get("adverse_seed_count"),
                    "benefit_gate_passed": bool(evidence.get("passed")),
                })
            arms.append({
                "label": arm["label"],
                "dose_class": arm["dose_class"],
                "outcomes": outcomes,
            })
        states.append({
            "state_kind": row["state_kind"],
            "scenario_id": row["scenario_id"],
            "scenario_role": row["scenario_role"],
            "disposition": row["disposition"],
            "reason": row["reason"],
            "arms": arms,
        })
    return {"states": states}


def _has_benefit(crisis: Mapping[str, Any], state_kind: str) -> bool:
    return any(
        outcome["benefit_gate_passed"]
        for state in crisis["states"]
        if state["state_kind"] == state_kind
        for arm in state["arms"]
        for outcome in arm["outcomes"]
    )


def _has_harm(crisis: Mapping[str, Any], state_kind: str) -> bool:
    return any(
        outcome["material"]
        and float(outcome["signed_mean_benefit"] or 0.0) < 0.0
        and int(outcome["adverse_seed_count"] or 0) >= 6
        for state in crisis["states"]
        if state["state_kind"] == state_kind
        for arm in state["arms"]
        for outcome in arm["outcomes"]
    )


def _classification(
    *,
    lever: str,
    contract: PolicyCausalContract,
    mechanism: Mapping[str, Any],
    crisis: Mapping[str, Any],
) -> tuple[str, str]:
    disposition = str(mechanism["disposition"])
    live = disposition.startswith("accepted")
    salient = bool(mechanism["salient_proximal_metrics"])
    anchor_benefit = _has_benefit(crisis, "anchor")
    adverse_harm = _has_harm(crisis, "adverse")
    structural = (
        contract.semantics in {"state-transition", "new-contracts-only"}
        or disposition == "accepted_structural_long_horizon"
    )
    if structural and live:
        return (
            "structural",
            "The lever changes an institution, legal cohort, or ownership state; "
            "its effect is valid but not a continuously calibrated macro dose.",
        )
    if not live:
        return (
            "removed",
            "The matched mechanism gate did not pass, so the lever cannot remain "
            "on the player surface on crisis correlation alone.",
        )
    if anchor_benefit and adverse_harm:
        return (
            "conditional",
            "The lever has supported crisis benefit and a supported adverse-state "
            "trade-off; the UI must expose both conditions.",
        )
    if anchor_benefit and disposition == "accepted":
        return (
            "effective",
            "The lever is salient in ordinary and binding states, improves an "
            "anchor-crisis loss, and passes the adverse-state harm screen.",
        )
    if anchor_benefit or disposition == "accepted_activation_only":
        return (
            "conditional",
            "The lever is useful only in its binding fixture or matched crisis; "
            "ordinary-state silence is an explicit scope condition.",
        )
    if salient:
        return (
            "expert_only",
            "The native mechanism is material, but the preregistered anchor-crisis "
            "benefit gate did not support a general player-facing efficacy claim.",
        )
    if disposition == "accepted_expert_only":
        return (
            "removed",
            "The mechanism is statistically detectable but remains below the "
            "preregistered gameplay-salience floor and has no supported crisis benefit.",
        )
    return (
        "removed",
        "No gameplay-salient mechanism or supported crisis benefit remains after "
        "the preregistered screens.",
    )


def build_r6_acceptance(
    *,
    p2_payload: Mapping[str, Any],
    crisis_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if p2_payload.get("status") != "accepted_with_explicit_defects":
        errors.append(f"unexpected R6 P2 status {p2_payload.get('status')!r}")
    if p2_payload.get("errors") != []:
        errors.append("R6 P2 execution errors remain")
    if crisis_payload.get("status") != "accepted":
        errors.append(f"unexpected R6 crisis status {crisis_payload.get('status')!r}")
    if crisis_payload.get("errors") != []:
        errors.append("R6 crisis execution errors remain")
    if p2_payload.get("counts", {}).get("cache_hits") != 0:
        errors.append("formal R6 mechanism evidence used cached runs")
    if crisis_payload.get("counts", {}).get("cache_hits") != 0:
        errors.append("formal R6 crisis evidence used cached runs")

    by_contract = _contracts()
    p2_by = {str(row["lever"]): row for row in p2_payload.get("reports", ())}
    crisis_by: dict[str, list[Mapping[str, Any]]] = {
        lever: [] for lever in R6_CANDIDATES
    }
    for row in crisis_payload.get("reports", ()):
        crisis_by[str(row["lever"])].append(row)
    excluded_by: dict[str, list[Mapping[str, Any]]] = {
        lever: [] for lever in R6_CANDIDATES
    }
    for row in crisis_payload.get("excluded_state_rows", ()):
        excluded_by[str(row["lever"])].append(row)
    if set(p2_by) != set(R6_CANDIDATES):
        errors.append("R6 P2 ledger does not exactly cover 36 candidates")

    reports: list[dict[str, Any]] = []
    for lever in R6_CANDIDATES:
        if lever not in p2_by:
            continue
        mechanism = _mechanism_summary(p2_by[lever])
        crisis = _crisis_summary(crisis_by[lever])
        classification, reason = _classification(
            lever=lever,
            contract=by_contract[lever],
            mechanism=mechanism,
            crisis=crisis,
        )
        reports.append({
            "lever": lever,
            "owner_role": by_contract[lever].owner_role,
            "decision_group": by_contract[lever].decision_group,
            "semantics": by_contract[lever].semantics,
            "classification": classification,
            "reason": reason,
            "mechanism": mechanism,
            "direction_and_magnitude": crisis,
            "guardrails": {
                "anchor_benefit_gate_passed": _has_benefit(crisis, "anchor"),
                "adverse_state_harm_detected": _has_harm(crisis, "adverse"),
            },
            "empirical_scope": {
                "population_per_country": 100_000,
                "ordinary_and_activation_seed_count": 4,
                "crisis_seed_count": 8,
                "tested_crisis_states": [
                    state["scenario_id"] for state in crisis["states"]
                ],
                "activation_only_exclusions": [
                    row["scenario_id"] for row in excluded_by[lever]
                ],
                "scale_confirmation_pending_r7": lever in R6_SCALE_PENDING,
                "empirical_real_world_claim": False,
            },
        })
    counts = {name: 0 for name in sorted(R6_CLASSIFICATIONS)}
    for report in reports:
        counts[report["classification"]] += 1
    if len(reports) != 36 or sum(counts.values()) != 36:
        errors.append("R6 final ledger does not exactly classify 36 candidates")
    if any(report["classification"] not in R6_CLASSIFICATIONS for report in reports):
        errors.append("R6 final ledger contains an invalid classification")
    if any(
        report["classification"] != "removed"
        and not report["mechanism"]["salient_proximal_metrics"]
        and not report["guardrails"]["anchor_benefit_gate_passed"]
        and report["classification"] != "structural"
        for report in reports
    ):
        errors.append("a gameplay-silent lever was retained without structural scope")

    acceptance_identity = {
        "schema_version": R6_SCHEMA_VERSION,
        "p0_root_hash": build_p0_payload()["hashes"]["p0_root"],
        "p2_acceptance_hash": p2_payload.get("hashes", {}).get("p2_acceptance"),
        "r5_acceptance_hash": p3_payload.get("hashes", {}).get("p3_acceptance"),
        "crisis_evidence_hash": crisis_payload.get("hashes", {}).get(
            "r6_crisis_evidence"
        ),
        "reports_hash": _canonical_hash(reports),
        "errors": errors,
    }
    return {
        "schema_version": R6_SCHEMA_VERSION,
        "status": "accepted" if not errors else "failed",
        "errors": errors,
        "protocol": {
            "candidates": 36,
            "population_per_country": 100_000,
            "mechanism_matched_seeds": 4,
            "crisis_matched_seeds": 8,
            "native_engine_workers": 8,
            "independent_seed_jobs": 8,
            "legacy_python_simulator_used": False,
            "real_world_empirical_calibration_claimed": False,
        },
        "counts": {
            "classifications": counts,
            "crisis_state_rows": crisis_payload.get("counts", {}).get(
                "designed_state_rows"
            ),
            "executed_native_mechanism_runs": p2_payload.get("counts", {}).get(
                "executed_native_runs"
            ),
            "executed_native_crisis_branches": crisis_payload.get(
                "counts", {}
            ).get("executed_native_branches"),
            "cache_hits": (
                int(p2_payload.get("counts", {}).get("cache_hits", 0))
                + int(crisis_payload.get("counts", {}).get("cache_hits", 0))
            ),
        },
        "reports": reports,
        "hashes": {
            "r6_reports": acceptance_identity["reports_hash"],
            "r6_acceptance": _canonical_hash(acceptance_identity),
        },
    }


def validate_r6_acceptance(
    payload: Mapping[str, Any],
    *,
    p2_payload: Mapping[str, Any],
    crisis_payload: Mapping[str, Any],
    p3_payload: Mapping[str, Any],
) -> list[str]:
    expected = build_r6_acceptance(
        p2_payload=p2_payload,
        crisis_payload=crisis_payload,
        p3_payload=p3_payload,
    )
    return [] if _jsonable(payload) == _jsonable(expected) else [
        "committed R6 acceptance does not reproduce from frozen evidence"
    ]


def render_r6_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy remediation R6 acceptance",
        "",
        f"- Status: `{payload['status']}`",
        f"- Candidates: {payload['protocol']['candidates']}",
        "- Population per country: 100,000",
        "- Mechanism design: four matched seeds across ordinary and binding states",
        "- Crisis design: eight matched seeds across anchor and adverse states",
        "- Native workers / seed jobs: 8 / 8",
        "- Legacy Python simulator used: no",
        "- Real-world empirical calibration claimed: no",
        f"- Acceptance hash: `{payload['hashes']['r6_acceptance']}`",
        "",
        "## Classification counts",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for name, count in payload["counts"]["classifications"].items():
        lines.append(f"| `{name}` | {count} |")
    lines.extend((
        "",
        "## Candidate ledger",
        "",
        "| Lever | Classification | Mechanism | Anchor benefit | Adverse harm | R7 scale |",
        "|---|---|---|---:|---:|---:|",
    ))
    for report in payload["reports"]:
        lines.append(
            f"| `{report['lever']}` | `{report['classification']}` | "
            f"`{report['mechanism']['disposition']}` | "
            f"{str(report['guardrails']['anchor_benefit_gate_passed']).lower()} | "
            f"{str(report['guardrails']['adverse_state_harm_detected']).lower()} | "
            f"{str(report['empirical_scope']['scale_confirmation_pending_r7']).lower()} |"
        )
    if payload["errors"]:
        lines.extend(("", "## Errors", ""))
        lines.extend(f"- {error}" for error in payload["errors"])
    return "\n".join(lines) + "\n"


__all__ = [
    "R6_CANDIDATES",
    "R6_CLASSIFICATIONS",
    "R6_SCHEMA_VERSION",
    "R6_STATE_DESIGN",
    "build_r6_acceptance",
    "build_r6_design",
    "render_r6_markdown",
    "run_r6_crises",
    "run_r6_mechanism",
    "validate_r6_acceptance",
]
