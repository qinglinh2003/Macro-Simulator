"""Coordinator hardening regressions for adversarial and joint policy flows."""
from __future__ import annotations

import copy
from dataclasses import replace
import pickle

import pytest

from macro_sim.checkpoint import save_checkpoint
from macro_sim.config import Config
from macro_sim.controllers.coordinator import policy_key
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
from macro_sim.controllers.occupants import RandomFuzzOccupant
from macro_sim.controllers.scheduler import CalendarSpec, DecisionScheduler
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.core.policy_control_specs import CONTROL_SPECS
from macro_sim.core.policy_registry import REGISTRY, apply_action_batch, prepare_action_batch
from macro_sim.world import World


def _cfg(seed: int = 0, **overrides) -> Config:
    values = dict(
        seed=seed,
        n_households=20,
        n_firms_c=15,
        n_firms_k=8,
        n_banks=2,
        n_ticks=80,
        government=True,
    )
    values.update(overrides)
    return Config.v13(**values)


def _world(
    n: int = 3,
    *,
    peg: bool = False,
    peg_economy: int = 0,
    peg_anchor: int | None = None,
) -> World:
    return World(
        [_cfg(index) for index in range(n)],
        base_seed=713,
        trade=True,
        capital=True,
        capital_mobility=0.2,
        peg=peg,
        peg_economy=peg_economy,
        peg_anchor=peg_anchor,
    )


def _context(
    session: ControlledSimulationSession,
    economy_id: int,
    seat: str,
    group: str,
    *,
    emergency: bool = False,
):
    return session.coordinator.open_context(
        session,
        economy_id,
        seat,
        group,
        observation={},
        expires_at_tick=session.boundary_tick,
        emergency=emergency,
        emergency_trigger="test" if emergency else None,
    )


def _proposal(
    context,
    proposal_id: str,
    actions,
    *,
    supersedes: str | None = None,
) -> PolicyProposal:
    return PolicyProposal(
        proposal_id=proposal_id,
        idempotency_key=proposal_id,
        context_id=context.context_id,
        actions=tuple(actions),
        reason="hardening_test",
        based_on_policy_versions=dict(context.policy_versions),
        supersedes_proposal_id=supersedes,
    )


def _submit(
    session: ControlledSimulationSession,
    context,
    proposal_id: str,
    actions,
    *,
    supersedes: str | None = None,
):
    proposal = _proposal(
        context, proposal_id, actions, supersedes=supersedes,
    )
    return proposal, session.coordinator.submit(session, proposal, actor="test")


def test_malformed_dynamic_references_reject_stably_and_retry_idempotently():
    session = ControlledSimulationSession(_world())
    sanctions_context = _context(
        session, 0, "external_affairs", "trade_and_migration", emergency=True,
    )
    anchor_context = _context(
        session, 0, "central_bank", "fx_operations", emergency=True,
    )
    world_before = pickle.dumps(session.world, protocol=5)
    versions_before = dict(session.policy_versions)
    admin_before = (
        copy.deepcopy(session.coordinator.admin_remaining),
        copy.deepcopy(session.coordinator.admin_reserved),
    )

    cases = (
        (sanctions_context, "sanctions-none", "sanctions_imposed_on", None),
        (sanctions_context, "sanctions-string", "sanctions_imposed_on", ["1"]),
        (sanctions_context, "sanctions-bool", "sanctions_imposed_on", [True]),
        (sanctions_context, "sanctions-negative", "sanctions_imposed_on", [-1]),
        (sanctions_context, "sanctions-large", "sanctions_imposed_on", [99]),
        (anchor_context, "anchor-string", "peg_anchor", "1"),
        (anchor_context, "anchor-bool", "peg_anchor", True),
        (anchor_context, "anchor-self", "peg_anchor", 0),
        (anchor_context, "anchor-large", "peg_anchor", 99),
    )
    for context, proposal_id, lever, value in cases:
        proposal = _proposal(
            context, proposal_id, (PolicyAction(lever, value),),
        )
        event_count = len(session.events.events)
        decision = session.coordinator.submit(session, proposal, actor="adversary")
        retry = session.coordinator.submit(session, proposal, actor="adversary")

        assert decision.status == "rejected"
        assert decision.reason_code.startswith("dynamic_reference:")
        assert retry == decision
        # One canonical input plus one derived rejection; the retry is inert.
        assert len(session.events.events) == event_count + 2

    assert not session.pending
    assert pickle.dumps(session.world, protocol=5) == world_before
    assert session.policy_versions == versions_before
    assert session.coordinator.admin_remaining == admin_before[0]
    assert session.coordinator.admin_reserved == admin_before[1]


