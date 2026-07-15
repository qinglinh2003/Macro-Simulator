from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics import Phase0VitalRates
from macro_sim.core.ledger import Ledger
from macro_sim.demographics.agents import Person
from macro_sim.demographics.economic_bridge import initialize_person_claims_from_households
from macro_sim.demographics.lifecycle import (
    age_income_capacity,
    expected_remaining_life_years,
    household_lifecycle_consumption_budget,
    person_permanent_income,
    person_wealth_draw,
)
from macro_sim.systems.planning import run_planning_phase
from macro_sim.systems.credit import run_credit_phase
from macro_sim.systems.settlement import run_settlement_phase


@dataclass
class _StubPerson:
    id: int
    age: int


@dataclass
class _ProfileWithMembers:
    members: list[_StubPerson]


@dataclass
class _ProfileWithMemberIds:
    member_ids: list[int]
    member_ages: dict[int, int]


@dataclass
class _ProfileWithNeeds:
    members: list[_StubPerson]
    need_units: float
    adult_count: int


class _ClaimsStub:
    def __init__(
        self,
        *,
        net_worth: dict[int, float],
        income_ema: dict[int, float],
        member_ages: dict[int, int] | None = None,
    ) -> None:
        self._net_worth = dict(net_worth)
        self._income_ema = dict(income_ema)
        self._member_ages = dict(member_ages or {})

    def net_worth(self, person_id: int) -> float:
        return float(self._net_worth[person_id])

    def income_ema(self, person_id: int) -> float:
        return float(self._income_ema[person_id])

    def age(self, person_id: int) -> int:
        if person_id not in self._member_ages:
            raise KeyError(person_id)
        return int(self._member_ages[person_id])


def test_remaining_life_declines_with_age():
    rates = Phase0VitalRates()

    assert expected_remaining_life_years(25, rates) > expected_remaining_life_years(70, rates)
    assert expected_remaining_life_years(0, rates) > expected_remaining_life_years(100, rates)


def test_person_wealth_draw_rises_as_remaining_life_shortens():
    wealth = 100.0

    young_daily = person_wealth_draw(wealth, remaining_life_years=50.0)
    old_daily = person_wealth_draw(wealth, remaining_life_years=10.0)

    assert old_daily > young_daily


def test_person_wealth_draw_ignores_negative_net_worth():
    assert person_wealth_draw(-100.0, remaining_life_years=30.0) == 0.0


def test_person_wealth_draw_prevents_division_by_zero():
    assert person_wealth_draw(123.0, remaining_life_years=0.0) == 123.0


def test_person_permanent_income_uses_income_capacity_not_saving_rate():
    income_ema = 10.0

    child_income = person_permanent_income(income_ema, age=12)
    prime_income = person_permanent_income(income_ema, age=40)
    retired_income = person_permanent_income(income_ema, age=70)

    assert child_income == 0.0
    assert prime_income == income_ema
    assert retired_income == 0.0


def test_age_income_capacity_piecewise_profile():
    assert age_income_capacity(12) == 0.0
    assert age_income_capacity(18) == pytest.approx(0.5)
    assert age_income_capacity(21) == pytest.approx(0.75)
    assert age_income_capacity(25) == pytest.approx(1.0)
    assert age_income_capacity(26) == pytest.approx(1.0)
    assert age_income_capacity(50) == pytest.approx(1.0)
    assert age_income_capacity(51) == pytest.approx(1.0)
    assert age_income_capacity(64) == pytest.approx(0.7)
    assert age_income_capacity(65) == 0.0


def test_same_wealth_older_household_draws_more_annuitized_wealth_than_young_household():
    young_budget = household_lifecycle_consumption_budget(
        profile=_ProfileWithMembers(members=[_StubPerson(1, 30), _StubPerson(2, 31)]),
        claims=_ClaimsStub(net_worth={1: 50.0, 2: 50.0}, income_ema={1: 0.0, 2: 0.0}),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )
    old_budget = household_lifecycle_consumption_budget(
        profile=_ProfileWithMembers(members=[_StubPerson(1, 72), _StubPerson(2, 73)]),
        claims=_ClaimsStub(net_worth={1: 50.0, 2: 50.0}, income_ema={1: 0.0, 2: 0.0}),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )

    assert old_budget > young_budget


def test_household_lifecycle_budget_sums_person_wealth_draws_not_average_life():
    mixed_age_budget = household_lifecycle_consumption_budget(
        profile=_ProfileWithMembers(members=[_StubPerson(1, 30), _StubPerson(2, 80)]),
        claims=_ClaimsStub(
            net_worth={1: 50.0, 2: 50.0},
            income_ema={1: 0.0, 2: 0.0},
        ),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )
    young_budget = household_lifecycle_consumption_budget(
        profile=_ProfileWithMembers(members=[_StubPerson(1, 30), _StubPerson(2, 30)]),
        claims=_ClaimsStub(
            net_worth={1: 50.0, 2: 50.0},
            income_ema={1: 0.0, 2: 0.0},
        ),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )

    assert mixed_age_budget > young_budget


