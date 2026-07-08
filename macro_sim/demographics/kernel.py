"""Genesis sampling and stochastic Phase 0 demographic ticks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Literal

import numpy as np

from macro_sim.demographics.agents import BirthEvent, DeathEvent, DivorceEvent, GuardianshipEvent, MarriageEvent, Person
from macro_sim.demographics.leslie import LeslieOracle, build_leslie_matrix, spectral_diagnostics, stable_age_distribution
from macro_sim.demographics.multistate import (
    MultiStateIndex,
    build_multistate_leslie_matrix,
    calibrate_marital_fertility_curve,
    stable_multistate_distribution,
)
from macro_sim.demographics.rates import Phase0VitalRates
from macro_sim.demographics.relationships import RelationshipConfig, RelationshipStats, build_genesis_relationships
from macro_sim.demographics.social import (
    SocialDynamicsConfig,
    apply_divorce_dynamics,
    apply_marriage_market,
    handle_partner_death,
    initialize_genesis_marriages,
    initialize_social_state,
    repair_minor_guardianship,
)


BirthHook = Callable[[BirthEvent, Person], None]
DeathHook = Callable[[DeathEvent, Person], None]
FertilityMode = Literal["all_women", "married_only"]
DEFAULT_START_DATE = date(2000, 1, 1)


@dataclass
class TickResult:
    tick: int
    old_headcount: int
    births: int
    deaths: int
    new_headcount: int


@dataclass
class GenesisState:
    rates: Phase0VitalRates
    people: list[Person]
    leslie_matrix: np.ndarray
    stable_distribution: np.ndarray
    rng_seed: int
    current_date: date = DEFAULT_START_DATE
    tick_index: int = 0
    next_person_id: int = 0
    birth_events: list[BirthEvent] = field(default_factory=list)
    death_events: list[DeathEvent] = field(default_factory=list)
    marriage_events: list[MarriageEvent] = field(default_factory=list)
    divorce_events: list[DivorceEvent] = field(default_factory=list)
    guardianship_events: list[GuardianshipEvent] = field(default_factory=list)
    relationship_stats: RelationshipStats | None = None
    next_household_id: int = 0
    public_guardian_household_id: int | None = None

    @property
    def alive_count(self) -> int:
        return sum(1 for person in self.people if person.alive)

    def oracle(self) -> LeslieOracle:
        return LeslieOracle(self.leslie_matrix, count_alive_by_age(self.people, self.rates.omega).astype(float))


def count_alive_by_age(people: list[Person], omega: int) -> np.ndarray:
    counts = np.zeros(omega + 1, dtype=int)
    for person in people:
        if person.alive:
            counts[min(person.age, omega)] += 1
    return counts


def _same_month_day_in_year(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def _add_years(day: date, years: int) -> date:
    return _same_month_day_in_year(day, day.year + years)


def _birth_date_for_completed_age(age: int, current_date: date, rng: np.random.Generator) -> date:
    earliest = _add_years(current_date, -(age + 1)) + timedelta(days=1)
    latest = _add_years(current_date, -age)
    span_days = (latest - earliest).days + 1
    return earliest + timedelta(days=int(rng.integers(0, span_days)))


def _days_in_calendar_year(day: date) -> int:
    return (date(day.year + 1, 1, 1) - date(day.year, 1, 1)).days


def _draw_sex(rng: np.random.Generator, rates: Phase0VitalRates) -> str:
    return "F" if rng.random() < rates.female_birth_share else "M"


def create_genesis_population(
    rates: Phase0VitalRates,
    *,
    n: int = 40_000,
    seed: int = 0,
    start_date: date = DEFAULT_START_DATE,
    build_relationships: bool = True,
    relationship_config: RelationshipConfig | None = None,
) -> GenesisState:
    if n <= 0:
        raise ValueError("n must be positive")
    rng = np.random.default_rng(seed)
    matrix = build_leslie_matrix(rates)
    stable = stable_age_distribution(matrix)
    ages = rng.choice(np.arange(rates.omega + 1), size=n, p=stable)
    people = [
        Person(
            id=idx,
            age=int(age),
            sex=_draw_sex(rng, rates),
            birth_date=_birth_date_for_completed_age(int(age), start_date, rng),
        )
        for idx, age in enumerate(ages)
    ]
    relationship_stats = None
    if build_relationships:
        relationship_stats = build_genesis_relationships(
            people,
            config=relationship_config,
            seed=seed + 10_003,
        )
    state = GenesisState(
        rates=rates,
        people=people,
        leslie_matrix=matrix,
        stable_distribution=stable,
        rng_seed=seed,
        current_date=start_date,
        next_person_id=n,
        relationship_stats=relationship_stats,
    )
    initialize_social_state(state)
    initialize_genesis_marriages(state, rng)
    return state


class MicroDemographicKernel:
    """Stochastic person-level kernel under frozen-economy Phase 0 rates."""

    def __init__(
        self,
        rates: Phase0VitalRates,
        *,
        rng_seed: int,
        on_birth: BirthHook | None = None,
        on_death: DeathHook | None = None,
        social_config: SocialDynamicsConfig | None = None,
        fertility_mode: FertilityMode = "married_only",
        marital_fertility_curve: np.ndarray | None = None,
    ) -> None:
        self.rates = rates
        self.rng = np.random.default_rng(rng_seed)
        self.on_birth = on_birth or (lambda event, person: None)
        self.on_death = on_death or (lambda event, person: None)
        self.social_config = social_config or SocialDynamicsConfig()
        if fertility_mode not in ("all_women", "married_only"):
            raise ValueError("fertility_mode must be 'all_women' or 'married_only'")
        self.fertility_mode = fertility_mode
        self.marital_fertility_curve = (
            _default_marital_fertility_curve(rates, self.social_config)
            if fertility_mode == "married_only" and marital_fertility_curve is None
            else marital_fertility_curve
        )

    def tick(self, state: GenesisState) -> TickResult:
        state.tick_index += 1
        tick = state.tick_index
        state.current_date = state.current_date + timedelta(days=1)
        dt_years = 1.0 / _days_in_calendar_year(state.current_date)
        old_headcount = state.alive_count
        existing = [person for person in state.people if person.alive]
        people_by_id = {person.id: person for person in state.people}

        for person in existing:
            person.age = min(person.completed_age_on(state.current_date), self.rates.omega)

        deaths = 0
        for person in existing:
            if person.age >= self.rates.omega:
                survives = False
            else:
                survives = self.rng.random() < self.rates.survival_probability(
                    person.age_years_on(state.current_date),
                    dt=dt_years,
                )
            if survives:
                person.age = min(person.completed_age_on(state.current_date), self.rates.omega)
            else:
                person.alive = False
                person.death_tick = tick
                deaths += 1
                handle_partner_death(state, person, people_by_id)
                event = DeathEvent(tick=tick, date=state.current_date, person_id=person.id, age=person.age)
                state.death_events.append(event)
                self.on_death(event, person)

        if self.social_config.guardianship_enabled and deaths > 0:
            repair_minor_guardianship(state, reason="parent_death")
        divorce_count_before = len(state.divorce_events)
        apply_divorce_dynamics(state, config=self.social_config, rng=self.rng, dt_years=dt_years)
        if self.social_config.guardianship_enabled and len(state.divorce_events) > divorce_count_before:
            repair_minor_guardianship(state, reason="divorce_custody")
        apply_marriage_market(state, config=self.social_config, rng=self.rng)

        people_by_id = {person.id: person for person in state.people}
        births: list[Person] = []
        for person in [candidate for candidate in state.people if candidate.alive]:
            if person.sex != "F" or person.age > self.rates.omega:
                continue
            father_id = _birth_father_id(person, people_by_id)
            annual_fertility = self._annual_fertility_rate(person, state.current_date, father_id)
            if annual_fertility <= 0.0:
                continue
            birth_count = int(self.rng.poisson(annual_fertility * dt_years))
            for _ in range(birth_count):
                newborn = Person(
                    id=state.next_person_id,
                    age=0,
                    sex=_draw_sex(self.rng, self.rates),
                    birth_date=state.current_date,
                    mother_id=person.id,
                    father_id=father_id,
                    household_id=person.household_id,
                    guardian_id=person.id,
                    guardian_household_reason="birth",
                )
                state.next_person_id += 1
                event = BirthEvent(
                    tick=tick,
                    date=state.current_date,
                    person_id=newborn.id,
                    mother_id=person.id,
                    father_id=father_id,
                )
                state.birth_events.append(event)
                self.on_birth(event, newborn)
                births.append(newborn)

        state.people.extend(births)
        new_headcount = state.alive_count
        if new_headcount != old_headcount + len(births) - deaths:
            raise AssertionError("person headcount stock-flow identity failed")
        return TickResult(
            tick=tick,
            old_headcount=old_headcount,
            births=len(births),
            deaths=deaths,
            new_headcount=new_headcount,
        )

    def repair_guardianships(self, state: GenesisState, *, reason: str = "guardian_repair") -> None:
        repair_minor_guardianship(state, reason=reason)

    def _annual_fertility_rate(self, mother: Person, current_date: date, father_id: int | None) -> float:
        age_years = mother.age_years_on(current_date)
        if self.fertility_mode == "all_women":
            return self.rates.fertility_rate(age_years)
        if father_id is None:
            return 0.0
        assert self.marital_fertility_curve is not None
        return _curve_rate(self.marital_fertility_curve, age_years)


def _birth_father_id(mother: Person, people_by_id: dict[int, Person]) -> int | None:
    if mother.partner_id is None:
        return None
    partner = people_by_id.get(mother.partner_id)
    if partner is None or not partner.alive or partner.sex != "M":
        return None
    return partner.id


def _curve_rate(curve: np.ndarray, age_years: float) -> float:
    if age_years < 0.0 or age_years > len(curve) - 1:
        return 0.0
    return float(np.interp(age_years, np.arange(len(curve), dtype=float), curve))


def _default_marital_fertility_curve(rates: Phase0VitalRates, social_config: SocialDynamicsConfig) -> np.ndarray:
    if rates.tfr <= 0.0:
        return np.zeros(rates.omega + 1, dtype=float)
    index = MultiStateIndex(rates.omega)
    matrix = build_multistate_leslie_matrix(rates, social_config, index=index)
    stable = stable_multistate_distribution(matrix)
    return calibrate_marital_fertility_curve(rates, stable, index)


def phase0_summary(rates: Phase0VitalRates) -> dict[str, float]:
    matrix = build_leslie_matrix(rates)
    diag = spectral_diagnostics(matrix, dt=rates.dt)
    return {
        "lambda1": diag.lambda1,
        "growth_rate": diag.growth_rate,
        "damping_ratio": diag.damping_ratio,
        "cycle_period": diag.cycle_period or float("nan"),
    }