def test_same_tick_peg_handoff_is_one_joint_atomic_transaction():
    session = ControlledSimulationSession(
        _world(peg=True, peg_economy=0, peg_anchor=2),
    )
    exit_context = _context(
        session, 0, "central_bank", "fx_operations", emergency=True,
    )
    _exit_proposal, exit_decision = _submit(
        session,
        exit_context,
        "peg-exit-0",
        (PolicyAction("fx_regime", "float"),),
    )
    enter_context = _context(
        session, 1, "central_bank", "fx_operations", emergency=True,
    )
    _enter_proposal, enter_decision = _submit(
        session,
        enter_context,
        "peg-enter-1",
        (PolicyAction("peg_anchor", 2), PolicyAction("fx_regime", "peg")),
    )

    assert exit_decision.status == enter_decision.status == "accepted_pending"
    assert exit_decision.effective_tick == enter_decision.effective_tick == 0
    results = session.coordinator.execute_due(session)

    assert [item.status for item in results] == ["effective", "effective"]
    assert session.world.economies[0].external_policy.fx_regime == "float"
    assert session.world.economies[1].external_policy.fx_regime == "peg"
    assert session.world.economies[1].external_policy.peg_anchor == 2
    assert session.policy_versions[policy_key(0, "fx_regime")] == 1
    assert session.policy_versions[policy_key(1, "fx_regime")] == 1
    assert session.policy_versions[policy_key(1, "peg_anchor")] == 1
    effective = [
        event for event in session.events.events
        if event["event_type"] == "policy_transaction_effective"
    ]
    assert len(effective) == 1
    assert set(effective[0]["payload"]["decision_ids"]) == {
        exit_decision.decision_id, enter_decision.decision_id,
    }
    # The legacy accessor must select the new active peg after the handoff, not
    # the retained orderly-exit state of economy 0.
    assert session.world.peg_economy == 1
    assert session.world.peg_anchor == 2
    for economy in session.world.economies:
        economy.ledger.assert_conserved()
        economy.ledger.assert_non_negative()


def test_joint_conflict_rejects_ambiguous_peggers_but_commits_safe_candidate():
    session = ControlledSimulationSession(_world())
    peg_decisions = []
    for economy_id in (0, 1):
        context = _context(
            session, economy_id, "central_bank", "fx_operations", emergency=True,
        )
        _proposal_used, decision = _submit(
            session,
            context,
            f"conflicting-peg-{economy_id}",
            (PolicyAction("peg_anchor", 2), PolicyAction("fx_regime", "peg")),
        )
        assert decision.status == "accepted_pending"
        peg_decisions.append(decision)

    safe_context = _context(
        session, 2, "central_bank", "monetary_stance", emergency=True,
    )
    _safe_proposal, safe_decision = _submit(
        session,
        safe_context,
        "safe-manual-rate",
        (
            PolicyAction("manual_policy_rate", 3.0e-4),
            PolicyAction("monetary_regime", "manual"),
        ),
    )
    results = session.coordinator.execute_due(session)
    by_id = {item.decision_id: item for item in results}

    assert all(
        by_id[item.decision_id].status == "failed_at_execution"
        for item in peg_decisions
    )
    assert all(
        by_id[item.decision_id].reason_code == "joint_world_conflict"
        for item in peg_decisions
    )
    assert by_id[safe_decision.decision_id].status == "effective"
    assert session.world.economies[2].policy.monetary_regime == "manual"
    assert session.world.economies[2].policy.manual_policy_rate == pytest.approx(3.0e-4)
    assert not session.world.peg_states
    effective = [
        event for event in session.events.events
        if event["event_type"] == "policy_transaction_effective"
    ]
    assert len(effective) == 1
    assert effective[0]["payload"]["decision_ids"] == [safe_decision.decision_id]


