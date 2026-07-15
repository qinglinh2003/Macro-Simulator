"""v22.1 — migration & remittances (PLAN_v22): labor crosses to higher wages, money flows
home, completing the current account (trade + factor income + transfers).

Gates: (1) migration off ⇒ no migrant stock, economies conserve as v21; (2) conservation
with migration on; (3) the low-wage economy is the net labor EXPORTER and the net remittance
RECEIVER; (4) remittances lift the labor-exporter's current account above its trade+factor
balance (the remittance wedge).
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.world import World
from macro_sim.world.fx import DEALER_ID
from macro_sim.world.migration import _collect, _distribute


# Explicit zero daily rate isolates migration/remittances from the separate external-
# interest channel while retaining the per-tick rate contract.
_PER_TICK_RATE = 0.0


def _pair():
    """A LOW-WAGE and a HIGH-WAGE economy — the gap must be in WAGES, not productivity.

    This model is DEMAND-constrained: doubling labor productivity `a` moves neither output
    nor wages (the same demand simply needs fewer workers), so a productivity gap gives no
    wage gap at all and the migration direction is then decided by noise. Migration responds
    to wages, so the economies must actually differ in wages (the genesis wage/price anchors).
    """
    lo = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0,
                     w_firm0=0.7, p_firm0=0.85,
                     r_interest=_PER_TICK_RATE,
                     central_bank=False)             # low-wage; keep the rate truly fixed
    hi = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0,
                     w_firm0=1.4, p_firm0=1.7,
                     r_interest=_PER_TICK_RATE,
                     central_bank=False)             # high-wage; isolate migration from Taylor feedback
    return lo, hi


def _world(pair, **kw):
    return World([*pair], base_seed=9, trade=True, capital=True, migration=True,
                 capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2, **kw)


def _mean(recs, key, i, n=40):
    return sum(r[key][i] for r in recs[-n:]) / n


def test_migration_off_no_flow_and_conserves():
    poor, rich = _pair()
    world = World([poor, rich], base_seed=9, trade=True, capital=True, capital_mobility=1.0)  # migration off
    world.run()
    assert world.world_records[-1]["migrant_stock"] == [0.0, 0.0]
    for econ in world.economies:
        econ.ledger.assert_conserved()


def test_migration_conserves():
    poor, rich = _pair()
    world = World([poor, rich], base_seed=9, trade=True, capital=True, migration=True,
                  capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()


def test_low_wage_economy_exports_labor_and_receives_remittances():
    poor, rich = _pair()
    world = World([poor, rich], base_seed=9, trade=True, capital=True, migration=True,
                  capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2)
    world.run()
    last = world.world_records[-1]
    assert last["migrant_stock"][0] > last["migrant_stock"][1]        # poor = net labor exporter
    assert _mean(world.world_records, "remittances", 0) > _mean(world.world_records, "remittances", 1)


def test_remittances_lift_current_account():
    """The labor-exporter's current account (with remittances) exceeds its trade+factor
    balance — remittances finance the deficit (the Philippines/Bangladesh pattern)."""
    poor, rich = _pair()
    world = World([poor, rich], base_seed=9, trade=True, capital=True, migration=True,
                  capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2)
    world.run()
    ca = _mean(world.world_records, "current_account", 0)
    remit = _mean(world.world_records, "remittances", 0)
    ca_ex_remit = ca - remit                    # trade balance + factor income only
    assert remit > 0.0                          # net remittance inflow to the labor exporter
    assert ca > ca_ex_remit                     # remittances improve the current account
    assert remit > 0.3 * abs(ca_ex_remit)       # ... materially (a large share of the CA)


# -- migration POLICY levers --------------------------------------------------

def test_immigration_cap_throttles_migration():
    """POLICY: an immigration quota on the host binds ⇒ fewer migrants than open borders ⇒
    the wage gap persists (policy blocks convergence)."""
    open_w = _world(_pair())
    open_w.run()
    capped = _world(_pair(), immigration_cap=0.03)     # rich admits ≤ 3% of its population
    capped.run()
    for econ in capped.economies:
        econ.ledger.assert_conserved()
    assert capped.world_records[-1]["migrant_stock"][0] < open_w.world_records[-1]["migrant_stock"][0]
    assert any(r["immigration_binding"][1] for r in capped.world_records)   # the quota bound


def test_remittance_tax_diverts_to_fiscal_and_conserves():
    """POLICY: an origin remittance tax skims the inflow to the government (fiscal revenue),
    lowering the net that reaches households; conserving."""
    taxed = _world(_pair(), remittance_tax=0.25)
    taxed.run()
    untaxed = _world(_pair())
    untaxed.run()
    for econ in taxed.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    assert _mean(taxed.world_records, "remittances", 0) < _mean(untaxed.world_records, "remittances", 0)
    assert _mean(taxed.world_records, "remittance_tax_rev", 0) > 0.0    # government collected revenue


def test_remittance_cash_rails_skip_empty_demographic_household(monkeypatch):
    cfg = Config.v13(
        n_ticks=1,
        n_households=8,
        demographics_population=12,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
    )
    world = World([cfg, cfg], base_seed=41, couple=True)
    econ = world.economies[0]
    empty = econ.households[0]
    bridge = econ.demographic_bridge
    original = bridge.household_has_living_members
    monkeypatch.setattr(
        bridge,
        "household_has_living_members",
        lambda account_id: account_id != empty.id and original(account_id),
    )
    empty_opening = econ.ledger.balance(empty.id)

    collected = _collect(econ, 10.0)
    assert collected == pytest.approx(10.0)
    assert econ.ledger.balance(empty.id) == pytest.approx(empty_opening)
    assert econ.ledger.balance(DEALER_ID) == pytest.approx(10.0)

    _distribute(econ, collected)
    assert econ.ledger.balance(empty.id) == pytest.approx(empty_opening)
    assert econ.ledger.balance(DEALER_ID) == pytest.approx(0.0)
    econ.ledger.assert_conserved()