def test_household_budget_works_with_member_id_profiles():
    profile = _ProfileWithMemberIds(member_ids=[1, 2], member_ages={1: 30, 2: 40})
    claims = _ClaimsStub(
        net_worth={1: 10.0, 2: 30.0},
        income_ema={1: 3.0, 2: 4.0},
    )
    budget = household_lifecycle_consumption_budget(
        profile=profile,
        claims=claims,
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=0.5,
    )

    assert budget > 0.0 and math.isfinite(budget)


def test_need_scaling_does_not_multiply_already_aggregated_income_by_household_size():
    budgets = []
    for size in (1, 2, 4):
        members = [_StubPerson(person_id, 30) for person_id in range(1, size + 1)]
        budgets.append(household_lifecycle_consumption_budget(
            profile=_ProfileWithNeeds(members=members, need_units=float(size), adult_count=size),
            claims=_ClaimsStub(
                net_worth={person.id: 0.0 for person in members},
                income_ema={person.id: 1.0 for person in members},
            ),
            rates=Phase0VitalRates(),
            alpha_income=0.8,
            alpha_wealth_draw=0.0,
        ))

    assert budgets == pytest.approx([0.8, 1.6, 3.2])
    assert budgets[2] / budgets[1] == pytest.approx(2.0)


def test_dependent_need_units_apply_to_per_adult_income_once():
    adult = _StubPerson(1, 35)
    child = _StubPerson(2, 10)
    adult_only = household_lifecycle_consumption_budget(
        profile=_ProfileWithNeeds([adult], need_units=1.0, adult_count=1),
        claims=_ClaimsStub(net_worth={1: 0.0}, income_ema={1: 1.0}),
        rates=Phase0VitalRates(), alpha_income=1.0, alpha_wealth_draw=0.0,
    )
    with_child = household_lifecycle_consumption_budget(
        profile=_ProfileWithNeeds([adult, child], need_units=1.65, adult_count=1),
        claims=_ClaimsStub(
            net_worth={1: 0.0, 2: 0.0}, income_ema={1: 1.0, 2: 0.0},
        ),
        rates=Phase0VitalRates(), alpha_income=1.0, alpha_wealth_draw=0.0,
    )

    assert with_child == pytest.approx(1.65 * adult_only)


@dataclass
class _HouseholdStub:
    id: str
    alpha1: float = 0.6
    alpha2: float = 0.02
    lambda_y: float = 0.5
    y_expected: float = 0.0
    income_realized: float = 0.0
    consumption_budget: float = 0.0
    spent: float = 0.0
    labor_sold: float = 0.0
    jg_labor: float = 0.0
    equity_value_ema: float = 0.0
    margin_debt: float = 0.0


@dataclass
class _DemographicState:
    people: list[Person]


class _NoOpRng:
    def random(self) -> float:
        return 1.0


def _demo_person(person_id: int, age: int, household_id: int) -> Person:
    return Person(
        id=person_id,
        age=age,
        sex="F",
        birth_date=__import__("datetime").date(2000 - age, 1, 1),
        household_id=household_id,
    )


def test_planning_phase_uses_lifecycle_budget_when_demographic_bridge_enabled():
    households = [_HouseholdStub("H0"), _HouseholdStub("H1")]
    econ = type("Econ", (), {})()
    econ.households = households
    econ.firms = []
    econ.ledger = Ledger({"H0": 100.0, "H1": 100.0, "BANK_0": 0.0})
    econ.rng = _NoOpRng()
    econ._pubcap_factor = 1.0
    econ.policy = type("Policy", (), {"min_wage": 0.0})()
    econ.cfg = type(
        "Cfg",
        (),
        {
            "planning": type(
                "Planning",
                (),
                {
                    "theta_wage": 0.0,
                    "theta_price": 0.0,
                    "lambda_q": 0.0,
                    "q_invest_floor": 0.0,
                    "q_invest_cap": 0.0,
                    "k_replacement_floor": False,
                    "wealth_effect": 0.0,
                    "mpc_wealth_curvature": 1.0,
                    "d_household0": 1.0,
                    "demographic_lifecycle_consumption": True,
                    "lifecycle_alpha_income": 0.6,
                    "lifecycle_alpha_wealth_draw": 1.0,
                },
            )()
        },
    )()
    state = _DemographicState(
        people=[
            _demo_person(1, 30, household_id=0),
            _demo_person(2, 72, household_id=1),
        ]
    )
    econ.demographic_state = state
    econ.demographic_bridge = initialize_person_claims_from_households(econ, state)
    econ.demographic_rates = Phase0VitalRates()

    run_planning_phase(econ)

    assert households[1].consumption_budget > households[0].consumption_budget