def test_cross_context_supersede_is_atomic_refunded_and_idempotent():
    scheduler = DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(100, admin_capacity=5.0),
            "emergency": CalendarSpec(100, admin_capacity=5.0),
        },
        triggers=(),
    )
    session = ControlledSimulationSession(World([_cfg()]), scheduler=scheduler)
    current = session.world.economies[0].policy.gov_deficit_target
    regular = _context(session, 0, "treasury", "fiscal_stance")
    first_proposal, first = _submit(
        session,
        regular,
        "first-fiscal",
        (PolicyAction("gov_deficit_target", current + 0.005),),
    )
    assert first.status == "accepted_pending"

    emergency = _context(
        session, 0, "treasury", "emergency", emergency=True,
    )
    masked = next(
        item for item in emergency.permitted_actions
        if item.lever == "gov_deficit_target"
    )
    assert not masked.allowed and masked.reason_code == "pending_conflict"

    ledgers_before_mismatch = (
        copy.deepcopy(session.coordinator.admin_remaining),
        copy.deepcopy(session.coordinator.admin_reserved),
    )
    _mismatch_proposal, mismatch = _submit(
        session,
        emergency,
        "different-lever-replacement",
        (PolicyAction(
            "gov_consumption_share",
            session.world.economies[0].policy.gov_consumption_share + 0.005,
        ),),
        supersedes=first_proposal.proposal_id,
    )
    assert mismatch.status == "rejected"
    assert mismatch.reason_code == "supersede_lever_mismatch"
    assert session.pending[first.decision_id].status == "accepted_pending"
    assert session.coordinator.admin_remaining == ledgers_before_mismatch[0]
    assert session.coordinator.admin_reserved == ledgers_before_mismatch[1]

    ledgers_before_bad = (
        copy.deepcopy(session.coordinator.admin_remaining),
        copy.deepcopy(session.coordinator.admin_reserved),
    )
    _bad_proposal, bad = _submit(
        session,
        emergency,
        "bad-replacement",
        (PolicyAction("gov_deficit_target", current + 0.10),),
        supersedes=first_proposal.proposal_id,
    )
    assert bad.status == "rejected"
    assert "max_step" in bad.reason_code
    assert session.pending[first.decision_id].status == "accepted_pending"
    assert session.coordinator.admin_remaining == ledgers_before_bad[0]
    assert session.coordinator.admin_reserved == ledgers_before_bad[1]

    replacement, second = _submit(
        session,
        emergency,
        "good-replacement",
        (PolicyAction("gov_deficit_target", current + 0.01),),
        supersedes=first_proposal.proposal_id,
    )
    assert second.status == "accepted_pending"
    assert second.effective_tick == 1
    assert session.pending[first.decision_id].status == "superseded"
    assert session.coordinator.decisions[first.decision_id].status == "superseded"
    assert session.coordinator.admin_remaining[(0, "treasury", "fiscal_stance")] \
        == pytest.approx(5.0)
    assert session.coordinator.admin_reserved[(0, "treasury", "fiscal_stance")] \
        == pytest.approx(0.0)
    assert session.coordinator.admin_remaining[(0, "treasury", "emergency")] \
        == pytest.approx(5.0 - second.reserved_admin_cost)
    assert session.coordinator.admin_reserved[(0, "treasury", "emergency")] \
        == pytest.approx(second.reserved_admin_cost)

    state_before_retry = (
        copy.deepcopy(session.coordinator.admin_remaining),
        copy.deepcopy(session.coordinator.admin_reserved),
        len(session.events.events),
        session.events.head_hash,
    )
    retry = session.coordinator.submit(session, replacement, actor="test")
    assert retry == second
    assert session.coordinator.admin_remaining == state_before_retry[0]
    assert session.coordinator.admin_reserved == state_before_retry[1]
    assert len(session.events.events) == state_before_retry[2]
    assert session.events.head_hash == state_before_retry[3]


