"""C1 acceptance gates for policy projection and World transactions.

These tests intentionally use the public controller/registry seams.  They pin the
properties that become safety-critical once a frontend, fuzz occupant, or RL policy
can submit arbitrary actions: preparation is pure, joint failures cannot leak a
partial commit, companion transitions are versioned, and zero-lag actions affect the
first engine read at their effective boundary.
"""
from __future__ import annotations

from dataclasses import asdict
import copy
import pickle

import pytest

from macro_sim.config import Config
from macro_sim.controllers.coordinator import SEATS, policy_key
from macro_sim.controllers.protocol import (
    DecisionContext,
    PendingDecision,
    PolicyAction,
    PolicyDecision,
    PolicyProposal,
)
from macro_sim.controllers.scheduler import DEFAULT_CALENDARS
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.controllers.transaction import (
    PolicyTransactionError,
    prepare_world_policy_transaction,
)
from macro_sim.core.policy_registry import (
    LEGACY_ALIASES,
    REGISTRY,
    Range,
    apply_action_batch,
    prepare_action_batch,
)
from macro_sim.world.world import World


def _cfg(seed: int = 0, **overrides) -> Config:
    params = dict(
        seed=seed,
        n_households=20,
        n_firms_c=15,
        n_firms_k=8,
        n_banks=2,
        demographics_population=120,
        n_ticks=100,
        government=True,
        central_bank=False,
    )
    params.update(overrides)
    return Config.v13(**params)


def _world(n: int = 3, *, coupled: bool = True) -> World:
    configs = [_cfg(seed=index) for index in range(n)]
    return World(
        configs,
        base_seed=1701,
        trade=coupled,
        capital=coupled,
        capital_mobility=0.2 if coupled else 0.0,
    )


def _synthetic_pending(
    session: ControlledSimulationSession,
    *,
    economy_id: int,
    seat: str,
    decision_group: str,
    actions: tuple[PolicyAction, ...],
    sequence: int,
    emergency: bool = True,
) -> PendingDecision:
    versions = {
        action.lever: session.policy_versions[policy_key(economy_id, action.lever)]
        for action in actions
    }
    context = DecisionContext(
        context_id=f"ctx:test:{economy_id}:{seat}:{sequence}",
        decision_window_id=f"window:test:{economy_id}:{seat}:{sequence}",
        economy_id=economy_id,
        seat=seat,
        decision_group=decision_group,
        boundary_tick=session.boundary_tick,
        expires_at_tick=session.boundary_tick,
        policy_versions=versions,
        observation={},
        emergency=emergency,
    )
    proposal = PolicyProposal(
        proposal_id=f"proposal:test:{sequence}",
        idempotency_key=f"idempotency:test:{sequence}",
        context_id=context.context_id,
        actions=actions,
        based_on_policy_versions=versions,
    )
    decision = PolicyDecision(
        decision_id=f"decision:test:{sequence}",
        proposal_id=proposal.proposal_id,
        status="accepted_pending",
        reason_code="accepted",
        accepted_tick=session.boundary_tick,
        effective_tick=session.boundary_tick,
        accepted_sequence=sequence,
    )
    return PendingDecision(decision=decision, proposal=proposal, context=context)


def _open_context(
    session: ControlledSimulationSession,
    economy_id: int,
    seat: str,
    decision_group: str,
    *,
    emergency: bool,
) -> DecisionContext:
    return session.coordinator.open_context(
        session,
        economy_id,
        seat,
        decision_group,
        observation={},
        expires_at_tick=session.boundary_tick,
        emergency=emergency,
        emergency_trigger="test" if emergency else None,
    )


