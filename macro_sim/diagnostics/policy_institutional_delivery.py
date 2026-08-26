"""Institutional delivery and occupant evaluation for Policy audit P8.

P8 keeps the economic experiment frozen and changes only the delivery path.  A
validated demand-recession action is passed through the real Controller clocks,
authority, release, cost, and human-ingress contracts over the native C++ World.
The separate occupant benchmark evaluates every candidate on one common native
environment; a migrated artifact is treated as a transfer probe when its training
environment contract differs, never as a silently compatible deployment model.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean, stdev
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from macro_sim import native_backend
from macro_sim.controllers.native_session import NativeControlledWorld
from macro_sim.controllers.occupants import (
    HumanQueueOccupant,
    NullOccupant,
    ScheduledOccupant,
)
from macro_sim.controllers.protocol import (
    PolicyAction,
    PolicyProposal,
    canonical_json,
)
from macro_sim.controllers.scheduler import (
    CalendarSpec,
    DEFAULT_CALENDARS,
    DecisionScheduler,
)
from macro_sim.controllers.session import (
    AWAITING_HUMAN,
    ControlledSimulationSession,
)
from macro_sim.diagnostics.config_experiment import (
    apply_native_activation_scenario,
    population_scaled_new_game,
)
from macro_sim.diagnostics.policy_crisis_effects import (
    ACCOUNTING_METRICS,
    P4_SCENARIO_ID,
    P4_SEVERITY,
    _capture,
)
from macro_sim.diagnostics.policy_scenarios import (
    CRISIS_MANIFESTS,
    DEFAULT_P3_SEEDS,
    _schedule_tape,
)
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.native_backend import NativeSimulationSession
from macro_sim.rl.artifact import load_artifact_bundle
from macro_sim.rl.baselines import (
    HeuristicPolicy,
    PredictModelPolicy,
    RandomMaskedPolicy,
)
from macro_sim.rl.experiment import (
    EvaluationPlan,
    ExperimentSeeds,
    evaluate_policies,
)
from macro_sim.rl.native_envs import NativeFiscalStabilizationEnvFactory


P8_SCHEMA_VERSION = "policy-causality-p8-v2"
P8_LEVER = "benefit_income_floor"
P8_VALUE = 0.20
P8_POPULATION = 100_000
P8_WORKERS = 8
P8_SEED_JOBS = 4
P8_RL_EVALUATION_SEEDS = tuple(range(60_001, 60_009))
P8_RL_POLICY_SEED_SALT = 8_808
P8_RL_ARTIFACT = "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl"
P8_METRICS = (
    "metric.economy.gov_deficit_to_gdp",
    "metric.economy.income_gini",
    "metric.economy.na.production_reconciliation_residual",
    "metric.economy.poverty_rate",
    "metric.economy.real_output",
    "metric.economy.unemployment_rate",
    "metric.shock.active_count",
    "metric.source.m4.conservation_drift",
    "metric.source.m4.transfer_payments",
    "metric.source.m6.clearing_residual",
)
P8_OUTCOMES: Mapping[str, str] = {
    "metric.economy.poverty_rate": "post_burnin_mean",
    "metric.economy.unemployment_rate": "post_burnin_mean",
    "metric.economy.real_output": "cumulative",
    "metric.economy.income_gini": "post_burnin_mean",
    "metric.economy.gov_deficit_to_gdp": "post_burnin_mean",
    "metric.source.m4.transfer_payments": "cumulative",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (set, frozenset, tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        canonical_json(_jsonable(value)).encode("utf-8")
    ).hexdigest()


def _without_runtime(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_runtime(item)
            for key, item in value.items()
            if key != "elapsed_seconds"
        }
    if isinstance(value, (list, tuple)):
        return [_without_runtime(item) for item in value]
    return value


def _load(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    return json.loads(Path(source).read_text(encoding="utf-8"))


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
        json.dump(
            _jsonable(payload), handle, indent=2, sort_keys=True,
            ensure_ascii=True, allow_nan=False,
        )
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _p4_row(p4: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        item for item in p4["reports"]
        if item.get("lever") == P8_LEVER
    ]
    if len(matches) != 1:
        raise ValueError(f"P4 must contain exactly one {P8_LEVER} report")
    return matches[0]


def _p3_crisis(p3: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        item for item in p3["reports"]["crises"]
        if item.get("scenario_id") == P4_SCENARIO_ID
    ]
    if len(matches) != 1:
        raise ValueError("P3 must contain exactly one demand-recession report")
    return matches[0]


def build_p8_manifest(
    p3_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
    p7_source: str | Path | Mapping[str, Any],
    rl_artifact: str | Path,
) -> dict[str, Any]:
    p3 = _load(p3_source)
    p4 = _load(p4_source)
    p7 = _load(p7_source)
    artifact_path = Path(rl_artifact)
    errors: list[str] = []

    p7_upstream = p7.get("manifest", {}).get(
        "upstream_acceptance_hashes", {}
    )
    for stage, report in (("p3", p3), ("p4", p4)):
        expected = p7_upstream.get(f"{stage}_acceptance")
        observed = report.get("hashes", {}).get(f"{stage}_acceptance")
        if expected != observed:
            errors.append(f"P7 does not bind the supplied {stage.upper()} acceptance")

    accepted_crises = {
        item.get("scenario_id")
        for item in p3.get("reports", {}).get("crises", ())
        if item.get("accepted")
    }
    if accepted_crises != {P4_SCENARIO_ID}:
        errors.append("P8 requires the single frozen P3 demand-recession crisis")

    row = _p4_row(p4)
    if row.get("disposition") != "accepted_crisis_efficacy":
        errors.append("P8 delivery action is not accepted by frozen P4 evidence")
    meaningful = [
        arm for arm in row.get("arms", ())
        if arm.get("dose_class") == "meaningful"
    ]
    expected_actions = [{"lever": P8_LEVER, "value": P8_VALUE}]
    if len(meaningful) != 1 or meaningful[0].get("actions") != expected_actions:
        errors.append("P8 delivery action differs from the frozen P4 meaningful arm")

    lever = REGISTRY[P8_LEVER]
    expected_control = {
        "admin_weight": 1.0,
        "decision_group": "labor_and_welfare",
        "emergency": True,
        "emergency_implementation_lag": 1,
        "implementation_lag": 7,
        "min_hold_ticks": 91,
        "owner_role": "labor_social",
    }
    actual_control = {
        name: getattr(lever, name) for name in expected_control
    }
    if actual_control != expected_control:
        errors.append("P8 representative Controller metadata drifted")

    if not artifact_path.is_file():
        errors.append("P8 RL transfer artifact is missing")
        artifact_sha = None
    else:
        artifact_sha = _file_sha256(artifact_path)

    payload = {
        "schema_version": P8_SCHEMA_VERSION,
        "errors": errors,
        "upstream_acceptance_hashes": {
            "p3_acceptance": p3.get("hashes", {}).get("p3_acceptance"),
            "p4_acceptance": p4.get("hashes", {}).get("p4_acceptance"),
            "p7_acceptance": p7.get("hashes", {}).get("p7_acceptance"),
        },
        "scenario": {
            "scenario_id": P4_SCENARIO_ID,
            "severity": P4_SEVERITY,
            "population": P8_POPULATION,
            "seeds": list(DEFAULT_P3_SEEDS),
            "workers_per_session": P8_WORKERS,
            "concurrent_seed_jobs": P8_SEED_JOBS,
        },
        "action": {
            "lever": P8_LEVER,
            "value": P8_VALUE,
            "controller_contract": actual_control,
        },
        "delivery_branches": [
            "crisis_control",
            "free_immediate",
            "precommitted_regular",
            "emergency",
            "scheduled_regular",
            "delayed_regular",
            "missed_meeting",
            "human_scheduled",
        ],
        "decomposition": [
            "economic_effect",
            "regular_implementation_delay",
            "information_plus_emergency_implementation_delay",
            "scheduled_meeting_delay",
            "additional_meeting_delay",
            "missed_action",
            "human_transport_gap",
            "adjustment_and_administrative_cost",
        ],
        "metrics": list(P8_METRICS),
        "outcomes": dict(P8_OUTCOMES),
        "occupant_benchmark": {
            "artifact_path": str(artifact_path),
            "artifact_sha256": artifact_sha,
            "evaluation_seeds": list(P8_RL_EVALUATION_SEEDS),
            "policies": [
                "heuristic",
                "human_recorded_hold",
                "no_action",
                "random",
                "rl_transfer",
            ],
            "actual_human_performance_claim": False,
        },
    }
    payload["manifest_hash"] = _canonical_hash({
        key: value for key, value in payload.items()
        if key != "manifest_hash"
    })
    return payload


def _native_genesis(seed: int) -> tuple[Any, Any, NativeSimulationSession]:
    manifest = CRISIS_MANIFESTS[P4_SCENARIO_ID]
    new_game = population_scaled_new_game(
        population=P8_POPULATION,
        days=manifest.burn_in_days + manifest.horizon_days + 4,
        seed=seed,
        countries=manifest.countries,
    )
    native_spec = native_backend.build_native_new_game_spec(new_game)
    apply_native_activation_scenario(
        native_spec, scenario=manifest.activation_scenario,
    )
    session = NativeSimulationSession.create_from_native_spec(
        native_spec,
        worker_count=P8_WORKERS,
        history_capacity_frames=(
            manifest.burn_in_days + manifest.horizon_days + 8
        ),
    )
    session.advance(manifest.burn_in_days)
    return new_game, native_spec, session


def _crisis_tape(session: NativeSimulationSession) -> str:
    manifest = CRISIS_MANIFESTS[P4_SCENARIO_ID]
    return _schedule_tape(
        session,
        manifest,
        severity=P4_SEVERITY,
        start_tick=manifest.burn_in_days + 1,
    )


def _run_direct_branch(
    base: NativeSimulationSession, *, action: bool,
) -> dict[str, Any]:
    manifest = CRISIS_MANIFESTS[P4_SCENARIO_ID]
    started = time.perf_counter()
    session = base.clone()
    tape_hash = _crisis_tape(session)
    actions = (
        ({"economy_id": 0, "lever": P8_LEVER, "value": P8_VALUE},)
        if action else ()
    )
    session.advance(manifest.horizon_days, actions=actions)
    return {
        "delivery": "free_policy" if action else "none",
        "policy_applied": session.policy_values(0)[P8_LEVER] == (
            P8_VALUE if action else 0.0
        ),
        "accepted_tick": manifest.burn_in_days if action else None,
        "effective_tick": manifest.burn_in_days + 1 if action else None,
        "adjustment_cost": 0.0,
        "reserved_admin_cost": 0.0,
        "tape_hash": tape_hash,
        "context_audits": [],
        "run": _capture(
            session,
            t0=manifest.burn_in_days,
            manifest=manifest,
            metric_ids=P8_METRICS,
        ),
        "elapsed_seconds": time.perf_counter() - started,
    }


def _scheduler(*, delayed: bool = False) -> DecisionScheduler:
    if not delayed:
        return DecisionScheduler()
    calendars = dict(DEFAULT_CALENDARS)
    calendars["labor_and_welfare"] = CalendarSpec(
        period_ticks=91,
        offset_ticks=30,
        window_ticks=1,
        admin_capacity=18.0,
    )
    return DecisionScheduler(calendars=calendars)


def _context_audit(context: Any) -> dict[str, Any]:
    observation = context.observation.to_dict()
    releases = observation.get("releases", ())
    future = [
        item["series_id"] for item in releases
        if int(item["released_at_tick"]) > context.boundary_tick
    ]
    oracle = [
        item["series_id"] for item in releases
        if item.get("access_class") == "oracle"
        and item.get("missing_reason") != "access_denied"
    ]
    denied_oracle = [
        item["series_id"] for item in releases
        if item.get("access_class") == "oracle"
        and item.get("missing_reason") == "access_denied"
    ]
    bulletins = observation.get("shock_bulletins", ())
    future_bulletins = [
        item.get("shock_id") for item in bulletins
        if int(item.get("announcement_tick", context.boundary_tick))
        > context.boundary_tick
    ]
    return {
        "boundary_tick": context.boundary_tick,
        "context_id": context.context_id,
        "decision_group": context.decision_group,
        "emergency": context.emergency,
        "emergency_trigger": context.emergency_trigger,
        "observation_hash": _canonical_hash(observation),
        "observation_role": observation.get("role"),
        "release_count": len(releases),
        "future_release_ids": future,
        "oracle_release_ids": oracle,
        "denied_oracle_release_ids": denied_oracle,
        "future_bulletin_ids": future_bulletins,
        "permitted_levers": sorted(
            item.lever for item in context.permitted_actions if item.allowed
        ),
    }


def _record_scheduled_shock_input(
    world: NativeControlledWorld,
    controlled: ControlledSimulationSession,
) -> str:
    tape_hash = _crisis_tape(world.native_session)
    controlled.events.append(
        "shock_scheduled",
        "input",
        controlled.boundary_tick,
        controlled.phase,
        economy_id=0,
        actor="p8_audit",
        payload={
            "scenario_id": P4_SCENARIO_ID,
            "severity": P4_SEVERITY,
            "tape_hash": tape_hash,
        },
    )
    world.sync_controller_state(controlled)
    return tape_hash


def _proposal(context: Any) -> PolicyProposal:
    proposal_id = f"p8-human:{context.context_id}"
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=(PolicyAction(P8_LEVER, P8_VALUE),),
        reason="p8_recorded_human_action",
        based_on_policy_versions=dict(context.policy_versions),
    )


def _run_controlled_branch(
    base: NativeSimulationSession,
    new_game: Any,
    *,
    branch: str,
) -> dict[str, Any]:
    manifest = CRISIS_MANIFESTS[P4_SCENARIO_ID]
    started = time.perf_counter()
    native = base.clone()
    world = NativeControlledWorld(
        native,
        new_game.configs(),
        trade=bool(new_game.world["trade"]),
        capital=bool(new_game.world["capital"]),
        migration=bool(new_game.world["migration"]),
    )
    delayed = branch in {"precommitted_regular", "delayed_regular"}
    controlled = ControlledSimulationSession(
        world, scheduler=_scheduler(delayed=delayed), run_mode="batch",
    )
    action = (PolicyAction(P8_LEVER, P8_VALUE),)
    if branch == "precommitted_regular":
        occupant: Any = ScheduledOccupant({30: action})
    elif branch == "emergency":
        occupant = ScheduledOccupant({tick: action for tick in range(31, 61)})
    elif branch == "scheduled_regular":
        occupant = ScheduledOccupant({91: action})
    elif branch == "delayed_regular":
        occupant = ScheduledOccupant({121: action})
    elif branch == "missed_meeting":
        occupant = NullOccupant()
    elif branch == "human_scheduled":
        occupant = HumanQueueOccupant()
    else:
        raise ValueError(f"unknown P8 delivery branch {branch!r}")
    controlled.assign_seat(0, "labor_social", occupant, actor="p8_audit")
    tape_hash = _record_scheduled_shock_input(world, controlled)

    context_audits: list[dict[str, Any]] = []
    latest_decisions: dict[str, Any] = {}
    target_tick = controlled.boundary_tick + manifest.horizon_days
    while controlled.boundary_tick < target_tick:
        result = controlled.advance()
        context_audits.extend(_context_audit(item) for item in result.contexts)
        if result.status == AWAITING_HUMAN:
            for context_id in result.missing_context_ids:
                context = controlled._opened_contexts[context_id]
                if (
                    context.boundary_tick == 91
                    and not context.emergency
                    and context.decision_group == "labor_and_welfare"
                ):
                    controlled.submit_human_proposal(
                        _proposal(context), actor="recorded_human",
                    )
                else:
                    controlled.timeout_context(
                        context_id, actor="p8_timeout",
                    )
            result = controlled.advance()
        for decision in result.decisions:
            latest_decisions[decision.decision_id] = decision

    action_decisions = [
        item for item in latest_decisions.values()
        if item.adjustment_cost > 0.0
    ]
    accepted_ticks = [
        item.accepted_tick for item in action_decisions
        if item.accepted_tick is not None
    ]
    effective_ticks = [
        item.effective_tick for item in action_decisions
        if item.effective_tick is not None
    ]
    return {
        "delivery": "controller",
        "policy_applied": native.policy_values(0)[P8_LEVER] == (
            P8_VALUE if branch != "missed_meeting" else 0.0
        ),
        "accepted_tick": min(accepted_ticks) if accepted_ticks else None,
        "effective_tick": min(effective_ticks) if effective_ticks else None,
        "adjustment_cost": sum(
            item.adjustment_cost for item in action_decisions
        ),
        "reserved_admin_cost": sum(
            item.reserved_admin_cost for item in action_decisions
        ),
        "decision_statuses": sorted({
            item.status for item in latest_decisions.values()
        }),
        "tape_hash": tape_hash,
        "context_audits": context_audits,
        "controller_event_head": controlled.events.head_hash,
        "controller_event_count": len(controlled.events.events),
        "run": _capture(
            native,
            t0=manifest.burn_in_days,
            manifest=manifest,
            metric_ids=P8_METRICS,
        ),
        "elapsed_seconds": time.perf_counter() - started,
    }


def _p4_run_hash(p4_dir: Path, seed: int, *, control: bool) -> str:
    source = (
        p4_dir / "runs" / "controls" / str(seed) / "crisis.json"
        if control else
        p4_dir / "runs" / P8_LEVER / "arm_2" / str(seed)
        / "crisis-immediate.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    run = dict(payload["result"]["run"])
    for key in ("metric_series", "metric_summaries"):
        run[key] = {
            metric: value for metric, value in run[key].items()
            if metric in P8_METRICS
        }
    for key in ("metric_series_by_economy", "metric_summaries_by_economy"):
        run[key] = {
            economy_id: {
                metric: value for metric, value in metrics.items()
                if metric in P8_METRICS
            }
            for economy_id, metrics in run[key].items()
        }
    return _canonical_hash(run)


def _run_delivery_seed(
    *,
    seed: int,
    p3: Mapping[str, Any],
    p4_dir: Path,
    manifest_hash: str,
    source_revision: str,
    cache_dir: Path,
    resume: bool,
) -> dict[str, Any]:
    cache = cache_dir / f"{seed}.json"
    signature_payload = {
        "schema_version": P8_SCHEMA_VERSION,
        "manifest_hash": manifest_hash,
        "source_revision": source_revision,
        "seed": seed,
    }
    signature = _canonical_hash(signature_payload)
    if resume and cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        if payload.get("run_signature") == signature:
            return dict(payload["result"])

    started = time.perf_counter()
    new_game, _native_spec, base = _native_genesis(seed)
    checkpoint_hash = hashlib.sha256(base.checkpoint()).hexdigest()
    p3_crisis = _p3_crisis(p3)
    expected_checkpoints = {
        int(item["seed"]): str(item["sha256"])
        for item in p3_crisis["frozen_common_checkpoint_hashes"]
    }
    if checkpoint_hash != expected_checkpoints[seed]:
        raise RuntimeError(
            f"seed {seed}: P8 checkpoint differs from frozen P3"
        )

    branches = {
        "crisis_control": _run_direct_branch(base, action=False),
        "free_immediate": _run_direct_branch(base, action=True),
    }
    for branch in (
        "precommitted_regular",
        "emergency",
        "scheduled_regular",
        "delayed_regular",
        "missed_meeting",
        "human_scheduled",
    ):
        branches[branch] = _run_controlled_branch(
            base, new_game, branch=branch,
        )

    expected_tapes = tuple(p3_crisis["frozen_tape_hashes"][P4_SEVERITY])
    tape_hashes = {item["tape_hash"] for item in branches.values()}
    if len(expected_tapes) != 1 or tape_hashes != {expected_tapes[0]}:
        raise RuntimeError(f"seed {seed}: P8 tape differs from frozen P3")

    result = {
        "seed": seed,
        "checkpoint_sha256": checkpoint_hash,
        "branches": branches,
        "p4_exact_parity": {
            "crisis_control": (
                _canonical_hash(branches["crisis_control"]["run"])
                == _p4_run_hash(p4_dir, seed, control=True)
            ),
            "free_immediate": (
                _canonical_hash(branches["free_immediate"]["run"])
                == _p4_run_hash(p4_dir, seed, control=False)
            ),
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    _atomic_json(cache, {
        "schema_version": "policy-p8-delivery-cache-v1",
        "run_signature": signature,
        "signature": signature_payload,
        "result": result,
    })
    return result


def _outcome(branch: Mapping[str, Any], metric: str, statistic: str) -> float:
    return float(
        branch["run"]["metric_summaries"][metric][statistic]
    )


def _paired(values: Iterable[float]) -> dict[str, Any]:
    checked = tuple(float(item) for item in values)
    if not checked or not all(math.isfinite(item) for item in checked):
        raise ValueError("paired P8 values must be finite and non-empty")
    mean = fmean(checked)
    spread = stdev(checked) if len(checked) > 1 else 0.0
    half = 1.96 * spread / math.sqrt(len(checked))
    return {
        "pairs": len(checked),
        "mean_difference": mean,
        "confidence_low": mean - half,
        "confidence_high": mean + half,
        "minimum": min(checked),
        "maximum": max(checked),
        "positive_count": sum(item > 0.0 for item in checked),
        "negative_count": sum(item < 0.0 for item in checked),
        "zero_count": sum(item == 0.0 for item in checked),
    }


def reduce_delivery(seed_runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons = {
        "economic_effect": ("free_immediate", "crisis_control"),
        "regular_implementation_delay": (
            "precommitted_regular", "free_immediate",
        ),
        "information_plus_emergency_implementation_delay": (
            "emergency", "free_immediate",
        ),
        "scheduled_meeting_delay": (
            "scheduled_regular", "precommitted_regular",
        ),
        "additional_meeting_delay": (
            "delayed_regular", "scheduled_regular",
        ),
        "missed_action": ("missed_meeting", "free_immediate"),
        "human_transport_gap": (
            "human_scheduled", "scheduled_regular",
        ),
    }
    decomposition: dict[str, Any] = {}
    for metric, statistic in P8_OUTCOMES.items():
        decomposition[metric] = {
            name: _paired(
                _outcome(run["branches"][left], metric, statistic)
                - _outcome(run["branches"][right], metric, statistic)
                for run in seed_runs
            )
            for name, (left, right) in comparisons.items()
        }
        decomposition[metric]["statistic"] = statistic

    expected_ticks = {
        "free_immediate": 31,
        "precommitted_regular": 37,
        "emergency": 32,
        "scheduled_regular": 98,
        "delayed_regular": 128,
        "missed_meeting": None,
        "human_scheduled": 98,
    }
    tick_gate = all(
        run["branches"][branch]["effective_tick"] == expected
        for run in seed_runs
        for branch, expected in expected_ticks.items()
    )
    context_audits = [
        audit
        for run in seed_runs
        for branch in run["branches"].values()
        for audit in branch.get("context_audits", ())
    ]
    release_gate = all(
        not audit["future_release_ids"]
        and not audit["oracle_release_ids"]
        and not audit["future_bulletin_ids"]
        and audit["observation_role"] == "labor_social"
        for audit in context_audits
    )
    human_parity = all(
        _canonical_hash(run["branches"]["human_scheduled"]["run"])
        == _canonical_hash(run["branches"]["scheduled_regular"]["run"])
        for run in seed_runs
    )
    p4_parity = all(
        all(run["p4_exact_parity"].values()) for run in seed_runs
    )
    policy_gate = all(
        branch["policy_applied"]
        for run in seed_runs
        for branch in run["branches"].values()
    )
    integrity_gate = all(
        branch["run"]["finite"]
        and branch["run"]["integrity"]["passed"]
        for run in seed_runs
        for branch in run["branches"].values()
    )
    return {
        "decomposition": decomposition,
        "gates": {
            "effective_ticks_match_contract": tick_gate,
            "human_transport_exact_economic_parity": human_parity,
            "no_future_or_oracle_information": release_gate,
            "p4_free_policy_exact_parity": p4_parity,
            "policies_reached_expected_state": policy_gate,
            "native_integrity": integrity_gate,
        },
        "context_count": len(context_audits),
        "human_performance_claim": False,
        "human_path_scope": (
            "Recorded human ingress and timeout semantics only; no participant "
            "decision-quality claim."
        ),
    }


def run_occupant_evaluation(rl_artifact: str | Path) -> dict[str, Any]:
    artifact = load_artifact_bundle(rl_artifact)
    factory = NativeFiscalStabilizationEnvFactory(worker_count=P8_WORKERS)
    probe = factory(P8_RL_EVALUATION_SEEDS[0])
    try:
        context_match = (
            artifact.context_contract_hash == probe.context_codec.contract_hash
        )
        action_match = (
            artifact.action_contract_hash == probe.action_codec.contract_hash
        )
        _observation, info = probe.reset(seed=P8_RL_EVALUATION_SEEDS[0])
        context = info["context"]
        releases = context["observation"]["releases"]
        release_safe = all(
            item["released_at_tick"] <= context["boundary_tick"]
            and (
                item["access_class"] != "oracle"
                or item.get("missing_reason") == "access_denied"
            )
            for item in releases
        )
    finally:
        probe.close()
    if not context_match or not action_match:
        raise ValueError("P8 RL artifact vector contracts do not match native task")

    trained_contract = _jsonable(
        dict(artifact.metadata.get("environment_contract", {}))
    )
    evaluation_contract = _jsonable(factory.environment_contract)
    environment_match = (
        trained_contract == evaluation_contract
        and artifact.metadata.get("environment_contract_hash")
        == factory.environment_contract_hash
    )
    plan = EvaluationPlan(
        seeds=ExperimentSeeds(
            training=(),
            evaluation=P8_RL_EVALUATION_SEEDS,
            policy_seed_salt=P8_RL_POLICY_SEED_SALT,
        ),
        gamma_per_tick=0.999,
        deterministic_models=True,
        max_decisions=51,
        bootstrap_resamples=1_000,
        bootstrap_seed=8_808,
    )
    fiscal_parameters = {
        "inflation_ceiling": 0.01,
        "inflation_emergency": 0.02,
        "unemployment_enter": 0.10,
        "unemployment_exit": 0.06,
    }
    random = RandomMaskedPolicy(change_probability=0.25, max_changes=1)
    result = evaluate_policies(
        factory,
        {
            "heuristic": HeuristicPolicy(
                "fiscal_stabilizer", fiscal_parameters,
            ),
            "human_recorded_hold": HeuristicPolicy("hold"),
            "no_action": HeuristicPolicy("hold"),
            "random": random,
            "rl_transfer": PredictModelPolicy(artifact.policy),
        },
        plan,
    )
    summaries = {
        name: {
            metric: result.summary(name, metric).to_dict()
            for metric in (
                "discounted_return", "reward_per_tick", "total_reward",
            )
        }
        for name in result.policy_names
    }
    action_counts = {
        name: {
            status: sum(
                int(episode.decision_status_counts.get(status, 0))
                for episode in result.episodes_for(name)
            )
            for status in sorted({
                key
                for episode in result.episodes_for(name)
                for key in episode.decision_status_counts
            })
        }
        for name in result.policy_names
    }
    advantages = {
        name: _paired(
            candidate.discounted_return - baseline.discounted_return
            for candidate, baseline in zip(
                result.episodes_for(name),
                result.episodes_for("human_recorded_hold"),
                strict=True,
            )
        )
        for name in result.policy_names
        if name != "human_recorded_hold"
    }
    return {
        "artifact": {
            "path": str(Path(rl_artifact)),
            "sha256": artifact.artifact_sha256,
            "context_contract_hash": artifact.context_contract_hash,
            "action_contract_hash": artifact.action_contract_hash,
            "training_environment_contract_hash": artifact.metadata.get(
                "environment_contract_hash"
            ),
        },
        "environment": {
            "contract": evaluation_contract,
            "contract_hash": factory.environment_contract_hash,
            "evaluation_seeds": list(P8_RL_EVALUATION_SEEDS),
            "released_observation_gate": release_safe,
        },
        "contract_assessment": {
            "action_codec_match": action_match,
            "context_codec_match": context_match,
            "training_environment_match": environment_match,
            "classification": (
                "eligible_native_evaluation"
                if environment_match else
                "explicit_cross_backend_transfer_probe"
            ),
            "superiority_claim_allowed": environment_match,
        },
        "experiment": result.to_dict(),
        "summaries": summaries,
        "discounted_return_advantage_vs_human_recorded_hold": advantages,
        "decision_status_counts": action_counts,
        "policy_contracts": {
            "heuristic": {
                "rule_name": "fiscal_stabilizer",
                "parameters": fiscal_parameters,
            },
            "human_recorded_hold": {
                "source": "frozen_external_action_trace",
                "participant_data": False,
            },
            "no_action": {"rule_name": "hold"},
            "random": {
                "change_probability": random.change_probability,
                "max_changes": random.max_changes,
            },
            "rl_transfer": {
                "deterministic": True,
                "training_contract_mismatch_explicit": not environment_match,
            },
        },
        "actual_human_decision_quality_evaluated": False,
    }


def run_p8(
    *,
    artifact_dir: str | Path,
    source_revision: str,
    p3_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
    p7_source: str | Path | Mapping[str, Any],
    p4_artifact_dir: str | Path,
    rl_artifact: str | Path = P8_RL_ARTIFACT,
    resume: bool = True,
    progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    artifact_path = Path(artifact_dir)
    p3 = _load(p3_source)
    manifest = build_p8_manifest(
        p3_source, p4_source, p7_source, rl_artifact,
    )
    errors = list(manifest["errors"])
    seed_runs: list[dict[str, Any]] = []
    if not errors:
        with ThreadPoolExecutor(max_workers=P8_SEED_JOBS) as executor:
            futures = {
                executor.submit(
                    _run_delivery_seed,
                    seed=seed,
                    p3=p3,
                    p4_dir=Path(p4_artifact_dir),
                    manifest_hash=manifest["manifest_hash"],
                    source_revision=source_revision,
                    cache_dir=artifact_path / "runs",
                    resume=resume,
                ): seed
                for seed in DEFAULT_P3_SEEDS
            }
            for future in as_completed(futures):
                result = future.result()
                seed_runs.append(result)
                if progress is not None:
                    progress(int(result["seed"]))
        seed_runs.sort(key=lambda item: item["seed"])

    delivery = reduce_delivery(seed_runs) if seed_runs else None
    occupant = run_occupant_evaluation(rl_artifact) if not errors else None
    if delivery is not None:
        errors.extend(
            f"P8 delivery gate failed: {name}"
            for name, passed in delivery["gates"].items()
            if not passed
        )
    if occupant is not None:
        assessment = occupant["contract_assessment"]
        if not assessment["action_codec_match"]:
            errors.append("P8 RL action codec mismatch")
        if not assessment["context_codec_match"]:
            errors.append("P8 RL context codec mismatch")
        if not occupant["environment"]["released_observation_gate"]:
            errors.append("P8 occupant benchmark exposes future or oracle data")

    limitations = [
        "The recorded human paths validate ingress, authority, timing, and common-environment parity; they are not participant performance data.",
    ]
    if occupant is not None and not occupant["contract_assessment"][
        "training_environment_match"
    ]:
        limitations.append(
            "The shipped RL artifact has matching vector codecs but a pre-native training environment contract; its native run is a transfer probe and carries no superiority claim."
        )
    evidence = {
        "delivery": delivery,
        "occupant": occupant,
        "limitations": limitations,
        "seed_runs": _without_runtime(seed_runs),
    }
    payload = {
        "schema_version": P8_SCHEMA_VERSION,
        "status": (
            "accepted_with_explicit_limitations" if not errors else "failed"
        ),
        "source_revision": source_revision,
        "errors": errors,
        "limitations": limitations,
        "manifest": manifest,
        "delivery": delivery,
        "occupant_evaluation": occupant,
        "seed_runs": seed_runs,
        "counts": {
            "delivery_seeds": len(seed_runs),
            "delivery_branches_per_seed": 8,
            "delivery_native_paths": len(seed_runs) * 8,
            "occupant_evaluation_seeds": (
                len(P8_RL_EVALUATION_SEEDS) if occupant is not None else 0
            ),
            "occupant_policies": (
                len(occupant["experiment"]["policy_names"])
                if occupant is not None else 0
            ),
        },
        "protocol": {
            "native_economic_engine": True,
            "legacy_python_simulator_used": False,
            "python_role": "orchestration_reduction_and_institutional_state",
            "workers_per_native_session": P8_WORKERS,
            "concurrent_delivery_seed_jobs": P8_SEED_JOBS,
            "released_observations_only": True,
            "oracle_metrics_used_for_decisions": False,
            "actual_human_performance_claim": False,
            "rl_superiority_claim": bool(
                occupant is not None
                and occupant["contract_assessment"]["superiority_claim_allowed"]
            ),
        },
        "hashes": {
            "p8_manifest": manifest["manifest_hash"],
            "p8_evidence": _canonical_hash(evidence),
        },
    }
    payload["hashes"]["p8_acceptance"] = _canonical_hash({
        "status": payload["status"],
        "source_revision": source_revision,
        "errors": errors,
        "limitations": limitations,
        "manifest": payload["hashes"]["p8_manifest"],
        "evidence": payload["hashes"]["p8_evidence"],
        "protocol": payload["protocol"],
    })
    artifact_path.mkdir(parents=True, exist_ok=True)
    _atomic_json(artifact_path / "p8_report.json", payload)
    (artifact_path / "p8_report.md").write_text(
        render_p8_markdown(payload) + "\n", encoding="utf-8",
    )
    return payload


def render_p8_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy causality P8 report",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Institutional delivery",
        "",
    ]
    delivery = payload.get("delivery")
    if delivery is None:
        lines.append("- Not executed.")
    else:
        for name, passed in delivery["gates"].items():
            lines.append(f"- `{name}`: `{'passed' if passed else 'failed'}`")
        poverty = delivery["decomposition"][
            "metric.economy.poverty_rate"
        ]
        lines.extend([
            "",
            "### Poverty-rate timing decomposition",
            "",
            "| Component | Mean increment | 95% interval |",
            "|---|---:|---:|",
        ])
        for name, item in poverty.items():
            if name == "statistic":
                continue
            lines.append(
                f"| `{name}` | {item['mean_difference']:.8g} | "
                f"[{item['confidence_low']:.8g}, {item['confidence_high']:.8g}] |"
            )
    lines.extend([
        "",
        "## Occupant evaluation",
        "",
    ])
    occupant = payload.get("occupant_evaluation")
    if occupant is None:
        lines.append("- Not executed.")
    else:
        assessment = occupant["contract_assessment"]
        lines.extend([
            f"- Classification: `{assessment['classification']}`",
            f"- Context codec match: `{assessment['context_codec_match']}`",
            f"- Action codec match: `{assessment['action_codec_match']}`",
            f"- Training environment match: `{assessment['training_environment_match']}`",
            f"- Superiority claim allowed: `{assessment['superiority_claim_allowed']}`",
            "",
            "| Occupant | Mean discounted return | Mean reward/tick |",
            "|---|---:|---:|",
        ])
        for name in occupant["experiment"]["policy_names"]:
            discounted = occupant["summaries"][name]["discounted_return"]
            per_tick = occupant["summaries"][name]["reward_per_tick"]
            lines.append(
                f"| `{name}` | {discounted['mean']:.6g} | {per_tick['mean']:.6g} |"
            )
    lines.extend([
        "",
        "## Explicit limitations",
        "",
    ])
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.extend([
        "",
        "## Hashes",
        "",
        f"- Manifest: `{payload['hashes']['p8_manifest']}`",
        f"- Evidence: `{payload['hashes']['p8_evidence']}`",
        f"- Acceptance: `{payload['hashes']['p8_acceptance']}`",
    ])
    return "\n".join(lines)


__all__ = [
    "P8_LEVER",
    "P8_SCHEMA_VERSION",
    "P8_VALUE",
    "build_p8_manifest",
    "reduce_delivery",
    "render_p8_markdown",
    "run_occupant_evaluation",
    "run_p8",
]
