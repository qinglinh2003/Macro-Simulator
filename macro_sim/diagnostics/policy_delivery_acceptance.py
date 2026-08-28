"""R9 policy delivery, UI scope, and occupant acceptance.

R9 does not recalibrate economic effects.  It binds the current R6-R8 evidence
to the complete Registry, proves that free and institutional paths hand the same
action to the native World at their documented boundaries, and refreshes the
heuristic, random, human-ingress, and RL-transfer probes on the native task.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

from macro_sim.controllers.native_session import NativeControlledWorld
from macro_sim.controllers.occupants import HumanQueueOccupant, ScheduledOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal, canonical_json
from macro_sim.controllers.session import AWAITING_HUMAN, ControlledSimulationSession
from macro_sim.core.policy_explanations import POLICY_EXPLANATIONS
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_institutional_delivery import (
    P8_LEVER,
    P8_RL_ARTIFACT,
    P8_VALUE,
    _context_audit,
    _crisis_tape,
    _native_genesis,
    _scheduler,
    run_occupant_evaluation,
)


R9_SCHEMA_VERSION = "policy-remediation-r9-v1"
R9_POLICY_EVIDENCE_SCHEMA_VERSION = "policy-evidence-v39-v1"
R9_SEEDS = (5101, 5113, 5129, 5143, 5159, 5177, 5193, 5209)
R9_POPULATION = 100_000
R9_NATIVE_WORKERS = 8
R9_JOBS = 8
R9_ACCEPTED_PHASES = ("R6", "R7", "R8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset, tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        canonical_json(_jsonable(value)).encode("utf-8")
    ).hexdigest()


def _acceptance_hash(payload: Mapping[str, Any], phase: str) -> str:
    if payload.get("status") != "accepted":
        raise ValueError(f"{phase} acceptance is not accepted")
    value = payload.get("hashes", {}).get(f"{phase.lower()}_acceptance")
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{phase} acceptance hash is malformed")
    return value


def build_policy_evidence_catalog(
    phase_acceptances: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the complete product catalog from accepted R6-R8 scope evidence."""
    if set(phase_acceptances) != set(R9_ACCEPTED_PHASES):
        raise ValueError("R9 policy evidence requires R6, R7, and R8")
    upstream = {
        phase: _acceptance_hash(phase_acceptances[phase], phase)
        for phase in R9_ACCEPTED_PHASES
    }
    r6 = phase_acceptances["R6"]
    r7 = phase_acceptances["R7"]
    r8 = phase_acceptances["R8"]
    r6_rows = {str(item["lever"]): item for item in r6.get("reports", ())}
    r7_rows = {str(item["lever"]): item for item in r7.get("reports", ())}
    if len(r6_rows) != 36 or len(r7_rows) != 7:
        raise ValueError("R9 policy evidence source coverage differs")
    if not set(r7_rows) <= set(r6_rows) <= set(REGISTRY):
        raise ValueError("R9 individual evidence names an unknown lever")

    package_findings: dict[str, list[dict[str, str]]] = {
        name: [] for name in REGISTRY
    }
    reports = r8.get("reports", ())
    if len(reports) != 9:
        raise ValueError("R9 policy package evidence must contain nine packages")
    for report in reports:
        for role, names in report.get("component_roles", {}).items():
            if role not in {"essential", "harmful", "redundant", "supportive"}:
                raise ValueError("R9 package evidence has an unknown component role")
            for name in names:
                if name not in REGISTRY:
                    raise ValueError("R9 package evidence names an unknown lever")
                package_findings[name].append({
                    "package_disposition": str(report["disposition"]),
                    "package_id": str(report["package_id"]),
                    "role": str(role),
                    "scenario_id": str(report["scenario_id"]),
                })

    policies: dict[str, dict[str, Any]] = {}
    for name in sorted(REGISTRY):
        individual = r6_rows.get(name)
        scale = r7_rows.get(name)
        scope = (
            individual.get("empirical_scope", {}) if individual is not None else {}
        )
        policies[name] = {
            "coverage": (
                "single_policy_calibrated"
                if individual is not None else "registry_and_route_only"
            ),
            "individual_classification": (
                str(individual["classification"])
                if individual is not None else "not_reclassified"
            ),
            "package_findings": sorted(
                package_findings[name],
                key=lambda item: (item["package_id"], item["role"]),
            ),
            "population_per_country": (
                int(scope["population_per_country"])
                if "population_per_country" in scope else None
            ),
            "real_world_empirical_claim": False,
            "scale_disposition": (
                str(scale["scale_disposition"])
                if scale is not None else None
            ),
            "tested_crisis_states": sorted(
                str(item) for item in scope.get("tested_crisis_states", ())
            ),
        }
    payload = {
        "schema_version": R9_POLICY_EVIDENCE_SCHEMA_VERSION,
        "upstream_acceptance_hashes": upstream,
        "policies": policies,
    }
    payload["catalog_sha256"] = _canonical_hash(payload)
    return payload


