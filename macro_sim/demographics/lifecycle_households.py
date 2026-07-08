"""Lifecycle household transitions such as adult children leaving home."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LifecycleHouseholdConfig:
    leave_home_min_age: int = 22
    leave_home_peak_end_age: int = 30
    annual_leave_rate_peak: float = 0.25
    annual_leave_rate_late: float = 0.05


@dataclass(frozen=True)
class LeavingHomeEvent:
    tick: int
    date: object
    person_id: int
    old_household_id: int
    new_household_id: int


def _parent_ids(person: Any) -> set[int]:
    return {
        int(parent_id)
        for parent_id in (getattr(person, "mother_id", None), getattr(person, "father_id", None))
        if parent_id is not None
    }


def _lives_with_parent(person: Any, people_by_id: dict[int, Any]) -> bool:
    return any(
        parent_id in people_by_id
        and getattr(people_by_id[parent_id], "alive", True)
        and getattr(people_by_id[parent_id], "household_id", None) == getattr(person, "household_id", None)
        for parent_id in _parent_ids(person)
    )


def apply_leaving_home_dynamics(state: Any, config: LifecycleHouseholdConfig, rng: Any) -> list[LeavingHomeEvent]:
    people_by_id = {int(person.id): person for person in getattr(state, "people", [])}
    events: list[LeavingHomeEvent] = []
    for person in list(people_by_id.values()):
        if not getattr(person, "alive", True):
            continue
        if getattr(person, "partner_id", None) is not None:
            continue
        if int(getattr(person, "age", 0)) < config.leave_home_min_age:
            continue
        if getattr(person, "household_id", None) is None:
            continue
        if not _lives_with_parent(person, people_by_id):
            continue
        annual_rate = (
            config.annual_leave_rate_peak
            if int(person.age) <= config.leave_home_peak_end_age
            else config.annual_leave_rate_late
        )
        if rng.random() >= min(1.0, max(0.0, annual_rate / 365.0)):
            continue
        old_household_id = int(person.household_id)
        new_household_id = int(getattr(state, "next_household_id", 0))
        state.next_household_id = new_household_id + 1
        person.household_id = new_household_id
        events.append(
            LeavingHomeEvent(
                tick=int(getattr(state, "tick_index", 0)),
                date=getattr(state, "current_date", None),
                person_id=int(person.id),
                old_household_id=old_household_id,
                new_household_id=new_household_id,
            )
        )
    return events
