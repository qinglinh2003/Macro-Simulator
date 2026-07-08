from __future__ import annotations

from datetime import date

import pytest

from macro_sim.demographics.agents import Person
from macro_sim.demographics.estate import EstateRecord
from macro_sim.demographics.economic_state import PersonClaimLedger
from macro_sim.demographics.inheritance import HeirDistribution, select_default_heirs, settle_estate


def _person(person_id: int, age: int = 40, **kwargs) -> Person:
    return Person(
        id=person_id,
        age=age,
        sex=kwargs.pop("sex", "F"),
        birth_date=date(2000 - age, 1, 1),
        **kwargs,
    )


def test_estate_transfers_to_spouse_and_children_without_changing_total_private_wealth():
    claims = PersonClaimLedger()
    for person_id in [1, 2, 3, 4]:
        claims.add_person(person_id, household_id=0)
    estate = EstateRecord(dead_person_id=1, net_worth=100.0, created_tick=10)
    claims.register_estate_suspense(estate.net_worth)
    before = claims.total_net_worth(include_estates=True)

    settle_estate(estate, heirs=HeirDistribution(spouse_id=2, child_ids=[3, 4]), claims=claims)

    assert claims.net_worth(1) == 0.0
    assert claims.net_worth(2) == pytest.approx(50.0)
    assert claims.net_worth(3) == pytest.approx(25.0)
    assert claims.net_worth(4) == pytest.approx(25.0)
    assert claims.total_net_worth(include_estates=True) == pytest.approx(before)
    assert estate.cleared is True


def test_default_heirs_choose_spouse_and_living_children():
    dead = _person(1, partner_id=2)
    people_by_id = {
        1: dead,
        2: _person(2, sex="M"),
        3: _person(3, age=12, mother_id=1, father_id=2),
        4: _person(4, age=10, mother_id=1, father_id=2),
        5: _person(5, age=8, mother_id=1, father_id=99, alive=False),
    }

    heirs = select_default_heirs(dead, people_by_id)

    assert heirs.spouse_id == 2
    assert heirs.child_ids == [3, 4]


def test_estate_without_heirs_moves_to_public_estate_account():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=0)
    estate = EstateRecord(dead_person_id=1, net_worth=40.0, created_tick=10)
    claims.register_estate_suspense(estate.net_worth)

    settle_estate(estate, heirs=HeirDistribution(), claims=claims, public_estate_account_id=999)

    assert claims.net_worth(999) == pytest.approx(40.0)
    assert estate.cleared is True
