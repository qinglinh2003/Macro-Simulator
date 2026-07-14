"""v23 P0: the capital annual-clock migration.

`plan_investment` computes K* = v * demand_expected. On the daily calendar demand_expected is
a PER-TICK flow while `v` is the textbook capital-output ratio against ANNUAL output. v13's
daily migration converted lambda_I, delta_K, r_interest, amort, eta and the inflation target
but MISSED `v`, so the desired capital stock was ticks_per_year too small: measured
K / annual GDP landed at ~0.004 against a configured 2.5. Capital then earned the
Cobb-Douglas share alpha while costing ~nothing to replace, which is what made the
capital-service price term, collateral value and P&L depreciation all economically inert.
"""
from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy


def test_flag_off_leaves_the_capital_parameters_untouched():
    cfg = Config.v13(seed=1, n_ticks=5)
    assert cfg.capital_annual_clock is False
    assert cfg.v == 2.5
    assert cfg.K_firm0 == 20.0
    assert cfg.A == 1.0


def test_annual_clock_rescales_the_joint_set():
    cfg = Config.v13(seed=1, n_ticks=5, capital_annual_clock=True, a_K=2.4)
    s = cfg.ticks_per_year
    assert cfg.v == pytest.approx(2.5 * s)          # desired capital now tracks ANNUAL output
    assert cfg.K_firm0 == pytest.approx(20.0 * s)   # genesis capital at the new scale
    assert cfg.A == pytest.approx(1.0 * s ** (-cfg.alpha))


def test_genesis_production_is_exactly_invariant():
    """The whole point of the joint migration: A' K'^a == A K^a, so genesis output, unit
    costs, prices and wages are preserved while the capital STOCK becomes economically real."""
    off = Config.v13(seed=1, n_ticks=5)
    on = Config.v13(seed=1, n_ticks=5, capital_annual_clock=True, a_K=2.4)
    assert on.A * on.K_firm0 ** on.alpha == pytest.approx(off.A * off.K_firm0 ** off.alpha, rel=1e-12)


def test_uncalibrated_capital_goods_productivity_is_rejected():
    """a_K was never calibrated (the K sector was inert under the broken clock). At a_K<=1.0 the
    now-real replacement flow eats ~1/3 of the labour force and drives a cost-push spiral."""
    with pytest.raises(AssertionError, match="capital-goods productivity"):
        Config.v13(seed=1, n_ticks=5, capital_annual_clock=True)


def _frontier(**over):
    from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
    params = dict(FULL_FRONTIER_FLAGS)
    params.update(seed=3, n_households=50, demographics_population=300, n_firms_c=30,
                  n_firms_k=15, n_banks=4, n_ticks=740)
    params.update(over)
    return Config.v13(**params)


def test_capital_output_ratio_reaches_a_macroeconomic_magnitude():
    """The regression this whole finding is about: K / ANNUAL GDP must be a macro quantity
    (order 1), not 0.004. Runs the frontier, which enables the annual clock."""
    econ = Economy(_frontier())
    recs = [econ.step() for _ in range(740)]
    tail = recs[-120:]
    k = sum(r.get("aggregate_capital", 0.0) for r in tail) / len(tail)
    gdp_daily = sum(r.get("real_gdp", 0.0) for r in tail) / len(tail)
    ratio = k / (gdp_daily * 365.0)
    assert ratio > 0.5, f"capital is still economically negligible: K/annual GDP = {ratio:.4f}"
    assert ratio < 6.0, f"capital stock is implausibly large: K/annual GDP = {ratio:.4f}"


def test_broken_clock_reproduces_the_negligible_capital_stock():
    """Pin the DEFECT so a regression cannot silently reintroduce it."""
    econ = Economy(_frontier(capital_annual_clock=False, a_K=1.0))
    recs = [econ.step() for _ in range(740)]
    tail = recs[-120:]
    k = sum(r.get("aggregate_capital", 0.0) for r in tail) / len(tail)
    gdp_daily = sum(r.get("real_gdp", 0.0) for r in tail) / len(tail)
    ratio = k / (gdp_daily * 365.0)
    assert ratio < 0.05, f"expected the broken clock's negligible capital, got {ratio:.4f}"
