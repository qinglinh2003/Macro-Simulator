import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import Phase0VitalRates, create_genesis_population
from macro_sim.demographics.agents import Person
from macro_sim.demographics.kernel import MicroDemographicKernel
from macro_sim.demographics.social import SocialDynamicsConfig, _annual_marriage_rate, social_health_snapshot


def _people_by_id(state):
    return {person.id: person for person in state.people}


def test_marriage_market_creates_bidirectional_partner_and_household():
    rates = Phase0VitalRates(makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    cfg = SocialDynamicsConfig(
        marriage_enabled=True,
        divorce_enabled=False,
        annual_marriage_rate_peak=365.0,
        marriage_market_interval_days=1,
        marriage_min_age=18,
        marriage_max_age=90,
        remarriage_cooldown_days=0,
    )
    state = create_genesis_population(rates, n=3_000, seed=41, start_date=date(2001, 1, 1))
    for person in state.people:
        person.partner_id = None
        person.marriage_start_date = None
        person.marriage_count = 0
        person.last_divorce_date = None
        person.last_widowed_date = None
    kernel = MicroDemographicKernel(rates, rng_seed=42, social_config=cfg, fertility_mode="all_women")

    kernel.tick(state)

    assert state.marriage_events
    event = state.marriage_events[0]
    people = _people_by_id(state)
    a = people[event.spouse_a_id]
    b = people[event.spouse_b_id]
    assert a.partner_id == b.id
    assert b.partner_id == a.id
    assert a.household_id == event.household_id
    assert b.household_id == event.household_id
    assert a.household_id == b.household_id
    assert a.marriage_start_date == state.current_date
    assert b.marriage_start_date == state.current_date
    assert a.marriage_count == 1
    assert b.marriage_count == 1


def test_divorce_splits_partners_and_keeps_minors_placed():
    rates = Phase0VitalRates(makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    cfg = SocialDynamicsConfig(
        marriage_enabled=False,
        divorce_enabled=True,
        annual_divorce_rate_base=365.0,
        divorce_min_marriage_duration_days=0,
    )
    state = create_genesis_population(rates, n=4_000, seed=51, start_date=date(2001, 1, 1))
    couple = next(
        (person, _people_by_id(state)[person.partner_id])
        for person in state.people
        if person.partner_id is not None and person.id < person.partner_id
    )
    spouse_a, spouse_b = couple
    spouse_a.marriage_start_date = state.current_date - timedelta(days=2000)
    spouse_b.marriage_start_date = spouse_a.marriage_start_date
    old_household = spouse_a.household_id
    kernel = MicroDemographicKernel(rates, rng_seed=52, social_config=cfg, fertility_mode="all_women")

    kernel.tick(state)

    assert state.divorce_events
    people = _people_by_id(state)
    assert people[spouse_a.id].partner_id is None
    assert people[spouse_b.id].partner_id is None
    assert people[spouse_a.id].household_id != people[spouse_b.id].household_id
    event = next(
        event
        for event in state.divorce_events
        if {event.spouse_a_id, event.spouse_b_id} == {spouse_a.id, spouse_b.id}
    )
    assert event.old_household_id == old_household
    assert all(person.household_id is not None for person in state.people if person.alive and person.age < 18)


def test_orphaned_minor_moves_to_public_guardian_household():
    rates = Phase0VitalRates(tfr=0.0, makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    cfg = SocialDynamicsConfig(marriage_enabled=False, divorce_enabled=False)
    start = date(2001, 1, 1)
    mother = Person(id=0, age=40, sex="F", birth_date=date(1961, 1, 1), household_id=0, partner_id=1)
    father = Person(id=1, age=42, sex="M", birth_date=date(1959, 1, 1), household_id=0, partner_id=0)
    child = Person(id=2, age=8, sex="F", birth_date=date(1992, 7, 1), household_id=0, mother_id=0, father_id=1)
    state = create_genesis_population(rates, n=10, seed=61, start_date=start, build_relationships=False)
    state.people = [mother, father, child]
    state.next_person_id = 3
    state.next_household_id = 1
    kernel = MicroDemographicKernel(rates, rng_seed=62, social_config=cfg, fertility_mode="all_women")

    mother.alive = False
    father.alive = False
    kernel.repair_guardianships(state, reason="parent_death")

    assert child.household_id == state.public_guardian_household_id
    assert child.guardian_id is None
    assert child.guardian_household_reason == "public_guardian"
    assert state.guardianship_events
    assert state.guardianship_events[-1].child_id == child.id
    assert state.guardianship_events[-1].reason == "public_guardian"


def test_social_health_snapshot_reports_relationship_invariants():
    rates = Phase0VitalRates(makeham_a=0.0, gompertz_b=0.0, infant_extra=0.0)
    state = create_genesis_population(rates, n=2_000, seed=101, start_date=date(2001, 1, 1))
    kernel = MicroDemographicKernel(rates, rng_seed=102, fertility_mode="all_women")
    for _ in range(60):
        kernel.tick(state)

    snapshot = social_health_snapshot(state)

    assert 0.0 <= snapshot.married_adult_share <= 1.0
    assert snapshot.bad_partner_links == 0
    assert snapshot.minor_household_missing == 0
    assert snapshot.alive == state.alive_count


def test_default_marriage_entry_rates_follow_union_profile_shape():
    cfg = SocialDynamicsConfig()
    current_date = date(2020, 1, 1)
    age22 = Person(id=1, age=22, sex="F", birth_date=date(1998, 1, 1))
    age42 = Person(id=2, age=42, sex="F", birth_date=date(1978, 1, 1))
    age58 = Person(id=3, age=58, sex="F", birth_date=date(1962, 1, 1))

    young_rate = _annual_marriage_rate(age22, current_date, cfg)
    prime_rate = _annual_marriage_rate(age42, current_date, cfg)
    mature_rate = _annual_marriage_rate(age58, current_date, cfg)

    assert prime_rate > young_rate
    assert mature_rate > young_rate


def test_default_marriage_dynamics_do_not_collapse_below_realistic_union_floor():
    rates = Phase0VitalRates()
    state = create_genesis_population(rates, n=600, seed=333, start_date=date(2001, 1, 1))
    kernel = MicroDemographicKernel(rates, rng_seed=334)

    while state.current_date < date(2021, 1, 1):
        kernel.tick(state)

    snapshot = social_health_snapshot(state)

    assert 0.40 < snapshot.married_adult_share < 0.70
    assert snapshot.bad_partner_links == 0
    assert snapshot.minor_household_missing == 0
