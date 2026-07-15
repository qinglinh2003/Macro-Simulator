"""Acceptance tests for the opt-in full firm income statement."""

from __future__ import annotations

import pytest

import macro_sim.economy as economy_module
from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.diagnostics.probes import DeepProbeCollector
from macro_sim.housing.market import run_housing_market_phase
from macro_sim.reporting.metrics import compute_tick_metrics
from macro_sim.systems.banking import reset_bank_realized_pnl
from macro_sim.systems.credit import run_firm_debt_service_phase
from macro_sim.systems.firm_accounting import reset_firm_pnl_flows
from macro_sim.systems.firm_demographics import bankrupt_firm, birth_consumption_firm
from macro_sim.systems.planning import run_planning_phase
from macro_sim.systems.settlement import run_settlement_phase


def _v3(**overrides) -> Economy:
    params = dict(
        seed=41,
        n_firms_c=1,
        n_firms_k=1,
        n_households=4,
        n_ticks=1,
        firm_full_pnl=True,
        bank_realized_pnl=True,
        amort=0.0,
        rho=0.5,
    )
    params.update(overrides)
    return Economy(Config.v3(**params))


def test_flag_is_default_off_frontier_on_and_false_is_bit_identical():
    assert Config().firm_full_pnl is False
    assert FULL_FRONTIER_FLAGS["firm_full_pnl"] is True

    params = dict(seed=44, n_firms_c=4, n_firms_k=2, n_households=12, n_ticks=30)
    implicit = Economy(Config.v3(**params))
    explicit = Economy(Config.v3(**params, firm_full_pnl=False))

    assert implicit.run() == explicit.run()
    assert "firm_pnl_net_income" not in implicit.records[-1]
    assert implicit.ledger.snapshot() == explicit.ledger.snapshot()
    assert implicit.rng.getstate() == explicit.rng.getstate()


def test_enabled_tick_exports_the_named_aggregate_bridge():
    econ = _v3()
    record = econ.step()

    for key in (
        "firm_pnl_revenue", "firm_pnl_intermediate_inputs",
        "firm_pnl_compensation", "firm_pnl_ebitda",
        "firm_pnl_depreciation", "firm_pnl_ebit",
        "firm_pnl_cash_interest", "firm_pnl_pre_tax_income",
        "firm_pnl_tax_total", "firm_pnl_net_income",
        "firm_pnl_dividends_paid", "firm_pnl_retained_earnings",
        "firm_pnl_interest_arrears",
    ):
        assert key in record
    assert record["profit_total"] == pytest.approx(record["firm_pnl_net_income"])
    assert record["firm_pnl_bridge_max_abs_residual"] == pytest.approx(0.0, abs=1e-12)
    assert record["firm_pnl_interest_cash_counter_residual"] == pytest.approx(0.0, abs=1e-12)
    assert record["firm_bank_interest_counterparty_residual"] == pytest.approx(0.0, abs=1e-12)


