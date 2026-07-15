from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.systems.banking import (
    _add_interbank_principal,
    assert_interbank_positions,
    bank_for,
    fail_bank,
    reset_bank_realized_pnl,
    run_interbank_phase,
)
from macro_sim.systems.credit import finalize_bank_pnl


def _economy(*, n_banks: int = 2, **overrides) -> Economy:
    params = dict(
        n_firms_c=2,
        n_firms_k=1,
        n_households=6,
        n_banks=n_banks,
        n_ticks=1,
        seed=11,
        d_bank0=300.0,
        interbank_rate_base=0.01,
        interbank_tightness=0.0,
        bank_realized_pnl=True,
    )
    params.update(overrides)
    return Economy(Config.v114(**params))


def _set_bank_reserves(econ: Economy, values: dict[str, float]) -> None:
    """Set a reserve stress while leaving aggregate base money conserved."""
    for bank in econ.banks:
        current = econ.ledger.reserves(bank.id)
        econ.ledger.move_reserves(bank.id, "CB", current)
    for bank_id, value in values.items():
        econ.ledger.move_reserves("CB", bank_id, value)
    econ.ledger.assert_reserves_conserved()


def _principal_assets(econ: Economy) -> float:
    return sum(
        claim.principal
        for bank in econ.banks
        for claim in bank.interbank_assets.values()
    )


def _principal_liabilities(econ: Economy) -> float:
    return sum(
        claim.principal
        for bank in econ.banks
        for claim in bank.interbank_liabilities.values()
    )


def test_new_funding_moves_only_available_principal_and_reports_actual_volume():
    econ = _economy(n_banks=3)
    borrower, lender_a, lender_b = econ.banks
    reserve_total = econ.ledger.total_reserves
    _set_bank_reserves(econ, {
        borrower.id: -100.0,
        lender_a.id: 30.0,
        lender_b.id: 10.0,
    })

    run_interbank_phase(econ)

    assert econ._interbank_volume == pytest.approx(40.0)
    assert econ.ledger.reserves(borrower.id) == pytest.approx(-60.0)
    assert econ.ledger.reserves(lender_a.id) == pytest.approx(0.0)
    assert econ.ledger.reserves(lender_b.id) == pytest.approx(0.0)
    assert _principal_assets(econ) == pytest.approx(40.0)
    assert _principal_liabilities(econ) == pytest.approx(40.0)
    assert econ.ledger.total_reserves == pytest.approx(reserve_total)
    assert_interbank_positions(econ)


def test_scarce_supply_rations_multiple_deficit_banks_pro_rata_not_by_id():
    econ = _economy(n_banks=3)
    borrower_a, borrower_b, lender = econ.banks
    _set_bank_reserves(econ, {
        borrower_a.id: -75.0,
        borrower_b.id: -25.0,
        lender.id: 40.0,
    })

    run_interbank_phase(econ)

    assert econ._interbank_volume == pytest.approx(40.0)
    assert econ.ledger.reserves(borrower_a.id) == pytest.approx(-45.0)
    assert econ.ledger.reserves(borrower_b.id) == pytest.approx(-15.0)
    assert lender.interbank_assets[borrower_a.id].principal == pytest.approx(30.0)
    assert lender.interbank_assets[borrower_b.id].principal == pytest.approx(10.0)
    assert_interbank_positions(econ)


