import sys
from datetime import date
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import Phase0VitalRates, create_genesis_population
from macro_sim.demographics.kernel import MicroDemographicKernel
from macro_sim.demographics.social import SocialDynamicsConfig


def _high_marital_curve(rates: Phase0VitalRates) -> np.ndarray:
    curve = np.zeros(rates.omega + 1, dtype=float)
    curve[15:50] = 500.0
    return curve


def test_married_only_fertility_blocks_births_from_single_women():
    rates = Phase0VitalRates(makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    state = create_genesis_population(rates, n=2_500, seed=81, start_date=date(2001, 1, 1))
    for person in state.people:
        person.partner_id = None
        person.marriage_start_date = None
    kernel = MicroDemographicKernel(
        rates,
        rng_seed=82,
        social_config=SocialDynamicsConfig(marriage_enabled=False, divorce_enabled=False),
        fertility_mode="married_only",
        marital_fertility_curve=_high_marital_curve(rates),
    )

    births = sum(kernel.tick(state).births for _ in range(10))

    assert births == 0
    assert not state.birth_events


def test_married_only_is_default_fertility_mode():
    rates = Phase0VitalRates()
    kernel = MicroDemographicKernel(rates, rng_seed=1)

    assert kernel.fertility_mode == "married_only"
    assert kernel.marital_fertility_curve is not None


def test_married_only_fertility_assigns_father_for_every_newborn():
    rates = Phase0VitalRates(makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    state = create_genesis_population(rates, n=2_500, seed=91, start_date=date(2001, 1, 1))
    kernel = MicroDemographicKernel(
        rates,
        rng_seed=92,
        social_config=SocialDynamicsConfig(marriage_enabled=False, divorce_enabled=False),
        fertility_mode="married_only",
        marital_fertility_curve=_high_marital_curve(rates),
    )

    births = 0
    for _ in range(10):
        births += kernel.tick(state).births
        if births:
            break

    newborns = [person for person in state.people if person.id >= 2_500]
    assert births > 0
    assert newborns
    assert all(person.mother_id is not None for person in newborns)
    assert all(person.father_id is not None for person in newborns)
    assert all(event.father_id is not None for event in state.birth_events)