def _validation_contract(validation: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"kind": type(validation).__name__}
    for field in ("lo", "hi", "max_step", "values"):
        if hasattr(validation, field):
            row[field] = _jsonable(getattr(validation, field))
    return row


def _registry_contract() -> dict[str, Any]:
    return {
        name: {
            "decision_group": lever.decision_group,
            "enabled_if": sorted(lever.enabled_if),
            "owner_role": lever.owner_role,
            "requires": sorted(lever.requires),
            "scope": lever.scope,
            "semantics": lever.semantics,
            "shadowed_by": list(lever.shadowed_by),
            "validation": _validation_contract(lever.validation),
        }
        for name, lever in sorted(REGISTRY.items())
    }


def build_r9_manifest(
    *,
    phase_acceptances: Mapping[str, Mapping[str, Any]],
    policy_evidence: Mapping[str, Any],
    rl_artifact: str | Path,
) -> dict[str, Any]:
    expected_catalog = build_policy_evidence_catalog(phase_acceptances)
    if _jsonable(policy_evidence) != _jsonable(expected_catalog):
        raise ValueError("packaged R9 policy evidence does not reproduce")
    artifact = Path(rl_artifact)
    if not artifact.is_file():
        raise ValueError("R9 RL transfer artifact is missing")
    lever = REGISTRY[P8_LEVER]
    action_contract = {
        "emergency_implementation_lag": lever.emergency_implementation_lag,
        "implementation_lag": lever.implementation_lag,
        "lever": P8_LEVER,
        "owner_role": lever.owner_role,
        "value": P8_VALUE,
    }
    if action_contract != {
        "emergency_implementation_lag": 1,
        "implementation_lag": 7,
        "lever": "benefit_income_floor",
        "owner_role": "labor_social",
        "value": 0.20,
    }:
        raise ValueError("R9 representative delivery contract drifted")
    manifest = {
        "schema_version": R9_SCHEMA_VERSION,
        "action": action_contract,
        "delivery_paths": [
            "free_immediate",
            "institutional_emergency",
            "institutional_regular",
            "recorded_human_regular",
        ],
        "occupants": [
            "heuristic", "human_recorded_hold", "no_action", "random",
            "rl_transfer",
        ],
        "policy_evidence_sha256": policy_evidence["catalog_sha256"],
        "population_per_country": R9_POPULATION,
        "registry_contract_sha256": _canonical_hash(_registry_contract()),
        "rl_artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "seeds": list(R9_SEEDS),
        "upstream_acceptance_hashes": dict(
            policy_evidence["upstream_acceptance_hashes"]
        ),
        "workers": {
            "concurrent_seed_jobs": R9_JOBS,
            "native_workers_per_session": R9_NATIVE_WORKERS,
        },
    }
    manifest["manifest_sha256"] = _canonical_hash(manifest)
    return manifest


def _policy_action() -> tuple[PolicyAction, ...]:
    return (PolicyAction(P8_LEVER, P8_VALUE),)


def _wire_action() -> tuple[dict[str, Any], ...]:
    return ({"economy_id": 0, "lever": P8_LEVER, "value": P8_VALUE},)


def _human_proposal(context: Any) -> PolicyProposal:
    proposal_id = f"r9-human:{context.context_id}"
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=_policy_action(),
        reason="r9_recorded_human_ingress",
        based_on_policy_versions=dict(context.policy_versions),
    )