def test_overnight_maturity_pays_cash_interest_and_returns_principal():
    econ = _economy()
    borrower, lender = econ.banks
    _set_bank_reserves(econ, {borrower.id: -50.0, lender.id: 50.0})
    run_interbank_phase(econ)
    claim = lender.interbank_assets[borrower.id]
    assert claim.principal == pytest.approx(50.0)
    assert borrower.interbank_interest_expense == 0.0
    assert lender.interbank_interest_income == 0.0

    reset_bank_realized_pnl(econ)
    interest = claim.principal * claim.rate
    borrower_capital = econ.ledger.balance(borrower.id)
    lender_capital = econ.ledger.balance(lender.id)
    reserve_total = econ.ledger.total_reserves
    econ.ledger.move_reserves("CB", borrower.id, claim.principal + interest)

    run_interbank_phase(econ)

    assert econ._interbank_volume == 0.0
    assert not lender.interbank_assets
    assert not borrower.interbank_liabilities
    assert borrower.interbank_interest_expense == pytest.approx(interest)
    assert lender.interbank_interest_income == pytest.approx(interest)
    assert econ.ledger.balance(borrower.id) == pytest.approx(borrower_capital - interest)
    assert econ.ledger.balance(lender.id) == pytest.approx(lender_capital + interest)
    assert econ.ledger.total_reserves == pytest.approx(reserve_total)
    assert_interbank_positions(econ)


def test_illiquid_claim_rolls_then_failed_borrower_defaults_to_actual_creditor():
    econ = _economy()
    borrower, lender = econ.banks
    _set_bank_reserves(econ, {borrower.id: -25.0, lender.id: 25.0})
    run_interbank_phase(econ)
    original = lender.interbank_assets[borrower.id]

    reset_bank_realized_pnl(econ)
    run_interbank_phase(econ)
    rolled = lender.interbank_assets[borrower.id]
    assert rolled.principal == pytest.approx(original.principal)
    assert rolled.accrued_interest == pytest.approx(original.principal * original.rate)
    assert borrower.interbank_interest_expense == 0.0
    assert lender.interbank_interest_income == 0.0

    borrower.alive = False
    reset_bank_realized_pnl(econ)
    lender_capital = econ.ledger.balance(lender.id)
    borrower_capital = econ.ledger.balance(borrower.id)
    reserves = {bank.id: econ.ledger.reserves(bank.id) for bank in econ.banks}
    run_interbank_phase(econ)
    finalize_bank_pnl(econ)

    assert not lender.interbank_assets
    assert not borrower.interbank_liabilities
    assert lender.realized_credit_losses == pytest.approx(original.principal)
    assert lender.profit == pytest.approx(-original.principal)
    assert econ._interbank_contagion_loss == pytest.approx(original.principal)
    assert econ.ledger.balance(lender.id) == pytest.approx(lender_capital - original.principal)
    assert econ.ledger.balance(borrower.id) == pytest.approx(borrower_capital + original.principal)
    assert {bank.id: econ.ledger.reserves(bank.id) for bank in econ.banks} == pytest.approx(reserves)
    econ.ledger.assert_conserved()
    econ.ledger.assert_reserves_conserved()
    assert_interbank_positions(econ)