def _submit(
    session: ControlledSimulationSession,
    context: DecisionContext,
    actions: tuple[PolicyAction, ...],
    *,
    suffix: str,
):
    versions = {
        action.lever: context.policy_versions[action.lever]
        for action in actions
    }
    proposal = PolicyProposal(
        proposal_id=f"proposal:{suffix}",
        idempotency_key=f"idempotency:{suffix}",
        context_id=context.context_id,
        actions=actions,
        based_on_policy_versions=versions,
    )
    return session.coordinator.submit(session, proposal, actor="test")


def test_registry_has_complete_c1_metadata_and_numeric_controls():
    assert len(REGISTRY) == 102
    numeric = {name: lever for name, lever in REGISTRY.items()
               if isinstance(lever.validation, Range)}
    assert len(numeric) == 79

    assert set(LEGACY_ALIASES.values()) <= set(REGISTRY)
    for name, lever in REGISTRY.items():
        assert lever.owner_role in SEATS, name
        assert lever.decision_group in DEFAULT_CALENDARS, name
        assert isinstance(lever.implementation_lag, int) and lever.implementation_lag >= 0
        assert isinstance(lever.min_hold_ticks, int) and lever.min_hold_ticks >= 0
        assert lever.cost_class in {"ordinary", "major", "regime_switch", "operational"}
        assert lever.admin_weight >= 0.0

    for name, lever in numeric.items():
        assert lever.control_scale is not None and lever.control_scale > 0.0, name
        assert lever.validation.max_step is not None and lever.validation.max_step > 0.0, name


def test_prepare_action_batch_is_pure_and_rejects_alias_duplicates():
    world = _world(1, coupled=False)
    econ = world.economies[0]
    before = pickle.dumps(econ, protocol=5)

    prepared = prepare_action_batch(
        econ,
        [("tax_income_rate", econ.policy.tax_income_rate + 0.01)],
        actor="test",
    )

    assert prepared.entries[0].name == "tax_income_rate"
    assert pickle.dumps(econ, protocol=5) == before

    alias = "firm_capital_haircut"
    canonical = LEGACY_ALIASES[alias]
    with pytest.warns(DeprecationWarning):
        with pytest.raises(ValueError, match="duplicate canonical policy lever"):
            prepare_action_batch(
                econ,
                [(alias, 0.31), (canonical, 0.31)],
                actor="test",
            )
    assert pickle.dumps(econ, protocol=5) == before


