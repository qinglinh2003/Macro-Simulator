from __future__ import annotations

import math
import random

import pytest

from macro_sim.behavior import planning as B
from macro_sim.config import Config
from macro_sim.domain.agents import Firm
from macro_sim.economy import Economy
from macro_sim.housing.market import investor_safe_asset_return_annual
from macro_sim.systems.banking import update_bank_valuation
from macro_sim.systems.central_bank import set_policy_rate
from macro_sim.systems.credit import run_credit_phase, run_household_debt_service_phase
from macro_sim.systems.goods import household_goods_cash_budget
from macro_sim.systems.planning import run_planning_phase
from macro_sim.systems.valuation import residual_income_fundamental, valuation_discount_rate


def _investment_target(rate: float) -> float:
    firm = Firm.create_c_firm(0, Config())
    firm.demand_expected = 30.0
    B.plan_investment(
        firm,
        nominal_loan_rate=rate,
        expected_inflation=0.0,
        neutral_nominal_rate=0.02,
        inflation_target=0.0,
        user_cost_elasticity=0.5,
        user_cost_multiplier_min=0.5,
        user_cost_multiplier_max=1.5,
        user_cost_floor=1.0e-9,
    )
    return firm.investment_target


def test_local_rate_derivatives_have_conventional_signs_without_saver_fiction():
    cut_investment = _investment_target(0.0)
    neutral_investment = _investment_target(0.02)
    hike_investment = _investment_target(0.08)
    assert cut_investment > neutral_investment > hike_investment

    def grant(rate: float) -> float:
        return B.credit_grant(
            500.0,
            200.0,
            50.0,
            10.0,
            expected_operating_cash_flow=20.0,
            loan_rate=rate,
            amort=0.05,
            min_dscr=1.25,
        )

    assert grant(0.01) > grant(0.05) > grant(0.10)

    def budget(rate: float, debt: float, deposits: float = 100.0) -> float:
        return B.reserve_household_debt_service(
            100.0,
            deposits=deposits,
            debt=debt,
            margin_debt=0.0,
            loan_rate=rate,
            amort=0.05,
        )

    assert budget(0.01, 100.0) > budget(0.05, 100.0) > budget(0.10, 100.0)
    assert budget(0.01, 0.0) == budget(0.10, 0.0) == 100.0
    # Cash-rich debtors are not assigned a fictitious income effect; cash-poor
    # debtors cannot plan to spend funds needed for the same-tick service phase.
    assert budget(0.10, 100.0, deposits=1_000.0) == 100.0
    assert budget(0.10, 100.0, deposits=10.0) == 0.0


def test_user_cost_is_finite_and_clipped_at_zlb_and_negative_real_rates():
    multiplier = B.investment_user_cost_multiplier(
        nominal_loan_rate=0.0,
        expected_inflation=1.0,
        neutral_nominal_rate=1.34e-4,
        inflation_target=5.4e-5,
        depreciation=2.28e-4,
        elasticity=0.5,
        multiplier_min=0.5,
        multiplier_max=1.5,
        user_cost_floor=1.0e-9,
    )
    assert math.isfinite(multiplier)
    assert multiplier == 1.5


def test_planning_reads_committed_inflation_lag_without_measurement_side_effects():
    econ = Economy(Config.v13(
        n_ticks=1,
        n_households=8,
        demographics_population=12,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
        monetary_direct_transmission=True,
    ))
    econ._prev_inflation = 8.0e-5
    econ._infl_ema = 5.0e-5
    econ.policy.policy_rate_override = 2.0e-4
    set_policy_rate(econ)
    committed_sensor = econ._infl_ema
    before = (econ._prev_inflation, len(econ.records))

    run_planning_phase(econ)

    # Planning consumes ordinary Calvo draws, but it neither collects metrics nor
    # advances either inflation observation state.
    assert econ._infl_ema == committed_sensor
    assert econ._prev_inflation == before[0]
    assert len(econ.records) == before[1]


def _integrated_phase_response(rate: float) -> tuple[float, float, float, float]:
    cfg = Config.v3(
        n_firms_c=2,
        n_firms_k=1,
        n_households=3,
        seed=41,
        theta_wage=0.0,
        theta_price=0.0,
        kappa=100.0,
        r_interest=0.02,
        r_neutral=0.02,
        monetary_direct_transmission=True,
        firm_credit_min_dscr=1.25,
    )
    econ = Economy(cfg)
    debtor = econ.households[0]
    debt_free = econ.households[1]
    econ.ledger.create_loan(debtor.id, 50.0)
    # Identify the consumption edge on a genuinely cash-constrained debtor.
    # Cash-rich debtors correctly keep the same budget (covered by the local test).
    econ.ledger.transfer(
        debtor.id,
        econ.households[2].id,
        econ.ledger.balance(debtor.id) - 10.0,
    )
    debtor.y_expected = debtor.income_realized = 10.0

    applicant = econ.c_firms[0]
    econ.ledger.transfer(applicant.id, econ.households[2].id, 190.0)
    econ.policy.policy_rate_override = rate
    set_policy_rate(econ)
    run_planning_phase(econ)

    investment = sum(firm.investment_target for firm in econ.investing_firms)
    debtor_budget = household_goods_cash_budget(econ, debtor)
    debt_free_budget = household_goods_cash_budget(econ, debt_free)

    # Keep the actual credit orchestrator and ledger posting, while pinning one
    # transparent applicant at a narrow positive operating-cash-flow margin so
    # the DSCR edge is identified in all three arms.
    applicant.price = 1.0
    applicant.demand_expected = 20.5
    applicant.wage = 1.0
    applicant.labor_demand_notional = 20.0
    applicant.production_target = 0.0
    applicant.investment_target = 0.0
    applicant.energy_intensity = 0.0
    run_credit_phase(econ)
    return investment, econ._new_loans, debtor_budget, debt_free_budget


