import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import Phase0VitalRates, build_leslie_matrix, create_genesis_population, stable_age_distribution
from macro_sim.demographics.agents import Person
from macro_sim.demographics.kernel import GenesisState, MicroDemographicKernel
from macro_sim.demographics.phase0 import generate_phase0_artifacts


def _minimal_state(person: Person, *, current_date: date, rates: Phase0VitalRates) -> GenesisState:
    matrix = build_leslie_matrix(rates)
    return GenesisState(
        rates=rates,
        people=[person],
        leslie_matrix=matrix,
        stable_distribution=stable_age_distribution(matrix),
        rng_seed=0,
        current_date=current_date,
        next_person_id=person.id + 1,
    )


def test_genesis_assigns_birth_dates_matching_completed_ages():
    start_date = date(2001, 1, 1)
    state = create_genesis_population(Phase0VitalRates(), n=5_000, seed=11, start_date=start_date)

    assert state.current_date == start_date
    assert all(person.birth_date <= start_date for person in state.people)
    assert all(person.completed_age_on(start_date) == person.age for person in state.people)
    assert len({person.birth_date for person in state.people}) > 365


def test_daily_tick_advances_calendar_and_updates_age_on_birthday():
    rates = Phase0VitalRates(makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0, tfr=0.0)
    person = Person(id=0, age=17, sex="F", birth_date=date(1983, 1, 2))
    state = _minimal_state(person, current_date=date(2001, 1, 1), rates=rates)
    kernel = MicroDemographicKernel(rates, rng_seed=0, fertility_mode="all_women")

    result = kernel.tick(state)

    assert state.current_date == date(2001, 1, 2)
    assert result.tick == 1
    assert person.age == 18
    assert person.age_years_on(state.current_date) == 18.0


def test_daily_birth_events_use_current_date_and_mother_household():
    rates = Phase0VitalRates(tfr=1000.0, makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    state = create_genesis_population(rates, n=2_500, seed=31, start_date=date(2001, 1, 1))
    kernel = MicroDemographicKernel(rates, rng_seed=7, fertility_mode="all_women")

    births = 0
    for _ in range(10):
        births += kernel.tick(state).births
        if births:
            break

    assert births > 0
    newborns = [person for person in state.people if person.id >= 2_500]
    assert newborns
    assert all(person.birth_date == state.current_date for person in newborns)
    assert all(person.age == 0 for person in newborns)
    assert all(event.date == state.current_date for event in state.birth_events)


def test_phase0_artifacts_include_current_date(tmp_path):
    metrics = generate_phase0_artifacts(output_dir=tmp_path, n=1_000, seed=22, start_date=date(2001, 1, 1))

    assert metrics["current_date"] == "2001-01-01"
    written = json.loads((tmp_path / "metrics.json").read_text())
    assert written["current_date"] == "2001-01-01"