def test_submission_validates_max_step_against_projected_effective_state():
    world = World([_cfg()])
    apply_action_batch(
        world.economies[0],
        (("manual_policy_rate", 3.0e-4), ("monetary_regime", "manual")),
        actor="genesis_test",
    )
    session = ControlledSimulationSession(world)
    leave_context = _context(
        session, 0, "central_bank", "monetary_stance",
    )
    _leave_proposal, leave = _submit(
        session,
        leave_context,
        "leave-manual",
        (PolicyAction("monetary_regime", "taylor"),),
    )
    assert leave.status == "accepted_pending" and leave.effective_tick == 1

    # Advance tick 0 without executing the boundary-1 pending decision.
    assert session.advance().status == "advanced"
    assert session.boundary_tick == 1
    assert session.world.economies[0].policy.manual_policy_rate == pytest.approx(3.0e-4)
    restage_context = _context(
        session, 0, "central_bank", "monetary_stance",
    )
    restaged_target = 0.005
    assert abs(restaged_target - 3.0e-4) > CONTROL_SPECS["manual_policy_rate"].max_step

    _restage_proposal, restage = _submit(
        session,
        restage_context,
        "restage-after-clear",
        (PolicyAction("manual_policy_rate", restaged_target),),
    )

    # The projected state is Taylor after the earlier transition, so a rate may
    # not be staged by itself.  This preserves manual <=> non-null rate at every
    # committed boundary and closes the old max-step bypass.
    assert restage.status == "rejected"
    execution = session.coordinator.execute_due(session)
    assert [item.status for item in execution] == ["effective"]
    assert session.world.economies[0].policy.monetary_regime == "taylor"
    assert session.world.economies[0].policy.manual_policy_rate is None


def test_minimal_peg_conflict_rejects_both_rivals_and_their_orphan_dependency():
    world = _world()
    apply_action_batch(
        world.economies[2],
        (("manual_policy_rate", 3.0e-4), ("monetary_regime", "manual")),
        actor="genesis_test",
    )
    session = ControlledSimulationSession(world)
    entrant_a = _context(
        session, 2, "central_bank", "fx_operations", emergency=True,
    )
    entrant_c = _context(
        session, 1, "central_bank", "fx_operations", emergency=True,
    )
    dependent_b = _context(
        session, 2, "central_bank", "monetary_stance", emergency=True,
    )
    _pa, a = _submit(
        session,
        entrant_a,
        "entrant-a-with-rate-clear",
        (
            PolicyAction("monetary_regime", "taylor"),
            PolicyAction("peg_anchor", 0),
            PolicyAction("fx_regime", "peg"),
        ),
    )
    _pc, c = _submit(
        session,
        entrant_c,
        "entrant-c",
        (PolicyAction("peg_anchor", 0), PolicyAction("fx_regime", "peg")),
    )
    _pb, b = _submit(
        session,
        dependent_b,
        "depends-on-a-rate-clear",
        (PolicyAction("manual_policy_rate", 0.005),),
    )
    assert [a.status, c.status, b.status] == [
        "accepted_pending", "accepted_pending", "rejected",
    ]

    results = session.coordinator.execute_due(session)
    by_id = {item.decision_id: item for item in results}
    assert by_id[a.decision_id].status == "failed_at_execution"
    assert by_id[c.decision_id].status == "failed_at_execution"
    assert b.reason_code is not None
    assert session.world.economies[2].policy.monetary_regime == "manual"
    assert session.world.economies[2].policy.manual_policy_rate == pytest.approx(3.0e-4)
    assert not session.world.peg