def test_lifecycle_budget_returns_zero_for_empty_demographic_household_account():
    households = [_HouseholdStub("H0"), _HouseholdStub("H1")]
    econ = type("Econ", (), {})()
    econ.households = households
    econ.ledger = Ledger({"H0": 100.0, "H1": 0.0, "BANK_0": 0.0})
    state = _DemographicState(people=[_demo_person(1, 40, household_id=0)])
    econ.demographic_state = state
    bridge = initialize_person_claims_from_households(econ, state)
    bridge.demographic_state = state
    bridge.econ = econ
    bridge.household_to_account[1] = "H1"
    bridge.account_to_household["H1"] = 1

    budget = bridge.household_lifecycle_consumption_budget(
        "H1",
        Phase0VitalRates(),
        alpha_income=1.0,
        alpha_wealth_draw=1.0,
    )

    assert budget == 0.0


def test_equal_dividends_skip_empty_demographic_household_accounts():
    households = [_HouseholdStub("H0"), _HouseholdStub("H1")]
    firm = SimpleNamespace(id="F0", revenue=10.0, wagebill=0.0, rho=1.0, profit=0.0, dividend_shortfall=0.0,
                           energy_cost_used=0.0)   # v17.0: settlement profit reads the energy opex field
    econ = SimpleNamespace(
        households=households,
        firms=[firm],
        c_firms=[firm],
        investing_firms=[],
        ledger=Ledger({"H0": 0.0, "H1": 0.0, "F0": 10.0, "CLEARING": 0.0, "BANK_0": 0.0}),
        cfg=SimpleNamespace(
            settlement=SimpleNamespace(
                government=False,
                pro_rata_dividends=False,
                per_firm_equity=False,
                gov_investment_share=0.0,
                public_capital_depreciation=0.0,
                job_guarantee=False,
            )
        ),
        policy=SimpleNamespace(
            tax_profit_rate=0.0,
            job_guarantee=False,
        ),
        public_capital=0.0,
    )
    state = _DemographicState(people=[_demo_person(1, 40, household_id=0)])
    econ.demographic_state = state
    bridge = initialize_person_claims_from_households(econ, state)
    bridge.demographic_state = state
    bridge.econ = econ
    bridge.household_to_account[1] = "H1"
    bridge.account_to_household["H1"] = 1
    econ.demographic_bridge = bridge

    run_settlement_phase(econ)

    assert econ.ledger.balance("H0") == pytest.approx(10.0)
    assert econ.ledger.balance("H1") == pytest.approx(0.0)
    bridge.assert_all_claim_identities(econ)


def test_household_credit_skips_empty_demographic_household_accounts():
    households = [_HouseholdStub("H0"), _HouseholdStub("H1")]
    households[0].y_expected = 1.0
    households[1].y_expected = 1.0
    econ = SimpleNamespace(
        households=households,
        firms=[],
        k_firms=[],
        banks=[SimpleNamespace(id="BANK_0", alive=True)],
        _bank_of={"H0": SimpleNamespace(id="BANK_0", alive=True), "H1": SimpleNamespace(id="BANK_0", alive=True)},
        _loan_book={"BANK_0": 0.0},
        ledger=Ledger({"H0": 0.0, "H1": 0.0, "BANK_0": 0.0}),
        policy=SimpleNamespace(kappa=10.0, hh_credit_limit=10.0),
        cfg=SimpleNamespace(
            credit=SimpleNamespace(
                bank_enabled=True,
                household_credit=True,
                margin_credit=False,
                hh_subsistence=2.0,
                hh_credit_limit=10.0,
                hh_amort=0.0,
                bank_target_capital_ratio=0.0,
                interbank=False,
                deposit_rate_disp=0.0,
                interest_by_deposits=False,
                amort=0.0,
            ),
            banking=SimpleNamespace(
                bank_capital_constraint=False,
                bank_equity=False,
            ),
        ),
    )
    state = _DemographicState(people=[_demo_person(1, 40, household_id=0)])
    econ.demographic_state = state
    bridge = initialize_person_claims_from_households(econ, state)
    bridge.demographic_state = state
    bridge.econ = econ
    bridge.household_to_account[1] = "H1"
    bridge.account_to_household["H1"] = 1
    econ.demographic_bridge = bridge

    run_credit_phase(econ)

    assert econ.ledger.debt("H0") > 0.0
    assert econ.ledger.debt("H1") == 0.0
    bridge.assert_all_claim_identities(econ)


