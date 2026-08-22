"""Policy causality audit P1: native route and boundary verification."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from macro_sim.core.native_policy_routes import (
    ENGINE_ROUTE_DEFECT,
    NATIVE_POLICY_ROUTES,
    NATIVE_ROUTE_DEFECTS,
    ROUTED,
)
from macro_sim.core.policy_registry import (
    Bool,
    Choices,
    EconomyId,
    EconomySet,
    IntRange,
    NullableRange,
    Range,
    REGISTRY,
)
from macro_sim.diagnostics.config_experiment import population_scaled_new_game
from macro_sim.diagnostics.policy_contracts import build_p0_payload
from macro_sim.native_backend import NativeSimulationSession


ROOT = Path(__file__).resolve().parents[2]
CONTROL_CONTRACT = ROOT / "schemas/m11/control_contract.json"
P1_SCHEMA_VERSION = "policy-causality-p1-v1"
ACCEPTED_STATUSES = frozenset({"accepted", "accepted_with_explicit_defects"})


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, (frozenset, set)):
        return [_jsonable(item) for item in sorted(value)]
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _same_tree(left: Any, right: Any) -> bool:
    """Compare native result trees while treating colocated NaNs as equal."""
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            _same_tree(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _same_tree(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def _control_rows() -> dict[str, dict[str, Any]]:
    payload = json.loads(CONTROL_CONTRACT.read_text(encoding="utf-8"))
    return {row["name"]: row for row in payload["rows"]}


def build_route_ledger() -> list[dict[str, Any]]:
    rows = _control_rows()
    output = []
    for name in sorted(REGISTRY):
        lever = REGISTRY[name]
        route = NATIVE_POLICY_ROUTES[name]
        control = rows[name]
        output.append({
            "lever": name,
            "scope": lever.scope,
            "semantics": lever.semantics,
            "handler_id": lever.handler_id,
            "route_section": route.route_section,
            "route_field": route.route_field,
            "generated_route_section": control["route_section"],
            "generated_route_field": control["route_field"],
            "first_native_read_point": route.read_point,
            "source_path": route.source_path,
            "source_anchor": route.source_anchor,
            "read_phase": route.read_phase,
            "disposition": route.disposition,
            "defect_reason": route.defect_reason,
        })
    return output


def verify_p1_static() -> list[str]:
    errors: list[str] = []
    rows = _control_rows()
    registry_names = set(REGISTRY)
    if set(NATIVE_POLICY_ROUTES) != registry_names:
        errors.append("native read-point catalog does not exactly cover Registry")
    if set(rows) != registry_names:
        errors.append("generated native control contract does not exactly cover Registry")
    for name in sorted(registry_names & set(NATIVE_POLICY_ROUTES) & set(rows)):
        lever = REGISTRY[name]
        route = NATIVE_POLICY_ROUTES[name]
        control = rows[name]
        if route.route_section != control["route_section"]:
            errors.append(f"{name}: native route section disagrees with control contract")
        if route.route_field != control["route_field"]:
            errors.append(f"{name}: native route field disagrees with control contract")
        if lever.read_point != route.read_point:
            errors.append(f"{name}: Registry read point is not the audited native route")
        if route.disposition == ROUTED:
            if not route.source_path or not route.source_anchor or not route.read_phase:
                errors.append(f"{name}: routed lever has incomplete read-point evidence")
                continue
            source = ROOT / route.source_path
            if not source.is_file():
                errors.append(f"{name}: native source does not exist: {route.source_path}")
                continue
            if route.source_anchor not in source.read_text(encoding="utf-8"):
                errors.append(
                    f"{name}: native source anchor is absent: {route.source_anchor}"
                )
        elif route.disposition == ENGINE_ROUTE_DEFECT:
            if not route.defect_reason:
                errors.append(f"{name}: route defect has no explicit reason")
            if route.source_path or route.source_anchor or route.read_phase:
                errors.append(f"{name}: route defect incorrectly claims a read point")
        else:
            errors.append(f"{name}: unknown route disposition {route.disposition!r}")

    m8_source = (ROOT / "native/src/simulation/m8.cpp").read_text(encoding="utf-8")
    mechanism_sources = {
        path: path.read_text(encoding="utf-8")
        for path in (ROOT / "native/src/simulation").glob("*.cpp")
        if "checkpoint" not in path.name
    }
    if any(
        "fiscal_uses_national_accounts_gdp" in source
        for source in mechanism_sources.values()
    ):
        errors.append(
            "fiscal_uses_national_accounts_gdp is marked defective but now has a "
            "simulation read"
        )
    expected_validation_reads = {
        "mortgage_risk_weight": 2,
        "mortgage_minimum_capital_ratio": 3,
    }
    for field, expected in expected_validation_reads.items():
        total_reads = sum(
            source.count(field) for source in mechanism_sources.values()
        )
        if total_reads != expected or m8_source.count(f"policy.{field}") != expected:
            errors.append(
                f"{field} defective-route evidence changed; inspect for a new "
                "economic consumer"
            )
    return errors


def _alternate_value(name: str, current: Any) -> Any:
    lever = REGISTRY[name]
    validation = lever.validation
    if isinstance(validation, Bool):
        return not current
    if isinstance(validation, Choices):
        return next(value for value in validation.values if value != current)
    if isinstance(validation, EconomyId):
        return 1
    if isinstance(validation, EconomySet):
        return [1]
    if isinstance(validation, NullableRange):
        if current is not None:
            return None
        width = validation.hi - validation.lo
        return validation.lo + min(
            width,
            lever.control_scale or max(width * 0.1, 1.0e-6),
        )
    if isinstance(validation, IntRange):
        delta = max(1, round(lever.control_scale or 1.0))
        increase = int(current) + delta
        return increase if increase <= int(validation.hi) else int(current) - delta
    if isinstance(validation, Range):
        width = validation.hi - validation.lo
        delta = lever.control_scale or max(width * 0.1, 1.0e-6)
        increase = float(current) + delta
        return increase if increase <= validation.hi else float(current) - delta
    raise TypeError(f"unsupported validation for {name}: {type(validation).__name__}")


def build_full_route_batch(
    current_values: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Build one valid, non-noop action for every Registry lever."""
    if set(current_values) != set(REGISTRY):
        raise ValueError("current policy view does not exactly cover Registry")
    actions = {
        name: {"economy_id": 0, "lever": name, "value": _alternate_value(name, value)}
        for name, value in current_values.items()
    }
    # Linked and cross-field invariants are expressed as one atomic final state.
    actions["monetary_regime"]["value"] = "manual"
    actions["manual_policy_rate"]["value"] = 0.001
    actions["r_max"]["value"] = max(float(actions["r_max"]["value"]), 0.002)
    actions["fx_regime"]["value"] = "peg"
    actions["peg_anchor"]["value"] = 1
    ordered = tuple(actions[name] for name in sorted(actions))
    unchanged = [
        action["lever"]
        for action in ordered
        if _jsonable(action["value"]) == _jsonable(current_values[action["lever"]])
    ]
    if unchanged:
        raise AssertionError("route batch contains no-op levers: " + ", ".join(unchanged))
    return ordered


