from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from macro_sim.demographics.economic_state import (
    PersonClaimLedger,
    build_household_economic_profiles,
    labor_supply_for_person,
    need_weight_for_person,
)


@dataclass
class _PersonStub:
    id: int
    age: int
    household_id: int = 0
    alive: bool = True


@dataclass
class _StateStub:
    people: list[_PersonStub]
    current_date: date = date(2000, 1, 1)


def test_person_claims_sum_to_household_deposits_and_debt():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=10, cash_claim=60.0, debt_claim=5.0)
    claims.add_person(2, household_id=10, cash_claim=40.0, debt_claim=15.0)

    claims.assert_household_claim_identity(
        household_id=10,
        deposits=100.0,
        debt=20.0,
        holdings={},
    )


def test_claim_identity_rejects_unbacked_cash():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=10, cash_claim=101.0)

    with pytest.raises(AssertionError, match="cash claim mismatch"):
        claims.assert_household_claim_identity(
            household_id=10,
            deposits=100.0,
            debt=0.0,
            holdings={},
        )


def test_claim_identity_sums_tiny_person_holdings_before_tolerance_filtering():
    claims = PersonClaimLedger()
    for person_id in range(8):
        claims.add_person(person_id, household_id=10)
        claims.balance_sheet(person_id).bank_equity_claims["BANK_2"] = 2.5e-8

    claims.assert_household_claim_identity(
        household_id=10,
        deposits=0.0,
        debt=0.0,
        holdings={"__bank_equity__:BANK_2": 2.0e-7},
    )


def test_claim_ledger_posts_household_flows_to_people_without_changing_total_net_worth():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=10, cash_claim=30.0)
    claims.add_person(2, household_id=10, cash_claim=70.0)

    before = claims.total_net_worth()
    claims.post_household_cash_flow(10, amount=20.0, reason="labor_income")
    claims.allocate_household_consumption(10, amount=10.0)

    assert claims.balance_sheet(1).labor_income_tick == pytest.approx(10.0)
    assert claims.balance_sheet(2).labor_income_tick == pytest.approx(10.0)
    assert claims.balance_sheet(1).consumption_allocated_tick == pytest.approx(5.0)
    assert claims.balance_sheet(2).consumption_allocated_tick == pytest.approx(5.0)
    assert claims.total_net_worth() == pytest.approx(before + 10.0)


def test_household_labor_supply_counts_working_age_people_only():
    state = _StateStub(
        people=[
            _PersonStub(1, 8),
            _PersonStub(2, 35),
            _PersonStub(3, 37),
            _PersonStub(4, 71),
        ]
    )
    claims = PersonClaimLedger()
    for person in state.people:
        claims.add_person(person.id, household_id=person.household_id)

    profiles = build_household_economic_profiles(state, claims)

    assert profiles[0].labor_supply == 2.0
    assert profiles[0].child_count == 1
    assert profiles[0].adult_count == 2
    assert profiles[0].elder_count == 1
    assert profiles[0].dependency_ratio == 1.0


def test_person_labor_supply_and_need_weights_are_age_derived():
    assert labor_supply_for_person(_PersonStub(1, 17)) == 0.0
    assert labor_supply_for_person(_PersonStub(2, 18)) == 1.0
    assert labor_supply_for_person(_PersonStub(3, 64)) == 1.0
    assert labor_supply_for_person(_PersonStub(4, 65)) == 0.0

    assert need_weight_for_person(_PersonStub(1, 8)) == pytest.approx(0.65)
    assert need_weight_for_person(_PersonStub(2, 35)) == pytest.approx(1.0)
    assert need_weight_for_person(_PersonStub(3, 71)) == pytest.approx(0.9)
