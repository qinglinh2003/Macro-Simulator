from __future__ import annotations

from datetime import date

import pytest

from macro_sim.core.ledger import Ledger
from macro_sim.demographics.agents import DivorceEvent, MarriageEvent, Person
from macro_sim.demographics.economic_bridge import DemographicEconomicBridge
from macro_sim.demographics.economic_state import PersonClaimLedger
from macro_sim.demographics.estate import EstateRegistry
from macro_sim.demographics.marriage_economics import (
    dissolve_marriage,
    record_marriage_contract,
)


def test_marriage_records_basis_without_equalizing_claims():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=0, cash_claim=100.0)
    claims.add_person(2, household_id=0, cash_claim=20.0)
    event = MarriageEvent(tick=1, date=date(2000, 1, 2), spouse_a_id=1, spouse_b_id=2, household_id=0)

    contract = record_marriage_contract(event, claims)

    assert contract.basis_by_person[1] == 100.0
    assert contract.basis_by_person[2] == 20.0
    assert claims.net_worth(1) == pytest.approx(100.0)
    assert claims.net_worth(2) == pytest.approx(20.0)


def test_death_settles_community_property_before_estate_creation():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=0, cash_claim=100.0)
    claims.add_person(2, household_id=0, cash_claim=20.0)
    event = MarriageEvent(tick=1, date=date(2000, 1, 2), spouse_a_id=1, spouse_b_id=2, household_id=0)
    contract = record_marriage_contract(event, claims)
    claims.balance_sheet(1).cash_claim = 200.0
    claims.balance_sheet(2).cash_claim = 40.0
    before = claims.total_net_worth()

    result = dissolve_marriage(contract, claims, reason="death")

    assert claims.net_worth(1) == pytest.approx(160.0)
    assert claims.net_worth(2) == pytest.approx(80.0)
    assert result.transfers == [(1, 2, 40.0)]
    assert claims.total_net_worth() == pytest.approx(before)


class _Household:
    def __init__(self, account_id: str) -> None:
        self.id = account_id


class _Econ:
    def __init__(self) -> None:
        self.households = [_Household("H0"), _Household("H1")]
        self.ledger = Ledger({"H0": 100.0, "H1": 20.0, "BANK_0": 0.0})


class _State:
    def __init__(self, people) -> None:
        self.people = people


def _person(person_id: int, household_id: int) -> Person:
    return Person(
        id=person_id,
        age=30,
        sex="F" if person_id == 1 else "M",
        birth_date=date(1970, 1, 1),
        household_id=household_id,
    )


def test_bridge_marriage_hook_creates_joint_account_and_records_contract():
    econ = _Econ()
    p1 = _person(1, household_id=2)
    p2 = _person(2, household_id=2)
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0", 1: "H1"},
        estates=EstateRegistry(),
        econ=econ,
    )
    bridge.demographic_state = _State([p1, p2])
    bridge.claims.add_person(1, household_id=0, cash_claim=100.0)
    bridge.claims.add_person(2, household_id=1, cash_claim=20.0)
    event = MarriageEvent(tick=3, date=date(2000, 1, 4), spouse_a_id=1, spouse_b_id=2, household_id=2)

    bridge.on_marriage(event)

    assert 2 in bridge.household_to_account
    joint_account = bridge.account_for_household_id(2)
    assert econ.ledger.balance(joint_account) == pytest.approx(120.0)
    assert bridge.claims.balance_sheet(1).household_id == 2
    assert bridge.claims.balance_sheet(2).household_id == 2
    assert frozenset({1, 2}) in bridge.marriage_contracts
    bridge.assert_all_claim_identities(econ)


def test_bridge_divorce_hook_dissolves_contract_and_splits_households():
    econ = _Econ()
    p1 = _person(1, household_id=2)
    p2 = _person(2, household_id=2)
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0", 1: "H1"},
        estates=EstateRegistry(),
        econ=econ,
    )
    bridge.demographic_state = _State([p1, p2])
    bridge.claims.add_person(1, household_id=0, cash_claim=100.0)
    bridge.claims.add_person(2, household_id=1, cash_claim=20.0)
    bridge.on_marriage(MarriageEvent(3, date(2000, 1, 4), 1, 2, 2))

    p1.household_id = 3
    p2.household_id = 4
    event = DivorceEvent(4, date(2000, 1, 5), 1, 2, old_household_id=2, household_a_id=3, household_b_id=4)

    bridge.on_divorce(event)

    assert frozenset({1, 2}) not in bridge.marriage_contracts
    assert bridge.claims.balance_sheet(1).household_id == 3
    assert bridge.claims.balance_sheet(2).household_id == 4
    assert econ.ledger.balance(bridge.account_for_household_id(3)) == pytest.approx(100.0)
    assert econ.ledger.balance(bridge.account_for_household_id(4)) == pytest.approx(20.0)
    bridge.assert_all_claim_identities(econ)
