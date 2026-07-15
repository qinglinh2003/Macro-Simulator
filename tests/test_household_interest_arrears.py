"""Household contractual-interest stock, cash waterfall and write-off bridge."""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.diagnostics.probes import DeepProbeCollector
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.housing.mortgage import Mortgage
from macro_sim.reporting.metrics import compute_tick_metrics
from macro_sim.systems.banking import bank_for, refresh_loan_books
from macro_sim.systems.credit import run_household_debt_service_phase
from macro_sim.systems.goods import household_goods_cash_budget, run_goods_phase


def make_econ(*, housing: bool = False, **overrides) -> Economy:
    params = dict(
        n_firms_c=1,
        n_firms_k=1,
        n_households=3,
        n_ticks=1,
        seed=97,
        r_interest=0.10,
        hh_amort=0.10,
        household_interest_arrears=True,
        bank_realized_pnl=True,
        d_bank0=100.0,
    )
    if housing:
        params.update(
            housing_enabled=True,
            housing_market_enabled=True,
            mortgage_enabled=True,
        )
    params.update(overrides)
    return Economy(Config.v3(**params))


def set_cash(econ: Economy, household, amount: float) -> None:
    sink = next(item for item in econ.households if item is not household)
    current = econ.ledger.balance(household.id)
    if current > amount:
        econ.ledger.transfer(household.id, sink.id, current - amount)
    elif current < amount:
        econ.ledger.transfer(sink.id, household.id, amount - current)


def originate(econ: Economy, household, amount: float) -> None:
    econ.ledger.create_loan(household.id, amount)


def attach_mortgage(econ: Economy, household, amount: float) -> Mortgage:
    dwelling = econ.housing.dwellings_of(household.id)[0]
    mortgage = Mortgage(
        account=household.id,
        dwelling_id=dwelling.id,
        balance=amount,
        bank_id=bank_for(econ, household.id).id,
    )
    econ.mortgage_book.loans[household.id] = mortgage
    return mortgage


def test_arrears_are_opt_in_and_enabled_by_the_diagnostic_frontier() -> None:
    cfg = Config.v3()

    assert cfg.household_interest_arrears is False
    assert cfg.credit.household_interest_arrears is False
    assert cfg.goods.household_interest_arrears is False
    assert FULL_FRONTIER_FLAGS["household_interest_arrears"] is True


def test_cash_eight_rolls_two_interest_without_repaying_principal_then_cures() -> None:
    econ = make_econ()
    household = econ.households[0]
    bank = bank_for(econ, household.id)
    originate(econ, household, 100.0)
    set_cash(econ, household, 8.0)

    run_household_debt_service_phase(econ)

    assert econ.ledger.balance(household.id) == pytest.approx(0.0)
    assert econ.ledger.debt(household.id) == pytest.approx(100.0)
    assert household.credit_interest_arrears_opening == pytest.approx(0.0)
    assert household.credit_interest_accrued == pytest.approx(10.0)
    assert household.credit_interest_due == pytest.approx(10.0)
    assert household.credit_interest_cash_paid == pytest.approx(8.0)
    assert household.credit_interest_arrears == pytest.approx(2.0)
    assert econ._hh_principal == pytest.approx(0.0)
    assert bank.loan_interest == pytest.approx(8.0)
    refresh_loan_books(econ)
    assert econ._loan_book[bank.id] == pytest.approx(100.0)

    econ.t += 1
    set_cash(econ, household, 15.0)
    bank_cash_interest_before = bank.loan_interest
    run_household_debt_service_phase(econ)

    assert household.credit_interest_arrears_opening == pytest.approx(2.0)
    assert household.credit_interest_accrued == pytest.approx(10.0)
    assert household.credit_interest_due == pytest.approx(12.0)
    assert household.credit_interest_cash_paid == pytest.approx(12.0)
    assert household.credit_interest_arrears == pytest.approx(0.0)
    assert econ.ledger.debt(household.id) == pytest.approx(97.0)
    assert econ._hh_principal == pytest.approx(3.0)
    assert bank.loan_interest - bank_cash_interest_before == pytest.approx(12.0)


def test_zero_principal_with_memo_arrears_still_services_cash_interest() -> None:
    econ = make_econ()
    household = econ.households[0]
    household.credit_interest_arrears = 4.0
    set_cash(econ, household, 4.0)

    run_household_debt_service_phase(econ)

    assert econ.ledger.debt(household.id) == 0.0
    assert household.credit_interest_cash_paid == pytest.approx(4.0)
    assert household.credit_interest_arrears == 0.0


