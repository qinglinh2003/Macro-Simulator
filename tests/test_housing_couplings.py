"""v15.5 couplings 1+2: the affordability signal, leave-home <- rent burden, and
fertility <- price-to-income (channel 2.1d).

One pipeline, per-channel flags, Phase 2 acceptance grammar: burn-in discard, anchor
at exactly 1, monotone + clipped multipliers, bit-identical off-state, and the kernel
untouched (2.1d composes into the ONE scalar the kernel already reads).
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.housing.affordability import HousingAffordabilitySignal


def feed_year(sig, year, *, price=1000.0, rent=0.14, wage=1.0, days=365):
    for _ in range(days):
        sig.observe_tick(year=year, house_price=price, rent_level=rent,
                         wages_paid=wage, labor=1.0)


def test_burnin_discard_and_anchor():
    sig = HousingAffordabilitySignal(burnin_years=2, leave_elasticity=1.0)
    feed_year(sig, 2000, rent=9.0)          # transient junk: discarded
    feed_year(sig, 2001, rent=0.01)
    feed_year(sig, 2002, rent=0.14)         # first clean year: anchor, ratios = 1
    sig.observe_tick(year=2003, house_price=1000.0, rent_level=0.14, wages_paid=1.0, labor=1.0)
    assert sig.pti_ratio == pytest.approx(1.0)
    assert sig.rent_burden_ratio == pytest.approx(1.0)
    assert sig.leave_mult == pytest.approx(1.0)


def test_rent_squeeze_lowers_leave_mult_and_clips():
    sig = HousingAffordabilitySignal(burnin_years=1, leave_elasticity=1.0)
    feed_year(sig, 2000)
    feed_year(sig, 2001)                    # anchor
    feed_year(sig, 2002, rent=0.28)         # rents double
    sig.observe_tick(year=2003, house_price=1000.0, rent_level=0.28, wages_paid=1.0, labor=1.0)
    assert sig.rent_burden_ratio == pytest.approx(2.0)
    assert sig.leave_mult == pytest.approx(0.5)          # 2^-1 = 0.5 (hits the clip floor)
    feed_year(sig, 2003, rent=1.4)          # x10: clip binds
    sig.observe_tick(year=2004, house_price=1000.0, rent_level=1.4, wages_paid=1.0, labor=1.0)
    assert sig.leave_mult == 0.5


def test_pti_rise_lowers_housing_fertility_mult():
    sig = HousingAffordabilitySignal(burnin_years=1, fertility_elasticity=0.5)
    feed_year(sig, 2000)
    feed_year(sig, 2001)                    # anchor at pti = 1000/365
    feed_year(sig, 2002, price=2000.0)      # prices double vs income
    sig.observe_tick(year=2003, house_price=2000.0, rent_level=0.14, wages_paid=1.0, labor=1.0)
    assert sig.pti_ratio == pytest.approx(2.0)
    assert sig.fertility_mult == pytest.approx(2.0 ** -0.5)


def test_zero_elasticity_never_moves_multipliers():
    sig = HousingAffordabilitySignal(burnin_years=1)
    feed_year(sig, 2000)
    feed_year(sig, 2001)
    feed_year(sig, 2002, price=5000.0, rent=0.7)
    sig.observe_tick(year=2003, house_price=5000.0, rent_level=0.7, wages_paid=1.0, labor=1.0)
    assert sig.pti_ratio > 1.0                            # observability lives
    assert sig.leave_mult == 1.0 and sig.fertility_mult == 1.0


# ---------------------------------------------------------------------------
# economy integration
# ---------------------------------------------------------------------------

def make_econ(**overrides):
    params = dict(
        seed=13,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=100,
        housing_enabled=True,
        housing_market_enabled=True,
        housing_rental_enabled=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_scaled_leave_rates_change_leaver_counts():
    """Unit-level power test: genesis people have NO parent links (leaving-home is
    dormant for genesis cohorts -- it only ever fires for simulation-born children),
    so build linked 24-year-olds by hand and drive the dynamics directly with the
    scaled rates the economy wiring would pass."""
    import numpy as np

    from macro_sim.demographics.agents import Person
    from macro_sim.demographics.kernel import create_genesis_population
    from macro_sim.demographics.lifecycle_households import (
        LifecycleHouseholdConfig,
        apply_leaving_home_dynamics,
    )
    from macro_sim.demographics.rates import Phase0VitalRates

    def leavers(rate_scale):
        state = create_genesis_population(Phase0VitalRates(), n=400, seed=5)
        adults = [p for p in state.people if 45 <= p.age <= 60][:150]
        for parent in adults:
            child = Person(
                id=state.next_person_id, age=24, sex="F",
                birth_date=parent.birth_date,          # only age matters here
                household_id=parent.household_id, mother_id=parent.id,
            )
            state.next_person_id += 1
            state.people.append(child)
        config = LifecycleHouseholdConfig(
            leave_home_min_age=22, leave_home_peak_end_age=30,
            annual_leave_rate_peak=0.25 * rate_scale,
            annual_leave_rate_late=0.05 * rate_scale,
        )
        rng = np.random.default_rng(7)
        total = 0
        for _ in range(365):
            total += len(apply_leaving_home_dynamics(state, config, rng))
        return total

    slow, fast = leavers(0.05), leavers(1.5)
    assert fast > 3 * max(slow, 1)           # ~150x0.31 vs ~150x0.012 expected


def test_economy_passes_scaled_leave_rates():
    """Wiring check: the pinned multiplier must reach apply_leaving_home_dynamics."""
    from macro_sim import economy as economy_module

    econ = make_econ(housing_leave_elasticity=1.0)
    econ.housing_affordability.leave_mult = 0.5
    econ.housing_affordability.burnin_years = 10**9
    captured = {}
    original = economy_module.apply_leaving_home_dynamics

    def spy(state, config, rng):
        captured["rate_peak"] = config.annual_leave_rate_peak
        return original(state, config, rng)

    economy_module.apply_leaving_home_dynamics = spy
    try:
        econ.step()
    finally:
        economy_module.apply_leaving_home_dynamics = original
    assert captured["rate_peak"] == pytest.approx(
        0.5 * econ.cfg.demographic_annual_leave_rate_peak
    )


def test_bridge_composes_housing_fertility_multiplier():
    econ = make_econ(housing_fertility_elasticity=0.5)
    econ.step()
    bridge = econ.demographic_bridge
    base = bridge.macro_signal.fertility_mult
    econ.housing_affordability.fertility_mult = 0.8      # pin the housing factor
    assert bridge.fertility_macro_multiplier == pytest.approx(base * 0.8)


def test_couplings_off_multipliers_stay_one():
    econ = make_econ()
    for _ in range(40):
        econ.step()
    assert econ.housing_affordability.leave_mult == 1.0
    assert econ.housing_affordability.fertility_mult == 1.0
    rec = econ.records[-1]
    assert rec["leave_home_mult"] == 1.0
    assert rec["housing_fertility_mult"] == 1.0