def test_joint_peg_conflict_prepare_leaves_all_live_state_untouched():
    session = ControlledSimulationSession(_world(3))
    left = _synthetic_pending(
        session,
        economy_id=0,
        seat="central_bank",
        decision_group="fx_operations",
        actions=(PolicyAction("peg_anchor", 2), PolicyAction("fx_regime", "peg")),
        sequence=0,
    )
    right = _synthetic_pending(
        session,
        economy_id=1,
        seat="central_bank",
        decision_group="fx_operations",
        actions=(PolicyAction("peg_anchor", 2), PolicyAction("fx_regime", "peg")),
        sequence=1,
    )

    world_before = pickle.dumps(session.world, protocol=5)
    versions_before = copy.deepcopy(session.policy_versions)
    last_effective_before = copy.deepcopy(session.last_effective_tick)
    admin_before = (
        copy.deepcopy(session.coordinator.admin_remaining),
        copy.deepcopy(session.coordinator.admin_reserved),
    )
    events_before = (session.events.canonical_bytes(), session.events.head_hash)
    pending_before = copy.deepcopy(session.pending)
    sequence_before = session.next_transaction_sequence
    fingerprint_before = session.policy_fingerprint

    with pytest.raises(PolicyTransactionError, match="at most ONE pegger"):
        prepare_world_policy_transaction(session, (left, right))

    # The projected World may fail; the complete live graph and every controller
    # ledger/version/event cursor remain byte-for-byte untouched.
    assert pickle.dumps(session.world, protocol=5) == world_before
    assert session.policy_versions == versions_before
    assert session.last_effective_tick == last_effective_before
    assert session.coordinator.admin_remaining == admin_before[0]
    assert session.coordinator.admin_reserved == admin_before[1]
    assert session.events.canonical_bytes() == events_before[0]
    assert session.events.head_hash == events_before[1]
    assert session.pending == pending_before
    assert session.next_transaction_sequence == sequence_before
    assert session.policy_fingerprint == fingerprint_before

    # Exercise the Coordinator's execution path as well.  Failure lifecycle events
    # are expected, but there must be no effective transaction/event, version bump,
    # retained cost, or mutation of the live engine graph.
    execution = ControlledSimulationSession(_world(3))
    contexts = (
        _open_context(execution, 0, "central_bank", "fx_operations", emergency=True),
        _open_context(execution, 1, "central_bank", "fx_operations", emergency=True),
    )
    capacity_before = (
        copy.deepcopy(execution.coordinator.admin_remaining),
        copy.deepcopy(execution.coordinator.admin_reserved),
    )
    for economy_id, context in enumerate(contexts):
        accepted = _submit(
            execution,
            context,
            (PolicyAction("peg_anchor", 2), PolicyAction("fx_regime", "peg")),
            suffix=f"joint-peg-{economy_id}",
        )
        assert accepted.status == "accepted_pending"

    engine_before_execution = pickle.dumps(execution.world, protocol=5)
    versions_before_execution = copy.deepcopy(execution.policy_versions)
    event_prefix = copy.deepcopy(execution.events.events)
    transaction_sequence = execution.next_transaction_sequence
    results = execution.coordinator.execute_due(execution)

    assert {item.status for item in results} == {"failed_at_execution"}
    assert pickle.dumps(execution.world, protocol=5) == engine_before_execution
    assert execution.policy_versions == versions_before_execution
    assert execution.coordinator.admin_remaining == capacity_before[0]
    assert execution.coordinator.admin_reserved == capacity_before[1]
    assert execution.next_transaction_sequence == transaction_sequence
    assert execution.events.events[:len(event_prefix)] == event_prefix
    execution_events = execution.events.events[len(event_prefix):]
    assert len(execution_events) == 2
    assert {event["event_type"] for event in execution_events} == {
        "decision_failed_at_execution"
    }
    assert not any(
        event["event_type"] == "policy_transaction_effective"
        for event in execution.events.events
    )


def test_out_of_range_sanctions_rejected_at_proposal_and_safe_at_execution():
    session = ControlledSimulationSession(_world(3))
    context = _open_context(
        session,
        0,
        "external_affairs",
        "trade_and_migration",
        emergency=True,
    )
    external_before = asdict(session.world.economies[0].external_policy)
    cache_before = copy.deepcopy(session.world.sanctions)
    versions_before = copy.deepcopy(session.policy_versions)
    admin_before = (
        copy.deepcopy(session.coordinator.admin_remaining),
        copy.deepcopy(session.coordinator.admin_reserved),
    )

    decision = _submit(
        session,
        context,
        (PolicyAction("sanctions_imposed_on", [99]),),
        suffix="bad-sanctions",
    )

    assert decision.status == "rejected"
    assert not session.pending
    assert asdict(session.world.economies[0].external_policy) == external_before
    assert session.world.sanctions == cache_before
    assert session.policy_versions == versions_before
    assert session.coordinator.admin_remaining == admin_before[0]
    assert session.coordinator.admin_reserved == admin_before[1]

    # Defense in depth: even a malformed pending object injected below the proposal
    # gateway fails on the isolated projection and cannot contaminate live caches.
    injected = _synthetic_pending(
        session,
        economy_id=0,
        seat="external_affairs",
        decision_group="trade_and_migration",
        actions=(PolicyAction("sanctions_imposed_on", [99]),),
        sequence=99,
    )
    live_before = pickle.dumps(session.world, protocol=5)
    event_before = (session.events.canonical_bytes(), session.events.head_hash)
    with pytest.raises(PolicyTransactionError, match="sanctions"):
        prepare_world_policy_transaction(session, (injected,))
    assert pickle.dumps(session.world, protocol=5) == live_before
    assert session.world.sanctions == cache_before
    assert session.policy_versions == versions_before
    assert (session.events.canonical_bytes(), session.events.head_hash) == event_before