def _state_identity(session: NativeSimulationSession) -> dict[str, Any]:
    snapshot = session.native_snapshot()
    return {
        "tick": session.tick,
        "digest": int(snapshot["digest"]),
        "policy_generation": int(session.bridge.policy_generation),
        "policy_values": _jsonable(session.policy_values()),
    }


def _invalid_batch_is_atomic(
    session: NativeSimulationSession,
    actions: Iterable[Mapping[str, Any]],
) -> tuple[bool, str]:
    before = _state_identity(session)
    try:
        prepared = session.prepare_boundary(actions=tuple(actions), advance_ticks=1)
    except Exception as exc:  # native validation error is the expected result
        return _state_identity(session) == before, str(exc)
    session.abort_prepared_boundary(prepared)
    return False, "invalid batch unexpectedly prepared"


def run_p1_native_smoke(
    *,
    population: int = 100_000,
    seed: int = 3_801,
    workers: int = 8,
    countries: int = 3,
) -> dict[str, Any]:
    """Run the one-seed P1 route smoke entirely on the native C++ state owner."""
    started = time.perf_counter()
    spec = population_scaled_new_game(
        population=population,
        days=3,
        seed=seed,
        countries=countries,
    )
    session = NativeSimulationSession.create(
        spec,
        worker_count=workers,
        history_capacity_frames=5,
    )
    opening = _state_identity(session)
    actions = build_full_route_batch(session.policy_values())
    projected = session.projected_policy_values(actions)[0]
    projected_all_changed = all(
        _jsonable(projected[action["lever"]]) == _jsonable(action["value"])
        and _jsonable(projected[action["lever"]])
        != _jsonable(opening["policy_values"][action["lever"]])
        for action in actions
    )

    manual_atomic, manual_error = _invalid_batch_is_atomic(session, (
        {"lever": "tax_income_rate", "value": 0.7},
        {"lever": "monetary_regime", "value": "manual"},
    ))
    peg_atomic, peg_error = _invalid_batch_is_atomic(session, (
        {"lever": "tariff", "value": 0.2},
        {"lever": "fx_regime", "value": "peg"},
    ))

    prepared = session.prepare_boundary(actions=actions, advance_ticks=1)
    preview_tick = int(prepared.lease.preview["next_tick"])
    try:
        session.native_snapshot()
    except Exception as exc:
        lease_isolated = "prepared boundary lease is outstanding" in str(exc)
    else:
        lease_isolated = False
    session.abort_prepared_boundary(prepared)
    staged_immutable = _state_identity(session) == opening

    # Prepare the same batch again for publication after proving that aborting a
    # staged preview leaves the completed day byte-identical at the public seam.
    prepared = session.prepare_boundary(actions=actions, advance_ticks=1)
    previous = prepared.previous_envelope
    committed = session.commit_prepared_boundary(
        prepared,
        payload=_canonical_json({
            "actions_sha256": _sha256(_jsonable(actions)),
            "phase": "p1_full_route_batch",
            "schema_version": 1,
        }).encode("utf-8"),
        event_sequence=int(previous.event_sequence),
        release_cursor=int(previous.release_cursor),
        decision_versions=list(previous.decision_versions),
        effective_versions=list(previous.effective_versions),
    )
    effective = _state_identity(session)
    applied = {
        action["lever"]
        for action in actions
        if _jsonable(effective["policy_values"][action["lever"]])
        == _jsonable(action["value"])
    }

    checkpoint_started = time.perf_counter()
    checkpoint = session.checkpoint(
        objective_envelope=b'{"audit":"policy-p1"}',
    )
    checkpoint_seconds = time.perf_counter() - checkpoint_started
    restored_control, objective = NativeSimulationSession.restore(
        spec,
        checkpoint,
        worker_count=workers,
    )
    restored_noop, noop_objective = NativeSimulationSession.restore(
        spec,
        checkpoint,
        worker_count=workers,
    )
    restored_identity = _state_identity(restored_control)
    checkpoint_restored = (
        objective == b'{"audit":"policy-p1"}'
        and noop_objective == objective
        and restored_identity == effective
        and _state_identity(restored_noop) == effective
    )

    no_op_actions = tuple(
        {"economy_id": 0, "lever": name, "value": value}
        for name, value in sorted(effective["policy_values"].items())
    )
    generation_before_noop = int(restored_noop.bridge.policy_generation)
    original_result = session.advance(1)
    restored_result = restored_control.advance(1)
    noop_result = restored_noop.advance(1, actions=no_op_actions)
    checkpoint_replay_equal = (
        int(original_result["digest"]) == int(restored_result["digest"])
        and _same_tree(session.native_snapshot(), restored_control.native_snapshot())
        and _same_tree(session.maintained_metrics(), restored_control.maintained_metrics())
    )
    no_op_replay_equal = (
        int(restored_result["digest"]) == int(noop_result["digest"])
        and _same_tree(restored_control.native_snapshot(), restored_noop.native_snapshot())
        and _same_tree(
            restored_control.maintained_metrics(), restored_noop.maintained_metrics()
        )
    )
    no_op_generation_unchanged = (
        int(restored_noop.bridge.policy_generation) == generation_before_noop
    )

    checks = {
        "all_102_values_projected_non_noop": projected_all_changed,
        "manual_linked_rejection_is_atomic": manual_atomic,
        "peg_linked_rejection_is_atomic": peg_atomic,
        "prepared_lease_isolates_uncommitted_state": lease_isolated,
        "staging_keeps_completed_day_immutable": staged_immutable,
        "valid_batch_commits_at_next_day": (
            preview_tick == opening["tick"] + 1
            and effective["tick"] == opening["tick"] + 1
        ),
        "policy_generation_advances_once": (
            effective["policy_generation"] == opening["policy_generation"] + 1
        ),
        "all_102_values_effective": len(applied) == len(REGISTRY),
        "checkpoint_restores_exact_state": checkpoint_restored,
        "exact_noop_keeps_policy_generation": no_op_generation_unchanged,
        "checkpoint_continuation_matches_original": checkpoint_replay_equal,
        "exact_noop_trajectory_matches_control": no_op_replay_equal,
    }
    return {
        "schema_version": "policy-causality-p1-native-smoke-v1",
        "population_per_country": population,
        "countries": countries,
        "seed": seed,
        "workers": workers,
        "lever_count": len(REGISTRY),
        "applied_lever_count": len(applied),
        "action_sha256": _sha256(_jsonable(actions)),
        "opening": {
            key: value for key, value in opening.items() if key != "policy_values"
        },
        "effective": {
            key: value for key, value in effective.items() if key != "policy_values"
        },
        "original_replay_digest": int(original_result["digest"]),
        "restored_replay_digest": int(restored_result["digest"]),
        "noop_replay_digest": int(noop_result["digest"]),
        "checkpoint_bytes": len(checkpoint),
        "checkpoint_seconds": checkpoint_seconds,
        "elapsed_seconds": time.perf_counter() - started,
        "checks": checks,
        "manual_rejection": manual_error,
        "peg_rejection": peg_error,
        "memory_bytes": session.memory_usage(),
        "storage_counts": session.storage_counts(),
        "passed": all(checks.values()),
    }


