"""v16-L5: the participation margin -- the reservation wage, and the policy lab.

Outside option = what the welfare state pays a non-worker (max of JG wage and
benefit rate). Jobless search iff expected earnings (wage_ref x e_i) clear
markup x outside; incumbents paid below the line quit to welfare at a daily
hazard. Non-search is a memo over partition-U; welfare quits are a REAL
separation class inside the flow gate.
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
        labor_matching="persistent",
        labor_person_efficiency=True,
        labor_participation=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_flag_off_no_effects():
    econ = make_econ(labor_participation=False)
    for _ in range(60):
        econ.step()
    assert econ.labor_accounts.welfare_quits_total == 0.0
    assert econ.labor_accounts.nonsearching_memo == 0.0
    assert len(econ.labor_market.nonsearch) == 0


def test_nonsearchers_are_the_low_e_tail():
    econ = make_econ(reservation_markup=1.6)     # push the line into the e distribution
    for _ in range(120):
        econ.step()                              # gates assert inside
    lm = econ.labor_market
    if not lm.nonsearch:
        pytest.skip("no voluntary idle at this seed/markup")
    idle_e = [lm.e_of(pid) for pid in lm.nonsearch]
    work_e = [lm.e_of(pid) for pid in lm.jobs if pid not in lm.suspended]
    assert work_e
    assert max(idle_e) <= 1.0 + 1e-9             # only the below-mean tail withdraws
    assert sum(idle_e) / len(idle_e) < sum(work_e) / len(work_e)


def test_benefit_trap_experiment():
    """The replacement-rate sweep moves participation: a richer outside option
    grows the voluntarily-idle share of the WORKFORCE (the jobless-pool ratio
    saturates at 1 -- under instant fill only the below-line tail stays jobless
    at all, so the denominator must be the whole supply)."""
    def idle_share(markup):
        econ = make_econ(reservation_markup=markup)
        for _ in range(150):
            econ.step()
        a = econ.labor_accounts
        return a.nonsearching_memo / max(1.0, a.labor_supply)

    lean, generous = idle_share(0.8), idle_share(2.0)
    assert generous > lean                       # the trap closes on the low-e tail
    assert generous > 0.02                       # and it is a real mass, not noise


def test_jg_wage_floor_cannibalizes_private_jobs():
    """JG wage approaching the market wage empties private employment through
    BOTH margins: below-line incumbents quit to welfare, and the jobless stop
    searching (jobs never form) -- measurable, finally."""
    def outcome(ratio):
        econ = make_econ(job_guarantee=True, jg_wage_ratio=ratio,
                         labor_relationship_wages=True)
        for _ in range(200):
            econ.step()
        a = econ.labor_accounts
        return a.welfare_quits_total, a.employed, a.nonsearching_memo

    quits_low, emp_low, idle_low = outcome(0.5)
    quits_high, emp_high, idle_high = outcome(1.1)
    assert emp_high < 0.5 * max(emp_low, 1.0)    # private employment collapses
    assert quits_high + idle_high > quits_low + idle_low   # via the two L5 channels


def test_full_stack_gates_green_l5():
    """All six v16 layers on: partition + flow gates + A4/A5 hold."""
    econ = make_econ(labor_suspension=True, labor_matching_friction=True,
                     labor_relationship_wages=True, labor_job_ladder=True)
    for _ in range(150):
        econ.step()
    a = econ.labor_accounts
    assert a.hires_total > 0
    assert a.employed > 0