def test_leaving_manual_records_and_versions_the_companion_clear():
    world = _world(1, coupled=False)
    apply_action_batch(
        world.economies[0],
        [("manual_policy_rate", 3.0e-4), ("monetary_regime", "manual")],
        actor="genesis-test",
    )
    session = ControlledSimulationSession(world)
    context = _open_context(
        session,
        0,
        "central_bank",
        "monetary_stance",
        emergency=True,
    )
    decision = _submit(
        session,
        context,
        (PolicyAction("monetary_regime", "taylor"),),
        suffix="leave-manual",
    )
    assert decision.status == "accepted_pending"
    assert decision.effective_tick == session.boundary_tick

    executed = session.coordinator.execute_due(session)

    assert executed[0].status == "effective"
    policy = session.world.economies[0].policy
    assert policy.monetary_regime == "taylor"
    assert policy.manual_policy_rate is None
    assert session.policy_versions[policy_key(0, "monetary_regime")] == 1
    assert session.policy_versions[policy_key(0, "manual_policy_rate")] == 1

    event = next(
        item for item in reversed(session.events.events)
        if item["event_type"] == "policy_transaction_effective"
    )
    changes = {item["lever"]: item for item in event["effective_changes"]}
    assert changes["monetary_regime"]["new"] == "taylor"
    assert changes["manual_policy_rate"]["new"] is None
    assert changes["manual_policy_rate"]["companion"] is True
    assert event["policy_versions_before"][policy_key(0, "manual_policy_rate")] == 0
    assert event["policy_versions_after"][policy_key(0, "manual_policy_rate")] == 1


def test_zero_lag_domestic_policy_is_seen_by_first_tick_read():
    session = ControlledSimulationSession(_world(1, coupled=False))
    context = _open_context(
        session,
        0,
        "central_bank",
        "monetary_stance",
        emergency=True,
    )
    target_rate = 3.0e-4
    decision = _submit(
        session,
        context,
        (
            PolicyAction("manual_policy_rate", target_rate),
            PolicyAction("monetary_regime", "manual"),
        ),
        suffix="zero-lag-domestic",
    )
    assert decision.effective_tick == session.boundary_tick
    session.coordinator.execute_due(session)

    # The effective state lands before tick 0.  Its first central-bank read in that
    # very tick must therefore emit the manual rate, not the genesis seed.
    records = session.world.step()
    assert records[0]["t"] == 0
    # The compact genesis record does not publish ``policy_rate`` yet; ``_rate`` is
    # the value consumed by the tick's credit/debt-service mechanisms.
    assert session.world.economies[0]._rate == pytest.approx(target_rate)


def test_zero_lag_external_policy_is_in_world_cache_before_first_tick_read():
    session = ControlledSimulationSession(_world(2))
    context = _open_context(
        session,
        0,
        "central_bank",
        "fx_operations",
        emergency=True,
    )
    target_control = 0.15
    decision = _submit(
        session,
        context,
        (PolicyAction("capital_control", target_control),),
        suffix="zero-lag-external",
    )
    assert decision.effective_tick == session.boundary_tick
    session.coordinator.execute_due(session)

    # The World transaction derives coupling caches as part of the same commit, so
    # no extra barrier/tick is needed before the external mechanism can read it.
    assert session.world.economies[0].external_policy.capital_control == pytest.approx(
        target_control
    )
    assert session.world.capital_control[0] == pytest.approx(target_control)
    assert session.world.t == session.boundary_tick == 0
    session.world.step()
    assert session.world.world_records[0]["t"] == 0
    assert session.world.capital_control[0] == pytest.approx(target_control)