def test_projected_prerequisite_version_rejects_guaranteed_stale_proposal():
    session = ControlledSimulationSession(World([_cfg(omo=False)]))
    enable_context = _context(
        session, 0, "central_bank", "liquidity_operations",
    )
    _enable_proposal, enable = _submit(
        session,
        enable_context,
        "enable-omo-next-boundary",
        (PolicyAction("omo", True),),
    )
    assert enable.status == "accepted_pending" and enable.effective_tick == 1
    session.advance()
    assert session.boundary_tick == 1
    assert session.world.economies[0].policy.omo is False

    dependent_context = _context(
        session, 0, "central_bank", "liquidity_operations",
    )
    indexed = next(
        item for item in dependent_context.permitted_actions
        if item.lever == "omo_index_deposits"
    )
    assert indexed.allowed
    _dependent_proposal, dependent = _submit(
        session,
        dependent_context,
        "doomed-omo-dependent",
        (PolicyAction("omo_index_deposits", False),),
    )
    assert dependent.status == "rejected"
    assert dependent.reason_code == "stale_projected_prerequisite_version"
    assert session.pending[enable.decision_id].status == "accepted_pending"


def test_large_peg_conflict_still_executes_obviously_unrelated_safe_decision():
    world = World([_cfg(seed=100 + idx) for idx in range(13)], couple=True)
    session = ControlledSimulationSession(world)
    entrants = []
    for economy_id in range(12):
        context = _context(
            session, economy_id, "central_bank", "fx_operations", emergency=True,
        )
        _proposal, decision = _submit(
            session,
            context,
            f"large-peg-entrant-{economy_id}",
            (
                PolicyAction("peg_anchor", 12),
                PolicyAction("fx_regime", "peg"),
            ),
        )
        assert decision.status == "accepted_pending"
        entrants.append(decision)

    safe_context = _context(
        session, 12, "central_bank", "monetary_stance", emergency=True,
    )
    _safe_proposal, safe = _submit(
        session,
        safe_context,
        "large-conflict-safe-rate",
        (
            PolicyAction("manual_policy_rate", 1.0e-4),
            PolicyAction("monetary_regime", "manual"),
        ),
    )
    assert safe.status == "accepted_pending"

    results = session.coordinator.execute_due(session)
    by_id = {item.decision_id: item for item in results}
    assert all(
        by_id[item.decision_id].status == "failed_at_execution"
        for item in entrants
    )
    assert by_id[safe.decision_id].status == "effective"
    assert world.economies[12].policy.monetary_regime == "manual"
    assert world.economies[12].policy.manual_policy_rate == pytest.approx(1.0e-4)
    assert not world.peg


def test_permitted_actions_filter_prerequisites_peg_constraints_and_admin_capacity():
    mechanism_world = World([_cfg(energy_enabled=True, omo=False)])
    mechanism = ControlledSimulationSession(mechanism_world)
    energy = _context(mechanism, 0, "energy", "energy_operations")
    at_cost = next(
        item for item in energy.permitted_actions if item.lever == "soe_price_at_cost"
    )
    assert not at_cost.allowed
    assert at_cost.reason_code == "disabled_prerequisite:soe_efirm"

    liquidity = _context(
        mechanism, 0, "central_bank", "liquidity_operations",
    )
    indexed = next(
        item for item in liquidity.permitted_actions if item.lever == "omo_index_deposits"
    )
    assert not indexed.allowed
    assert indexed.reason_code == "disabled_prerequisite:omo"

    low_capacity = ControlledSimulationSession(
        World([_cfg(seed=9)]),
        scheduler=DecisionScheduler(
            calendars={
                "fiscal_stance": CalendarSpec(10, admin_capacity=0.5),
            },
            triggers=(),
        ),
    )
    fiscal = _context(low_capacity, 0, "treasury", "fiscal_stance")
    deficit = next(
        item for item in fiscal.permitted_actions
        if item.lever == "gov_deficit_target"
    )
    assert not deficit.allowed and deficit.reason_code == "admin_capacity_exceeded"

    peg_world = _world(peg=True, peg_economy=0, peg_anchor=2)
    apply_action_batch(
        peg_world.economies[1], (("peg_anchor", 2),), actor="staged_anchor",
    )
    peg_session = ControlledSimulationSession(peg_world)
    contender = _context(
        peg_session, 1, "central_bank", "fx_operations", emergency=True,
    )
    regime = next(
        item for item in contender.permitted_actions if item.lever == "fx_regime"
    )
    anchor = next(
        item for item in contender.permitted_actions if item.lever == "peg_anchor"
    )
    assert not regime.allowed
    assert regime.reason_code == "joint_constraint:peg_unavailable"
    assert 0 not in anchor.choices  # a pegging economy cannot itself be an anchor
    assert anchor.choices == (2, None)

    fresh_session = ControlledSimulationSession(_world())
    fresh = _context(
        fresh_session, 1, "central_bank", "fx_operations", emergency=True,
    )
    fresh_regime = next(
        item for item in fresh.permitted_actions if item.lever == "fx_regime"
    )
    fresh_anchor = next(
        item for item in fresh.permitted_actions if item.lever == "peg_anchor"
    )
    assert fresh_regime.allowed and fresh_anchor.allowed
    assert fresh_anchor.choices == (0, 2, None)

    random_context = replace(
        fresh,
        permitted_actions=(fresh_anchor, fresh_regime),
    )
    random_proposal = RandomFuzzOccupant(
        seed=3, action_probability=1.0, max_actions=2,
    ).propose(random_context)
    assert {action.lever for action in random_proposal.actions} == {
        "fx_regime", "peg_anchor",
    }
    random_decision = fresh_session.coordinator.submit(
        fresh_session, random_proposal, actor="random_fuzz",
    )
    assert random_decision.status == "accepted_pending"


