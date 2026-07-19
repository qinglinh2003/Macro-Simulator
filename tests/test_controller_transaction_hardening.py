"""Hardening regressions for immutable wire snapshots and sealed World commits."""
from __future__ import annotations

import pickle

import pytest

from macro_sim.config import Config
from macro_sim.controllers.coordinator import policy_key
from macro_sim.controllers.protocol import (
    DecisionContext,
    PendingDecision,
    PolicyAction,
    PolicyDecision,
    PolicyProposal,
    canonical_json,
)
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.controllers.transaction import (
    PolicyTransactionError,
    commit_world_policy_transaction,
    prepare_world_policy_transaction,
)
from macro_sim.world import World


def _session() -> ControlledSimulationSession:
    cfg = Config.v13(
        seed=281,
        n_households=20,
        n_firms_c=15,
        n_firms_k=8,
        n_banks=2,
        demographics_population=120,
        n_ticks=40,
        government=True,
    )
    return ControlledSimulationSession(
        World([cfg], trade=False, capital=False, capital_mobility=0.0)
    )


def _pending_tax_change(
    session: ControlledSimulationSession,
    *,
    sequence: int = 0,
) -> PendingDecision:
    lever = "tax_income_rate"
    economy = session.world.economies[0]
    target = float(economy.policy.tax_income_rate) + 0.01
    versions = {lever: session.policy_versions[policy_key(0, lever)]}
    context = DecisionContext(
        context_id=f"context:hardening:{sequence}",
        decision_window_id=f"window:hardening:{sequence}",
        economy_id=0,
        seat="treasury",
        decision_group="tax_and_transfers",
        boundary_tick=session.boundary_tick,
        expires_at_tick=session.boundary_tick,
        policy_versions=versions,
        observation={},
    )
    proposal = PolicyProposal(
        proposal_id=f"proposal:hardening:{sequence}",
        idempotency_key=f"idempotency:hardening:{sequence}",
        context_id=context.context_id,
        actions=(PolicyAction(lever, target),),
        based_on_policy_versions=versions,
    )
    decision = PolicyDecision(
        decision_id=f"decision:hardening:{sequence}",
        proposal_id=proposal.proposal_id,
        status="accepted_pending",
        reason_code="accepted",
        accepted_tick=session.boundary_tick,
        effective_tick=session.boundary_tick,
        accepted_sequence=sequence,
    )
    return PendingDecision(decision=decision, proposal=proposal, context=context)


def test_protocol_values_and_version_maps_are_detached_deeply_immutable_snapshots():
    raw_value = [{"targets": [1, 2]}]
    proposal_versions = {"x": 0}
    context_versions = {"x": 0}
    pending_policy = {"x": {"targets": [1]}}

    action = PolicyAction("x", raw_value)
    proposal = PolicyProposal(
        "proposal:immutable",
        "idempotency:immutable",
        "context:immutable",
        (action,),
        based_on_policy_versions=proposal_versions,
    )
    context = DecisionContext(
        "context:immutable",
        "window:immutable",
        0,
        "treasury",
        "fiscal_stance",
        0,
        0,
        context_versions,
        {},
        pending_policy=pending_policy,
    )

    raw_value[0]["targets"].append(99)
    proposal_versions["x"] = 99
    context_versions["x"] = 99
    pending_policy["x"]["targets"].append(99)

    assert action.to_dict()["value"] == [{"targets": [1, 2]}]
    assert dict(proposal.based_on_policy_versions) == {"x": 0}
    assert dict(context.policy_versions) == {"x": 0}
    assert context.to_dict()["pending_policy"] == {"x": {"targets": [1]}}

    with pytest.raises(TypeError):
        proposal.based_on_policy_versions["x"] = 2  # type: ignore[index]
    with pytest.raises(TypeError):
        context.policy_versions["x"] = 2  # type: ignore[index]
    with pytest.raises(TypeError):
        action.value[0]["targets"] = (7,)  # type: ignore[index]

    restored = pickle.loads(pickle.dumps((proposal, context), protocol=5))
    assert canonical_json(restored[0].to_dict()) == canonical_json(proposal.to_dict())
    assert canonical_json(restored[1].to_dict()) == canonical_json(context.to_dict())


