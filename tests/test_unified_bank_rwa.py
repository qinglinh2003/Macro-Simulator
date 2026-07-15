"""One per-bank RWA envelope shared by ordinary credit and mortgages."""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.systems.banking import (
    bank_for,
    bank_rwa_capacity,
    bank_rwa_exposure,
    fail_bank,
    grant_loan,
    refresh_loan_books,
    resolve_bank_failures,
)
from macro_sim.systems.credit import run_household_debt_service_phase
from macro_sim.systems.equity import run_per_firm_equity_phase


def make_econ(**overrides) -> Economy:
    params = dict(
        seed=902,
        n_households=20,
        demographics_population=100,
        n_firms_c=8,
        n_firms_k=4,
        n_banks=1,
        bank_rate_competition=False,
        bank_relationship_lock_in=True,
        housing_enabled=True,
        housing_market_enabled=True,
        mortgage_enabled=True,
        mortgage_underwriting=True,
        unified_bank_rwa=True,
        mortgage_risk_weight=0.5,
        mortgage_min_capital_ratio=0.1,
        mortgage_dsti_cap=1.0,
        mortgage_stress_rate_addon=0.0,
        bank_target_capital_ratio=0.0,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def set_bank_capital(econ: Economy, bank_id: str, target: float) -> None:
    current = econ.ledger.balance(bank_id)
    if current > target:
        econ.ledger.transfer(bank_id, econ._fiscal, current - target)
    elif current < target:
        econ.ledger.transfer(econ._fiscal, bank_id, target - current)


def qualify(household, income: float = 1_000.0) -> None:
    household.income_realized = income
    household.y_expected = income


def originate(econ: Economy, household, amount: float, dwelling_id: int) -> bool:
    qualify(household)
    return econ.mortgage_book.originate(
        econ,
        household,
        dwelling_id,
        amount,
        price=max(100.0, amount / econ.mortgage_book.ltv_cap),
    )


def test_switch_is_default_off_frontier_on_and_banking_view_wired() -> None:
    cfg = Config.v13()
    assert cfg.unified_bank_rwa is False
    assert cfg.banking.unified_bank_rwa is False
    assert FULL_FRONTIER_FLAGS["unified_bank_rwa"] is True
    assert cfg.bank_relationship_lock_in is False
    assert cfg.banking.bank_relationship_lock_in is False
    assert FULL_FRONTIER_FLAGS["bank_relationship_lock_in"] is True


def test_unified_rwa_rejects_an_unguarded_mortgage_configuration() -> None:
    with pytest.raises(AssertionError, match="requires mortgage underwriting"):
        Config.v13(
            housing_enabled=True,
            housing_market_enabled=True,
            mortgage_enabled=True,
            mortgage_underwriting=False,
            unified_bank_rwa=True,
        )


def test_single_bank_ordinary_credit_consumes_mortgage_capacity() -> None:
    econ = make_econ(bank_capital_constraint=False)
    bank = econ.bank
    set_bank_capital(econ, bank.id, 10.0)

    # Capital 10 / ratio 10% = 100 RWA.  A 60 ordinary loan leaves 40 RWA,
    # hence 80 principal of a 50%-weighted mortgage.
    assert grant_loan(econ, econ.firms[0].id, 60.0) == pytest.approx(60.0)
    buyer = econ.households[0]
    qualify(buyer)
    decision = econ.mortgage_book.underwrite(econ, buyer, 1001, 100.0, 80.0)
    denied = econ.mortgage_book.underwrite(econ, buyer, 1001, 100.0, 80.0 + 1e-6)

    assert decision.approved
    assert decision.available_capacity == pytest.approx(80.0)
    assert denied.reason == "ltv"  # amount also crosses the configured 80% LTV
    # Isolate the capital boundary at a larger collateral value.
    assert econ.mortgage_book.underwrite(econ, buyer, 1001, 200.0, 80.0 + 1e-6).reason == "bank_capacity"


def test_mortgage_stock_consumes_next_ordinary_credit_grant() -> None:
    econ = make_econ(bank_capital_constraint=False)
    bank = econ.bank
    set_bank_capital(econ, bank.id, 10.0)
    buyer = econ.households[0]

    # Housing is after the ordinary credit phase in a tick.  This mortgage is
    # therefore the opening stock seen by the next credit phase: 80 x 50%=40 RWA,
    # leaving only 60 of 100%-weighted ordinary lending.
    assert originate(econ, buyer, 80.0, 1002)
    firm = econ.firms[0]
    assert grant_loan(econ, firm.id, 80.0) == pytest.approx(60.0)
    assert econ.ledger.debt(firm.id) == pytest.approx(60.0)
    assert bank_rwa_exposure(econ, bank, use_cache=False) == pytest.approx(100.0)
    assert bank_rwa_capacity(econ, bank) == pytest.approx(0.0)


def test_sequential_mortgages_cannot_reuse_stale_same_session_headroom() -> None:
    econ = make_econ(bank_capital_constraint=False)
    set_bank_capital(econ, econ.bank.id, 10.0)
    assert grant_loan(econ, econ.firms[0].id, 60.0) == pytest.approx(60.0)
    first, second = econ.households[:2]

    assert originate(econ, first, 60.0, 1003)
    qualify(second)
    decision = econ.mortgage_book.underwrite(econ, second, 1004, 100.0, 30.0)

    # 60 ordinary + 60*0.5 mortgage = 90 RWA, so only 20 more mortgage
    # principal remains; the first mutation updated both the shadow and cache.
    assert decision.reason == "bank_capacity"
    assert decision.available_capacity == pytest.approx(20.0)
    assert not econ.mortgage_book.originate(econ, second, 1004, 30.0, price=100.0)
    assert econ.ledger.debt(second.id) == pytest.approx(0.0)


def test_post_credit_principal_repayment_releases_live_mortgage_headroom() -> None:
    econ = make_econ(bank_capital_constraint=False)
    set_bank_capital(econ, econ.bank.id, 10.0)
    firm = econ.firms[0]
    assert grant_loan(econ, firm.id, 60.0) == pytest.approx(60.0)
    refresh_loan_books(econ)

    # Reproduce the scheduler boundary: the credit cache still says 60 after a
    # later debt-service phase repays 20, while ledger principal is now 40.
    econ.ledger.repay(firm.id, 20.0)
    assert econ._loan_book[econ.bank.id] == pytest.approx(60.0)
    assert econ.ledger.debt(firm.id) == pytest.approx(40.0)
    buyer = econ.households[0]
    qualify(buyer)

    decision = econ.mortgage_book.underwrite(econ, buyer, 1007, 200.0, 80.0)
    # 100 RWA limit - 40 live ordinary exposure = 60 RWA = 120 mortgage
    # principal.  Reading the stale cache would have reported only 80.
    assert decision.approved
    assert decision.available_capacity == pytest.approx(120.0)


def test_generic_household_repayment_reduces_mortgage_shadow_pro_rata() -> None:
    econ = make_econ(
        bank_capital_constraint=False,
        household_credit=True,
        r_interest=0.0,
    )
    buyer = econ.households[0]
    assert originate(econ, buyer, 80.0, 1009)
    assert grant_loan(econ, buyer.id, 20.0) == pytest.approx(20.0)
    assert econ.ledger.debt(buyer.id) == pytest.approx(100.0)
    assert econ.mortgage_book.loans[buyer.id].balance == pytest.approx(80.0)

    principal = econ.cfg.hh_amort * 100.0
    run_household_debt_service_phase(econ)

    expected_mortgage = 80.0 - principal * 0.8
    expected_total_debt = 100.0 - principal
    assert econ.mortgage_book.loans[buyer.id].balance == pytest.approx(expected_mortgage)
    assert econ.ledger.debt(buyer.id) == pytest.approx(expected_total_debt)
    assert bank_rwa_exposure(econ, econ.bank, use_cache=False) == pytest.approx(
        (expected_total_debt - expected_mortgage)
        + econ.mortgage_book.risk_weight * expected_mortgage
    )


def test_multi_bank_rwa_is_attributed_to_the_authoritative_creditor() -> None:
    econ = make_econ(n_banks=2, bank_capital_constraint=False)
    bank_a, bank_b = econ.banks
    firm, buyer = econ.firms[0], econ.households[0]
    econ._bank_of[firm.id] = bank_a
    econ._bank_of[buyer.id] = bank_b
    set_bank_capital(econ, bank_a.id, 10.0)
    set_bank_capital(econ, bank_b.id, 10.0)

    assert grant_loan(econ, firm.id, 40.0) == pytest.approx(40.0)
    assert originate(econ, buyer, 50.0, 1005)
    refresh_loan_books(econ)

    assert bank_for(econ, firm.id) is bank_a
    assert bank_for(econ, buyer.id) is bank_b
    assert bank_rwa_exposure(econ, bank_a) == pytest.approx(40.0)
    assert bank_rwa_exposure(econ, bank_b) == pytest.approx(25.0)
    assert bank_rwa_capacity(econ, bank_a) == pytest.approx(60.0)
    assert bank_rwa_capacity(econ, bank_b) == pytest.approx(75.0)


def test_existing_ordinary_debt_stays_with_relationship_bank_on_top_up() -> None:
    econ = make_econ(
        n_banks=3,
        bank_capital_constraint=False,
        bank_rate_competition=True,
        bank_search_m=2,
    )
    incumbent, cheapest, other = econ.banks
    borrower = econ.firms[0]
    econ._bank_of[borrower.id] = incumbent
    econ._rate = 0.01
    econ._bank_spread = {
        incumbent.id: 0.003,
        cheapest.id: -0.003,
        other.id: 0.0,
    }
    for bank in econ.banks:
        set_bank_capital(econ, bank.id, 20.0)

    # This opening balance is already an asset of the incumbent.  A top-up may
    # use its remaining capacity, but cannot silently sell the opening asset to a
    # cheaper rival.
    econ.ledger.create_loan(borrower.id, 20.0)
    refresh_loan_books(econ)
    assert grant_loan(econ, borrower.id, 10.0) == pytest.approx(10.0)

    assert bank_for(econ, borrower.id) is incumbent
    assert econ.ledger.debt(borrower.id) == pytest.approx(30.0)
    assert econ._loan_book[incumbent.id] == pytest.approx(30.0)
    assert econ._loan_book[cheapest.id] == pytest.approx(0.0)


def test_mortgagor_top_up_does_not_move_mortgage_or_relationship_bank() -> None:
    econ = make_econ(
        n_banks=3,
        bank_capital_constraint=False,
        bank_rate_competition=True,
        bank_search_m=2,
    )
    incumbent, cheapest, other = econ.banks
    buyer = econ.households[0]
    econ._bank_of[buyer.id] = incumbent
    econ._rate = 0.01
    econ._bank_spread = {
        incumbent.id: 0.003,
        cheapest.id: -0.003,
        other.id: 0.0,
    }
    for bank in econ.banks:
        set_bank_capital(econ, bank.id, 20.0)
    assert originate(econ, buyer, 40.0, 1010)
    refresh_loan_books(econ)

    assert grant_loan(econ, buyer.id, 10.0) == pytest.approx(10.0)

    mortgage = econ.mortgage_book.loans[buyer.id]
    assert bank_for(econ, buyer.id) is incumbent
    assert mortgage.bank_id == incumbent.id
    assert mortgage.balance == pytest.approx(40.0)
    assert econ.ledger.debt(buyer.id) == pytest.approx(50.0)
    assert econ._loan_book[incumbent.id] == pytest.approx(50.0)
    assert econ._loan_book[cheapest.id] == pytest.approx(0.0)


def test_debt_free_borrower_can_choose_a_cheaper_bank_before_origination() -> None:
    econ = make_econ(
        n_banks=3,
        bank_capital_constraint=False,
        bank_rate_competition=True,
        bank_search_m=2,
    )
    incumbent, cheapest, other = econ.banks
    borrower = econ.firms[0]
    econ._bank_of[borrower.id] = incumbent
    econ._rate = 0.01
    econ._bank_spread = {
        incumbent.id: 0.003,
        cheapest.id: -0.003,
        other.id: 0.0,
    }
    for bank in econ.banks:
        set_bank_capital(econ, bank.id, 20.0)
    refresh_loan_books(econ)

    assert econ.ledger.debt(borrower.id) == 0.0
    assert grant_loan(econ, borrower.id, 10.0) == pytest.approx(10.0)
    assert bank_for(econ, borrower.id) is cheapest
    assert econ._loan_book[incumbent.id] == pytest.approx(0.0)
    assert econ._loan_book[cheapest.id] == pytest.approx(10.0)


def test_failure_migration_moves_mortgage_rwa_to_the_surviving_bank() -> None:
    econ = make_econ(n_banks=2, bank_capital_constraint=False)
    failed, survivor = econ.banks
    buyer = econ.households[0]
    econ._bank_of[buyer.id] = failed
    set_bank_capital(econ, failed.id, 10.0)
    set_bank_capital(econ, survivor.id, 10.0)
    assert originate(econ, buyer, 50.0, 1008)
    assert econ.mortgage_book.loans[buyer.id].bank_id == failed.id

    fail_bank(econ, failed)

    assert bank_for(econ, buyer.id) is survivor
    assert econ.mortgage_book.loans[buyer.id].bank_id == survivor.id
    assert bank_rwa_exposure(econ, survivor, use_cache=False) == pytest.approx(25.0)


def test_failure_migration_keeps_mortgage_creditor_aligned_without_unified_rwa() -> None:
    econ = make_econ(
        n_banks=2,
        bank_capital_constraint=True,
        unified_bank_rwa=False,
    )
    failed, survivor = econ.banks
    buyer = econ.households[0]
    econ._bank_of[buyer.id] = failed
    set_bank_capital(econ, failed.id, 20.0)
    set_bank_capital(econ, survivor.id, 20.0)
    assert originate(econ, buyer, 40.0, 1012)

    fail_bank(econ, failed)

    assert bank_for(econ, buyer.id) is survivor
    assert econ.mortgage_book.loans[buyer.id].bank_id == survivor.id


def _unified_rwa_failure_outcome(*, reverse_bank_list: bool) -> tuple:
    econ = make_econ(n_banks=3, bank_capital_constraint=False)
    by_id = {bank.id: bank for bank in econ.banks}
    failed = by_id["BANK_0"]
    parking_bank = by_id["BANK_1"]
    ordinary_borrower = econ.firms[0]
    mortgagor = econ.households[0]

    # Remove genesis-assignment noise so the two migrations below are the whole
    # failure cohort and their deterministic round-robin result is observable.
    for agent in list(econ.firms) + list(econ.households):
        econ._bank_of[agent.id] = parking_bank
    econ._bank_of[ordinary_borrower.id] = failed
    econ._bank_of[mortgagor.id] = failed
    for bank in econ.banks:
        set_bank_capital(econ, bank.id, 20.0)
    econ.ledger.create_loan(ordinary_borrower.id, 10.0)
    assert originate(econ, mortgagor, 40.0, 1011)
    refresh_loan_books(econ)

    set_bank_capital(econ, failed.id, -1.0)
    if reverse_bank_list:
        econ.banks.reverse()
    resolve_bank_failures(econ)

    return (
        failed.alive,
        econ._bank_failures_total,
        bank_for(econ, ordinary_borrower.id).id,
        bank_for(econ, mortgagor.id).id,
        econ.mortgage_book.loans[mortgagor.id].bank_id,
    )


def test_unified_rwa_resolves_negative_capital_and_is_bank_list_order_invariant() -> None:
    forward = _unified_rwa_failure_outcome(reverse_bank_list=False)
    reversed_order = _unified_rwa_failure_outcome(reverse_bank_list=True)

    assert forward == reversed_order
    failed_alive, failures, ordinary_bank, mortgage_bank, mortgage_creditor = forward
    assert not failed_alive
    assert failures == 1
    assert ordinary_bank == "BANK_1"
    assert mortgage_bank == "BANK_2"
    assert mortgage_creditor == mortgage_bank


def test_zero_capital_and_failed_bank_close_both_credit_paths_safely() -> None:
    econ = make_econ(bank_capital_constraint=False, bank_target_capital_ratio=0.0)
    bank = econ.bank
    buyer = econ.households[0]
    qualify(buyer)
    set_bank_capital(econ, bank.id, 0.0)

    assert grant_loan(econ, econ.firms[0].id, 1.0) == 0.0
    assert econ.mortgage_book.underwrite(econ, buyer, 1006, 100.0, 1.0).reason == "bank_capacity"
    assert bank_rwa_capacity(econ, bank, min_capital_ratio=0.0) == 0.0

    bank.alive = False
    assert grant_loan(econ, econ.firms[0].id, 1.0) == 0.0
    assert econ.mortgage_book.underwrite(econ, buyer, 1006, 100.0, 1.0).reason == "bank_unavailable"


def test_margin_credit_uses_the_same_sequential_rwa_envelope() -> None:
    econ = make_econ(bank_capital_constraint=False, portfolio_adjust=1.0)
    set_bank_capital(econ, econ.bank.id, 0.5)  # supports exactly 5 RWA
    firm = econ.c_firms[0]
    firm.share_price = firm.share_last_price = 0.01
    # Give every household some collateral in one deliberately underpriced watched
    # firm so the margin path requests more credit than the common bank can supply.
    for household in econ.households:
        household.watchlist = [firm.id]
        household.holdings = {firm.id: 100.0}
        cash = econ.ledger.balance(household.id)
        econ.ledger.transfer(household.id, econ._fiscal, cash - 0.1)
        econ.demographic_bridge.post_household_cash_delta(
            household.id, 0.1 - cash, reason="test_setup"
        )

    run_per_firm_equity_phase(econ)

    total_debt = sum(econ.ledger.debt(household.id) for household in econ.households)
    assert 0.0 < econ._hh_margin_new <= 5.0 + 1e-9
    assert total_debt == pytest.approx(econ._hh_margin_new)
    assert bank_rwa_exposure(econ, econ.bank, use_cache=False) <= 5.0 + 1e-9


def test_explicit_off_preserves_legacy_trajectory() -> None:
    common = dict(
        seed=903,
        n_ticks=20,
        n_households=20,
        demographics_population=100,
        n_firms_c=8,
        n_firms_k=4,
        n_banks=2,
        housing_enabled=True,
        housing_market_enabled=True,
        mortgage_enabled=True,
        mortgage_underwriting=True,
    )
    implicit = Economy(Config.v13(**common))
    explicit = Economy(Config.v13(**common, unified_bank_rwa=False))
    assert implicit.run() == explicit.run()
