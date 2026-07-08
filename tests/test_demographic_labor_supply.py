from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from macro_sim.core.ledger import Ledger
from macro_sim.demographics.agents import Person
from macro_sim.demographics.economic_bridge import initialize_person_claims_from_households
from macro_sim.systems.labor import run_labor_phase
from macro_sim.systems.settlement import run_household_fiscal_phase


class _NoShuffleRng:
    def shuffle(self, items):
        return None


@dataclass
class _HouseholdStub:
    id: str
    labor_sold: float = 0.0
    jg_labor: float = 0.0
    income_realized: float = 0.0


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


def _firm() -> SimpleNamespace:
    return SimpleNamespace(
        id="F0",
        labor_demand_eff=5.0,
        wage=1.0,
        hired=0.0,
        wagebill=0.0,
        tech="linear",
        a=1.0,
        inventory=0.0,
        produced=0.0,
    )


def _econ(*, demographics: bool) -> SimpleNamespace:
    households = [_HouseholdStub("H0"), _HouseholdStub("H1")]
    ledger = Ledger({"H0": 0.0, "H1": 0.0, "F0": 10.0, "GOV": 100.0, "BANK_0": 0.0})
    econ = SimpleNamespace(
        households=households,
        firms=[_firm()],
        ledger=ledger,
        rng=_NoShuffleRng(),
        _pubcap_factor=1.0,
        _fiscal="GOV",
        policy=SimpleNamespace(
            tax_income_rate=0.0,
            income_allowance=0.0,
            job_guarantee=False,
            jg_wage_ratio=0.0,
            min_wage=0.0,
            benefit_replacement=0.5,
            tax_wealth_rate=0.0,
            wealth_allowance=0.0,
        ),
        cfg=SimpleNamespace(settlement=SimpleNamespace(jg_productivity=0.0)),
        c_firms=[],
        _tax_income=0.0,
        _tax_wealth=0.0,
        _benefit_paid=0.0,
        _jg_spending=0.0,
        _jg_employment=0.0,
        _jg_capital_units=0.0,
    )
    if demographics:
        state = _DemographicStateStub(
            people=[
                _person(1, 30, household_id=0),
                _person(2, 31, household_id=0),
                _person(3, 8, household_id=1),
                _person(4, 71, household_id=1),
            ]
        )
        econ.demographic_state = state
        econ.demographic_bridge = initialize_person_claims_from_households(econ, state)
    return econ


def test_labor_phase_uses_demographic_supply_when_enabled():
    econ = _econ(demographics=True)

    run_labor_phase(econ)

    assert econ.households[0].labor_sold == pytest.approx(2.0)
    assert econ.households[1].labor_sold == pytest.approx(0.0)
    assert econ.demographic_bridge.claims.balance_sheet(1).labor_income_tick == pytest.approx(1.0)
    assert econ.demographic_bridge.claims.balance_sheet(2).labor_income_tick == pytest.approx(1.0)
    assert econ.ledger.balance("H0") == pytest.approx(2.0)
    assert econ.ledger.balance("H1") == pytest.approx(0.0)


def test_labor_phase_uses_legacy_supply_when_demographics_disabled():
    econ = _econ(demographics=False)

    run_labor_phase(econ)

    assert all(h.labor_sold <= 1.0 for h in econ.households)
    assert sum(h.labor_sold for h in econ.households) == pytest.approx(2.0)


def test_unemployment_benefit_uses_demographic_labor_supply():
    econ = _econ(demographics=True)
    econ.households[0].labor_sold = 1.0

    run_household_fiscal_phase(econ)

    assert econ._benefit_paid == pytest.approx(0.5)
    assert econ.ledger.balance("H0") == pytest.approx(0.5)
    assert econ.ledger.balance("H1") == pytest.approx(0.0)
