"""v15.2: mortgages over the existing household credit rails.

The loan is ordinary non-margin ledger debt (the certified credit machinery
amortizes and charges the floating rate); the book tracks collateralization and
foreclosure, reconciled per session by clamping against the ledger truth.

Headline acceptance: the CREDIT UNLOCK regime pair -- at the production price anchor
(3.5y income) v15.1 certified a cash-constrained null (sales ~ 0); the same economy
with mortgages enabled must trade.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy


def make_econ(**overrides):
    params = dict(
        seed=13,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=400,
        housing_enabled=True,
        housing_market_enabled=True,
        mortgage_enabled=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def empty_household_by_pinned_mortality(econ, target, max_ticks: int = 120) -> None:
    bridge = econ.demographic_bridge
    hh_id = int(bridge.household_id_for_account(target.id))
    bridge.stratification.mortality_strata[hh_id] = 1e5
    for _ in range(max_ticks):
        econ.step()
        alive = [p for p in econ.demographic_state.people
                 if p.alive and p.household_id == hh_id]
        if not alive:
            return
    raise AssertionError("pinned mortality failed to empty the household in time")


@pytest.fixture(scope="module")
def unlock_econ():
    """The credit-unlock scenario: certified v15.1 null (seed 31, 3.5y anchor) with
    mortgages at LTV 0.9. The unlock is a SLOW intersection -- decaying probate asks
    meet first-time buyers' growing savings (houseless leavers hold ~0-50 against a
    ~200 down payment at first: years of saving before the down payment is honest
    first-time-buyer economics, not a bug)."""
    econ = make_econ(seed=31, mortgage_ltv_cap=0.9)
    for _ in range(3):
        econ.step()
    empty_household_by_pinned_mortality(econ, econ.households[0])
    econ._first_sale_tick = None
    econ._balance_at_origination = None
    for _ in range(800):
        econ.step()
        book = econ.mortgage_book
        if econ._balance_at_origination is None and book.loans:
            econ._balance_at_origination = max(l.balance for l in book.loans.values())
        if econ._first_sale_tick is None and econ.housing_market.sales_total > 0:
            econ._first_sale_tick = econ.t
        if econ._first_sale_tick is not None and econ.t - econ._first_sale_tick >= 200:
            break                                        # 200 post-sale ticks for amortization
    return econ


def test_credit_unlock_flips_the_cash_constrained_null(unlock_econ):
    econ = unlock_econ
    assert econ.housing_market.sales_total >= 1          # v15.1 certified 0 in this regime
    assert econ.mortgage_book.originated_total > 0.0     # ...and the sale was credit-financed
    # the book is reconciled per SESSION (like the margin shadow, it may run stale-high
    # between sessions as the credit machinery amortizes): assert AFTER maintenance
    econ.mortgage_book.maintain(econ)
    for loan in econ.mortgage_book.loans.values():
        assert econ.housing.owner_of(loan.dwelling_id) == loan.account
        assert loan.balance <= econ.ledger.debt(loan.account) + 1e-9
    econ.housing.assert_invariants()


def test_origination_respects_ltv_and_budget(unlock_econ):
    econ = unlock_econ
    book = econ.mortgage_book
    # every origination was capped at ltv_cap x price; asks never exceeded the anchor
    # x (1+markup), so the cap in money terms is bounded by that
    anchor = 3.5 * 365.0
    assert econ._balance_at_origination is not None
    assert econ._balance_at_origination <= book.ltv_cap * anchor * 1.05 + 1e-6


def test_book_amortizes_with_the_credit_machinery(unlock_econ):
    """Secured balances FALL without any mortgage-side repayment code: the existing
    hh_amort machinery services the debt and the session clamp follows."""
    econ = unlock_econ
    remaining = [l.balance for l in econ.mortgage_book.loans.values()]
    assert not remaining or min(remaining) < econ._balance_at_origination


def test_foreclosure_seizes_title_and_lists():
    econ = make_econ(seed=13)
    for _ in range(65):
        econ.step()
    book = econ.mortgage_book
    housing = econ.housing
    # manufacture a distressed underwater borrower: originate synthetically, then
    # crash the collateral value and drain the account via the maintenance test
    target = next(h for h in econ.households if housing.dwellings_of(h.id))
    dwelling = housing.dwellings_of(target.id)[0]
    econ.ledger.create_loan(target.id, 500.0)
    econ.demographic_bridge.post_household_debt_creation(target.id, 500.0)
    spend = econ.ledger.balance(target.id) * 0.999
    econ.ledger.transfer(target.id, econ._fiscal, spend)
    econ.demographic_bridge._post_household_cash_delta(
        int(econ.demographic_bridge.household_id_for_account(target.id)), -spend, reason="test_drain")
    from macro_sim.housing.mortgage import Mortgage
    book.loans[target.id] = Mortgage(account=target.id, dwelling_id=dwelling.id, balance=500.0)
    econ._house_price = 10.0                             # collateral crash: deep underwater
    before = book.foreclosures_total
    book.maintain(econ)
    assert book.foreclosures_total == before + 1
    assert housing.owner_of(dwelling.id) != target.id    # bank holds title
    assert econ.housing_market.is_listed(dwelling.id)    # forced bank listing
    assert target.id not in book.loans
    housing.assert_invariants()


def test_mortgage_off_leaves_market_untouched():
    econ = make_econ(mortgage_enabled=False)
    assert econ.mortgage_book is None
    for _ in range(35):
        econ.step()
    assert "mortgage_count" not in econ.records[-1]
