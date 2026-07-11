"""Unit tests for the Phase 2 macro->demography signal (annual EWMA level + cycle).

Burn-in semantics: the first `burnin_years` completed years are DISCARDED (the
genesis transient must never enter the EWMA); the first post-burn-in year seeds
both the EWMA and the level baseline, so x starts exactly at 1.
"""

from __future__ import annotations

import pytest

from macro_sim.demographics.macro_signal import DemoMacroSignal


def feed_year(signal: DemoMacroSignal, year: int, wage: float, *, days: int = 365,
              labor: float = 1.0, price: float = 1.0) -> None:
    """Feed one flat year of daily observations (rollover fires on the NEXT year's first tick)."""
    for _ in range(days):
        signal.observe_tick(year=year, wages_paid=wage * labor, labor=labor, price=price)


def make_signal(**overrides) -> DemoMacroSignal:
    params = dict(halflife_years=5.0, burnin_years=2)
    params.update(overrides)
    return DemoMacroSignal(**params)


def alpha(halflife: float = 5.0) -> float:
    return 1.0 - 0.5 ** (1.0 / halflife)


def test_burnin_years_are_discarded_entirely():
    sig = make_signal(fertility_elasticity=1.0, mortality_elasticity=1.0)
    feed_year(sig, 2000, wage=1.0)
    feed_year(sig, 2001, wage=5.0)     # wild transient inside burn-in must leave NO trace
    sig.observe_tick(year=2002, wages_paid=1.0, labor=1.0, price=1.0)  # finalizes 2001
    assert sig.ewma is None            # nothing smoothed yet
    assert sig.baseline is None
    assert sig.fertility_mult == 1.0
    assert sig.mortality_mult == 1.0
    assert sig.signal_x == 1.0


def test_first_clean_year_anchors_x_at_one():
    sig = make_signal(fertility_elasticity=0.3)
    feed_year(sig, 2000, wage=9.0)     # burn-in (discarded)
    feed_year(sig, 2001, wage=0.2)     # burn-in (discarded)
    feed_year(sig, 2002, wage=2.0)     # first clean year: EWMA seed + baseline
    sig.observe_tick(year=2003, wages_paid=2.0, labor=1.0, price=1.0)
    assert sig.ewma == pytest.approx(2.0)
    assert sig.baseline == pytest.approx(2.0)
    assert sig.signal_x == pytest.approx(1.0)
    assert sig.signal_z == pytest.approx(1.0)
    assert sig.fertility_mult == pytest.approx(1.0)


def test_constant_economy_keeps_signals_at_neutral():
    sig = make_signal(fertility_elasticity=0.3, mortality_elasticity=0.15)
    for year in range(2000, 2010):
        feed_year(sig, year, wage=2.0)
    sig.observe_tick(year=2010, wages_paid=2.0, labor=1.0, price=1.0)
    assert sig.signal_x == pytest.approx(1.0)
    assert sig.signal_z == pytest.approx(1.0)
    assert sig.fertility_mult == pytest.approx(1.0)
    assert sig.mortality_mult == pytest.approx(1.0)


def test_step_response_matches_ewma_closed_form():
    sig = make_signal(fertility_elasticity=1.0)
    w0, w1 = 1.0, 1.2
    feed_year(sig, 2000, wage=w0)      # burn-in (discarded)
    feed_year(sig, 2001, wage=w0)      # burn-in (discarded)
    feed_year(sig, 2002, wage=w0)      # anchor year: ewma = baseline = w0
    feed_year(sig, 2003, wage=w1)      # step year
    feed_year(sig, 2004, wage=w1)
    sig.observe_tick(year=2005, wages_paid=w1, labor=1.0, price=1.0)  # finalizes 2004

    a = alpha()
    ewma_2003 = w0 + a * (w1 - w0)
    ewma_2004 = ewma_2003 + a * (w1 - ewma_2003)
    assert sig.ewma == pytest.approx(ewma_2004)
    assert sig.baseline == pytest.approx(w0)
    assert sig.signal_x == pytest.approx(ewma_2004 / w0)
    # z is measured against the PRE-update EWMA of its own year
    assert sig.signal_z == pytest.approx(w1 / ewma_2003)
    assert sig.fertility_mult == pytest.approx((ewma_2004 / w0) ** -1.0)


def test_zero_elasticity_never_recomputes_multiplier():
    sig = make_signal()                # both elasticities 0.0 (production default)
    feed_year(sig, 2000, wage=1.0)
    feed_year(sig, 2001, wage=1.0)
    feed_year(sig, 2002, wage=1.0)     # anchor
    feed_year(sig, 2003, wage=3.0)     # x moves...
    sig.observe_tick(year=2004, wages_paid=3.0, labor=1.0, price=1.0)
    assert sig.signal_x > 1.0          # ...observability lives
    assert sig.fertility_mult == 1.0   # ...but the multiplier is untouched (bit-identity anchor)
    assert sig.mortality_mult == 1.0


def test_multiplier_is_monotone_and_clipped():
    lo, hi = 0.5, 1.5
    results = []
    for wage_after in (0.05, 0.8, 1.0, 1.3, 20.0):
        sig = make_signal(fertility_elasticity=1.0, fertility_mult_lo=lo, fertility_mult_hi=hi,
                          halflife_years=0.5)   # fast EWMA so x tracks the step quickly
        feed_year(sig, 2000, wage=1.0)
        feed_year(sig, 2001, wage=1.0)
        feed_year(sig, 2002, wage=1.0)          # anchor at 1.0
        for year in range(2003, 2013):
            feed_year(sig, year, wage=wage_after)
        sig.observe_tick(year=2013, wages_paid=wage_after, labor=1.0, price=1.0)
        assert lo <= sig.fertility_mult <= hi
        results.append(sig.fertility_mult)
    assert results == sorted(results, reverse=True)   # income up => fertility multiplier down
    assert results[0] == hi                           # deep slump clips at the ceiling
    assert results[-1] == lo                          # boom clips at the floor


def test_zero_activity_year_holds_last_level():
    sig = make_signal(fertility_elasticity=0.3)
    feed_year(sig, 2000, wage=1.0)
    feed_year(sig, 2001, wage=1.0)
    feed_year(sig, 2002, wage=1.0)              # anchor
    feed_year(sig, 2003, wage=1.1)
    feed_year(sig, 2004, wage=0.0, labor=0.0)   # total collapse: no wages, no labor
    sig.observe_tick(year=2005, wages_paid=1.0, labor=1.0, price=1.0)
    a = alpha()
    ewma_2003 = 1.0 + a * (1.1 - 1.0)
    # 2004 reuses the last observed real wage (1.1) instead of dividing by zero
    ewma_2004 = ewma_2003 + a * (1.1 - ewma_2003)
    assert sig.ewma == pytest.approx(ewma_2004)
    assert sig.fertility_mult == pytest.approx(sig.signal_x ** -0.3)


def test_price_deflation_uses_annual_mean_price():
    sig = make_signal()
    feed_year(sig, 2000, wage=1.0)
    feed_year(sig, 2001, wage=1.0)
    feed_year(sig, 2002, wage=1.0)              # anchor (real wage 1.0)
    # nominal wage doubles but so does the price level: real wage unchanged
    feed_year(sig, 2003, wage=2.0, price=2.0)
    sig.observe_tick(year=2004, wages_paid=2.0, labor=1.0, price=2.0)
    assert sig.signal_x == pytest.approx(1.0)
    assert sig.signal_z == pytest.approx(1.0)
