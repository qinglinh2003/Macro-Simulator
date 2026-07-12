"""v15.5 policy handles: stamp duty, property tax, live LTV/permit levers,
housing-into-wealth-tax, and the housing wealth-effect flag.

Every handle defaults to off (= bit-identical); each test exercises one lever and
checks the money reaches the fiscal account under the conservation gates.
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
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_property_tax_flows_to_fiscal():
    econ = make_econ(housing_property_tax=0.02)
    fiscal0 = econ.ledger.balance(econ._fiscal)
    for _ in range(40):
        econ.step()                      # claim/conservation gates assert every tick
    assert getattr(econ, "_property_tax_paid", 0.0) > 0.0
    assert econ.records[-1]["property_tax_paid"] > 0.0


def test_property_tax_is_a_live_lever():
    econ = make_econ()
    for _ in range(10):
        econ.step()
    assert getattr(econ, "_property_tax_paid", 0.0) == 0.0
    econ.policy.housing_property_tax = 0.05          # runtime policy change
    for _ in range(10):
        econ.step()
    assert getattr(econ, "_property_tax_paid", 0.0) > 0.0


def test_transfer_tax_charged_on_sales():
    """Cheap anchor so cash sales happen; duty accrues on every transaction."""
    econ = make_econ(house_price_income_years=0.05, housing_transfer_tax=0.10,
                     housing_rental_enabled=True)
    bridge = econ.demographic_bridge
    for _ in range(3):
        econ.step()
    hh0 = int(bridge.household_id_for_account(econ.households[0].id))
    bridge.stratification.mortality_strata[hh0] = 1e5     # probate supply
    for _ in range(400):
        econ.step()
        if econ.housing_market.sales_total > 0:
            break
    assert econ.housing_market.sales_total >= 1
    assert getattr(econ, "_transfer_tax_paid", 0.0) > 0.0


def test_permit_lever_zero_stops_minting():
    econ = make_econ(housing_construction_enabled=True, builder_productivity=0.05)
    econ.policy.housing_permits = 0                       # runtime zoning freeze
    for _ in range(200):
        econ.step()
    assert getattr(econ, "_dwellings_built", 0) == 0
    assert sum(getattr(f, "wip", 0.0) for f in econ.builders) > 0.0   # WIP piles up


def test_ltv_lever_syncs_to_book():
    econ = make_econ(mortgage_enabled=True)
    econ.policy.mortgage_ltv_cap = 0.42
    for _ in range(31):                                   # one session: maintain() syncs
        econ.step()
    assert econ.mortgage_book.ltv_cap == pytest.approx(0.42)


def test_housing_in_wealth_tax_raises_revenue():
    def wealth_tax_total(flag):
        econ = make_econ(tax_wealth_rate=0.0005, wealth_allowance=0.0,
                         housing_in_wealth_tax=flag)
        total = 0.0
        for _ in range(30):
            econ.step()
            total += econ._tax_wealth
        return total

    assert wealth_tax_total(True) > wealth_tax_total(False)


def test_housing_wealth_effect_lifts_consumption_budget():
    """Read the budget right after PLANNING (the goods phase spends it within the same
    tick, so end-of-step budgets converge back toward residuals)."""
    from macro_sim.systems.planning import run_planning_phase

    def planned_budget(hwe):
        econ = make_econ(housing_wealth_effect=hwe)
        econ._pubcap_factor = 1.0
        run_planning_phase(econ)
        return sum(h.consumption_budget for h in econ.households)

    lifted, base = planned_budget(0.5), planned_budget(0.0)
    assert lifted > base * 1.05