def test_emergency_contexts_share_admin_capacity_until_next_calendar_window():
    scheduler = DecisionScheduler(
        calendars={
            "emergency": CalendarSpec(
                period_ticks=4,
                window_ticks=2,
                admin_capacity=5.0,
            ),
        },
        triggers=(),
    )
    session = ControlledSimulationSession(World([_cfg()]), scheduler=scheduler)
    current = session.world.economies[0].policy.gov_deficit_target

    first_context = _context(
        session, 0, "treasury", "emergency", emergency=True,
    )
    _proposal, first = _submit(
        session,
        first_context,
        "emergency-budget-spend",
        (PolicyAction("gov_deficit_target", current + 0.005),),
    )
    assert first.status == "accepted_pending"
    key = (0, "treasury", "emergency")
    spent_remaining = session.coordinator.admin_remaining[key]
    assert spent_remaining < scheduler.calendars["emergency"].admin_capacity
    assert session.coordinator.admin_replenished_at[key] == 0

    session.advance()
    _context(session, 0, "treasury", "emergency", emergency=True)
    assert session.coordinator.admin_remaining[key] == spent_remaining
    assert session.coordinator.admin_replenished_at[key] == 0

    session.advance()
    _context(session, 0, "treasury", "emergency", emergency=True)
    assert session.coordinator.admin_remaining[key] == spent_remaining
    assert session.coordinator.admin_replenished_at[key] == 0

    session.advance()
    session.advance()
    _context(session, 0, "treasury", "emergency", emergency=True)
    assert session.boundary_tick == 4
    assert session.coordinator.admin_remaining[key] == 5.0
    assert session.coordinator.admin_replenished_at[key] == 4