def test_proposal_action_order_is_canonical_for_hashing_and_pickle():
    left = PolicyProposal(
        "proposal:ordered",
        "idempotency:ordered",
        "context:ordered",
        (PolicyAction("zeta", 2), PolicyAction("alpha", 1)),
        based_on_policy_versions={"zeta": 0, "alpha": 0},
    )
    right = PolicyProposal(
        "proposal:ordered",
        "idempotency:ordered",
        "context:ordered",
        (PolicyAction("alpha", 1), PolicyAction("zeta", 2)),
        based_on_policy_versions={"alpha": 0, "zeta": 0},
    )

    assert [action.lever for action in left.actions] == ["alpha", "zeta"]
    assert left.to_dict() == right.to_dict()
    assert canonical_json(left.to_dict()) == canonical_json(right.to_dict())
    assert pickle.loads(pickle.dumps(left, protocol=5)).to_dict() == left.to_dict()


def test_projection_tamper_before_commit_is_rejected_without_live_mutation():
    session = _session()
    pending = _pending_tax_change(session)
    prepared = prepare_world_policy_transaction(session, (pending,))
    live_before = pickle.dumps(session.world, protocol=5)
    versions_before = dict(session.policy_versions)
    sequence_before = session.next_transaction_sequence

    prepared.projected_world.economies[0].policy.tax_income_rate = 0.77

    with pytest.raises(PolicyTransactionError, match="projection changed"):
        commit_world_policy_transaction(session, prepared)

    assert pickle.dumps(session.world, protocol=5) == live_before
    assert dict(session.policy_versions) == versions_before
    assert session.next_transaction_sequence == sequence_before


def test_committed_world_is_detached_from_caller_held_projection():
    session = _session()
    pending = _pending_tax_change(session)
    expected = pending.proposal.actions[0].value
    prepared = prepare_world_policy_transaction(session, (pending,))

    changes = commit_world_policy_transaction(session, prepared)

    assert session.world.economies[0].policy.tax_income_rate == expected
    assert changes[0]["lever"] == "tax_income_rate"
    version_after = session.policy_versions[policy_key(0, "tax_income_rate")]
    fingerprint_after = session.policy_fingerprint

    prepared.projected_world.economies[0].policy.tax_income_rate = 0.77

    assert session.world.economies[0].policy.tax_income_rate == expected
    assert session.policy_versions[policy_key(0, "tax_income_rate")] == version_after
    assert session.policy_fingerprint == fingerprint_after


def test_policy_projection_excludes_metric_history_and_commit_reattaches_it():
    session = _session()
    economy = session.world.economies[0]
    economy.records.extend(({"tick": 1}, {"tick": 2}))
    session.world.world_records.append({"tick": 2})
    economy_history = economy.records
    world_history = session.world.world_records
    assert economy.state.records is economy_history

    prepared = prepare_world_policy_transaction(
        session, (_pending_tax_change(session),)
    )

    projected_economy = prepared.projected_world.economies[0]
    assert prepared.projected_world.world_records == []
    assert projected_economy.records == []
    assert projected_economy.state.records is projected_economy.records

    commit_world_policy_transaction(session, prepared)

    committed_economy = session.world.economies[0]
    assert session.world.world_records is world_history
    assert committed_economy.records is economy_history
    assert committed_economy.state.records is economy_history
    assert committed_economy.records == [{"tick": 1}, {"tick": 2}]


def test_corrupt_sealed_bytes_are_rejected_before_publication():
    session = _session()
    prepared = prepare_world_policy_transaction(session, (_pending_tax_change(session),))
    live_before = pickle.dumps(session.world, protocol=5)
    object.__setattr__(prepared, "sealed_world", prepared.sealed_world + b"corrupt")

    with pytest.raises(PolicyTransactionError, match="integrity"):
        commit_world_policy_transaction(session, prepared)

    assert pickle.dumps(session.world, protocol=5) == live_before