def test_person_household_move_transfers_margin_debt_shadow_state():
    households = [_HouseholdStub("H0")]
    econ = SimpleNamespace(
        households=households,
        ledger=Ledger({"H0": 100.0, "BANK_0": 0.0}),
        cfg=SimpleNamespace(),
    )
    person = _demo_person(1, 24, household_id=0)
    state = _DemographicState(people=[person])
    econ.demographic_state = state
    bridge = initialize_person_claims_from_households(econ, state)
    bridge.demographic_state = state
    bridge.econ = econ
    econ.demographic_bridge = bridge
    econ.ledger.create_loan("H0", 40.0)
    bridge.post_household_debt_creation("H0", 40.0)
    households[0].margin_debt = 40.0

    person.household_id = 1
    new_account = bridge.create_household_for_person(person.id)

    assert new_account == "H1"
    assert econ.ledger.debt("H0") == pytest.approx(0.0)
    assert econ.ledger.debt("H1") == pytest.approx(40.0)
    assert households[0].margin_debt == pytest.approx(0.0)
    assert econ.households[1].margin_debt == pytest.approx(40.0)
    bridge.assert_all_claim_identities(econ)


def test_person_household_move_normalizes_internal_negative_cash_before_transfer():
    households = [_HouseholdStub("H0")]
    econ = SimpleNamespace(
        households=households,
        ledger=Ledger({"H0": 0.0, "BANK_0": 0.0}),
        cfg=SimpleNamespace(),
    )
    mover = _demo_person(1, 24, household_id=0)
    stayer = _demo_person(2, 50, household_id=0)
    state = _DemographicState(people=[mover, stayer])
    econ.demographic_state = state
    bridge = initialize_person_claims_from_households(econ, state)
    bridge.demographic_state = state
    bridge.econ = econ
    econ.demographic_bridge = bridge
    bridge.claims.balance_sheet(mover.id).cash_claim = 4.5
    bridge.claims.balance_sheet(stayer.id).cash_claim = -4.5

    mover.household_id = 1
    new_account = bridge.create_household_for_person(mover.id)

    assert new_account == "H1"
    assert econ.ledger.balance("H0") == pytest.approx(0.0)
    assert econ.ledger.balance("H1") == pytest.approx(0.0)
    assert bridge.claims.balance_sheet(mover.id).cash_claim == pytest.approx(0.0)
    assert bridge.claims.balance_sheet(stayer.id).cash_claim == pytest.approx(0.0)
    bridge.assert_all_claim_identities(econ)


def test_consumption_posting_preserves_household_cash_claim_sum():
    households = [_HouseholdStub("H0")]
    econ = type("Econ", (), {})()
    econ.households = households
    econ.ledger = Ledger({"H0": 200.0, "BANK_0": 0.0})
    state = _DemographicState(
        people=[
            _demo_person(1, 40, household_id=0),
            _demo_person(2, 41, household_id=0),
            _demo_person(3, 8, household_id=0),
        ]
    )
    bridge = initialize_person_claims_from_households(econ, state)

    bridge.post_household_consumption("H0", spent=60.0, fixed_share=0.30)

    assert bridge.claim_cash_sum("H0") == pytest.approx(140.0)
    assert bridge.consumption_allocated_sum("H0") == pytest.approx(60.0)


def test_child_costs_split_between_living_parents():
    households = [_HouseholdStub("H0")]
    econ = type("Econ", (), {})()
    econ.households = households
    econ.ledger = Ledger({"H0": 200.0, "BANK_0": 0.0})
    state = _DemographicState(
        people=[
            _demo_person(1, 40, household_id=0),
            _demo_person(2, 41, household_id=0),
            _demo_person(3, 8, household_id=0),
        ]
    )
    state.people[2].mother_id = 1
    state.people[2].father_id = 2
    bridge = initialize_person_claims_from_households(econ, state)

    allocation = bridge.allocate_child_cost(child_id=3, amount=30.0)

    assert allocation.parent_charges == {1: 15.0, 2: 15.0}
    assert allocation.public_charge == 0.0


def test_orphan_child_costs_go_to_public_support():
    households = [_HouseholdStub("H0")]
    econ = type("Econ", (), {})()
    econ.households = households
    econ.ledger = Ledger({"H0": 0.0, "BANK_0": 0.0})
    state = _DemographicState(
        people=[
            _demo_person(1, 40, household_id=0),
            _demo_person(2, 41, household_id=0),
            _demo_person(3, 8, household_id=0),
        ]
    )
    state.people[0].alive = False
    state.people[1].alive = False
    state.people[2].mother_id = 1
    state.people[2].father_id = 2
    bridge = initialize_person_claims_from_households(econ, state)

    allocation = bridge.allocate_child_cost(child_id=3, amount=30.0)

    assert allocation.parent_charges == {}
    assert allocation.public_charge == 30.0
    assert bridge.orphan_support_spending == pytest.approx(30.0)
