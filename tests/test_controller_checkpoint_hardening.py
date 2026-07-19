"""Continuation-identity and structural guards for controlled checkpoints."""
from __future__ import annotations

from functools import partial
from operator import add
import pickle
from dataclasses import replace
from types import SimpleNamespace

import pytest

from macro_sim.checkpoint import (
    load_checkpoint,
    read_header,
    save_checkpoint,
    session_digest,
)
from macro_sim.config import Config
from macro_sim.controllers.costs import CostWeights
from macro_sim.controllers.coordinator import policy_key
from macro_sim.controllers.occupants import HumanQueueOccupant
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.world import World


def _session() -> ControlledSimulationSession:
    cfg = Config.v13(
        seed=71,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=20,
        government=True,
    )
    return ControlledSimulationSession(World([cfg]))


def _clone(session: ControlledSimulationSession) -> ControlledSimulationSession:
    return pickle.loads(pickle.dumps(session, protocol=5))


class _CallbackOwner:
    def __init__(self, value: int) -> None:
        self.value = value

    def read(self) -> int:
        return self.value


def test_session_digest_is_roundtrip_stable_and_covers_all_continuation_state():
    source = _session()
    source.run(2)
    baseline = session_digest(source)
    assert session_digest(_clone(source)) == baseline

    changed = _clone(source)
    changed.world.economies[0].rng.random()
    assert session_digest(changed) != baseline

    changed = _clone(source)
    changed.engine_log_cursors[0] += 1
    assert session_digest(changed) != baseline

    changed = _clone(source)
    changed.coordinator.admin_replenished_at[
        (0, "treasury", "fiscal_stance")
    ] = changed.boundary_tick
    assert session_digest(changed) != baseline

    changed = _clone(source)
    changed.cost_spec.class_weights["ordinary"] = CostWeights(fixed=9.0, l1=1.0)
    assert session_digest(changed) != baseline

    changed = _clone(source)
    changed.policy_fingerprint = "tampered"
    assert session_digest(changed) != baseline


def test_semantic_digest_captures_bound_method_owner_and_function_closure_state():
    bound_left = SimpleNamespace(callback=_CallbackOwner(1).read)
    bound_right = SimpleNamespace(callback=_CallbackOwner(999).read)
    assert bound_left.callback() != bound_right.callback()
    assert session_digest(bound_left) != session_digest(bound_right)

    def callback(value: int):
        return lambda: value

    closure_left = SimpleNamespace(callback=callback(2))
    closure_right = SimpleNamespace(callback=callback(3))
    assert closure_left.callback() != closure_right.callback()
    assert session_digest(closure_left) != session_digest(closure_right)

    partial_left = SimpleNamespace(callback=partial(add, 1))
    partial_right = SimpleNamespace(callback=partial(add, 2))
    assert partial_left.callback(10) != partial_right.callback(10)
    assert session_digest(partial_left) != session_digest(partial_right)


def test_demographic_rng_graph_digest_is_stable_across_pickle_roundtrip():
    cfg = Config(
        n_households=20,
        n_firms=4,
        n_ticks=5,
        seed=73,
        demographics_enabled=True,
        demographics_population=20,
        demographic_lifecycle_consumption=True,
    )
    source = ControlledSimulationSession(World([cfg]))
    source.run(1)

    first = session_digest(source)
    restored = _clone(source)
    assert session_digest(restored) == first
    assert session_digest(_clone(restored)) == first


def test_controlled_checkpoint_header_and_load_cover_policy_fingerprint(tmp_path):
    source = _session()
    source.run(2)
    path = tmp_path / "controlled.msim"
    save_checkpoint(str(path), source, tick=source.boundary_tick)

    header = read_header(str(path))
    assert header["policy_fingerprint"] == source.policy_fingerprint
    loaded, sidecar, loaded_header = load_checkpoint(str(path))
    assert sidecar == {}
    assert loaded_header == header
    assert session_digest(loaded) == session_digest(source)


def test_checkpoint_metadata_cannot_override_integrity_header(tmp_path):
    source = _session()
    with pytest.raises(ValueError, match="reserved header fields.*session_digest"):
        save_checkpoint(
            str(tmp_path / "reserved-meta.msim"),
            source,
            tick=source.boundary_tick,
            meta={"session_digest": "forged"},
        )


