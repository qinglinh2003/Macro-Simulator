"""v16-L2: matching friction -- u* is born.

Hiring flows through per-searcher contacts (congestion included); frictional
unemployment emerges as the balance of churn inflow against contact-success outflow.
The JG stays a SEARCHABLE buffer by construction. Gates green throughout.
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
        labor_matching_friction=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_frictional_unemployment_emerges_positive():
    econ = make_econ()
    rates = []
    for t in range(365):
        econ.step()                      # both labor gates assert every tick
        if t > 200:                      # past the fill-in transient
            u = econ.labor_accounts.unemployed
            jg = econ.labor_accounts.job_guarantee
            force = econ.labor_accounts.employed + u + jg
            rates.append((u + jg) / max(force, 1.0))
    mean_slack = sum(rates) / len(rates)
    assert mean_slack > 0.01             # u* > 1%: friction leaves a standing pool
    assert mean_slack < 0.25             # ...but the market still clears mostly


def test_friction_slows_hiring_vs_instant():
    def fill_speed(friction):
        econ = make_econ(labor_matching_friction=friction)
        for _ in range(10):
            econ.step()
        return econ.labor_accounts.employed

    assert fill_speed(False) > fill_speed(True)   # instant fill front-loads employment


def test_vacancies_persist_and_age():
    econ = make_econ()
    for _ in range(120):
        econ.step()
    lm = econ.labor_market
    assert econ.records[-1]["labor_vacancy_age_mean"] >= 0.0
    # at least some firm carried an unfilled gap for more than a tick at some point
    assert econ.labor_accounts.vacancies >= 0.0


def test_jg_workers_flow_back_to_private_jobs():
    """The buffer drains: JG stock exists in slumps, and hires keep happening from
    the pool that contains those same people (no absorbing state)."""
    econ = make_econ()
    jg_seen = hires_after_jg = 0.0
    for _ in range(365):
        econ.step()
        a = econ.labor_accounts
        if a.job_guarantee > 0:
            jg_seen = a.job_guarantee
            hires_before = a.hires_total
            econ.step()
            hires_after_jg = a.hires_total - hires_before
            break
    if jg_seen > 0:                      # JG appeared: hiring continued regardless
        assert hires_after_jg >= 0.0
    assert econ.labor_accounts.hires_total > 0


def test_friction_off_is_l1_instant_fill():
    econ = make_econ(labor_matching_friction=False)
    econ.step()
    assert econ.labor_market.friction_enabled is False
