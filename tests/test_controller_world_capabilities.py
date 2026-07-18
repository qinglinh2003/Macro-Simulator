from __future__ import annotations

from macro_sim.config import Config
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.world import World


def _cfg(seed: int) -> Config:
    return Config.v13(
        seed=seed,
        n_households=6,
        n_firms_c=4,
        n_firms_k=2,
        n_banks=1,
        n_ticks=5,
        government=True,
    )


def _submit(session, context, actions):
    proposal = PolicyProposal(
        proposal_id=f"proposal:{context.context_id}",
        idempotency_key=f"idempotency:{context.context_id}",
        context_id=context.context_id,
        actions=tuple(actions),
        based_on_policy_versions=dict(context.policy_versions),
    )
    return session.coordinator.submit(session, proposal, actor="test")


def test_disabled_world_modules_mask_their_policy_levers():
    session = ControlledSimulationSession(World([_cfg(1), _cfg(2)]))
    cases = (
        ("external_affairs", "trade_and_migration", "tariff", "trade"),
        ("central_bank", "fx_operations", "capital_control", "capital"),
        ("external_affairs", "trade_and_migration", "immigration_cap", "migration"),
        ("central_bank", "fx_operations", "fx_regime", "coupling"),
    )
    for seat, group, lever, capability in cases:
        context = session.coordinator.open_context(
            session, 0, seat, group, observation={}, expires_at_tick=0,
        )
        item = next(action for action in context.permitted_actions if action.lever == lever)
        assert item.allowed is False
        assert item.reason_code == f"missing_world_capability:{capability}"


def test_injected_peg_cannot_become_effective_without_fx_layer():
    session = ControlledSimulationSession(World([_cfg(3), _cfg(4)]))
    context = session.coordinator.open_context(
        session, 0, "central_bank", "fx_operations",
        observation={}, expires_at_tick=0, emergency=True,
        emergency_trigger="test",
    )
    decision = _submit(session, context, (
        PolicyAction("peg_anchor", 1),
        PolicyAction("fx_regime", "peg"),
    ))
    assert decision.status == "rejected"
    assert "missing_world_capability" in decision.reason_code
    assert session.world.economies[0].external_policy.fx_regime == "float"


def test_enabled_world_modules_expose_corresponding_levers():
    session = ControlledSimulationSession(World(
        [_cfg(5), _cfg(6)], trade=True, capital=True, migration=True,
    ))
    external_context = session.coordinator.open_context(
        session, 0, "external_affairs", "trade_and_migration",
        observation={}, expires_at_tick=0,
    )
    central_bank_context = session.coordinator.open_context(
        session, 0, "central_bank", "fx_operations",
        observation={}, expires_at_tick=0,
    )
    by_name = {
        item.lever: item
        for context in (external_context, central_bank_context)
        for item in context.permitted_actions
    }
    for name in ("tariff", "capital_control", "immigration_cap", "sanctions_imposed_on"):
        assert by_name[name].allowed is True, (name, by_name[name].reason_code)