def test_exact_income_statement_bridge_and_replacement_cost_depreciation():
    econ = _v3()
    firm = econ.c_firms[0]
    econ._firm_pnl_capital_price = 5.0       # no K trade: explicit hold-last price
    firm.revenue = 100.0
    firm.wagebill = 30.0
    firm.energy_cost_used = 10.0
    firm.capital = 20.0                     # opening productive stock
    firm.delta_K = 0.10
    firm.investment = 3.0                   # asset swap, never an expense

    run_settlement_phase(econ)

    assert firm.pnl_revenue == pytest.approx(100.0)
    assert firm.pnl_intermediate_inputs == pytest.approx(10.0)
    assert firm.pnl_compensation == pytest.approx(30.0)
    assert firm.pnl_ebitda == pytest.approx(60.0)
    assert firm.pnl_capital_price == pytest.approx(5.0)
    assert firm.pnl_depreciation == pytest.approx(0.10 * 20.0 * 5.0)
    assert firm.pnl_ebit == pytest.approx(50.0)
    assert firm.pnl_pre_tax_income == pytest.approx(50.0)
    assert firm.pnl_net_income == pytest.approx(50.0)
    assert firm.pnl_dividends_paid == pytest.approx(25.0)
    assert firm.pnl_retained_earnings == pytest.approx(25.0)
    assert firm.profit == firm.pnl_net_income  # documented compatibility migration
    assert firm.capital == pytest.approx(20.0 * 0.90 + 3.0)

    assert firm.pnl_ebitda == pytest.approx(
        firm.pnl_revenue - firm.pnl_intermediate_inputs - firm.pnl_compensation
    )
    assert firm.pnl_ebit == pytest.approx(firm.pnl_ebitda - firm.pnl_depreciation)
    assert firm.pnl_pre_tax_income == pytest.approx(firm.pnl_ebit - firm.pnl_interest_expense)
    assert firm.pnl_net_income == pytest.approx(
        firm.pnl_pre_tax_income - firm.pnl_profit_tax - firm.pnl_windfall_tax
    )
    assert firm.pnl_retained_earnings == pytest.approx(
        firm.pnl_net_income - firm.pnl_dividends_paid
    )


def test_cash_interest_reconciles_borrower_bank_ledger_and_carries_arrears():
    econ = _v3(r_interest=0.10)
    firm, bank = econ.c_firms[0], econ.banks[0]
    econ.ledger.create_loan(firm.id, 50.0)
    econ.ledger.transfer(
        firm.id,
        econ.households[0].id,
        econ.ledger.balance(firm.id) - 2.0,
    )
    reset_bank_realized_pnl(econ)
    firm_open = econ.ledger.balance(firm.id)
    bank_open = econ.ledger.balance(bank.id)

    run_firm_debt_service_phase(econ)

    assert firm.pnl_interest_accrued == pytest.approx(5.0)
    assert firm.pnl_interest_due == pytest.approx(5.0)
    assert firm.pnl_interest_expense == pytest.approx(2.0)
    assert firm.pnl_interest_shortfall == pytest.approx(3.0)
    assert firm.pnl_interest_arrears == pytest.approx(3.0)
    assert econ._interest_paid == pytest.approx(2.0)
    assert bank.loan_interest == pytest.approx(2.0)
    assert firm_open - econ.ledger.balance(firm.id) == pytest.approx(2.0)
    assert econ.ledger.balance(bank.id) - bank_open == pytest.approx(2.0)

    # Next service window explicitly presents opening arrears and collects them
    # together with the new contractual interest; they never silently disappear.
    econ.ledger.transfer(econ.households[0].id, firm.id, 20.0)
    reset_firm_pnl_flows(firm)
    reset_bank_realized_pnl(econ)
    run_firm_debt_service_phase(econ)
    assert firm.pnl_interest_arrears_opening == pytest.approx(3.0)
    assert firm.pnl_interest_accrued == pytest.approx(5.0)
    assert firm.pnl_interest_due == pytest.approx(8.0)
    assert firm.pnl_interest_expense == pytest.approx(8.0)
    assert firm.pnl_interest_arrears == pytest.approx(0.0)
    assert bank.loan_interest == pytest.approx(8.0)


def test_exit_after_settlement_keeps_current_pnl_in_reporting_perimeter():
    """An exiting borrower must not disappear from its already-settled cash bridge."""
    econ = _v3(r_interest=0.10)
    firm = econ.c_firms[0]
    econ.ledger.create_loan(firm.id, 50.0)
    reset_bank_realized_pnl(econ)

    run_firm_debt_service_phase(econ)
    run_settlement_phase(econ)
    cash_interest = firm.pnl_interest_expense
    assert cash_interest > 0.0

    bankrupt_firm(econ, firm)
    assert firm not in econ.firms
    assert firm in econ._exited_firms_tick

    record = compute_tick_metrics(econ)
    probes = DeepProbeCollector().collect(econ, record)
    for snapshot in (record, probes):
        assert snapshot["firm_pnl_cash_interest"] == pytest.approx(cash_interest)
        assert snapshot["firm_pnl_interest_cash_counter_residual"] == pytest.approx(0.0)
        assert snapshot["firm_bank_interest_counterparty_residual"] == pytest.approx(0.0)