@pytest.mark.parametrize("resolution", ["cancel", "execute"])
def test_old_window_resolution_cannot_change_new_window_admin_budget(resolution):
    scheduler = DecisionScheduler(
        calendars={
            "fiscal_stance": CalendarSpec(
                period_ticks=2,
                admin_capacity=8.0,
            ),
        },
        triggers=(),
    )
    session = ControlledSimulationSession(World([_cfg()]), scheduler=scheduler)
    policy = session.world.economies[0].policy

    old_context = _context(session, 0, "treasury", "fiscal_stance")
    _old_proposal, old = _submit(
        session,
        old_context,
        f"old-window-{resolution}",
        (PolicyAction("gov_deficit_target", policy.gov_deficit_target + 0.005),),
    )
    assert old.status == "accepted_pending"
    assert old.effective_tick == 7

    session.run(2)
    new_context = _context(session, 0, "treasury", "fiscal_stance")
    key = (0, "treasury", "fiscal_stance")
    assert session.coordinator.admin_replenished_at[key] == 2
    assert session.coordinator.admin_remaining[key] == 8.0
    _new_proposal, new = _submit(
        session,
        new_context,
        f"new-window-{resolution}",
        (
            PolicyAction(
                "gov_consumption_share",
                policy.gov_consumption_share + 0.005,
            ),
        ),
    )
    assert new.status == "accepted_pending"
    new_window_budget = (
        session.coordinator.admin_remaining[key],
        session.coordinator.admin_reserved[key],
    )

    if resolution == "cancel":
        session.cancel_pending(old.decision_id, actor="test")
        assert session.coordinator.decisions[old.decision_id].status == "cancelled"
    else:
        session.run(5)
        assert session.boundary_tick == old.effective_tick
        session.advance()
        assert session.coordinator.decisions[old.decision_id].status == "effective"

    assert session.coordinator.admin_remaining[key] == pytest.approx(
        new_window_budget[0]
    )
    assert session.coordinator.admin_reserved[key] == pytest.approx(
        new_window_budget[1]
    )
    assert sum(new_window_budget) == pytest.approx(8.0)


def test_proposal_id_is_global_and_duplicate_rejection_is_checkpoint_safe(tmp_path):
    session = ControlledSimulationSession(_world(n=2))
    first_context = _context(session, 0, "treasury", "fiscal_stance")
    current0 = session.world.economies[0].policy.gov_deficit_target
    _first_proposal, first = _submit(
        session,
        first_context,
        "globally-unique-proposal",
        (PolicyAction("gov_deficit_target", current0 + 0.005),),
    )
    assert first.status == "accepted_pending"

    second_context = _context(session, 1, "treasury", "fiscal_stance")
    current1 = session.world.economies[1].policy.gov_deficit_target
    duplicate = PolicyProposal(
        proposal_id="globally-unique-proposal",
        idempotency_key="different-idempotency-key",
        context_id=second_context.context_id,
        actions=(PolicyAction("gov_deficit_target", current1 + 0.005),),
        reason="duplicate id adversary",
        based_on_policy_versions=dict(second_context.policy_versions),
    )
    key = (1, "treasury", "fiscal_stance")
    budget_before = (
        session.coordinator.admin_remaining[key],
        session.coordinator.admin_reserved[key],
    )
    rejected = session.coordinator.submit(session, duplicate, actor="adversary")
    assert rejected.status == "rejected"
    assert rejected.reason_code == "duplicate_proposal_id"
    assert session.coordinator.submit(session, duplicate, actor="adversary") == rejected
    assert (
        session.coordinator.admin_remaining[key],
        session.coordinator.admin_reserved[key],
    ) == budget_before

    save_checkpoint(
        str(tmp_path / "duplicate-proposal.msim"),
        session,
        tick=session.boundary_tick,
    )


def test_coordinator_enforces_control_max_step_when_registry_validator_does_not(
    monkeypatch,
):
    name = "gov_deficit_target"
    lever = REGISTRY[name]
    # Model the required compatibility state: direct set_lever keeps the broad
    # Registry range, while controller procedure owns the per-decision step cap.
    monkeypatch.setitem(
        REGISTRY,
        name,
        replace(
            lever,
            validation=replace(lever.validation, max_step=None),
        ),
    )
    session = ControlledSimulationSession(World([_cfg(seed=27)]))
    context = _context(session, 0, "treasury", "fiscal_stance")
    current = session.world.economies[0].policy.gov_deficit_target
    target = current + 0.05

    # The low-level Registry accepts this domain-valid target when used directly.
    prepare_action_batch(
        session.world.economies[0], ((name, target),), actor="legacy_setter",
    )
    permitted = next(
        item for item in context.permitted_actions if item.lever == name
    )
    assert permitted.max_step == CONTROL_SPECS[name].max_step == 0.02

    _proposal_used, decision = _submit(
        session,
        context,
        "controller-step-too-large",
        (PolicyAction(name, target),),
    )
    assert decision.status == "rejected"
    assert "max_step" in decision.reason_code
    assert session.world.economies[0].policy.gov_deficit_target == current
    assert not session.pending
