"""Phase 2.1: the kernel's fertility hazard responds to the macro multiplier.

The multiplier reaches the kernel as `economic_state.fertility_macro_multiplier`
(a single population-wide scalar). These tests drive the kernel with a stub
economic state -- the signal that produces the scalar is tested separately in
test_demographic_macro_signal.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from macro_sim.demographics.kernel import MicroDemographicKernel, create_genesis_population
from macro_sim.demographics.rates import Phase0VitalRates


@dataclass
class _EconomicStateStub:
    fertility_macro_multiplier: float = 1.0


def run_kernel(multiplier: float | None, *, n: int = 600, ticks: int = 120, seed: int = 11):
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=n, seed=seed)
    kernel = MicroDemographicKernel(rates, rng_seed=seed + 1)
    economic_state = None if multiplier is None else _EconomicStateStub(multiplier)
    for _ in range(ticks):
        kernel.tick(state, economic_state=economic_state)
    return state


def test_zero_multiplier_stops_all_births():
    state = run_kernel(0.0)
    assert len(state.birth_events) == 0
    assert len(state.death_events) > 0      # mortality is untouched by the fertility channel


def test_high_multiplier_scales_births_up():
    baseline = run_kernel(1.0)
    boosted = run_kernel(8.0)
    assert len(baseline.birth_events) > 0
    assert len(boosted.birth_events) > 4 * len(baseline.birth_events)


def test_neutral_multiplier_is_bit_identical_to_no_economic_state():
    detached = run_kernel(None)
    neutral = run_kernel(1.0)
    assert [(e.tick, e.person_id, e.mother_id) for e in detached.birth_events] == [
        (e.tick, e.person_id, e.mother_id) for e in neutral.birth_events
    ]
    assert [(e.tick, e.person_id) for e in detached.death_events] == [
        (e.tick, e.person_id) for e in neutral.death_events
    ]
    assert [(e.tick, tuple(sorted(e.partner_ids))) for e in detached.marriage_events] == [
        (e.tick, tuple(sorted(e.partner_ids))) for e in neutral.marriage_events
    ]


def test_bridge_without_signal_reports_neutral_multiplier():
    from macro_sim.demographics.economic_bridge import DemographicEconomicBridge

    bridge = DemographicEconomicBridge(claims=None, household_to_account={})
    assert bridge.fertility_macro_multiplier == 1.0
    assert bridge.mortality_macro_multiplier == 1.0