def test_principal_repayment_is_a_balance_sheet_move_not_a_pnl_expense():
    econ = _v3(r_interest=0.10, amort=0.10)
    firm = econ.c_firms[0]
    econ.ledger.create_loan(firm.id, 50.0)
    firm.revenue = 20.0
    reset_bank_realized_pnl(econ)

    run_firm_debt_service_phase(econ)
    run_settlement_phase(econ)

    assert econ._principal_repaid == pytest.approx(5.0)
    assert firm.pnl_interest_expense == pytest.approx(5.0)
    assert firm.pnl_ebit == pytest.approx(20.0 - firm.pnl_depreciation)
    assert firm.pnl_pre_tax_income == pytest.approx(firm.pnl_ebit - 5.0)


def test_interest_arrears_and_current_interest_are_paid_before_principal():
    econ = _v3(r_interest=0.10, amort=0.20)
    firm, bank = econ.c_firms[0], econ.banks[0]
    econ.ledger.create_loan(firm.id, 50.0)
    firm.pnl_interest_arrears = 3.0
    # Cash cannot cover arrears (3), current interest (5), and contractual
    # principal (10).  The interest-first waterfall must pay 8 + only 2 of
    # principal; the old implementation paid all 10 of principal and no interest.
    econ.ledger.transfer(
        firm.id,
        econ.households[0].id,
        econ.ledger.balance(firm.id) - 10.0,
    )
    reset_bank_realized_pnl(econ)
    bank_open = econ.ledger.balance(bank.id)

    run_firm_debt_service_phase(econ)

    assert firm.pnl_interest_arrears_opening == pytest.approx(3.0)
    assert firm.pnl_interest_accrued == pytest.approx(5.0)
    assert firm.pnl_interest_due == pytest.approx(8.0)
    assert firm.pnl_interest_expense == pytest.approx(8.0)
    assert firm.pnl_interest_arrears == pytest.approx(0.0)
    assert econ._interest_paid == pytest.approx(8.0)
    assert bank.loan_interest == pytest.approx(8.0)
    assert econ.ledger.balance(bank.id) - bank_open == pytest.approx(8.0)
    assert econ._principal_repaid == pytest.approx(2.0)
    assert econ.ledger.debt(firm.id) == pytest.approx(48.0)
    assert econ.ledger.balance(firm.id) == pytest.approx(0.0)


def test_tax_bases_are_pre_tax_income_and_losses_never_pay_dividends():
    econ = Economy(Config.v9(
        seed=7,
        n_firms_c=1,
        n_firms_k=1,
        n_households=4,
        n_ticks=1,
        firm_full_pnl=True,
        tax_profit_rate=0.25,
        tax_energy_windfall=0.10,
        rho=0.5,
    ))
    firm = econ.c_firms[0]
    firm.sells = "energy"                    # exercise the sequential windfall surtax
    econ._firm_pnl_capital_price = 5.0
    firm.revenue = 100.0
    firm.wagebill = 20.0
    firm.energy_cost_used = 10.0
    firm.capital = 20.0
    firm.delta_K = 0.10
    firm.pnl_interest_expense = 10.0
    loss_firm = econ.k_firms[0]
    loss_firm.wagebill = 5.0

    run_settlement_phase(econ)

    assert firm.pnl_ebitda == pytest.approx(70.0)
    assert firm.pnl_depreciation == pytest.approx(10.0)
    assert firm.pnl_pre_tax_income == pytest.approx(50.0)
    assert firm.pnl_profit_tax == pytest.approx(12.5)
    assert firm.pnl_windfall_tax == pytest.approx(3.75)
    assert firm.pnl_net_income == pytest.approx(33.75)
    assert firm.pnl_dividends_paid == pytest.approx(16.875)
    assert firm.pnl_retained_earnings == pytest.approx(16.875)

    assert loss_firm.pnl_net_income < 0.0       # compensation with no revenue
    assert loss_firm.pnl_dividends_paid == 0.0
    assert loss_firm.pnl_retained_earnings == loss_firm.pnl_net_income


