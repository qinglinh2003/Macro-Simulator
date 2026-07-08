from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from macro_sim.core.ledger import Ledger
from macro_sim.domain.agents import Bank
from macro_sim.demographics.agents import BirthEvent, DeathEvent, MarriageEvent, Person
from macro_sim.demographics.economic_bridge import DemographicEconomicBridge
from macro_sim.demographics.economic_state import PersonClaimLedger
from macro_sim.demographics.estate import EstateRegistry
from macro_sim.demographics.marriage_economics import record_marriage_contract


@dataclass
class _HouseholdStub:
    id: str
    shares: float = 0.0
    holdings: dict[str, float] = None

    def __post_init__(self) -> None:
        if self.holdings is None:
            self.holdings = {}


@dataclass
class _EconStub:
    households: list[_HouseholdStub]
    ledger: Ledger
    banks: list = None
    equity: object | None = None
    _bonds: list[dict] = None

    def __post_init__(self) -> None:
        if self.banks is None:
            self.banks = []
        if self._bonds is None:
            self._bonds = []


@dataclass
class _DemographicStateStub:
    people: list[Person]


def _bridge() -> DemographicEconomicBridge:
    ledger = Ledger({"H0": 30.0, "BANK_0": 100.0})
    ledger.allow_negative("BANK_0")
    return DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0"},
        estates=EstateRegistry(),
        econ=_EconStub(households=[_HouseholdStub("H0")], ledger=ledger),
    )


def _person(person_id: int, age: int = 30) -> Person:
    return Person(
        id=person_id,
        age=age,
        sex="F",
        birth_date=date(2000 - age, 1, 1),
        household_id=0,
    )


def test_birth_creates_zero_endowment_balance_sheet():
    bridge = _bridge()
    newborn = _person(10, age=0)
    event = BirthEvent(tick=1, date=date(2000, 1, 2), person_id=10, mother_id=1, father_id=2)

    bridge.on_birth(event, newborn)

    sheet = bridge.claims.balance_sheet(newborn.id)
    assert sheet.cash_claim == 0.0
    assert sheet.debt_claim == 0.0
    assert sheet.household_id == newborn.household_id


def test_death_moves_positive_net_worth_to_estate_suspense():
    bridge = _bridge()
    dead = _person(11, age=70)
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=90.0, debt_claim=10.0)
    event = DeathEvent(tick=5, date=date(2000, 1, 6), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    estate = bridge.estates.estate_for(dead.id)
    assert estate.net_worth == pytest.approx(80.0)
    assert bridge.claims.net_worth(dead.id) == pytest.approx(0.0)
    assert bridge.claims.total_net_worth(include_estates=True) == pytest.approx(80.0)


def test_unclaimed_estate_suspense_survives_reconcile_without_double_counting():
    ledger = Ledger({"H0": 80.0, "BANK_0": 100.0})
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0"},
        estates=EstateRegistry(),
        econ=_EconStub(households=[_HouseholdStub("H0")], ledger=ledger),
    )
    dead = _person(14, age=80)
    dead.alive = False
    bridge.demographic_state = _DemographicStateStub(people=[dead])
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=80.0)
    event = DeathEvent(tick=5, date=date(2000, 1, 6), person_id=dead.id, age=80)

    bridge.on_death(event, dead)
    bridge.reconcile_financial_claims_from_economy(bridge.econ)

    assert bridge.estates.estate_for(dead.id).net_worth == pytest.approx(80.0)
    bridge.assert_all_claim_identities(bridge.econ)


