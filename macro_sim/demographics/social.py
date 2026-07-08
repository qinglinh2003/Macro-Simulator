"""Daily marriage, divorce, and guardianship dynamics for Phase 0 demography."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import exp
from typing import Protocol

import numpy as np

from macro_sim.demographics.agents import DivorceEvent, GuardianshipEvent, MarriageEvent, Person
from macro_sim.demographics.union import MEDIUM_FAMILY_FORMATION_PROFILE, UnionTargetProfile


class SocialState(Protocol):
    people: list[Person]
    tick_index: int
    current_date: date
    next_household_id: int
    public_guardian_household_id: int | None
    marriage_events: list[MarriageEvent]
    divorce_events: list[DivorceEvent]
    guardianship_events: list[GuardianshipEvent]


@dataclass(frozen=True)
class SocialDynamicsConfig:
    union_target_profile: UnionTargetProfile | None = field(default_factory=lambda: MEDIUM_FAMILY_FORMATION_PROFILE)
    marriage_enabled: bool = True
    marriage_min_age: int = 18
    marriage_max_age: int = 75
    marriage_peak_age: float = 28.0
    marriage_age_width: float = 9.0
    annual_marriage_rate_peak: float = 0.30
    remarriage_rate_multiplier: float = 0.65
    widowed_remarriage_multiplier: float = 0.75
    remarriage_cooldown_days: int = 365
    marriage_market_interval_days: int = 30
    marriage_age_gap_mean: float = 2.0
    marriage_age_gap_sd: float = 4.5
    marriage_max_age_gap: int = 18
    marriage_acceptance_base: float = 0.85
    marriage_age_gap_penalty: float = 0.06
    marriage_same_household_forbidden: bool = True
    marriage_close_kin_forbidden: bool = True

    divorce_enabled: bool = True
    annual_divorce_rate_base: float = 0.012
    divorce_peak_duration_years: float = 5.0
    divorce_duration_width: float = 4.0
    divorce_peak_multiplier: float = 2.0
    divorce_child_multiplier: float = 0.75
    divorce_age_gap_multiplier_per_10y: float = 1.25
    divorce_min_marriage_duration_days: int = 365

    custody_mother_priority: float = 0.75
    custody_keep_siblings_together: bool = True
    guardianship_enabled: bool = True
    guardian_search_grandparents: bool = True
    guardian_search_adult_siblings: bool = True
    guardian_search_same_household_adults: bool = True
    guardian_max_household_size: int = 8
    guardian_prefer_kin: bool = True


@dataclass(frozen=True)
class SocialHealthStats:
    alive: int
    adults: int
    minors: int
    married_adult_share: float
    bad_partner_links: int
    minor_household_missing: int
    public_guardian_minors: int
    marriages: int
    divorces: int
    guardianship_events: int


def social_health_snapshot(state: SocialState) -> SocialHealthStats:
    people_by_id = _people_by_id(state.people)
    alive = [person for person in state.people if person.alive]
    adults = [person for person in alive if person.age >= 18]
    minors = [person for person in alive if person.age < 18]
    married = [person for person in adults if person.partner_id is not None]
    bad_links = 0
    for person in married:
        partner = people_by_id.get(person.partner_id)
        if partner is None or not partner.alive or partner.partner_id != person.id:
            bad_links += 1
    public_guardian_minors = sum(
        1 for person in minors if person.household_id == state.public_guardian_household_id
    )
    return SocialHealthStats(
        alive=len(alive),
        adults=len(adults),
        minors=len(minors),
        married_adult_share=0.0 if not adults else float(len(married) / len(adults)),
        bad_partner_links=bad_links,
        minor_household_missing=sum(1 for person in minors if person.household_id is None),
        public_guardian_minors=public_guardian_minors,
        marriages=len(state.marriage_events),
        divorces=len(state.divorce_events),
        guardianship_events=len(state.guardianship_events),
    )


def initialize_social_state(state: SocialState) -> None:
    max_household = max((person.household_id for person in state.people if person.household_id is not None), default=-1)
    state.next_household_id = max(state.next_household_id, int(max_household) + 1)


def initialize_genesis_marriages(state: SocialState, rng: np.random.Generator) -> None:
    for person in state.people:
        if person.partner_id is None or person.id > person.partner_id:
            continue
        partner = _people_by_id(state.people).get(person.partner_id)
        if partner is None:
            continue
        years = int(rng.integers(1, 16))
        start = state.current_date.replace(year=state.current_date.year - years)
        person.marriage_start_date = start
        partner.marriage_start_date = start
        person.marriage_count = max(1, person.marriage_count)
        partner.marriage_count = max(1, partner.marriage_count)


def handle_partner_death(state: SocialState, dead: Person, people_by_id: dict[int, Person]) -> None:
    if dead.partner_id is None:
        return
    partner = people_by_id.get(dead.partner_id)
    if partner is not None and partner.alive and partner.partner_id == dead.id:
        partner.partner_id = None
        partner.marriage_start_date = None
        partner.last_widowed_date = state.current_date
    dead.partner_id = None
    dead.marriage_start_date = None


def repair_minor_guardianship(state: SocialState, *, reason: str = "guardian_repair") -> None:
    if not getattr(state, "people", None):
        return
    people_by_id = _people_by_id(state.people)
    adult_by_household = _adult_by_household(state.people)
    for child in [person for person in state.people if person.alive and person.age < 18]:
        if child.household_id in adult_by_household:
            if child.guardian_id is None:
                child.guardian_id = adult_by_household[child.household_id].id
            continue
        old_household_id = child.household_id
        guardian = _select_guardian(child, state.people, people_by_id, adult_by_household)
        if guardian is not None and guardian.household_id is not None:
            child.household_id = guardian.household_id
            child.guardian_id = guardian.id
            child.guardian_household_reason = reason
            event_reason = reason
        else:
            child.household_id = _public_guardian_household(state)
            child.guardian_id = None
            child.guardian_household_reason = "public_guardian"
            event_reason = "public_guardian"
        state.guardianship_events.append(
            GuardianshipEvent(
                tick=state.tick_index,
                date=state.current_date,
                child_id=child.id,
                old_household_id=old_household_id,
                new_household_id=child.household_id,
                guardian_id=child.guardian_id,
                reason=event_reason,
            )
        )


def apply_divorce_dynamics(
    state: SocialState,
    *,
    config: SocialDynamicsConfig,
    rng: np.random.Generator,
    dt_years: float,
) -> None:
    if not config.divorce_enabled:
        return
    people_by_id = _people_by_id(state.people)
    couples = [
        (person, people_by_id[person.partner_id])
        for person in state.people
        if person.alive
        and person.partner_id is not None
        and person.partner_id in people_by_id
        and person.id < person.partner_id
        and people_by_id[person.partner_id].alive
    ]
    minor_parent_ids_by_household = _minor_parent_ids_by_household(state.people)
    rng.shuffle(couples)
    for a, b in couples:
        if a.partner_id != b.id or b.partner_id != a.id:
            continue
        duration_days = _marriage_duration_days(a, state.current_date)
        if duration_days < config.divorce_min_marriage_duration_days:
            continue
        has_minor_child = bool(minor_parent_ids_by_household.get(a.household_id, set()) & {a.id, b.id})
        probability = min(1.0, _annual_divorce_rate(a, b, state.current_date, config, has_minor_child) * dt_years)
        if rng.random() < probability:
            _divorce_couple(state, a, b)


def apply_marriage_market(
    state: SocialState,
    *,
    config: SocialDynamicsConfig,
    rng: np.random.Generator,
) -> None:
    if not config.marriage_enabled:
        return
    if config.marriage_market_interval_days <= 0:
        return
    if state.tick_index % config.marriage_market_interval_days != 0:
        return
    interval_years = config.marriage_market_interval_days / 365.0
    entrants = [
        person
        for person in state.people
        if _eligible_for_marriage_market(person, state.current_date, config)
        and rng.random() < min(1.0, _annual_marriage_rate(person, state.current_date, config) * interval_years)
    ]
    females = [person for person in entrants if person.sex == "F"]
    males = [person for person in entrants if person.sex == "M"]
    rng.shuffle(females)
    rng.shuffle(males)
    unmatched_males = {person.id: person for person in males}
    for female in females:
        if female.partner_id is not None:
            continue
        candidate = _best_marriage_candidate(female, unmatched_males.values(), config)
        if candidate is None:
            continue
        age_gap = abs(candidate.age - female.age)
        acceptance = max(0.0, config.marriage_acceptance_base - config.marriage_age_gap_penalty * age_gap)
        if rng.random() > acceptance:
            continue
        unmatched_males.pop(candidate.id, None)
        _marry_pair(state, female, candidate)


def _divorce_couple(state: SocialState, a: Person, b: Person) -> None:
    old_household_id = a.household_id
    household_a = _new_household_id(state)
    household_b = _new_household_id(state)
    a.partner_id = None
    b.partner_id = None
    a.marriage_start_date = None
    b.marriage_start_date = None
    a.last_divorce_date = state.current_date
    b.last_divorce_date = state.current_date
    a.household_id = household_a
    b.household_id = household_b

    for child in [person for person in state.people if person.alive and person.age < 18 and person.household_id == old_household_id]:
        if child.mother_id == a.id:
            child.household_id = household_a
            child.guardian_id = a.id
        elif child.mother_id == b.id:
            child.household_id = household_b
            child.guardian_id = b.id
        elif child.father_id == a.id:
            child.household_id = household_a
            child.guardian_id = a.id
        elif child.father_id == b.id:
            child.household_id = household_b
            child.guardian_id = b.id
        else:
            child.household_id = household_a
            child.guardian_id = a.id
        child.guardian_household_reason = "divorce_custody"

    state.divorce_events.append(
        DivorceEvent(
            tick=state.tick_index,
            date=state.current_date,
            spouse_a_id=a.id,
            spouse_b_id=b.id,
            old_household_id=old_household_id,
            household_a_id=household_a,
            household_b_id=household_b,
        )
    )


def _marry_pair(state: SocialState, a: Person, b: Person) -> None:
    household_id = _new_household_id(state)
    old_households = {a.household_id, b.household_id}
    a.partner_id = b.id
    b.partner_id = a.id
    a.marriage_start_date = state.current_date
    b.marriage_start_date = state.current_date
    a.marriage_count += 1
    b.marriage_count += 1
    a.household_id = household_id
    b.household_id = household_id
    for child in state.people:
        if not child.alive or child.age >= 18:
            continue
        if child.household_id in old_households and (child.mother_id in {a.id, b.id} or child.father_id in {a.id, b.id} or child.guardian_id in {a.id, b.id}):
            child.household_id = household_id
            child.guardian_id = child.mother_id if child.mother_id in {a.id, b.id} else child.father_id
            child.guardian_household_reason = "parent_marriage"
    state.marriage_events.append(MarriageEvent(state.tick_index, state.current_date, a.id, b.id, household_id))


def _eligible_for_marriage_market(person: Person, current_date: date, config: SocialDynamicsConfig) -> bool:
    if not person.alive or person.partner_id is not None:
        return False
    if person.age < config.marriage_min_age or person.age > config.marriage_max_age:
        return False
    if person.last_divorce_date is not None and (current_date - person.last_divorce_date).days < config.remarriage_cooldown_days:
        return False
    return True


def _annual_marriage_rate(person: Person, current_date: date, config: SocialDynamicsConfig) -> float:
    age_years = person.age_years_on(current_date)
    if config.union_target_profile is not None:
        max_target = max((band.target_share for band in config.union_target_profile.bands), default=0.0)
        target = config.union_target_profile.target_share(int(age_years))
        rate = 0.0 if max_target <= 0.0 else config.annual_marriage_rate_peak * target / max_target
    else:
        hump = exp(-0.5 * ((age_years - config.marriage_peak_age) / config.marriage_age_width) ** 2)
        rate = config.annual_marriage_rate_peak * hump
    if person.last_divorce_date is not None or person.marriage_count > 0:
        rate *= config.remarriage_rate_multiplier
    if person.last_widowed_date is not None:
        rate *= config.widowed_remarriage_multiplier
    return rate


def _annual_divorce_rate(
    a: Person,
    b: Person,
    current_date: date,
    config: SocialDynamicsConfig,
    has_minor_child: bool,
) -> float:
    duration_years = _marriage_duration_days(a, current_date) / 365.0
    peak = exp(-0.5 * ((duration_years - config.divorce_peak_duration_years) / config.divorce_duration_width) ** 2)
    rate = config.annual_divorce_rate_base * (1.0 + (config.divorce_peak_multiplier - 1.0) * peak)
    if has_minor_child:
        rate *= config.divorce_child_multiplier
    age_gap = abs(a.age - b.age)
    rate *= config.divorce_age_gap_multiplier_per_10y ** (age_gap / 10.0)
    return rate


def _marriage_duration_days(person: Person, current_date: date) -> int:
    if person.marriage_start_date is None:
        return 3650
    return max(0, (current_date - person.marriage_start_date).days)


def _best_marriage_candidate(female: Person, males, config: SocialDynamicsConfig) -> Person | None:
    candidates = [
        male
        for male in males
        if _compatible_spouses(female, male, config)
    ]
    if not candidates:
        return None
    target_age = female.age + config.marriage_age_gap_mean
    return min(candidates, key=lambda male: (abs(male.age - target_age), abs(male.age - female.age), male.id))


def _compatible_spouses(a: Person, b: Person, config: SocialDynamicsConfig) -> bool:
    if a.sex == b.sex:
        return False
    if abs(a.age - b.age) > config.marriage_max_age_gap:
        return False
    if config.marriage_same_household_forbidden and a.household_id == b.household_id:
        return False
    if config.marriage_close_kin_forbidden and _close_kin(a, b):
        return False
    return True


def _close_kin(a: Person, b: Person) -> bool:
    parents_a = {a.mother_id, a.father_id} - {None}
    parents_b = {b.mother_id, b.father_id} - {None}
    if a.id in parents_b or b.id in parents_a:
        return True
    if parents_a & parents_b:
        return True
    return False


def _select_guardian(
    child: Person,
    people: list[Person],
    people_by_id: dict[int, Person],
    adult_by_household: dict[int, Person],
) -> Person | None:
    same_household = adult_by_household.get(child.household_id)
    if same_household is not None:
        return same_household
    for parent_id in (child.mother_id, child.father_id):
        parent = people_by_id.get(parent_id)
        if parent is not None and parent.alive and parent.age >= 18:
            return parent
    for parent_id in (child.mother_id, child.father_id):
        parent = people_by_id.get(parent_id)
        if parent is None:
            continue
        for grandparent_id in (parent.mother_id, parent.father_id):
            grandparent = people_by_id.get(grandparent_id)
            if grandparent is not None and grandparent.alive and grandparent.age >= 18:
                return grandparent
    for sibling in people:
        if not sibling.alive or sibling.id == child.id or sibling.age < 18:
            continue
        if child.mother_id is not None and sibling.mother_id == child.mother_id:
            return sibling
        if child.father_id is not None and sibling.father_id == child.father_id:
            return sibling
    return None


def _adult_by_household(people: list[Person]) -> dict[int, Person]:
    adults: dict[int, Person] = {}
    for person in people:
        if not person.alive or person.age < 18 or person.household_id is None:
            continue
        current = adults.get(person.household_id)
        if current is None or person.id < current.id:
            adults[person.household_id] = person
    return adults


def _minor_parent_ids_by_household(people: list[Person]) -> dict[int, set[int]]:
    index: dict[int, set[int]] = {}
    for person in people:
        if not person.alive or person.age >= 18 or person.household_id is None:
            continue
        parents = index.setdefault(person.household_id, set())
        if person.mother_id is not None:
            parents.add(person.mother_id)
        if person.father_id is not None:
            parents.add(person.father_id)
    return index


def _public_guardian_household(state: SocialState) -> int:
    if state.public_guardian_household_id is None:
        state.public_guardian_household_id = _new_household_id(state)
    return state.public_guardian_household_id


def _new_household_id(state: SocialState) -> int:
    household_id = state.next_household_id
    state.next_household_id += 1
    return household_id


def _people_by_id(people: list[Person]) -> dict[int, Person]:
    return {person.id: person for person in people}
