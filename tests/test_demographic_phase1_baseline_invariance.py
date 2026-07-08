from __future__ import annotations

from macro_sim.demographics import Phase0VitalRates, create_genesis_population
from macro_sim.demographics.economic_bridge import run_phase1_invariance_check
from macro_sim.demographics.kernel import MicroDemographicKernel


def _person_state(state):
    return [
        (p.id, p.alive, p.age, p.household_id, p.partner_id, p.mother_id, p.father_id)
        for p in state.people
    ]


def test_empty_economic_state_does_not_change_population_path():
    rates = Phase0VitalRates()
    base = create_genesis_population(rates, n=500, seed=11)
    with_bridge = create_genesis_population(rates, n=500, seed=11)

    base_kernel = MicroDemographicKernel(rates, rng_seed=12)
    bridge_kernel = MicroDemographicKernel(rates, rng_seed=12)

    for _ in range(365):
        assert base_kernel.tick(base) == bridge_kernel.tick(with_bridge, economic_state=object())

    assert _person_state(base) == _person_state(with_bridge)


def test_birth_death_economic_hooks_do_not_change_demographic_path():
    result = run_phase1_invariance_check(
        rates=Phase0VitalRates(),
        n=500,
        seed=21,
        years=1,
        enabled_channels=["birth_death_balance_sheet"],
    )

    assert result["event_sequence_equal"] is True
    assert result["alive_by_age_equal"] is True
    assert result["person_state_equal"] is True