def _controlled_path(
    base: Any,
    new_game: Any,
    *,
    delivery: str,
) -> dict[str, Any]:
    native = base.clone()
    tape_hash: str | None = None
    emergency = delivery == "emergency"
    if emergency:
        tape_hash = _crisis_tape(native)
    world = NativeControlledWorld(
        native,
        new_game.configs(),
        trade=bool(new_game.world["trade"]),
        capital=bool(new_game.world["capital"]),
        migration=bool(new_game.world["migration"]),
    )
    scheduler = _scheduler(delayed=not emergency)
    controlled = ControlledSimulationSession(
        world, scheduler=scheduler, run_mode="batch",
    )
    human = delivery == "human_regular"
    occupant: Any = (
        HumanQueueOccupant()
        if human else ScheduledOccupant({31 if emergency else 30: _policy_action()})
    )
    controlled.assign_seat(0, "labor_social", occupant, actor="r9_acceptance")
    target = 33 if emergency else 38
    contexts: list[dict[str, Any]] = []
    decisions: dict[str, Any] = {}
    while controlled.boundary_tick < target:
        result = controlled.advance()
        contexts.extend(_context_audit(item) for item in result.contexts)
        if result.status == AWAITING_HUMAN:
            for context_id in result.missing_context_ids:
                context = controlled._opened_contexts[context_id]
                controlled.submit_human_proposal(
                    _human_proposal(context), actor="recorded_human",
                )
            result = controlled.advance()
            contexts.extend(_context_audit(item) for item in result.contexts)
        for decision in result.decisions:
            decisions[decision.decision_id] = decision
    action_decisions = [
        item for item in decisions.values()
        if item.adjustment_cost > 0.0
    ]
    accepted = sorted(
        item.accepted_tick for item in action_decisions
        if item.accepted_tick is not None
    )
    effective = sorted(
        item.effective_tick for item in action_decisions
        if item.effective_tick is not None
    )
    return {
        "accepted_tick": accepted[0] if accepted else None,
        "context_audits": contexts,
        "digest": int(native.native_snapshot()["digest"]),
        "effective_tick": effective[0] if effective else None,
        "policy_value": native.policy_values(0)[P8_LEVER],
        "tape_hash": tape_hash,
        "tick": native.tick,
    }


def _direct_path(base: Any, *, wait_ticks: int, shock: bool) -> dict[str, Any]:
    native = base.clone()
    tape_hash = _crisis_tape(native) if shock else None
    if wait_ticks:
        native.advance(wait_ticks)
    native.advance(actions=_wire_action())
    return {
        "digest": int(native.native_snapshot()["digest"]),
        "policy_value": native.policy_values(0)[P8_LEVER],
        "tape_hash": tape_hash,
        "tick": native.tick,
    }


def _free_product_path(seed: int) -> dict[str, Any]:
    from macro_sim.desktop.native_runtime import NativeSimulationRuntime

    runtime = NativeSimulationRuntime(seed=seed)
    direct = runtime.session.clone()
    opening_digest = int(runtime.session.native_snapshot()["digest"])
    staged = runtime.stage_policy([
        {"lever": P8_LEVER, "value": P8_VALUE},
    ])
    staged_digest = int(runtime.session.native_snapshot()["digest"])
    advanced = runtime.advance(1)
    direct.advance(actions=(
        {"economy_id": runtime.player_economy, "lever": P8_LEVER,
         "value": P8_VALUE},
    ))
    return {
        "accepted_tick": staged["last_verdict"]["accepted_tick"],
        "digest": int(runtime.session.native_snapshot()["digest"]),
        "direct_digest": int(direct.native_snapshot()["digest"]),
        "effective_tick": advanced["last_verdict"]["effective_tick"],
        "opening_digest": opening_digest,
        "policy_value": runtime.session.policy_values(
            runtime.player_economy
        )[P8_LEVER],
        "staged_digest": staged_digest,
        "tick": runtime.tick,
    }


def _run_delivery_seed(seed: int) -> dict[str, Any]:
    started = time.perf_counter()
    new_game, _native_spec, base = _native_genesis(seed)
    regular_direct = _direct_path(base, wait_ticks=7, shock=False)
    regular = _controlled_path(base, new_game, delivery="regular")
    human = _controlled_path(base, new_game, delivery="human_regular")
    emergency_direct = _direct_path(base, wait_ticks=2, shock=True)
    emergency = _controlled_path(base, new_game, delivery="emergency")
    return {
        "emergency": emergency,
        "emergency_direct": emergency_direct,
        "free_product": _free_product_path(seed),
        "human_regular": human,
        "regular": regular,
        "regular_direct": regular_direct,
        "seed": seed,
        "elapsed_seconds": time.perf_counter() - started,
    }


