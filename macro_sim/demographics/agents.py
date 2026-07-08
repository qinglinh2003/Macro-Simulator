"""Person records and demographic events for the Phase 0 population kernel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def _same_month_day_in_year(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


@dataclass
class Person:
    id: int
    age: int
    sex: str
    birth_date: date
    alive: bool = True
    mother_id: int | None = None
    father_id: int | None = None
    household_id: int | None = None
    partner_id: int | None = None
    guardian_id: int | None = None
    guardian_household_reason: str | None = None
    marriage_start_date: date | None = None
    marriage_count: int = 0
    last_divorce_date: date | None = None
    last_widowed_date: date | None = None
    death_tick: int | None = None

    def completed_age_on(self, current_date: date) -> int:
        birthday_this_year = _same_month_day_in_year(self.birth_date, current_date.year)
        years = current_date.year - self.birth_date.year
        if birthday_this_year > current_date:
            years -= 1
        return years

    def age_years_on(self, current_date: date) -> float:
        completed = self.completed_age_on(current_date)
        last_birthday = _same_month_day_in_year(self.birth_date, current_date.year)
        if last_birthday > current_date:
            last_birthday = _same_month_day_in_year(self.birth_date, current_date.year - 1)
        next_birthday = _same_month_day_in_year(self.birth_date, last_birthday.year + 1)
        age_year_days = max(1, (next_birthday - last_birthday).days)
        elapsed_days = (current_date - last_birthday).days
        return float(completed + elapsed_days / age_year_days)


@dataclass(frozen=True)
class BirthEvent:
    tick: int
    date: date
    person_id: int
    mother_id: int | None
    father_id: int | None


@dataclass(frozen=True)
class DeathEvent:
    tick: int
    date: date
    person_id: int
    age: int


@dataclass(frozen=True)
class MarriageEvent:
    tick: int
    date: date
    spouse_a_id: int
    spouse_b_id: int
    household_id: int


@dataclass(frozen=True)
class DivorceEvent:
    tick: int
    date: date
    spouse_a_id: int
    spouse_b_id: int
    old_household_id: int | None
    household_a_id: int
    household_b_id: int


@dataclass(frozen=True)
class GuardianshipEvent:
    tick: int
    date: date
    child_id: int
    old_household_id: int | None
    new_household_id: int
    guardian_id: int | None
    reason: str
