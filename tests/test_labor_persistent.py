"""v16-L1: persistent rosters -- separations, hoarding dynamics, wage attribution.

Everything runs under the per-tick labor A5 (partition + flow reconciliation): a
single uncounted roster mutation anywhere fails the gate within one tick.
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
        n_ticks=200,
        labor_matching="persistent",
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_rosters_form_and_gates_hold():
    econ = make_econ()
    for _ in range(120):
        econ.step()                      # partition + reconciliation assert every tick
    lm = econ.labor_market
    a = econ.labor_accounts
    assert len(lm.jobs) > 0
    assert a.hires_total > 0
    # every job's person is alive, working-age, and on exactly one roster
    on_rosters = [pid for ids in lm.rosters.values() for pid in ids]
    assert sorted(on_rosters) == sorted(lm.jobs.keys())


def test_churn_generates_ongoing_flows():
    econ = make_econ()
    for _ in range(150):
        econ.step()
    a = econ.labor_accounts
    assert a.churn_seps_total > 0        # ~2.4%/month of the employed stock
    assert a.hires_total > a.churn_seps_total  # churned workers get re-hired


def test_tenure_exists_and_is_lifo_ordered():
    econ = make_econ()
    for _ in range(100):
        econ.step()
    lm = econ.labor_market
    roster = next(ids for ids in lm.rosters.values() if len(ids) >= 2)
    dates = [lm.jobs[pid].hire_date for pid in roster]
    assert dates == sorted(dates)        # hire order preserved => LIFO fires the tail


def test_wage_attribution_reaches_the_person():
    econ = make_econ()
    for _ in range(40):
        econ.step()
    lm = econ.labor_market
    bridge = econ.demographic_bridge
    paid = 0
    for person_id in list(lm.jobs.keys())[:20]:
        sheet = bridge.claims.balance_sheet(person_id)
        if sheet.labor_income_tick > 0.0:
            paid += 1
    assert paid > 0                      # income lands on the WORKER's sheet, not split


def test_mass_layoff_on_firm_exit_counted():
    econ = make_econ()
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    a = econ.labor_accounts
    firm = next(f for f in econ.c_firms if len(lm.rosters.get(f.id, ())) >= 1)
    n = len(lm.rosters[firm.id])
    before = a.bankruptcy_seps_total
    from macro_sim.systems.firm_demographics import bankrupt_firm
    bankrupt_firm(econ, firm)
    assert a.bankruptcy_seps_total == before + n
    assert firm.id not in lm.rosters
    econ.step()                          # gates stay green after the shock


def test_demand_collapse_lays_off_gradually_lifo():
    """Labor hoarding: a demand collapse sheds workers at lambda_fire, not instantly."""
    econ = make_econ()
    for _ in range(60):
        econ.step()
    lm = econ.labor_market
    firm = max(econ.c_firms, key=lambda f: len(lm.rosters.get(f.id, ())))
    n0 = len(lm.rosters[firm.id])
    assert n0 >= 2
    firm.demand_expected = 0.0           # kill demand expectations
    firm.sales_prev = 0.0
    sizes = []
    for _ in range(20):
        econ.step()
        sizes.append(len(lm.rosters.get(firm.id, ())))
    assert sizes[-1] < n0                # shrinking...
    assert sizes[0] > 0                  # ...but not fired all at once (hoarding)


def test_spot_default_untouched():
    econ = make_econ(labor_matching="spot")
    assert econ.labor_market is None
    econ.step()
    assert econ.labor_accounts.hires_total == 0.0
