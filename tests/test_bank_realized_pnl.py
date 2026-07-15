from __future__ import annotations

import pytest

import macro_sim.systems.credit as credit_system
from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.reporting.metrics import compute_tick_metrics
from macro_sim.systems.banking import (
    record_bank_credit_loss,
    reset_bank_realized_pnl,
    run_interbank_phase,
)
from macro_sim.systems.credit import finalize_bank_pnl, run_debt_service_phase
from macro_sim.systems.securities import run_bill_maturity_phase


def test_realized_bank_pnl_is_opt_in_and_enabled_by_the_diagnostic_frontier():
    cfg = Config.v3()

    assert cfg.bank_realized_pnl is False
    assert cfg.banking.bank_realized_pnl is False
    assert cfg.credit.bank_realized_pnl is False
    assert FULL_FRONTIER_FLAGS["bank_realized_pnl"] is True


def _v3(**overrides) -> Economy:
    params = dict(
        n_firms_c=1,
        n_firms_k=1,
        n_households=2,
        n_ticks=1,
        seed=1,
        d_bank0=100.0,
        bank_realized_pnl=True,
    )
    params.update(overrides)
    return Economy(Config.v3(**params))


def test_realized_pnl_bridge_contains_only_posted_cash_and_loss_legs(monkeypatch):
    econ = _v3()
    bank = econ.banks[0]
    reset_bank_realized_pnl(econ)
    bank.rho = 0.0
    bank.loan_interest = 10.0
    bank.bond_coupon = 3.0
    bank.interbank_interest_income = 2.0
    bank.interbank_interest_expense = 1.0
    bank.external_interest_expense = 1.5
    bank.realized_credit_losses = 12.0
    valued_profit = []
    monkeypatch.setattr(
        credit_system,
        "update_bank_valuation",
        lambda model: valued_profit.extend(item.profit for item in model.banks),
    )

    finalize_bank_pnl(econ)

    assert bank.profit == pytest.approx(0.5)
    assert bank.interest_income == pytest.approx(10.0)  # legacy loan-interest alias
    assert bank.dividends_paid == 0.0
    assert valued_profit == [pytest.approx(0.5)]


def test_writeoff_is_net_before_dividend_and_valuation(monkeypatch):
    econ = _v3()
    bank = econ.banks[0]
    firm = econ.firms[0]
    reset_bank_realized_pnl(econ)
    econ.ledger.create_loan(firm.id, 100.0)
    household_cash_before = sum(econ.ledger.balance(h.id) for h in econ.households)

    run_debt_service_phase(econ)

    assert bank.loan_interest > 0.0
    assert bank.profit == 0.0
    assert bank.dividends_paid == 0.0
    assert sum(econ.ledger.balance(h.id) for h in econ.households) == household_cash_before

    loss = bank.loan_interest + 1.0
    econ.ledger.write_off(firm.id, bank.id, loss)
    record_bank_credit_loss(econ, bank.id, loss)
    valued_profit = []
    monkeypatch.setattr(
        credit_system,
        "update_bank_valuation",
        lambda model: valued_profit.extend(item.profit for item in model.banks),
    )

    finalize_bank_pnl(econ)

    assert bank.profit == pytest.approx(-1.0)
    assert bank.dividends_paid == 0.0
    assert sum(econ.ledger.balance(h.id) for h in econ.households) == household_cash_before
    assert valued_profit == [pytest.approx(-1.0)]


def test_target_capital_mode_never_distributes_existing_capital():
    econ = Economy(Config.v11(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_banks=2,
        n_ticks=1,
        seed=2,
        d_bank0=100.0,
        bank_target_capital_ratio=0.1,
        bank_realized_pnl=True,
    ))
    reset_bank_realized_pnl(econ)
    bank = econ.banks[0]
    bank.loan_interest = 5.0
    capital_before = econ.ledger.balance(bank.id)

    finalize_bank_pnl(econ)

    assert bank.profit == pytest.approx(5.0)
    assert bank.dividends_paid == pytest.approx(5.0)
    assert bank.dividends_paid <= bank.profit
    assert econ.ledger.balance(bank.id) == pytest.approx(capital_before - 5.0)


def test_bank_bond_coupon_and_interbank_interest_enter_named_legs():
    bond_econ = Economy(Config.v123(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_banks=2,
        n_ticks=1,
        seed=3,
    ))
    reset_bank_realized_pnl(bond_econ)
    bank = bond_econ.banks[0]
    face = 100.0
    bond_econ._bonds = [{
        "holder": bank.id,
        "face": face,
        "cost": face,
        "matures_at": bond_econ.t + 2,
    }]
    bond_econ._bonds_outstanding = face
    bond_econ._bond_holdings = {bank.id: face}

    run_bill_maturity_phase(bond_econ)

    assert bank.bond_coupon == pytest.approx(bond_econ.cfg.bond_coupon * face)

    ib_econ = Economy(Config.v114(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_banks=2,
        n_ticks=1,
        seed=4,
        d_bank0=100.0,
    ))
    reset_bank_realized_pnl(ib_econ)
    borrower, lender = ib_econ.banks
    opening = ib_econ.ledger.reserves(borrower.id)
    ib_econ.ledger.move_reserves(borrower.id, lender.id, opening + 10.0)

    run_interbank_phase(ib_econ)

    claim = lender.interbank_assets[borrower.id]
    assert borrower.interbank_interest_expense == 0.0  # originated now; due next phase
    reset_bank_realized_pnl(ib_econ)
    ib_econ.ledger.move_reserves(
        "CB",
        borrower.id,
        claim.principal * (1.0 + claim.rate),
    )
    run_interbank_phase(ib_econ)

    assert borrower.interbank_interest_expense > 0.0
    assert lender.interbank_interest_income == pytest.approx(borrower.interbank_interest_expense)


def test_reset_clears_every_realized_leg():
    econ = _v3()
    bank = econ.banks[0]
    bank.interest_income = 1.0
    bank.loan_interest = 2.0
    bank.bond_coupon = 3.0
    bank.interbank_interest_income = 4.0
    bank.interbank_interest_expense = 5.0
    bank.external_interest_expense = 6.0
    bank.realized_credit_losses = 7.0
    bank.dividends_paid = 8.0
    bank.profit = -9.0

    reset_bank_realized_pnl(econ)

    assert (
        bank.interest_income,
        bank.loan_interest,
        bank.bond_coupon,
        bank.interbank_interest_income,
        bank.interbank_interest_expense,
        bank.external_interest_expense,
        bank.realized_credit_losses,
        bank.dividends_paid,
        bank.profit,
    ) == (0.0,) * 9


def test_firm_demographics_does_not_erase_an_earlier_tick_writeoff():
    """Housing/probate losses occur before the firm-demography phase."""
    from macro_sim.systems.firm_demographics import run_firm_demographics_phase

    econ = _v3(firm_dynamics=False)
    econ._writeoffs = 7.5
    run_firm_demographics_phase(econ)

    assert econ._writeoffs == pytest.approx(7.5)


def test_total_principal_metric_includes_ordinary_household_repayment():
    econ = _v3(household_credit=True, hh_amort=0.10)
    household = econ.households[0]
    econ.ledger.create_loan(household.id, 10.0)

    run_debt_service_phase(econ)
    record = compute_tick_metrics(econ)

    assert econ._hh_principal == pytest.approx(1.0)
    assert record["principal_repaid"] == 0.0  # legacy firm-only compatibility field
    assert record["total_principal_repaid"] == pytest.approx(1.0)
