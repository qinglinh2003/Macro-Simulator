"""Phase 2.2: mortality responds to the macro level signal via DERIVED vital rates.

Gompertz-Makeham hazards are closed under proportional scaling, so the bridge
hands the kernel (and the memoized e(a) lifecycle table) a scaled
Phase0VitalRates instance instead of threading a multiplier through every
signature. These tests cover the closed-form identity, the neutrality anchor,
the kernel response, the e(a)/consumption coupling, and the parameterized
frozen-economy oracle (Leslie growth under scaled rates).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

import pytest

from macro_sim.demographics.economic_bridge import DemographicEconomicBridge
from macro_sim.demographics.kernel import MicroDemographicKernel, create_genesis_population
from macro_sim.demographics.leslie import build_leslie_matrix, spectral_diagnostics
from macro_sim.demographics.lifecycle import expected_remaining_life_years
from macro_sim.demographics.macro_signal import DemoMacroSignal
from macro_sim.demographics.rates import Phase0VitalRates, expected_life_at_birth


def scaled(rates: Phase0VitalRates, m: float) -> Phase0VitalRates:
    return dataclasses.replace(
        rates,
        makeham_a=rates.makeham_a * m,
        gompertz_b=rates.gompertz_b * m,
        infant_extra=rates.infant_extra * m,
    )


def test_gm_family_is_closed_under_hazard_scaling():
    base = Phase0VitalRates()
    eff = scaled(base, 2.0)
    for age in (0.0, 0.4, 1.0, 30.0, 64.5, 85.0):
        # hazard x2 <=> survival^2, including the infant-extra overlap window
        assert eff.survival_probability(age, dt=1.0) == pytest.approx(
            base.survival_probability(age, dt=1.0) ** 2.0, rel=1e-12
        )


def test_bridge_derives_effective_rates_and_caches():
    base = Phase0VitalRates()

    @dataclass
    class _EconStub:
        demographic_rates: Any

    bridge = DemographicEconomicBridge(claims=None, household_to_account={}, econ=_EconStub(base))
    bridge.macro_signal = DemoMacroSignal()

    assert bridge.effective_vital_rates is base          # neutral: the base object itself

    bridge.macro_signal.mortality_mult = 1.3             # pin (elasticity 0 never recomputes)
    eff = bridge.effective_vital_rates
    assert eff is not base
    assert eff.makeham_a == pytest.approx(base.makeham_a * 1.3)
    assert eff.gompertz_b == pytest.approx(base.gompertz_b * 1.3)
    assert eff.infant_extra == pytest.approx(base.infant_extra * 1.3)
    assert bridge.effective_vital_rates is eff           # cached instance, stable identity
    assert bridge.e0_effective < expected_life_at_birth(base)


def test_kernel_death_rate_follows_effective_rates():
    @dataclass
    class _EconomicStateStub:
        effective_vital_rates: Any = None
        fertility_macro_multiplier: float = 1.0

    def run(mult: float | None, ticks: int = 120, seed: int = 23):
        rates = Phase0VitalRates()
        state = create_genesis_population(rates, n=600, seed=seed)
        kernel = MicroDemographicKernel(rates, rng_seed=seed + 1)
        stub = None if mult is None else _EconomicStateStub(
            effective_vital_rates=scaled(rates, mult) if mult != 1.0 else rates
        )
        for _ in range(ticks):
            kernel.tick(state, economic_state=stub)
        return state

    detached = run(None)
    neutral = run(1.0)
    heavy = run(20.0)
    assert [(e.tick, e.person_id) for e in detached.death_events] == [
        (e.tick, e.person_id) for e in neutral.death_events
    ]
    assert [(e.tick, e.person_id, e.mother_id) for e in detached.birth_events] == [
        (e.tick, e.person_id, e.mother_id) for e in neutral.birth_events
    ]
    assert len(heavy.death_events) > 4 * len(neutral.death_events)


def test_remaining_life_shrinks_under_higher_mortality():
    base = Phase0VitalRates()
    eff = scaled(base, 2.0)
    for age in (0, 30, 65, 80):
        assert expected_remaining_life_years(age, eff) < expected_remaining_life_years(age, base)


def test_parameterized_frozen_oracle_growth_falls_with_mortality():
    base = Phase0VitalRates()
    g_base = spectral_diagnostics(build_leslie_matrix(base), dt=base.dt).growth_rate
    g_heavy = spectral_diagnostics(build_leslie_matrix(scaled(base, 1.5)), dt=base.dt).growth_rate
    assert g_heavy < g_base
