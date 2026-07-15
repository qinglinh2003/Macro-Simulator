"""v20.1 — the FX layer is INERT with zero trade: rates flat, dealer inventory zero,
balance of payments trivially balanced (PLAN_v20 §11 v20.1 gate). Plus the numéraire
gauge properties (§2): geometric-basket normalization + triangular consistency.
"""

from __future__ import annotations

import math

import pytest

from macro_sim.config import Config
from macro_sim.world import World
from macro_sim.world.fx import DEALER_ID, RateVector
from macro_sim.world.trade import rate_grope_signal


def _macro_cfg(seed: int = 0) -> Config:
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=120, seed=seed)


# -- the rate vector (numéraire gauge) -------------------------------------------

def test_ratevector_genesis_is_unit_and_normalized():
    r = RateVector(3)
    assert r.e == [1.0, 1.0, 1.0]
    assert abs(sum(r.log_e)) < 1e-12          # Σ log e_i = 0 (equal-weight basket)


def test_ratevector_triangular_consistency():
    r = RateVector(3)
    r.log_e = [0.4, -0.1, 0.7]
    r._normalize()
    # cross-rates derived from one vector ⇒ i→j→k→i round-trips to 1 (no arbitrage)
    round_trip = r.bilateral(0, 1) * r.bilateral(1, 2) * r.bilateral(2, 0)
    assert abs(round_trip - 1.0) < 1e-12


def test_ratevector_normalization_preserves_ratios():
    r = RateVector(3)
    before = r.bilateral(0, 1)
    r.log_e = [x + 5.0 for x in r.log_e]      # a pure gauge shift (multiply all e_i by e^5)
    r._normalize()
    assert abs(r.bilateral(0, 1) - before) < 1e-12   # bilateral rates are gauge-invariant


def test_grope_with_zero_signal_is_noop():
    r = RateVector(2)
    r.grope([0.0, 0.0], lam=0.5)
    assert r.e == [1.0, 1.0]


def test_extreme_external_gap_uses_a_finite_relative_fx_adjustment(monkeypatch):
    """A crisis-sized stock gap is cleared over time, not in one infinite log step."""
    world = World([_macro_cfg(), _macro_cfg()], base_seed=5, couple=True)
    monkeypatch.setattr(
        world,
        "market_external_positions",
        lambda: [1.0e300, -1.0e300],
    )

    signal = rate_grope_signal(world)

    assert signal == pytest.approx([1.0, -1.0])
    world.rates.grope(signal, world.fx_lambda)
    assert all(math.isfinite(value) for value in world.rates.e)
    assert abs(sum(world.rates.log_e)) < 1.0e-12


# -- the FX layer inside the World (zero trade) ----------------------------------

def test_fx_layer_inert_with_zero_trade():
    world = World([_macro_cfg(), _macro_cfg()], base_seed=5, couple=True, fx_lambda=0.05)
    world.run()

    # rates flat at unity, dealer inventory zero, BoP trivially balanced, no revaluation
    last = world.world_records[-1]
    assert last["e"] == [1.0, 1.0]
    assert all(abs(x) < 1e-9 for x in last["dealer_inventory"])
    assert abs(last["bop_numeraire"]) < 1e-9
    assert abs(last["dealer_valuation"]) < 1e-9
    assert len(world.world_records) == world.economies[0].cfg.n_ticks


def test_dealer_accounts_installed_and_conserving():
    world = World([_macro_cfg(), _macro_cfg()], base_seed=5, couple=True)
    world.run()
    # dealer has a (zero) account in each economy's ledger; each economy still conserves
    # (assert_conserved runs every tick inside econ.step — a raise would fail the run)
    for econ in world.economies:
        assert econ.ledger.has_account(DEALER_ID)
        assert abs(econ.ledger.balance(DEALER_ID)) < 1e-9
        econ.ledger.assert_conserved()