def test_mortgage_only_household_services_with_consumer_and_margin_credit_off() -> None:
    econ = make_econ(
        housing=True,
        household_credit=False,
        margin_credit=False,
    )
    household = econ.households[0]
    originate(econ, household, 80.0)
    mortgage = attach_mortgage(econ, household, 80.0)
    set_cash(econ, household, 20.0)

    run_household_debt_service_phase(econ)

    assert econ._hh_interest == pytest.approx(8.0)
    assert econ._hh_principal == pytest.approx(8.0)
    assert econ.ledger.debt(household.id) == pytest.approx(72.0)
    assert mortgage.balance == pytest.approx(72.0)


def test_mortgage_and_consumer_principal_amortize_pro_rata() -> None:
    econ = make_econ(housing=True, r_interest=0.0)
    household = econ.households[0]
    originate(econ, household, 100.0)
    mortgage = attach_mortgage(econ, household, 80.0)
    set_cash(econ, household, 10.0)

    run_household_debt_service_phase(econ)

    assert econ.ledger.debt(household.id) == pytest.approx(90.0)
    assert mortgage.balance == pytest.approx(72.0)
    assert econ.ledger.debt(household.id) - mortgage.balance == pytest.approx(18.0)


def test_goods_reservation_includes_opening_arrears_and_contractual_service() -> None:
    econ = make_econ(monetary_direct_transmission=False)
    household = econ.households[0]
    originate(econ, household, 100.0)
    household.credit_interest_arrears = 2.0
    household.consumption_budget = 25.0
    for other in econ.households[1:]:
        other.consumption_budget = 0.0
    set_cash(econ, household, 25.0)
    for firm in econ.c_firms:
        firm.price = 1.0
        firm.inventory = 100.0

    assert household_goods_cash_budget(econ, household) == pytest.approx(3.0)
    run_goods_phase(econ)

    assert econ._hh_contractual_debt_service_due == pytest.approx(22.0)
    assert econ._hh_interest_arrears_in_goods_reservation == pytest.approx(2.0)
    assert econ._hh_debt_service_reserved == pytest.approx(22.0)


def test_foreclosure_extinguishes_arrears_pro_rata_without_extra_bank_loss() -> None:
    econ = make_econ(housing=True)
    household = econ.households[0]
    bank = bank_for(econ, household.id)
    originate(econ, household, 100.0)
    attach_mortgage(econ, household, 80.0)
    household.credit_interest_arrears = 10.0
    set_cash(econ, household, 0.0)
    econ._house_price = 1.0

    econ.mortgage_book.maintain(econ)

    assert econ.ledger.debt(household.id) == pytest.approx(20.0)
    assert household.credit_interest_arrears == pytest.approx(2.0)
    assert household.credit_interest_arrears_extinguished == pytest.approx(8.0)
    assert bank.realized_credit_losses == pytest.approx(80.0)
    assert household.id not in econ.mortgage_book.loans
    record = compute_tick_metrics(econ)
    assert record["household_interest_arrears_opening"] == pytest.approx(10.0)
    assert record["household_interest_arrears_extinguished"] == pytest.approx(8.0)
    assert record["household_interest_arrears_closing"] == pytest.approx(2.0)
    assert record["household_interest_arrears_stock_flow_residual"] == pytest.approx(0.0)


def test_metrics_and_deep_probe_publish_an_exact_household_interest_bridge() -> None:
    econ = make_econ()
    household = econ.households[0]
    originate(econ, household, 100.0)
    household.credit_interest_arrears = 2.0
    set_cash(econ, household, 15.0)

    run_household_debt_service_phase(econ)
    record = compute_tick_metrics(econ)
    probe = DeepProbeCollector().collect(econ, record)

    assert record["household_interest_arrears_opening"] == pytest.approx(2.0)
    assert record["household_interest_accrued"] == pytest.approx(10.0)
    assert record["household_interest_due"] == pytest.approx(12.0)
    assert record["household_interest_cash_paid"] == pytest.approx(12.0)
    assert record["household_interest_arrears_closing"] == pytest.approx(0.0)
    assert record["household_interest_arrears_extinguished"] == pytest.approx(0.0)
    assert record["household_interest_arrears_stock_flow_residual"] == pytest.approx(0.0)
    assert record["household_interest_cash_counter_residual"] == pytest.approx(0.0)
    assert probe["household_interest_arrears_opening"] == pytest.approx(2.0)
    assert probe["household_interest_accrued"] == pytest.approx(10.0)
    assert probe["household_interest_cash_paid"] == pytest.approx(12.0)
    assert probe["household_interest_arrears_stock_flow_residual"] == pytest.approx(0.0)
