"""Regression gates for retained FX reserves across peg lifecycle transitions."""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.controllers.observation import (
    DEFAULT_OBSERVATION_SPEC,
    ReleaseService,
)
from macro_sim.world import World


def _world(*, anchor: int) -> World:
    cfg = Config.v3(
        seed=0,
        n_households=4,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
        n_ticks=4,
        government=True,
        central_bank=False,
        r_interest=0.0,
    )
    return World(
        [cfg, cfg, cfg],
        base_seed=31,
        couple=True,
        capital=True,
        capital_mobility=0.0,
        fx_lambda=0.0,
        peg=True,
        peg_economy=0,
        peg_anchor=anchor,
        peg_reserves0=100.0,
    )


def _reserve_value(world: World, pegger: int) -> float:
    state = world.peg_states[pegger]
    balance = world.economies[state.anchor].ledger.balance(state.reserve_account_id)
    return balance / world.rates.e[state.anchor]


def test_anchor_round_trip_reuses_account_and_preserves_reserve_value() -> None:
    """A->B->A must reuse the zero-balance A account, not add it twice."""
    world = _world(anchor=1)
    account = "CBRES:0"

    # Use non-unit, unequal rates so the test covers the conversion rather than
    # merely moving the same nominal balance between ledgers.
    world.rates.grope([0.20, -0.15, -0.05], 0.5)
    value0 = _reserve_value(world, 0)
    market0 = world.market_external_positions()

    for anchor in (2, 1):
        inventory0 = world.dealer.inventory()
        rates0 = list(world.rates.e)
        world.economies[0].external_policy.peg_anchor = anchor
        world._commit_external_policies()

        assert world.peg_states[0].anchor == anchor
        assert _reserve_value(world, 0) == pytest.approx(value0)
        assert world.market_external_positions() == pytest.approx(market0)
        world.dealer.assert_flow_is_passthrough(inventory0, rates0)
        for economy in world.economies:
            economy.ledger.assert_conserved()

    # Both historical host ledgers retain the named account; the inactive host is
    # simply zero while the current host owns the full converted reserve balance.
    assert world.economies[1].ledger.has_account(account)
    assert world.economies[2].ledger.has_account(account)
    assert world.economies[1].ledger.balance(account) > 0.0
    assert world.economies[2].ledger.balance(account) == pytest.approx(0.0)


def test_handoff_and_exit_net_all_retained_reserves_without_principal_jump() -> None:
    """Inactive peg states remain official assets, never private NFA/principal."""
    world = _world(anchor=2)
    zero = pytest.approx([0.0, 0.0, 0.0], abs=1.0e-10)

    world.step()  # runtime adoptions seed reserves only after genesis (t > 0)
    assert world.market_external_positions() == zero
    assert world._factor_interest_principal == zero

    # Pegger 0 exits while pegger 1 adopts the same anchor.  Pegger 0's state is
    # retained for history and its real reserve asset remains in anchor 2's ledger.
    principal0 = list(world._factor_interest_principal)
    world.economies[0].external_policy.fx_regime = "float"
    world.economies[1].external_policy.peg_anchor = 2
    world.economies[1].external_policy.fx_regime = "peg"
    world.step()

    assert not world.peg_states[0].intact
    assert world.peg_states[1].intact
    assert world._peg_reserve_balances() == pytest.approx({0: 100.0, 1: 100.0})
    assert world.market_external_positions() == zero
    assert world.world_records[-1]["nfa"] == zero
    assert world._factor_interest_principal == pytest.approx(principal0)

    # The second pegger now exits too.  With no active peg, both historical states
    # still have reserves; active-single-peg selection used to hide one of them.
    principal1 = list(world._factor_interest_principal)
    world.economies[1].external_policy.fx_regime = "float"
    world.step()

    assert not world.peg
    assert all(not state.intact for state in world.peg_states.values())
    assert world._peg_reserve_balances() == pytest.approx({0: 100.0, 1: 100.0})
    assert world.market_external_positions() == zero
    assert world.world_records[-1]["nfa"] == zero
    assert world._factor_interest_principal == pytest.approx(principal1)
    for economy in world.economies:
        economy.ledger.assert_conserved()


def test_exited_peg_reentry_moves_old_reserves_before_new_anchor_seed() -> None:
    """Re-entry at a new anchor must not orphan the exited peg's old asset."""
    world = _world(anchor=1)
    account = "CBRES:0"

    # Non-unit, unequal rates make a nominal copy distinguishable from the
    # required value-preserving currency conversion.
    world.rates.grope([0.20, -0.15, -0.05], 0.5)
    world.step()
    old_anchor = 1
    new_anchor = 2
    old_balance = world.economies[old_anchor].ledger.balance(account)
    old_value = old_balance / world.rates.e[old_anchor]

    world.economies[0].external_policy.fx_regime = "float"
    world.economies[0].external_policy.peg_anchor = None
    world.step()
    assert not world.peg_states[0].intact
    assert world.economies[old_anchor].ledger.balance(account) == pytest.approx(
        old_balance
    )

    inventory_before = world.dealer.inventory()
    rates_before = list(world.rates.e)
    market_before = world.market_external_positions()
    world.economies[0].external_policy.peg_anchor = new_anchor
    world.economies[0].external_policy.fx_regime = "peg"
    world._commit_external_policies()

    converted = old_balance * world.rates.bilateral(new_anchor, old_anchor)
    expected_balance = converted + world._peg_reserves0
    assert world.peg_states[0].anchor == new_anchor
    assert world.peg_states[0].intact
    assert world.economies[old_anchor].ledger.balance(account) == pytest.approx(0.0)
    assert world.economies[new_anchor].ledger.balance(account) == pytest.approx(
        expected_balance
    )
    assert world._peg_reserve_balances() == pytest.approx({0: expected_balance})
    assert expected_balance / world.rates.e[new_anchor] == pytest.approx(
        old_value + world._peg_reserves0 / world.rates.e[new_anchor]
    )
    assert world.market_external_positions() == pytest.approx(market_before)
    world.dealer.assert_flow_is_passthrough(inventory_before, rates_before)
    for economy in world.economies:
        economy.ledger.assert_conserved()

    # The first post-reentry record and a newly attached release service must see
    # the complete consolidated reserve holding, never just the newly seeded leg.
    world.step()
    assert world.world_records[-1]["reserves_by_economy"] == pytest.approx(
        {0: expected_balance, 1: 0.0, 2: 0.0}
    )
    service = ReleaseService(DEFAULT_OBSERVATION_SPEC)
    observed = service.observe(
        world, world.t, economy_id=0, role="central_bank"
    ).release("fx_reserves")
    assert observed.value == pytest.approx(expected_balance)