def test_failure_closes_liabilities_and_bridges_assets_before_resolution():
    econ = _economy(n_banks=3, bank_resolution_fund=True)
    failed, creditor, asset_debtor = econ.banks
    rate = 0.02

    # The failing bank is simultaneously a wholesale lender and borrower.
    econ.ledger.move_reserves(failed.id, asset_debtor.id, 20.0)
    _add_interbank_principal(failed, asset_debtor, 20.0, rate)
    econ.ledger.move_reserves(creditor.id, failed.id, 30.0)
    _add_interbank_principal(creditor, failed, 30.0, rate)
    assert failed.interbank_assets and failed.interbank_liabilities
    assert_interbank_positions(econ)

    # A real ledger-backed loss makes the bank insolvent by exactly 10.  Default
    # on its 30 liability and transfer of its 20 asset should net the estate to
    # zero before the fiscal resolution fund is sized.
    borrower = next(
        account
        for account in list(econ.firms) + list(econ.households)
        if bank_for(econ, account.id) is failed
    )
    writeoff = econ.ledger.balance(failed.id) + 10.0
    econ.ledger.create_loan(borrower.id, writeoff)
    econ.ledger.write_off(borrower.id, failed.id, writeoff)
    assert econ.ledger.balance(failed.id) == pytest.approx(-10.0)
    fiscal_before = econ.ledger.balance(econ._fiscal)

    fail_bank(econ, failed)

    assert not failed.alive
    assert failed.interbank_assets == {}
    assert failed.interbank_liabilities == {}
    assert econ.ledger.balance(failed.id) == pytest.approx(0.0, abs=1e-9)
    assert econ.ledger.reserves(failed.id) == pytest.approx(0.0, abs=1e-9)
    assert econ.ledger.balance(econ._fiscal) == pytest.approx(fiscal_before)
    assert creditor.realized_credit_losses == pytest.approx(30.0)
    assert creditor.profit == pytest.approx(-30.0)
    assert econ._interbank_contagion_loss == pytest.approx(30.0)
    assert creditor.interbank_assets[asset_debtor.id].principal == pytest.approx(20.0)
    assert asset_debtor.interbank_liabilities[creditor.id].principal == pytest.approx(20.0)
    assert_interbank_positions(econ)

    # A later market phase may collect the bridged claim, but never into the
    # failed account and never books its default loss a second time.
    loss_once = creditor.realized_credit_losses
    profit_once = creditor.profit
    run_interbank_phase(econ)
    assert creditor.realized_credit_losses == pytest.approx(loss_once)
    assert creditor.profit == pytest.approx(profit_once)
    assert econ.ledger.balance(failed.id) == pytest.approx(0.0, abs=1e-9)
    assert econ.ledger.reserves(failed.id) == pytest.approx(0.0, abs=1e-9)
    assert_interbank_positions(econ)


def test_failure_loss_is_net_before_creditor_dividends():
    econ = _economy(n_banks=3, bank_resolution_fund=True, rho=1.0)
    failed, creditor, survivor = econ.banks
    principal = 30.0
    econ.ledger.move_reserves(creditor.id, failed.id, principal)
    _add_interbank_principal(creditor, failed, principal, 0.0)

    # The creditor earned 40 in cash this tick, but loses 30 when its borrower
    # fails.  Only the net 10 may be distributed at close.
    creditor.loan_interest = 40.0
    fail_bank(econ, failed)
    finalize_bank_pnl(econ)

    assert survivor.alive
    assert creditor.realized_credit_losses == pytest.approx(principal)
    assert creditor.profit == pytest.approx(10.0)
    assert creditor.dividends_paid <= 10.0 + 1e-9


def test_resolution_fund_records_actual_treasury_cash_outflow():
    econ = _economy(n_banks=2, bank_resolution_fund=True)
    failed = econ.banks[0]
    borrower = next(
        account
        for account in list(econ.firms) + list(econ.households)
        if bank_for(econ, account.id) is failed
    )
    desired_hole = 25.0
    writeoff = econ.ledger.balance(failed.id) + desired_hole
    econ.ledger.create_loan(borrower.id, writeoff)
    econ.ledger.write_off(borrower.id, failed.id, writeoff)
    fiscal_before = econ.ledger.balance(econ._fiscal)
    econ._bank_resolution_fund_paid = 0.0

    fail_bank(econ, failed)

    assert econ._bank_resolution_fund_paid == pytest.approx(desired_hole)
    assert econ.ledger.balance(econ._fiscal) == pytest.approx(
        fiscal_before - desired_hole
    )
    assert econ.ledger.balance(failed.id) == pytest.approx(0.0, abs=1e-9)


def test_bilateral_hard_gate_rejects_an_unmirrored_claim():
    econ = _economy()
    borrower, lender = econ.banks
    _set_bank_reserves(econ, {borrower.id: -10.0, lender.id: 10.0})
    run_interbank_phase(econ)
    borrower.interbank_liabilities.clear()

    with pytest.raises(AssertionError, match="unmirrored interbank claim"):
        assert_interbank_positions(econ)