def _ui_contract() -> dict[str, Any]:
    from macro_sim.desktop.native_runtime import NativeSimulationRuntime

    runtime = NativeSimulationRuntime(seed=R9_SEEDS[0])
    schema = runtime.schema()
    levers = [
        lever
        for seat in schema["seats"].values()
        for lever in seat["levers"]
    ]
    names = {str(lever["name"]) for lever in levers}
    return {
        "all_definitions_complete": all(
            set(lever.get("player_help", {}))
            == {"meaning", "mechanics", "tradeoffs", "watch"}
            and all(
                isinstance(value, str) and value.strip()
                for value in lever["player_help"].values()
            )
            for lever in levers
        ),
        "all_evidence_scopes_complete": all(
            isinstance(lever.get("evidence_scope"), dict)
            for lever in levers
        ),
        "all_registry_domains_present": names == set(REGISTRY),
        "control_mode": schema.get("control_mode"),
        "evidence_catalog_sha256": schema.get("policy_evidence_sha256"),
        "lever_count": len(levers),
        "read_points_complete": all(
            isinstance(lever.get("read_point"), str)
            and bool(lever["read_point"].strip())
            for lever in levers
        ),
    }


def _delivery_gates(seed_runs: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    context_audits = [
        audit
        for run in seed_runs
        for branch in ("regular", "human_regular", "emergency")
        for audit in run[branch]["context_audits"]
    ]
    return {
        "documented_delivery_ticks": all(
            run["free_product"]["accepted_tick"] == 0
            and run["free_product"]["effective_tick"] == 1
            and run["regular"]["accepted_tick"] == 30
            and run["regular"]["effective_tick"] == 37
            and run["human_regular"]["accepted_tick"] == 30
            and run["human_regular"]["effective_tick"] == 37
            and run["emergency"]["accepted_tick"] == 31
            and run["emergency"]["effective_tick"] == 32
            for run in seed_runs
        ),
        "emergency_exact_native_parity": all(
            run["emergency"]["digest"] == run["emergency_direct"]["digest"]
            and run["emergency"]["tape_hash"]
            == run["emergency_direct"]["tape_hash"]
            for run in seed_runs
        ),
        "free_immediate_exact_native_parity": all(
            run["free_product"]["digest"]
            == run["free_product"]["direct_digest"]
            and run["free_product"]["opening_digest"]
            == run["free_product"]["staged_digest"]
            for run in seed_runs
        ),
        "human_ingress_exact_native_parity": all(
            run["human_regular"]["digest"]
            == run["regular_direct"]["digest"]
            for run in seed_runs
        ),
        "institutional_regular_exact_native_parity": all(
            run["regular"]["digest"] == run["regular_direct"]["digest"]
            for run in seed_runs
        ),
        "policies_reached_expected_state": all(
            run[branch]["policy_value"] == P8_VALUE
            for run in seed_runs
            for branch in (
                "emergency", "emergency_direct", "free_product",
                "human_regular", "regular", "regular_direct",
            )
        ),
        "released_observations_only": bool(context_audits) and all(
            not audit["future_release_ids"]
            and not audit["oracle_release_ids"]
            and not audit["future_bulletin_ids"]
            and audit["observation_role"] == "labor_social"
            for audit in context_audits
        ),
    }


def run_r9(
    *,
    phase_acceptances: Mapping[str, Mapping[str, Any]],
    policy_evidence: Mapping[str, Any],
    rl_artifact: str | Path = P8_RL_ARTIFACT,
    source_revision: str,
    jobs: int = R9_JOBS,
    progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    manifest = build_r9_manifest(
        phase_acceptances=phase_acceptances,
        policy_evidence=policy_evidence,
        rl_artifact=rl_artifact,
    )
    seed_runs: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(_run_delivery_seed, seed): seed for seed in R9_SEEDS
        }
        for future in as_completed(futures):
            run = future.result()
            seed_runs.append(run)
            if progress is not None:
                progress(int(run["seed"]))
    seed_runs.sort(key=lambda item: item["seed"])
    delivery_gates = _delivery_gates(seed_runs)
    ui = _ui_contract()
    ui_gates = {
        "definitions_complete": bool(ui["all_definitions_complete"]),
        "evidence_scopes_complete": bool(ui["all_evidence_scopes_complete"]),
        "registry_domains_complete": bool(ui["all_registry_domains_present"]),
        "read_points_complete": bool(ui["read_points_complete"]),
        "free_policy_mode": ui["control_mode"] == "free_policy",
        "evidence_catalog_bound": (
            ui["evidence_catalog_sha256"]
            == policy_evidence["catalog_sha256"]
        ),
    }
    occupant = run_occupant_evaluation(rl_artifact)
    occupant_gates = {
        "action_codec_match": bool(
            occupant["contract_assessment"]["action_codec_match"]
        ),
        "context_codec_match": bool(
            occupant["contract_assessment"]["context_codec_match"]
        ),
        "released_observations_only": bool(
            occupant["environment"]["released_observation_gate"]
        ),
    }
    errors = [
        f"R9 {scope} gate failed: {name}"
        for scope, gates in (
            ("delivery", delivery_gates),
            ("UI", ui_gates),
            ("occupant", occupant_gates),
        )
        for name, passed in gates.items()
        if not passed
    ]
    limitations = [
        "Recorded human ingress validates transport, authority, timing, and native execution parity; it is not participant performance data.",
    ]
    if not occupant["contract_assessment"]["training_environment_match"]:
        limitations.append(
            "The shipped RL artifact matches the vector codecs but not the native training-environment contract; R9 treats it only as a transfer probe and makes no superiority claim."
        )
    evidence_core = {
        "delivery_gates": delivery_gates,
        "occupant": occupant,
        "seed_runs": [
            {key: value for key, value in run.items() if key != "elapsed_seconds"}
            for run in seed_runs
        ],
        "ui": ui,
        "ui_gates": ui_gates,
    }
    payload = {
        "schema_version": R9_SCHEMA_VERSION,
        "status": "accepted_with_explicit_limitations" if not errors else "failed",
        "source_revision": source_revision,
        "errors": errors,
        "limitations": limitations,
        "manifest": manifest,
        "delivery": {
            "gates": delivery_gates,
            "seed_runs": seed_runs,
        },
        "occupant_evaluation": occupant,
        "occupant_gates": occupant_gates,
        "ui_contract": ui,
        "ui_gates": ui_gates,
        "counts": {
            "delivery_native_paths": len(seed_runs) * 6,
            "delivery_seeds": len(seed_runs),
            "occupant_evaluation_seeds": len(
                occupant["environment"]["evaluation_seeds"]
            ),
            "occupant_policies": len(occupant["experiment"]["policy_names"]),
            "registry_levers": len(REGISTRY),
        },
        "protocol": {
            "actual_human_performance_claim": False,
            "concurrent_seed_jobs": jobs,
            "legacy_python_simulator_used": False,
            "native_economic_engine": True,
            "native_workers_per_session": R9_NATIVE_WORKERS,
            "population_per_country": R9_POPULATION,
            "python_role": "orchestration_reduction_and_controller_state",
            "rl_superiority_claim": bool(
                occupant["contract_assessment"]["superiority_claim_allowed"]
            ),
        },
        "hashes": {
            "r9_evidence": _canonical_hash(evidence_core),
            "r9_manifest": manifest["manifest_sha256"],
        },
    }
    payload["hashes"]["r9_acceptance"] = _canonical_hash({
        "errors": errors,
        "evidence": payload["hashes"]["r9_evidence"],
        "limitations": limitations,
        "manifest": payload["hashes"]["r9_manifest"],
        "protocol": payload["protocol"],
        "source_revision": source_revision,
        "status": payload["status"],
    })
    return payload


def reduce_r9_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove runtime-only fields while retaining every formal R9 gate."""
    return {
        "schema_version": payload["schema_version"],
        "status": payload["status"],
        "source_revision": payload["source_revision"],
        "errors": deepcopy(payload["errors"]),
        "limitations": deepcopy(payload["limitations"]),
        "manifest": deepcopy(payload["manifest"]),
        "delivery_gates": deepcopy(payload["delivery"]["gates"]),
        "delivery_seed_evidence": [
            {
                "seed": run["seed"],
                "digests": {
                    branch: run[branch]["digest"]
                    for branch in (
                        "emergency", "emergency_direct", "human_regular",
                        "regular", "regular_direct",
                    )
                } | {
                    "free_immediate": run["free_product"]["digest"],
                    "free_immediate_direct": run["free_product"]["direct_digest"],
                },
                "effective_ticks": {
                    "emergency": run["emergency"]["effective_tick"],
                    "free_immediate": run["free_product"]["effective_tick"],
                    "human_regular": run["human_regular"]["effective_tick"],
                    "regular": run["regular"]["effective_tick"],
                },
            }
            for run in payload["delivery"]["seed_runs"]
        ],
        "occupant_contract_assessment": deepcopy(
            payload["occupant_evaluation"]["contract_assessment"]
        ),
        "occupant_gates": deepcopy(payload["occupant_gates"]),
        "occupant_summaries": deepcopy(
            payload["occupant_evaluation"]["summaries"]
        ),
        "ui_contract": deepcopy(payload["ui_contract"]),
        "ui_gates": deepcopy(payload["ui_gates"]),
        "counts": deepcopy(payload["counts"]),
        "protocol": deepcopy(payload["protocol"]),
        "execution_hashes": deepcopy(payload["hashes"]),
    }


def build_r9_acceptance(evidence: Mapping[str, Any]) -> dict[str, Any]:
    evidence_hash = _canonical_hash(evidence)
    acceptance = {
        "schema_version": R9_SCHEMA_VERSION,
        "status": evidence["status"],
        "source_revision": evidence["source_revision"],
        "errors": deepcopy(evidence["errors"]),
        "limitations": deepcopy(evidence["limitations"]),
        "upstream_acceptance_hashes": deepcopy(
            evidence["manifest"]["upstream_acceptance_hashes"]
        ),
        "delivery_gates": deepcopy(evidence["delivery_gates"]),
        "occupant_contract_assessment": deepcopy(
            evidence["occupant_contract_assessment"]
        ),
        "occupant_gates": deepcopy(evidence["occupant_gates"]),
        "ui_gates": deepcopy(evidence["ui_gates"]),
        "counts": deepcopy(evidence["counts"]),
        "protocol": deepcopy(evidence["protocol"]),
        "hashes": {
            "policy_evidence": evidence["manifest"]["policy_evidence_sha256"],
            "r9_evidence": evidence_hash,
            "r9_manifest": evidence["manifest"]["manifest_sha256"],
        },
    }
    acceptance["hashes"]["r9_acceptance"] = _canonical_hash(acceptance)
    return acceptance


def validate_r9_acceptance(
    evidence: Mapping[str, Any], acceptance: Mapping[str, Any],
) -> list[str]:
    expected = build_r9_acceptance(evidence)
    return [] if _jsonable(expected) == _jsonable(acceptance) else [
        "committed R9 acceptance does not reproduce"
    ]


def render_r9_markdown(acceptance: Mapping[str, Any]) -> str:
    lines = [
        "# Policy remediation R9 acceptance",
        "",
        f"Status: `{acceptance['status']}`",
        "",
        "## Delivery and UI gates",
        "",
    ]
    for scope in ("delivery_gates", "ui_gates", "occupant_gates"):
        lines.append(f"### {scope.replace('_', ' ').title()}")
        lines.append("")
        for name, passed in acceptance[scope].items():
            lines.append(f"- `{name}`: `{'passed' if passed else 'failed'}`")
        lines.append("")
    assessment = acceptance["occupant_contract_assessment"]
    lines.extend([
        "## Occupant contract",
        "",
        f"- Classification: `{assessment['classification']}`",
        f"- Training environment match: `{assessment['training_environment_match']}`",
        f"- Superiority claim allowed: `{assessment['superiority_claim_allowed']}`",
        "",
        "## Explicit limitations",
        "",
    ])
    lines.extend(f"- {item}" for item in acceptance["limitations"])
    lines.extend([
        "",
        "## Hashes",
        "",
        f"- Policy evidence: `{acceptance['hashes']['policy_evidence']}`",
        f"- R9 evidence: `{acceptance['hashes']['r9_evidence']}`",
        f"- R9 acceptance: `{acceptance['hashes']['r9_acceptance']}`",
        "",
    ])
    return "\n".join(lines)


__all__ = [
    "R9_ACCEPTED_PHASES",
    "R9_SCHEMA_VERSION",
    "build_policy_evidence_catalog",
    "build_r9_acceptance",
    "build_r9_manifest",
    "reduce_r9_evidence",
    "render_r9_markdown",
    "run_r9",
    "validate_r9_acceptance",
]