def test_paired_cut_neutral_hike_phase_irf_identifies_all_three_direct_channels():
    cut = _integrated_phase_response(0.0)
    neutral = _integrated_phase_response(0.02)
    hike = _integrated_phase_response(0.05)

    for index in range(3):
        assert cut[index] > neutral[index] > hike[index]
    assert cut[3] == neutral[3] == hike[3]


def test_goods_boundary_reserves_cash_but_actual_debt_service_posts_only_once():
    cfg = Config.v7(
        n_firms_c=2,
        n_firms_k=1,
        n_households=3,
        seed=3,
        monetary_direct_transmission=True,
        r_interest=0.02,
        r_neutral=0.02,
    )
    econ = Economy(cfg)
    household = econ.households[0]
    econ.ledger.create_loan(household.id, 50.0)
    opening_cash = econ.ledger.balance(household.id)
    opening_debt = econ.ledger.debt(household.id)
    econ._rate = 0.02

    run_planning_phase(econ)
    assert econ.ledger.balance(household.id) == opening_cash
    assert econ.ledger.debt(household.id) == opening_debt

    scheduled = cfg.hh_amort * opening_debt + econ._rate * opening_debt
    assert household_goods_cash_budget(econ, household) <= max(0.0, opening_cash - scheduled)
    run_household_debt_service_phase(econ)
    assert opening_cash - econ.ledger.balance(household.id) == pytest.approx(scheduled)
    assert opening_debt - econ.ledger.debt(household.id) == pytest.approx(cfg.hh_amort * opening_debt)


def test_household_credit_is_rechecked_at_the_final_goods_cash_reservation():
    econ = Economy(Config.v7(
        n_firms_c=2,
        n_firms_k=1,
        n_households=3,
        seed=31,
        monetary_direct_transmission=True,
        hh_credit_limit=10.0,
        r_interest=0.02,
    ))
    household = econ.households[0]
    econ.ledger.create_loan(household.id, 50.0)
    econ.ledger.transfer(
        household.id,
        econ.households[1].id,
        econ.ledger.balance(household.id) - 10.0,
    )
    household.y_expected = 50.0
    household.consumption_budget = 200.0
    household._consumption_budget_before_debt_service = 200.0

    run_credit_phase(econ)

    service = B.household_contractual_debt_service(
        debt=econ.ledger.debt(household.id),
        margin_debt=household.margin_debt,
        loan_rate=econ._rate,
        amort=econ.cfg.hh_amort,
    )
    assert econ._hh_credit_new > 0.0
    assert household_goods_cash_budget(econ, household) <= max(
        0.0, econ.ledger.balance(household.id) - service
    )


def test_current_wage_received_after_planning_restores_affordable_consumption():
    econ = Economy(Config.v7(
        n_firms_c=2,
        n_firms_k=1,
        n_households=3,
        seed=37,
        monetary_direct_transmission=True,
        r_interest=0.02,
    ))
    household = econ.households[0]
    payer = econ.firms[0]
    econ.ledger.create_loan(household.id, 50.0)
    econ.ledger.transfer(
        household.id,
        econ.households[1].id,
        econ.ledger.balance(household.id),
    )
    household.consumption_budget = 80.0

    # Planning/credit run before labor.  The goods boundary must use the live
    # wage-funded cash position rather than permanently cap demand at opening cash.
    assert household_goods_cash_budget(econ, household) == 0.0
    econ.ledger.transfer(payer.id, household.id, 100.0)
    service = B.household_contractual_debt_service(
        debt=econ.ledger.debt(household.id),
        margin_debt=household.margin_debt,
        loan_rate=econ._rate,
        amort=econ.cfg.hh_amort,
    )
    assert household_goods_cash_budget(econ, household) == pytest.approx(
        min(80.0, 100.0 - service)
    )