def build_p1_payload(smoke: Mapping[str, Any] | None = None) -> dict[str, Any]:
    static_errors = verify_p1_static()
    ledger = build_route_ledger()
    routed = sum(item["disposition"] == ROUTED for item in ledger)
    defects = sum(item["disposition"] == ENGINE_ROUTE_DEFECT for item in ledger)
    dynamic_errors = []
    if smoke is not None and not smoke.get("passed", False):
        dynamic_errors.extend(
            f"native smoke failed: {name}"
            for name, passed in smoke.get("checks", {}).items()
            if not passed
        )
    errors = [*static_errors, *dynamic_errors]
    if errors or smoke is None:
        status = "incomplete"
    elif defects:
        status = "accepted_with_explicit_defects"
    else:
        status = "accepted"
    control = json.loads(CONTROL_CONTRACT.read_text(encoding="utf-8"))
    route_hash = _sha256(ledger)
    p0_root = build_p0_payload()["hashes"]["p0_root"]
    p1_root = _sha256({
        "p0_root": p0_root,
        "native_control_contract": control["semantic_sha256"],
        "route_ledger": route_hash,
        "defects": sorted(NATIVE_ROUTE_DEFECTS),
    })
    smoke_evidence = None
    acceptance_root = None
    if smoke is not None:
        smoke_evidence = _sha256({
            key: _jsonable(smoke[key])
            for key in (
                "schema_version",
                "population_per_country",
                "countries",
                "seed",
                "workers",
                "lever_count",
                "applied_lever_count",
                "action_sha256",
                "opening",
                "effective",
                "original_replay_digest",
                "restored_replay_digest",
                "noop_replay_digest",
                "checkpoint_bytes",
                "checks",
                "manual_rejection",
                "peg_rejection",
                "storage_counts",
                "passed",
            )
        })
        acceptance_root = _sha256({
            "p1_root": p1_root,
            "native_smoke_evidence": smoke_evidence,
        })
    return {
        "schema_version": P1_SCHEMA_VERSION,
        "status": status,
        "counts": {
            "levers": len(REGISTRY),
            "generated_native_routes": len(control["rows"]),
            "native_read_points": routed,
            "explicit_route_defects": defects,
            "static_errors": len(static_errors),
            "dynamic_errors": len(dynamic_errors),
        },
        "hashes": {
            "p0_root": p0_root,
            "native_control_contract": control["semantic_sha256"],
            "route_ledger": route_hash,
            "p1_root": p1_root,
            "native_smoke_evidence": smoke_evidence,
            "p1_acceptance": acceptance_root,
        },
        "errors": errors,
        "route_defects": sorted(NATIVE_ROUTE_DEFECTS),
        "routes": ledger,
        "native_smoke": _jsonable(smoke) if smoke is not None else None,
    }


