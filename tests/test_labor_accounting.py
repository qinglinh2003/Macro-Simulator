"""v16-L0: labor accounting shell -- five-state stocks, the identity gate, gauges.

Under the spot market the identity is arithmetic (U is derived); the gate's teeth
arrive with L1 rosters. These tests pin the shell's semantics so every later stage
reports into an already-verified object.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.labor import LaborAccounts


def make_econ(**overrides):
    params = dict(
        seed=13,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=60,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_states_partition_the_labor_supply_every_tick():
    econ = make_econ()
    for _ in range(60):
        econ.step()                     # the gate asserts inside phase 5 every tick
    a = econ.labor_accounts
    assert a.employed + a.unemployed + a.suspended + a.job_guarantee == pytest.approx(a.labor_supply)
    assert a.employed > 0.0
    assert a.suspended == 0.0           # L1b state: identically zero before it exists


def test_olf_covers_the_nonworking_ages():
    econ = make_econ()
    econ.step()
    a = econ.labor_accounts
    state = econ.demographic_state
    persons = sum(1 for p in state.people if p.alive)
    assert a.labor_supply + a.out_of_labor_force == pytest.approx(persons)


def test_flow_counters_stay_zero_under_spot():
    econ = make_econ()
    for _ in range(40):
        econ.step()
    a = econ.labor_accounts
    assert a.hires_total == a.churn_seps_total == a.layoff_seps_total == 0.0
    assert a.bankruptcy_seps_total == a.death_seps_total == a.recalls_total == 0.0


def test_metrics_columns_present_and_consistent():
    econ = make_econ()
    econ.step()
    rec = econ.records[-1]
    a = econ.labor_accounts
    assert rec["labor_E"] == pytest.approx(a.employed)
    assert rec["labor_u_rate"] == pytest.approx(a.unemployment_rate)
    assert rec["labor_v_rate"] >= 0.0


def test_gate_catches_a_corrupted_stock():
    a = LaborAccounts(employed=10.0, unemployed=5.0, labor_supply=20.0)
    with pytest.raises(AssertionError, match="identity"):
        a.assert_identity()
    a2 = LaborAccounts(employed=-1.0, unemployed=1.0, labor_supply=0.0)
    with pytest.raises(AssertionError):
        a2.assert_identity()


def test_flag_off_leaves_no_trace():
    econ = make_econ(labor_accounting=False)
    assert econ.labor_accounts is None
    econ.step()
    assert "labor_E" not in econ.records[-1]