def _lifecycle_budget(direct: bool) -> tuple[float, float, float]:
    cfg = Config.v13(
        n_ticks=1,
        n_households=8,
        demographics_population=12,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
        seed=8,
        monetary_direct_transmission=direct,
        lifecycle_alpha_wealth_draw=100.0,
    )
    econ = Economy(cfg)
    household = econ.households[0]
    econ.ledger.create_loan(household.id, 20.0)
    econ.demographic_bridge.post_household_debt_creation(household.id, 20.0)
    econ.policy.policy_rate_override = 3.0e-4
    set_policy_rate(econ)
    opening_cash = econ.ledger.balance(household.id)
    run_planning_phase(econ)
    assert econ.ledger.balance(household.id) == opening_cash
    return household_goods_cash_budget(econ, household), B.household_contractual_debt_service(
        debt=20.0,
        margin_debt=0.0,
        loan_rate=3.0e-4,
        amort=cfg.hh_amort,
    ), opening_cash


def test_lifecycle_consumption_uses_the_same_debt_cash_reservation():
    unreserved, scheduled, opening_cash = _lifecycle_budget(False)
    reserved, same_scheduled, same_opening_cash = _lifecycle_budget(True)
    assert same_scheduled == scheduled
    assert same_opening_cash == opening_cash
    assert reserved == pytest.approx(min(unreserved, max(0.0, opening_cash - scheduled)))


def test_default_off_path_never_calls_direct_helpers_or_consumes_extra_rng(monkeypatch):
    cfg = Config.v3(
        n_firms_c=2,
        n_firms_k=1,
        n_households=3,
        seed=19,
        monetary_direct_transmission=False,
    )
    econ = Economy(cfg)
    applicant = econ.c_firms[0]
    econ.ledger.transfer(applicant.id, econ.households[0].id, 190.0)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("direct helper reached while master flag is off")

    monkeypatch.setattr(B, "investment_user_cost_multiplier", forbidden)
    monkeypatch.setattr(B, "reserve_household_debt_service", forbidden)
    monkeypatch.setattr(B, "firm_debt_service_headroom", forbidden)

    expected_rng = random.Random()
    expected_rng.setstate(econ.rng.getstate())
    for _firm in econ.firms:
        expected_rng.random()  # wage Calvo draw
        expected_rng.random()  # price Calvo draw
    run_planning_phase(econ)
    assert econ.rng.getstate() == expected_rng.getstate()
    run_credit_phase(econ)


def test_housing_investor_uses_real_safe_asset_return_not_policy_as_deposit_rate():
    direct = Economy(Config.v13(
        n_ticks=1,
        n_households=8,
        demographics_population=12,
        n_firms_c=2,
                n_firms_k=1,
                n_banks=1,
                monetary_direct_transmission=True,
                bank_equity_trading=False,
            ))
    direct._rate = 5.0e-4
    direct._bonds_outstanding = 0.0
    assert investor_safe_asset_return_annual(direct) == 0.0

    direct._bonds_outstanding = 100.0
    expected_bond_return = math.expm1(365.0 * math.log1p(direct.cfg.bond_coupon))
    assert investor_safe_asset_return_annual(direct) == pytest.approx(expected_bond_return)

    legacy = Economy(Config.v13(
        n_ticks=1,
        n_households=8,
        demographics_population=12,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
        monetary_direct_transmission=False,
    ))
    legacy._rate = 5.0e-4
    assert investor_safe_asset_return_annual(legacy) == pytest.approx(5.0e-4 * 365.0)


def test_daily_valuation_discount_is_policy_sensitive_and_continuous_at_zlb():
    def economy_at(rate: float) -> Economy:
        econ = Economy(Config.v13(
            n_ticks=1,
            n_households=8,
            demographics_population=12,
            n_firms_c=2,
            n_firms_k=1,
            n_banks=1,
            monetary_direct_transmission=True,
            bank_equity_trading=False,
        ))
        econ._rate = rate
        return econ

    at_zlb = economy_at(0.0)
    just_above = economy_at(1.0e-9)
    zlb_discount = valuation_discount_rate(at_zlb)
    above_discount = valuation_discount_rate(just_above)
    assert zlb_discount == pytest.approx(at_zlb.cfg.valuation_risk_premium)
    assert above_discount - zlb_discount == pytest.approx(1.0e-9)

    zlb_value = residual_income_fundamental(
        book_value=100.0,
        residual_income=1.0,
        shares_outstanding=100.0,
        discount_rate=zlb_discount,
    )
    above_value = residual_income_fundamental(
        book_value=100.0,
        residual_income=1.0,
        shares_outstanding=100.0,
        discount_rate=above_discount,
    )
    assert math.isfinite(zlb_value)
    assert zlb_value > above_value
    assert (zlb_value - above_value) / zlb_value < 1.0e-4
    assert residual_income_fundamental(
        book_value=-100.0,
        residual_income=0.0,
        shares_outstanding=100.0,
        discount_rate=zlb_discount,
    ) == 0.0

    for econ in (at_zlb, just_above):
        bank = econ.banks[0]
        bank.profit = 1.0
        bank.earnings_ema = 1.0
        update_bank_valuation(econ)
        assert math.isfinite(bank.share_price)
    assert at_zlb.banks[0].share_price > just_above.banks[0].share_price