def test_death_with_living_child_settles_estate_and_moves_ledger_cash():
    ledger = Ledger({"H0": 100.0, "H1": 0.0, "BANK_0": 100.0})
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0", 1: "H1"},
        estates=EstateRegistry(),
        econ=_EconStub(households=[_HouseholdStub("H0"), _HouseholdStub("H1")], ledger=ledger),
    )
    dead = _person(20, age=70)
    dead.alive = False
    child = _person(21, age=35)
    child.household_id = 1
    child.mother_id = dead.id
    bridge.demographic_state = _DemographicStateStub(people=[dead, child])
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=100.0)
    bridge.claims.add_person(child.id, household_id=1, cash_claim=0.0)
    event = DeathEvent(tick=8, date=date(2000, 1, 9), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    estate = bridge.estates.estate_for(dead.id)
    assert estate.cleared
    assert estate.net_worth == pytest.approx(0.0)
    assert bridge.claims.balance_sheet(child.id).cash_claim == pytest.approx(100.0)
    assert ledger.balance("H0") == pytest.approx(0.0)
    assert ledger.balance("H1") == pytest.approx(100.0)
    bridge.assert_all_claim_identities(bridge.econ)


def test_death_with_living_child_inherits_complex_asset_package():
    ledger = Ledger({"H0": 40.0, "H1": 0.0, "BANK_0": 100.0})
    bank = Bank(id="BANK_0")
    bank.owners = {"H0": 5.0}
    source_household = _HouseholdStub("H0", shares=4.0, holdings={"F1": 6.0})
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0", 1: "H1"},
        estates=EstateRegistry(),
        econ=_EconStub(
            households=[source_household, _HouseholdStub("H1")],
            ledger=ledger,
            banks=[bank],
            equity=object(),
            _bonds=[{"holder": "H0", "face": 20.0, "cost": 18.0, "matures_at": 9}],
        ),
    )
    dead = _person(30, age=70)
    dead.alive = False
    child = _person(31, age=35)
    child.household_id = 1
    child.mother_id = dead.id
    bridge.demographic_state = _DemographicStateStub(people=[dead, child])
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=40.0)
    dead_sheet = bridge.claims.balance_sheet(dead.id)
    dead_sheet.equity_claims["__aggregate_equity__"] = 4.0
    dead_sheet.equity_claims["F1"] = 6.0
    dead_sheet.bond_face_claim = 20.0
    dead_sheet.bank_equity_claims["BANK_0"] = 5.0
    bridge.claims.add_person(child.id, household_id=1, cash_claim=0.0)
    event = DeathEvent(tick=8, date=date(2000, 1, 9), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    child_sheet = bridge.claims.balance_sheet(child.id)
    assert child_sheet.cash_claim == pytest.approx(40.0)
    assert child_sheet.equity_claims["__aggregate_equity__"] == pytest.approx(4.0)
    assert child_sheet.equity_claims["F1"] == pytest.approx(6.0)
    assert child_sheet.bond_face_claim == pytest.approx(20.0)
    assert child_sheet.bank_equity_claims["BANK_0"] == pytest.approx(5.0)
    assert bridge.claims.balance_sheet(dead.id).net_worth == pytest.approx(0.0)
    assert ledger.balance("H0") == pytest.approx(0.0)
    assert ledger.balance("H1") == pytest.approx(40.0)
    assert source_household.holdings.get("F1", 0.0) == pytest.approx(0.0)
    assert bridge.econ.households[1].holdings["F1"] == pytest.approx(6.0)
    assert sum(lot["face"] for lot in bridge.econ._bonds if lot["holder"] == "H1") == pytest.approx(20.0)
    assert bank.owners["H1"] == pytest.approx(5.0)
    bridge.assert_all_claim_identities(bridge.econ)


def test_unclaimed_complex_estate_keeps_asset_package_backing_household_ledger():
    ledger = Ledger({"H0": 40.0, "BANK_0": 100.0})
    bank = Bank(id="BANK_0")
    bank.owners = {"H0": 5.0}
    household = _HouseholdStub("H0", shares=4.0, holdings={"F1": 6.0})
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0"},
        estates=EstateRegistry(),
        econ=_EconStub(
            households=[household],
            ledger=ledger,
            banks=[bank],
            equity=object(),
            _bonds=[{"holder": "H0", "face": 20.0, "cost": 18.0, "matures_at": 9}],
        ),
    )
    dead = _person(32, age=70)
    dead.alive = False
    bridge.demographic_state = _DemographicStateStub(people=[dead])
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=40.0)
    dead_sheet = bridge.claims.balance_sheet(dead.id)
    dead_sheet.equity_claims["__aggregate_equity__"] = 4.0
    dead_sheet.equity_claims["F1"] = 6.0
    dead_sheet.bond_face_claim = 20.0
    dead_sheet.bank_equity_claims["BANK_0"] = 5.0
    event = DeathEvent(tick=8, date=date(2000, 1, 9), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    estate = bridge.estates.estate_for(dead.id)
    assert estate.net_worth == pytest.approx(75.0)
    assert bridge.claims.balance_sheet(dead.id).cash_claim == pytest.approx(40.0)
    assert bridge.claims.balance_sheet(dead.id).equity_claims["F1"] == pytest.approx(6.0)
    assert bridge.claims.estate_suspense_by_household.get(0, 0.0) == pytest.approx(0.0)
    bridge.assert_all_claim_identities(bridge.econ)


def test_death_dissolves_marriage_before_estate_settlement():
    bridge = _bridge()
    dead = _person(22, age=70)
    spouse = _person(23, age=68)
    dead.partner_id = spouse.id
    spouse.partner_id = dead.id
    spouse.sex = "M"
    bridge.demographic_state = _DemographicStateStub(people=[dead, spouse])
    bridge.econ.ledger = Ledger({"H0": 240.0, "BANK_0": 100.0})
    bridge.econ.ledger.allow_negative("BANK_0")
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=100.0)
    bridge.claims.add_person(spouse.id, household_id=0, cash_claim=20.0)
    marriage = MarriageEvent(tick=1, date=date(1990, 1, 1), spouse_a_id=dead.id, spouse_b_id=spouse.id, household_id=0)
    bridge.marriage_contracts[frozenset({dead.id, spouse.id})] = record_marriage_contract(marriage, bridge.claims)
    bridge.claims.balance_sheet(dead.id).cash_claim = 200.0
    bridge.claims.balance_sheet(spouse.id).cash_claim = 40.0
    dead.alive = False
    event = DeathEvent(tick=9, date=date(2000, 1, 10), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    assert bridge.estates.estate_for(dead.id).cleared
    assert bridge.claims.balance_sheet(dead.id).net_worth == pytest.approx(0.0)
    assert bridge.claims.balance_sheet(spouse.id).cash_claim == pytest.approx(240.0)
    assert bridge.claims.total_net_worth(include_estates=True) == pytest.approx(240.0)
    bridge.assert_all_claim_identities(bridge.econ)


def test_insolvent_death_writes_unpaid_debt_to_lending_bank():
    bridge = _bridge()
    dead = _person(12, age=70)
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=30.0, debt_claim=100.0)
    bridge.econ.ledger.create_loan("H0", 100.0)
    bridge.assign_person_creditor_bank(dead.id, "BANK_0")
    bank_before = bridge.bank_capital("BANK_0")
    event = DeathEvent(tick=6, date=date(2000, 1, 7), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    assert bridge.estates.estate_for(dead.id).net_worth == pytest.approx(0.0)
    assert bridge.claims.net_worth(dead.id) == pytest.approx(0.0)
    assert bridge.death_writeoff_flow == pytest.approx(70.0)
    assert bridge.bank_capital("BANK_0") == pytest.approx(bank_before - 70.0)


def test_insolvent_death_uses_cash_before_bank_writeoff_and_preserves_identity():
    ledger = Ledger({"H0": 30.0, "SINK": 0.0, "BANK_0": 100.0})
    ledger.allow_negative("BANK_0")
    ledger.create_loan("H0", 100.0)
    ledger.transfer("H0", "SINK", 100.0)
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0"},
        estates=EstateRegistry(),
        econ=_EconStub(households=[_HouseholdStub("H0")], ledger=ledger),
    )
    dead = _person(40, age=70)
    bridge.demographic_state = _DemographicStateStub(people=[dead])
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=30.0, debt_claim=100.0)
    bridge.assign_person_creditor_bank(dead.id, "BANK_0")
    event = DeathEvent(tick=7, date=date(2000, 1, 8), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    assert ledger.balance("H0") == pytest.approx(0.0)
    assert ledger.debt("H0") == pytest.approx(0.0)
    assert bridge.death_writeoff_flow == pytest.approx(70.0)
    assert bridge.bank_capital("BANK_0") == pytest.approx(30.0)
    assert bridge.claims.balance_sheet(dead.id).net_worth == pytest.approx(0.0)
    bridge.assert_all_claim_identities(bridge.econ)


def test_insolvent_death_infers_creditor_bank_from_household_bank_mapping():
    ledger = Ledger({"H0": 30.0, "BANK_0": 100.0, "BANK_1": 100.0})
    ledger.allow_negative("BANK_0")
    ledger.allow_negative("BANK_1")
    ledger.create_loan("H0", 100.0)
    ledger.transfer("H0", "BANK_0", 100.0)
    bank = Bank(id="BANK_1")
    econ = _EconStub(households=[_HouseholdStub("H0")], ledger=ledger, banks=[bank])
    econ._bank_of = {"H0": bank}
    bridge = DemographicEconomicBridge(
        claims=PersonClaimLedger(),
        household_to_account={0: "H0"},
        estates=EstateRegistry(),
        econ=econ,
    )
    dead = _person(41, age=70)
    bridge.demographic_state = _DemographicStateStub(people=[dead])
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=30.0, debt_claim=100.0)
    event = DeathEvent(tick=7, date=date(2000, 1, 8), person_id=dead.id, age=70)

    bridge.on_death(event, dead)

    assert bridge.death_writeoff_flow == pytest.approx(70.0)
    assert bridge.bank_capital("BANK_1") == pytest.approx(30.0)
    assert bridge.bank_capital("BANK_0") == pytest.approx(200.0)
    bridge.assert_all_claim_identities(bridge.econ)


def test_insolvent_death_without_known_creditor_bank_halts():
    bridge = _bridge()
    dead = _person(13, age=70)
    bridge.claims.add_person(dead.id, household_id=0, cash_claim=30.0, debt_claim=100.0)
    event = DeathEvent(tick=7, date=date(2000, 1, 8), person_id=dead.id, age=70)

    with pytest.raises(RuntimeError, match="missing creditor bank"):
        bridge.on_death(event, dead)