def test_full_pnl_phase_order_services_debt_and_housing_before_close(monkeypatch):
    econ = _v3()
    calls: list[str] = []
    monkeypatch.setattr(economy_module, "run_firm_debt_service_phase", lambda _: calls.append("firm_debt"))
    monkeypatch.setattr(economy_module, "run_household_debt_service_phase", lambda _: calls.append("household_debt"))
    monkeypatch.setattr(economy_module, "run_housing_market_phase", lambda _: calls.append("housing"))
    monkeypatch.setattr(economy_module, "run_settlement_phase", lambda _: calls.append("settlement"))
    monkeypatch.setattr(econ, "_phase5_check_and_record", lambda: {})
    monkeypatch.setattr(econ, "_commit_cross_tick_state", lambda: None)

    econ._run_settlement_and_commit_phases()

    assert calls == ["firm_debt", "household_debt", "housing", "settlement"]


def test_builder_primary_sale_reaches_tax_net_income_and_retained_earnings():
    econ = Economy(Config.v13(
        seed=1,
        n_households=5,
        demographics_population=20,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
        n_ticks=1,
        housing_enabled=True,
        housing_market_enabled=True,
        housing_construction_enabled=True,
        firm_full_pnl=True,
        tax_profit_rate=0.25,
        tax_consumption_rate=0.0,
        tax_income_rate=0.0,
        tax_wealth_rate=0.0,
        gov_deficit_target=0.0,
        job_guarantee=False,
        rho=0.5,
    ))
    buyer, other = econ.households[:2]
    for dwelling in list(econ.housing.dwellings_of(buyer.id)):
        econ.housing.transfer(dwelling.id, other.id)  # one genuinely houseless buyer
    builder = econ.builders[0]
    dwelling = econ.housing.mint(builder.id)
    builder.inventory = 1.0
    econ.housing_market.list_dwelling(econ, dwelling.id, builder.id, forced=False)
    econ.housing_market.listings[dwelling.id].ask = 10.0
    econ.housing_market.buyer_buffer = 0.0

    run_housing_market_phase(econ)
    assert econ.housing.owner_of(dwelling.id) == buyer.id
    assert builder.revenue == pytest.approx(10.0)
    run_settlement_phase(econ)

    assert builder.pnl_revenue == pytest.approx(10.0)
    assert builder.pnl_pre_tax_income == pytest.approx(10.0)
    assert builder.pnl_profit_tax == pytest.approx(2.5)
    assert builder.pnl_net_income == pytest.approx(7.5)
    assert builder.pnl_dividends_paid == pytest.approx(3.75)
    assert builder.pnl_retained_earnings == pytest.approx(3.75)


def test_post_close_startup_capital_sale_is_carried_and_recognized_once():
    econ = _v3()
    supplier = econ.k_firms[0]
    run_settlement_phase(econ)             # establish this tick's accounting cutoff
    profit_at_close = supplier.profit
    price = supplier.price

    birth_consumption_firm(
        econ,
        econ.households[0],
        startup_deposits=1.0,
        capital_lots=[(supplier, 1.0)],
    )

    assert supplier.revenue == pytest.approx(price)
    assert supplier.profit == pytest.approx(profit_at_close)
    assert supplier.pnl_revenue_carry == pytest.approx(price)

    run_planning_phase(econ)
    run_settlement_phase(econ)

    assert supplier.pnl_revenue_carry_opening == pytest.approx(price)
    assert supplier.pnl_revenue == pytest.approx(price)
    assert supplier.pnl_revenue_carry == pytest.approx(0.0)
    assert supplier.profit == supplier.pnl_net_income
