"""v16-L1b: suspension -- the employment LOLR.

Liquidity != insolvency at the match level: cash-crunched firms suspend (LIFO)
instead of firing; recall in place within the timer; timeout converts to layoff;
suspended workers search as recall unemployment with a reservation threshold.
All under the partition + flow-reconciliation gates every tick.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.labor.persistent import Suspension


def make_econ(**overrides):
    params = dict(
        seed=13,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=300,
        labor_matching="persistent",
        labor_suspension=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def drain_firm(econ, firm) -> None:
    """Simulate a liquidity freeze: strip the firm's deposits (to fiscal, A5-safe)."""
    balance = econ.ledger.balance(firm.id)
    if balance > 0:
        econ.ledger.transfer(firm.id, econ._fiscal, balance)


def biggest_employer(econ):
    lm = econ.labor_market
    return max(econ.c_firms, key=lambda f: lm.active_count(f.id))


def test_cash_freeze_suspends_instead_of_firing():
    econ = make_econ()
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    a = econ.labor_accounts
    firm = biggest_employer(econ)
    n_active = lm.active_count(firm.id)
    assert n_active >= 1
    layoffs_before = a.layoff_seps_total
    drain_firm(econ, firm)
    econ.step()                          # gates assert inside
    assert a.suspensions_total >= 1
    assert len(lm.suspended) >= 1
    # the cash crunch produced suspensions, not a layoff wave at this firm
    assert a.layoff_seps_total - layoffs_before <= n_active / 2


def test_recall_in_place_when_cash_returns():
    econ = make_econ(suspension_timer=200)
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    a = econ.labor_accounts
    firm = biggest_employer(econ)
    members_before = set(lm.rosters.get(firm.id, ()))
    drain_firm(econ, firm)
    econ.step()
    assert any(pid in lm.suspended for pid in lm.rosters.get(firm.id, ()))
    # refund the firm: recalls should fire at the next labor phase
    econ.ledger.transfer(econ._fiscal, firm.id, 500.0)
    recalls_before = a.recalls_total
    for _ in range(3):
        econ.step()
    assert a.recalls_total > recalls_before
    # recalled members are the SAME people (match capital preserved)
    assert members_before & set(lm.rosters.get(firm.id, ()))


def test_timeout_converts_to_layoff():
    econ = make_econ(suspension_timer=5)
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    a = econ.labor_accounts
    firm = biggest_employer(econ)
    drain_firm(econ, firm)
    econ.step()
    assert len(lm.suspended) >= 1
    before = a.suspension_timeouts_total
    for _ in range(10):                  # timer 5 << 10: unrecalled suspensions expire
        drain_firm(econ, firm)           # keep it broke
        econ.step()
    assert a.suspension_timeouts_total > before


def test_suspended_reservation_respected_in_unit():
    """Poaching honors the theta threshold at the matching step (unit-level)."""
    econ = make_econ()
    lm = econ.labor_market
    # a synthetic suspension with a high prior wage: no firm posts >= 0.9 x 100
    for _ in range(40):
        econ.step()
    person = next(iter(lm.jobs))
    lm.suspended[person] = Suspension(firm_id=lm.jobs[person].firm_id,
                                      since_tick=econ.t, wage_at=100.0)
    econ.labor_accounts.suspensions_total += 1   # count the synthetic E->S move, or the
    poached_before = econ.labor_accounts.suspension_poached_total  # flow gate fires (it did)
    econ.step()
    assert econ.labor_accounts.suspension_poached_total == poached_before


def test_flag_off_never_suspends():
    econ = make_econ(labor_suspension=False)
    for _ in range(80):
        econ.step()
    assert econ.labor_accounts.suspensions_total == 0.0
    assert len(econ.labor_market.suspended) == 0
