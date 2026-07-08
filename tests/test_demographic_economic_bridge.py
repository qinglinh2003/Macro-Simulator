from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pytest

from macro_sim.domain.agents import Bank
from macro_sim.core.ledger import Ledger
from macro_sim.demographics.agents import Person
from macro_sim.demographics.economic_bridge import initialize_person_claims_from_households


@dataclass
class _HouseholdStub:
    id: str
    labor_sold: float = 0.0
    income_realized: float = 0.0
    shares: float = 0.0
    holdings: dict[str, float] = field(default_factory=dict)
    margin_debt: float = 0.0


@dataclass
class _EconStub:
    households: list[_HouseholdStub]
    ledger: Ledger
    c_firms: list = field(default_factory=list)
    banks: list = field(default_factory=list)
    equity: object | None = None
    _bonds: list[dict] = field(default_factory=list)


@dataclass
class _DemographicStateStub:
    people: list[Person]


def _person(person_id: int, age: int, household_id: int) -> Person:
    return Person(
        id=person_id,
        age=age,
        sex="F" if person_id % 2 else "M",
        birth_date=date(2000 - age, 1, 1),
        household_id=household_id,
    )


def test_genesis_claims_seed_adult_equal_and_reconcile_household_cash():
    econ = _EconStub(
        households=[_HouseholdStub("H0")],
        ledger=Ledger({"H0": 120.0, "BANK_0": 50.0}),
    )
    state = _DemographicStateStub(
        people=[
            _person(1, 36, household_id=0),
            _person(2, 35, household_id=0),
            _person(3, 7, household_id=0),
        ]
    )

    bridge = initialize_person_claims_from_households(econ, state)

    assert bridge.account_for_household_id(0) == "H0"
    assert bridge.household_id_for_account("H0") == 0
    assert bridge.claims.balance_sheet(1).cash_claim == pytest.approx(60.0)
    assert bridge.claims.balance_sheet(2).cash_claim == pytest.approx(60.0)
    assert bridge.claims.balance_sheet(3).cash_claim == pytest.approx(0.0)
    bridge.claims.assert_household_claim_identity(0, deposits=120.0, debt=0.0, holdings={})


def test_bridge_posts_labor_income_to_working_age_members_only():
    econ = _EconStub(
        households=[_HouseholdStub("H0")],
        ledger=Ledger({"H0": 0.0, "BANK_0": 50.0}),
    )
    state = _DemographicStateStub(
        people=[
            _person(1, 36, household_id=0),
            _person(2, 8, household_id=0),
        ]
    )
    bridge = initialize_person_claims_from_households(econ, state)

    bridge.post_labor_income("H0", amount=12.0)

    assert bridge.claims.balance_sheet(1).cash_claim == pytest.approx(12.0)
    assert bridge.claims.balance_sheet(2).cash_claim == pytest.approx(0.0)
    assert bridge.household_labor_supply("H0") == pytest.approx(1.0)


def test_bridge_identity_check_compares_person_claims_to_economic_ledger():
    econ = _EconStub(
        households=[_HouseholdStub("H0")],
        ledger=Ledger({"H0": 100.0, "BANK_0": 50.0}),
    )
    state = _DemographicStateStub(people=[_person(1, 40, household_id=0)])
    bridge = initialize_person_claims_from_households(econ, state)
    bridge.assert_all_claim_identities(econ)

    bridge.claims.balance_sheet(1).cash_claim += 1.0
    with pytest.raises(AssertionError, match="cash claim mismatch"):
        bridge.assert_all_claim_identities(econ)


def test_bridge_seeds_complex_household_asset_claims_and_reconciles_changes():
    ledger = Ledger({"H0": 100.0, "BANK_0": 50.0})
    ledger.create_loan("H0", 20.0)
    household = _HouseholdStub(
        "H0",
        shares=6.0,
        holdings={"F0": 10.0},
        margin_debt=20.0,
    )
    bank = Bank(id="BANK_0")
    bank.shares_outstanding = 100.0
    bank.owners = {"H0": 4.0}
    econ = _EconStub(
        households=[household],
        ledger=ledger,
        banks=[bank],
        equity=object(),
        _bonds=[{"holder": "H0", "face": 30.0, "cost": 30.0, "matures_at": 9}],
    )
    state = _DemographicStateStub(
        people=[
            _person(1, 40, household_id=0),
            _person(2, 38, household_id=0),
            _person(3, 9, household_id=0),
        ]
    )

    bridge = initialize_person_claims_from_households(econ, state)

    assert bridge.claims.balance_sheet(1).equity_claims["F0"] == pytest.approx(5.0)
    assert bridge.claims.balance_sheet(2).equity_claims["__aggregate_equity__"] == pytest.approx(3.0)
    assert bridge.claims.balance_sheet(1).bond_face_claim == pytest.approx(15.0)
    assert bridge.claims.balance_sheet(2).bank_equity_claims["BANK_0"] == pytest.approx(2.0)
    bridge.assert_all_claim_identities(econ)

    household.holdings["F0"] = 12.0
    household.holdings["F1"] = 8.0
    household.shares = 4.0
    household.margin_debt = 10.0
    econ._bonds = [{"holder": "H0", "face": 42.0, "cost": 42.0, "matures_at": 12}]
    bank.owners = {"H0": 6.0}
    ledger.repay("H0", 10.0)

    bridge.reconcile_financial_claims_from_economy(econ)

    bridge.assert_all_claim_identities(econ)
    assert sum(
        bridge.claims.balance_sheet(pid).equity_claims.get("F1", 0.0)
        for pid in (1, 2, 3)
    ) == pytest.approx(8.0)


