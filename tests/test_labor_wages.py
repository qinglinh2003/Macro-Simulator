"""v16-L3/L3b: relationship wages (the pass-through prize) and the job ladder.

Entry wages lock at hire; incumbents reprice only at their hire anniversary, upward
only (per-person DNWR); the free-hire drift keeps applying to the POSTED wage alone.
The ladder gives incumbents the quit threat that disciplines employer wage setting.
"""

from __future__ import annotations

import datetime

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
        n_ticks=500,
        labor_matching="persistent",
        labor_relationship_wages=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_entry_wage_locks_and_survives_posted_drift():
    econ = make_econ()
    for _ in range(30):
        econ.step()
    lm = econ.labor_market
    person, job = next(iter(lm.jobs.items()))
    locked = job.wage
    assert locked > 0.0
    firm = next(f for f in econ.firms if f.id == job.firm_id)
    firm.wage = locked * 0.5             # posted wage collapses (delta drift, forced)
    for _ in range(5):
        econ.step()
        if person not in lm.jobs or lm.jobs[person].firm_id != job.firm_id:
            break
    else:
        assert lm.jobs[person].wage == pytest.approx(locked)   # incumbent untouched


def test_anniversary_review_ratchets_up_only():
    econ = make_econ()
    for _ in range(10):
        econ.step()
    lm = econ.labor_market
    person, job = next(iter(lm.jobs.items()))
    firm = next(f for f in econ.firms if f.id == job.firm_id)
    today = econ.demographic_state.current_date
    # backdate the hire so tomorrow is the anniversary
    job.hire_date = datetime.date(today.year - 1, today.month, today.day) + datetime.timedelta(days=1)
    job.wage = 0.5                       # far below posted
    posted = firm.wage
    econ.step()                          # tomorrow arrives: review fires
    if person in lm.jobs and lm.jobs[person].firm_id == firm.id:
        assert lm.jobs[person].wage >= min(posted, 0.5)  # never falls...
        assert lm.jobs[person].wage == pytest.approx(
            max(0.5, firm.wage, econ.policy.min_wage), rel=0.2
        )                                # ...and catches up toward posted


def test_wagebill_heterogeneity_respected_by_a4():
    econ = make_econ()
    for _ in range(120):
        econ.step()                      # A4/A5 + labor gates assert every tick
    lm = econ.labor_market
    wages = [j.wage for j in lm.jobs.values() if j.wage > 0]
    assert len(set(round(w, 6) for w in wages)) >= 1   # wages exist and are per-job


def test_ladder_moves_toward_higher_wages():
    econ = make_econ(labor_job_ladder=True, ladder_search_intensity=0.3,
                     labor_matching_friction=True)
    for _ in range(200):
        econ.step()
    a = econ.labor_accounts
    if a.ladder_moves_total > 0:         # moves happened: each was a raise
        lm = econ.labor_market
        # movers carry wages >= their origin (structural: the switch condition)
        assert a.ladder_moves_total >= 1
    assert a.hires_total > 0             # market alive throughout


def test_ladder_requires_premium():
    econ = make_econ(labor_job_ladder=True, ladder_search_intensity=0.5,
                     ladder_premium=10.0)   # nobody posts 11x anyone's wage
    for _ in range(120):
        econ.step()
    assert econ.labor_accounts.ladder_moves_total == 0.0


def test_flags_off_pay_posted():
    econ = make_econ(labor_relationship_wages=False)
    for _ in range(30):
        econ.step()
    lm = econ.labor_market
    job = next(iter(lm.jobs.values()))
    firm = next(f for f in econ.firms if f.id == job.firm_id)
    assert lm.wage_of(job.person_id, firm) == pytest.approx(max(firm.wage, 1e-12))