def render_p1_markdown(payload: Mapping[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Policy causality audit P1 route ledger",
        "",
        f"Status: **{payload['status']}**",
        "",
        f"P1 root: `{payload['hashes']['p1_root']}`",
        "",
    ]
    if payload["hashes"]["p1_acceptance"] is not None:
        lines.extend([
            f"P1 acceptance: `{payload['hashes']['p1_acceptance']}`",
            "",
        ])
    lines.extend([
        "## Counts",
        "",
        f"- Registry levers: {counts['levers']}",
        f"- Routed native read points: {counts['native_read_points']}",
        f"- Explicit route defects: {counts['explicit_route_defects']}",
        f"- Static errors: {counts['static_errors']}",
        f"- Dynamic errors: {counts['dynamic_errors']}",
        "",
    ])
    smoke = payload["native_smoke"]
    if smoke is not None:
        lines.extend([
            "## Native smoke",
            "",
            f"- Population per economy: {smoke['population_per_country']}",
            f"- Economies: {smoke['countries']}",
            f"- Seed: {smoke['seed']}",
            f"- Engine workers: {smoke['workers']}",
            f"- Applied levers: {smoke['applied_lever_count']}",
            f"- Checkpoint bytes: {smoke['checkpoint_bytes']}",
            f"- Passed: {smoke['passed']}",
            "",
            "### Checks",
            "",
        ])
        for name, passed in smoke["checks"].items():
            lines.append(f"- `{name}`: {passed}")
        lines.extend(["", "## Explicit defects", ""])
    else:
        lines.extend(["## Explicit defects", ""])
    for name in payload["route_defects"]:
        route = NATIVE_POLICY_ROUTES[name]
        lines.append(f"- `{name}`: {route.defect_reason}")
    lines.extend(["", "## Routes", ""])
    for item in payload["routes"]:
        lines.append(
            f"- `{item['lever']}`: {item['disposition']}; "
            f"`{item['first_native_read_point']}`"
        )
    return "\n".join(lines) + "\n"
