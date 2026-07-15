"""Dedicated mortgage underwriting: pure decisions and atomic housing sales."""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.housing.market import run_housing_market_phase
from macro_sim.housing.mortgage import Mortgage
from macro_sim.reporting.metrics import compute_tick_metrics
from macro_sim.systems.banking import bank_economic_capital, bank_for, loan_rate_for


def make_econ(**overrides) -> Economy:
    params = dict(
        seed=421,
        n_households=20,
        n_firms_c=20,
        n_firms_k=10,
        n_banks=2,
        demographics_population=100,
        housing_enabled=True,
        housing_market_enabled=True,
        housing_session_interval=1,
        housing_buyer_buffer=0.0,
        mortgage_enabled=True,
        mortgage_underwriting=True,
        mortgage_ltv_cap=0.8,
        housing_rental_enabled=False,
        housing_construction_enabled=False,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def set_household_balance(econ: Economy, account: str, target: float) -> None:
    current = econ.ledger.balance(account)
    delta = target - current
    if delta > 0.0:
        econ.ledger.transfer(econ._fiscal, account, delta)
    elif delta < 0.0:
        econ.ledger.transfer(account, econ._fiscal, -delta)
    if abs(delta) > 0.0:
        econ.demographic_bridge.post_household_cash_delta(account, delta, reason="test_setup")


def set_bank_capital(econ: Economy, bank_id: str, target: float) -> None:
    current = econ.ledger.balance(bank_id)
    if current > target:
        econ.ledger.transfer(bank_id, econ._fiscal, current - target)
    elif current < target:
        econ.ledger.transfer(econ._fiscal, bank_id, target - current)


def prepare_mortgaged_sale(econ: Economy, *, price: float = 100.0):
    buyer, seller = econ.households[:2]
    buyer_home = econ.housing.dwellings_of(buyer.id)[0]
    seller_home = econ.housing.dwellings_of(seller.id)[0]
    econ.housing.transfer(buyer_home.id, seller.id)  # buyer becomes the sole need-driven bidder
    econ.housing_market.list_dwelling(econ, seller_home.id, seller.id, forced=False)
    econ.housing_market.listings[seller_home.id].ask = price
    set_household_balance(econ, buyer.id, price * (1.0 - econ.mortgage_book.ltv_cap))
    return buyer, seller, seller_home


def test_underwriting_is_default_off_but_diagnostic_frontier_enables_it():
    cfg = Config.v13()
    assert cfg.mortgage_underwriting is False
    assert FULL_FRONTIER_FLAGS["mortgage_underwriting"] is True


def test_ltv_boundary_and_per_tick_stress_rate_are_exact():
    econ = make_econ()
    buyer = econ.households[0]
    buyer.income_realized = buyer.y_expected = 100.0
    book = econ.mortgage_book

    at_cap = book.underwrite(econ, buyer, 123, price=100.0, amount=80.0)
    over_cap = book.underwrite(econ, buyer, 123, price=100.0, amount=80.0 + 1e-6)

    assert at_cap.approved
    assert over_cap.reason == "ltv"
    expected_rate = loan_rate_for(econ, buyer.id)
    expected_payment = 80.0 * (
        econ.cfg.credit.hh_amort + expected_rate + book.stress_rate_addon
    )
    assert at_cap.contract_rate == pytest.approx(expected_rate)
    assert at_cap.stressed_payment == pytest.approx(expected_payment)


def test_dsti_uses_committed_lagged_income_not_partial_current_flows():
    econ = make_econ()
    buyer = econ.households[0]
    book = econ.mortgage_book
    buyer.income_realized = 1.0
    buyer.y_expected = 2.0
    payment_rate = (
        econ.cfg.credit.hh_amort
        + loan_rate_for(econ, buyer.id)
        + book.stress_rate_addon
    )
    boundary = 2.0 * book.dsti_cap / payment_rate
    price = boundary * 2.0

    below = book.underwrite(econ, buyer, 124, price, boundary * (1.0 - 1e-7))
    above = book.underwrite(econ, buyer, 124, price, boundary * (1.0 + 1e-7))
    assert below.approved
    assert below.qualifying_income == pytest.approx(2.0)
    assert above.reason == "dsti"

    buyer.income_realized = 0.0
    assert book.underwrite(econ, buyer, 124, price, 1.0).approved
    buyer.income_realized = 10.0
    buyer.y_expected = 0.0
    assert book.underwrite(econ, buyer, 124, price, 1.0).reason == "income"


def test_risk_weighted_portfolio_capacity_is_per_bank_and_has_teeth():
    econ = make_econ(mortgage_risk_weight=0.5, mortgage_min_capital_ratio=0.1)
    buyer = econ.households[0]
    buyer.income_realized = buyer.y_expected = 100.0
    bank = bank_for(econ, buyer.id)
    set_bank_capital(econ, bank.id, 10.0)
    assert bank_economic_capital(econ, bank) == pytest.approx(10.0)

    # Capital 10 at a 10% ratio supports 100 RWA.  An existing 180 mortgage at
    # weight 0.5 consumes 90 RWA, leaving exactly 20 of mortgage principal.
    econ.mortgage_book.loans["OTHER"] = Mortgage(
        account="OTHER",
        dwelling_id=-1,
        balance=180.0,
        bank_id=bank.id,
    )
    approved = econ.mortgage_book.underwrite(econ, buyer, 125, 100.0, 20.0)
    denied = econ.mortgage_book.underwrite(econ, buyer, 125, 100.0, 20.0 + 1e-6)
    assert approved.approved
    assert approved.available_capacity == pytest.approx(20.0)
    assert denied.reason == "bank_capacity"

    other_bank = next(candidate for candidate in econ.banks if candidate.id != bank.id)
    assert econ.mortgage_book.bank_balance_total(other_bank.id) == 0.0


def test_zero_capital_bank_rejects_without_creating_a_loan():
    econ = make_econ()
    buyer = econ.households[0]
    buyer.income_realized = buyer.y_expected = 100.0
    bank = bank_for(econ, buyer.id)
    set_bank_capital(econ, bank.id, 0.0)
    debt_before = econ.ledger.debt(buyer.id)

    decision = econ.mortgage_book.underwrite(econ, buyer, 126, 100.0, 80.0)
    originated = econ.mortgage_book.originate(econ, buyer, 126, 80.0, price=100.0)

    assert decision.reason == "bank_capacity"
    assert not originated
    assert econ.ledger.debt(buyer.id) == pytest.approx(debt_before)
    assert buyer.id not in econ.mortgage_book.loans


def test_rejected_sale_is_atomic_for_cash_debt_title_and_listing():
    econ = make_econ()
    buyer, seller, dwelling = prepare_mortgaged_sale(econ)
    buyer.income_realized = 0.0
    buyer.y_expected = 0.0
    snapshot = {
        "buyer_cash": econ.ledger.balance(buyer.id),
        "seller_cash": econ.ledger.balance(seller.id),
        "buyer_debt": econ.ledger.debt(buyer.id),
        "owner": econ.housing.owner_of(dwelling.id),
        "originated": econ.mortgage_book.originated_total,
        "sales": econ.housing_market.sales_total,
    }

    run_housing_market_phase(econ)

    assert econ.ledger.balance(buyer.id) == pytest.approx(snapshot["buyer_cash"])
    assert econ.ledger.balance(seller.id) == pytest.approx(snapshot["seller_cash"])
    assert econ.ledger.debt(buyer.id) == pytest.approx(snapshot["buyer_debt"])
    assert econ.housing.owner_of(dwelling.id) == snapshot["owner"]
    assert econ.mortgage_book.originated_total == pytest.approx(snapshot["originated"])
    assert econ.housing_market.sales_total == snapshot["sales"]
    assert econ.housing_market.is_listed(dwelling.id)
    assert buyer.id not in econ.mortgage_book.loans


def test_qualified_buyer_closes_normally_and_books_bank_portfolio():
    econ = make_econ()
    buyer, seller, dwelling = prepare_mortgaged_sale(econ)
    buyer.income_realized = buyer.y_expected = 1.0
    bank = bank_for(econ, buyer.id)

    run_housing_market_phase(econ)

    loan = econ.mortgage_book.loans[buyer.id]
    assert econ.housing.owner_of(dwelling.id) == buyer.id
    assert econ.ledger.debt(buyer.id) == pytest.approx(80.0)
    assert loan.balance == pytest.approx(80.0)
    assert loan.bank_id == bank.id
    assert econ.mortgage_book.bank_balance_total(bank.id) == pytest.approx(80.0)
    assert econ.mortgage_book.originated_tick == pytest.approx(80.0)
    assert econ.housing_market.sales_total == 1
    assert not econ.housing_market.is_listed(dwelling.id)

    record = compute_tick_metrics(econ)
    assert record["mortgage_originated_tick"] == pytest.approx(80.0)
    assert record["new_loans_total"] == pytest.approx(80.0)

    run_housing_market_phase(econ)
    next_record = compute_tick_metrics(econ)
    assert next_record["mortgage_originated_tick"] == 0.0
    assert next_record["new_loans_total"] == 0.0


def test_mortgage_bank_attribution_follows_authoritative_creditor_migration():
    econ = make_econ()
    buyer, _seller, _dwelling = prepare_mortgaged_sale(econ)
    buyer.income_realized = buyer.y_expected = 1.0
    original = bank_for(econ, buyer.id)
    replacement = next(bank for bank in econ.banks if bank.id != original.id)
    run_housing_market_phase(econ)
    assert econ.mortgage_book.bank_balance_total(original.id) == pytest.approx(80.0)

    econ._bank_of[buyer.id] = replacement
    econ.mortgage_book.maintain(econ)

    loan = econ.mortgage_book.loans[buyer.id]
    assert loan.bank_id == replacement.id
    assert econ.mortgage_book.bank_balance_total(original.id) == 0.0
    assert econ.mortgage_book.bank_balance_total(replacement.id) == pytest.approx(80.0)


def test_explicit_underwriting_false_preserves_legacy_trajectory():
    common = dict(
        seed=522,
        n_households=20,
        n_firms_c=20,
        n_firms_k=10,
        n_banks=2,
        demographics_population=100,
        housing_enabled=True,
        housing_market_enabled=True,
        mortgage_enabled=True,
        n_ticks=35,
    )
    implicit = Economy(Config.v13(**common))
    explicit = Economy(Config.v13(**common, mortgage_underwriting=False))
    assert implicit.run() == explicit.run()
