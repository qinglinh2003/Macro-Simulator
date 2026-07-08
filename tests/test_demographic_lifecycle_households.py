from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from macro_sim.core.ledger import Ledger
from macro_sim.demographics.agents import Person
from macro_sim.demographics.economic_bridge import initialize_person_claims_from_households
from macro_sim.demographics.lifecycle_households import (
    LifecycleHouseholdConfig,
    apply_leaving_home_dynamics,
)


class _LowRng:
    def random(self) -> float:
        return 0.0


@dataclass
class _State:
    people: list[Person]
    next_household_id: int = 1
    tick_index: int = 1
    current_date: date = date(2000, 1, 1)


@dataclass
class _Household:
    id: str


@dataclass
class _Econ:
    households: list[_Household]
    ledger: Ledger


def _person(person_id: int, age: int, household_id: int, **kwargs) -> Person:
    return Person(
        id=person_id,
        age=age,
        sex=kwargs.pop("sex", "F"),
        birth_date=date(2000 - age, 1, 1),
        household_id=household_id,
        **kwargs,
    )


def test_adult_child_leaves_home_and_keeps_parent_links():
    mother = _person(1, 50, 0)
    father = _person(2, 52, 0, sex="M")
    child = _person(3, 23, 0, mother_id=1, father_id=2)
    state = _State([mother, father, child])

    events = apply_leaving_home_dynamics(
        state,
        config=LifecycleHouseholdConfig(annual_leave_rate_peak=365.0),
        rng=_LowRng(),
    )

    assert events
    assert child.household_id != 0
    assert child.mother_id == 1
    assert child.father_id == 2


def test_bridge_creates_household_account_for_person_after_leaving_home():
    mother = _person(1, 50, 0)
    child = _person(2, 23, 0, mother_id=1)
    state = _State([mother, child])
    econ = _Econ(households=[_Household("H0")], ledger=Ledger({"H0": 100.0, "BANK_0": 0.0}))
    bridge = initialize_person_claims_from_households(econ, state)
    apply_leaving_home_dynamics(
        state,
        config=LifecycleHouseholdConfig(annual_leave_rate_peak=365.0),
        rng=_LowRng(),
    )

    account_id = bridge.create_household_for_person(child.id)

    assert account_id in econ.ledger.snapshot()
    assert bridge.account_for_household_id(child.household_id) == account_id
    assert bridge.claims.balance_sheet(child.id).household_id == child.household_id
