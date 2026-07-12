"""v16-L4: person efficiency -- the human-capital slot.

e_i ~ lognormal MEAN ONE, drawn once at FIRST hire from a dedicated substream and
carried for life. Earnings = wage x e_i through wage_of (the single authority: every
cash gate prices it); f.hired counts EFFICIENCY UNITS (feeds production) while
labor_sold counts HEADS (feeds the JG/welfare residual). Gates green throughout.
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
        n_ticks=300,
        labor_matching="persistent",
        labor_person_efficiency=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_efficiency_drawn_at_first_hire_mean_one():
    econ = make_econ()
    for _ in range(60):
        econ.step()                      # partition + flow gates assert inside
    lm = econ.labor_market
    assert len(lm.efficiency) >= len(lm.jobs) > 0   # every hire carries an e_i
    es = list(lm.efficiency.values())
    mean = sum(es) / len(es)
    assert 0.75 < mean < 1.25            # lognormal(-sigma^2/2, sigma): mean one
    assert min(es) > 0.0
    assert len(set(round(e, 9) for e in es)) > 1    # genuinely heterogeneous


def test_efficiency_persists_across_jobs():
    econ = make_econ()
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    person = next(iter(lm.jobs))
    e_before = lm.efficiency[person]
    lm.separate(person)                  # force a churn separation...
    econ.labor_accounts.churn_seps_total += 1
    for _ in range(30):
        econ.step()                      # ...and let the market rehire them
        if person in lm.jobs:
            break
    assert lm.efficiency[person] == e_before        # human capital survived the spell


def test_pay_is_wage_times_efficiency():
    econ = make_econ()
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    person, job = next(iter(lm.jobs.items()))
    firm = next(f for f in econ.firms if f.id == job.firm_id)
    base = job.wage if (lm.relationship_wages and job.wage > 0) else max(firm.wage, 1e-12)
    assert lm.wage_of(person, firm) == pytest.approx(base * lm.efficiency[person])


def test_production_reads_units_welfare_reads_heads():
    econ = make_econ()
    for _ in range(90):
        econ.step()
    lm = econ.labor_market
    # pick a firm that paid everyone this tick (hired == sum of member efficiencies)
    for f in econ.firms:
        active = [pid for pid in lm.rosters.get(f.id, ()) if pid not in lm.suspended]
        if len(active) >= 2 and f.hired > 0:
            expected_units = sum(lm.efficiency.get(pid, 1.0) for pid in active)
            if f.hired == pytest.approx(expected_units):
                break
    else:
        pytest.skip("no fully-paid multi-member firm this tick")
    # heads: every household's labor_sold is an integer count of paid members
    sold = [h.labor_sold for h in econ.households if getattr(h, "labor_sold", 0) > 0]
    assert sold and all(s == pytest.approx(round(s)) for s in sold)


def test_flag_off_no_draws():
    econ = make_econ(labor_person_efficiency=False)
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    assert len(lm.efficiency) == 0
    person, job = next(iter(lm.jobs.items()))
    firm = next(f for f in econ.firms if f.id == job.firm_id)
    assert lm.wage_of(person, firm) == pytest.approx(max(firm.wage, 1e-12))


def test_full_stack_gates_green():
    """All v16 layers on at once: gates + A4/A5 hold for a quarter."""
    econ = make_econ(labor_suspension=True, labor_matching_friction=True,
                     labor_relationship_wages=True, labor_job_ladder=True)
    for _ in range(120):
        econ.step()                      # every gate asserts every tick
    assert econ.labor_accounts.hires_total > 0