def test_bridge_posts_complex_asset_trades_incrementally():
    ledger = Ledger({"H0": 100.0, "CLEARING": 0.0, "TSY": 0.0, "BANK_0": 50.0})
    household = _HouseholdStub("H0")
    bank = Bank(id="BANK_0")
    bank.owners = {}
    econ = _EconStub(households=[household], ledger=ledger, banks=[bank])
    state = _DemographicStateStub(
        people=[
            _person(1, 40, household_id=0),
            _person(2, 38, household_id=0),
        ]
    )
    bridge = initialize_person_claims_from_households(econ, state)

    ledger.transfer("H0", "CLEARING", 12.0)
    household.holdings["F1"] = 4.0
    bridge.post_household_equity_trade("H0", "F1", cash_delta=-12.0, share_delta=4.0)

    ledger.transfer("CLEARING", "H0", 3.0)
    household.holdings["F1"] = 3.0
    bridge.post_household_equity_trade("H0", "F1", cash_delta=3.0, share_delta=-1.0)

    ledger.transfer("H0", "TSY", 10.0)
    econ._bonds.append({"holder": "H0", "face": 10.0, "cost": 10.0, "matures_at": 5})
    bridge.post_household_bond_trade("H0", cash_delta=-10.0, face_delta=10.0)

    ledger.transfer("H0", "CLEARING", 8.0)
    bank.owners = {"H0": 2.0}
    bridge.post_household_bank_equity_trade("H0", "BANK_0", cash_delta=-8.0, share_delta=2.0)

    ledger.create_loan("H0", 6.0)
    bridge.post_household_debt_creation("H0", 6.0)
    ledger.repay("H0", 2.0)
    bridge.post_household_debt_repayment("H0", 2.0)

    bridge.assert_all_claim_identities(econ)
    assert sum(
        bridge.claims.balance_sheet(pid).equity_claims.get("F1", 0.0)
        for pid in (1, 2)
    ) == pytest.approx(3.0)
    assert sum(bridge.claims.balance_sheet(pid).bond_face_claim for pid in (1, 2)) == pytest.approx(10.0)
    assert sum(
        bridge.claims.balance_sheet(pid).bank_equity_claims.get("BANK_0", 0.0)
        for pid in (1, 2)
    ) == pytest.approx(2.0)


def test_bridge_identity_rejects_stale_complex_asset_claims():
    ledger = Ledger({"H0": 100.0, "BANK_0": 50.0})
    econ = _EconStub(
        households=[_HouseholdStub("H0")],
        ledger=ledger,
        banks=[Bank(id="BANK_0")],
    )
    state = _DemographicStateStub(people=[_person(1, 40, household_id=0)])
    bridge = initialize_person_claims_from_households(econ, state)

    bridge.claims.balance_sheet(1).equity_claims["STALE_FIRM"] = 1.0

    with pytest.raises(AssertionError, match="holding claim mismatch"):
        bridge.assert_all_claim_identities(econ)


def test_create_household_for_person_moves_complex_portfolio_claims():
    ledger = Ledger({"H0": 100.0, "BANK_0": 50.0})
    household = _HouseholdStub("H0", holdings={"F1": 6.0}, shares=4.0)
    bank = Bank(id="BANK_0")
    bank.owners = {"H0": 3.0}
    econ = _EconStub(
        households=[household],
        ledger=ledger,
        banks=[bank],
        equity=object(),
        _bonds=[{"holder": "H0", "face": 20.0, "cost": 18.0, "matures_at": 5}],
    )
    person = _person(1, 24, household_id=0)
    state = _DemographicStateStub(people=[person])
    bridge = initialize_person_claims_from_households(econ, state)

    person.household_id = 1
    account_id = bridge.create_household_for_person(person.id)

    assert account_id == "H1"
    assert ledger.balance("H0") == pytest.approx(0.0)
    assert ledger.balance("H1") == pytest.approx(100.0)
    assert household.holdings.get("F1", 0.0) == pytest.approx(0.0)
    assert econ.households[-1].holdings["F1"] == pytest.approx(6.0)
    assert household.shares == pytest.approx(0.0)
    assert econ.households[-1].shares == pytest.approx(4.0)
    assert sum(lot["face"] for lot in econ._bonds if lot["holder"] == "H0") == pytest.approx(0.0)
    assert sum(lot["face"] for lot in econ._bonds if lot["holder"] == "H1") == pytest.approx(20.0)
    assert bank.owners.get("H0", 0.0) == pytest.approx(0.0)
    assert bank.owners["H1"] == pytest.approx(3.0)
    bridge.assert_all_claim_identities(econ)