def test_save_rejects_inconsistent_live_fingerprint_cursor_and_ticks(tmp_path):
    bad_fingerprint = _session()
    bad_fingerprint.policy_fingerprint = "not-the-world"
    with pytest.raises(ValueError, match="policy fingerprint"):
        save_checkpoint(
            str(tmp_path / "bad-fingerprint.msim"),
            bad_fingerprint,
            tick=bad_fingerprint.boundary_tick,
        )

    bad_cursor = _session()
    bad_cursor.engine_log_cursors[0] = 1
    with pytest.raises(ValueError, match="cursor.*out of bounds"):
        save_checkpoint(
            str(tmp_path / "bad-cursor.msim"),
            bad_cursor,
            tick=bad_cursor.boundary_tick,
        )

    bad_tick = _session()
    bad_tick.world.economies[0].t += 1
    with pytest.raises(ValueError, match="economy 0 tick"):
        save_checkpoint(
            str(tmp_path / "bad-tick.msim"),
            bad_tick,
            tick=bad_tick.boundary_tick,
        )


def _accepted_pending_session() -> ControlledSimulationSession:
    session = _session()
    context = session.coordinator.open_context(
        session,
        0,
        "treasury",
        "fiscal_stance",
        {},
        expires_at_tick=0,
    )
    lever = "gov_consumption_share"
    current = session.world.economies[0].policy.gov_consumption_share
    proposal = PolicyProposal(
        "proposal:checkpoint-index",
        "idempotency:checkpoint-index",
        context.context_id,
        (PolicyAction(lever, current + 0.001),),
        based_on_policy_versions={
            lever: session.coordinator.policy_versions[policy_key(0, lever)],
        },
    )
    decision = session.coordinator.submit(session, proposal, actor="test")
    assert decision.status == "accepted_pending"
    return session


def test_checkpoint_phase_current_missing_and_collected_indexes_are_guarded(tmp_path):
    waiting = _session()
    waiting.assign_seat(0, "treasury", HumanQueueOccupant())
    result = waiting.advance()
    assert result.status == "awaiting_human"
    save_checkpoint(
        str(tmp_path / "valid-waiting.msim"), waiting, tick=waiting.boundary_tick,
    )

    bad_phase = _clone(waiting)
    bad_phase.phase = "boundary_start"
    with pytest.raises(ValueError, match="boundary_start.*open context"):
        save_checkpoint(
            str(tmp_path / "bad-phase.msim"), bad_phase, tick=bad_phase.boundary_tick,
        )

    bad_current = _clone(waiting)
    bad_current.current_context_ids = bad_current.current_context_ids[:-1]
    with pytest.raises(ValueError, match="open/missing context"):
        save_checkpoint(
            str(tmp_path / "bad-current.msim"), bad_current,
            tick=bad_current.boundary_tick,
        )

    ready = _clone(waiting)
    for context_id in tuple(ready.missing_context_ids):
        ready.timeout_context(context_id)
    assert ready.phase == "ready_to_commit"
    save_checkpoint(str(tmp_path / "valid-ready.msim"), ready, tick=ready.boundary_tick)

    bad_collected = _clone(ready)
    bad_collected._collected.pop(next(iter(bad_collected._collected)))
    with pytest.raises(ValueError, match="ready_to_commit.*collection"):
        save_checkpoint(
            str(tmp_path / "bad-collected.msim"), bad_collected,
            tick=bad_collected.boundary_tick,
        )


def test_checkpoint_decision_pending_and_idempotency_indexes_are_guarded(tmp_path):
    source = _accepted_pending_session()
    save_checkpoint(str(tmp_path / "valid-pending.msim"), source, tick=0)

    bad_pending = _clone(source)
    pending = next(iter(bad_pending.coordinator.pending.values()))
    pending.decision = replace(pending.decision, status="effective")
    with pytest.raises(ValueError, match="pending/decision indexes"):
        save_checkpoint(str(tmp_path / "bad-pending.msim"), bad_pending, tick=0)

    bad_payload = _clone(source)
    key = next(iter(bad_payload.coordinator.idempotency_payload))
    bad_payload.coordinator.idempotency_payload[key] = "{}"
    with pytest.raises(ValueError, match="idempotency payload does not match"):
        save_checkpoint(str(tmp_path / "bad-idempotency.msim"), bad_payload, tick=0)

    bad_context = _clone(source)
    context_id = next(iter(bad_context.coordinator.proposal_for_context))
    bad_context.coordinator.proposal_for_context["context:unknown"] = (
        bad_context.coordinator.proposal_for_context.pop(context_id)
    )
    with pytest.raises(ValueError, match="references unknown context"):
        save_checkpoint(str(tmp_path / "bad-context.msim"), bad_context, tick=0)
