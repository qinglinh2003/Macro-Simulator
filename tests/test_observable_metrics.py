import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.reporting.metrics import compute_tick_metrics
from macro_sim.systems.securities import bond_market_value, reindex_bonds


def test_real_activity_observable_metrics_are_exported_from_firm_state():
    econ = Economy(Config.v2(n_households=4, n_firms_c=2, n_firms_k=1, seed=11))
    c0, c1 = econ.c_firms
    k0 = econ.k_firms[0]

    c0.produced, c0.sales, c0.revenue, c0.inventory = 8.0, 5.0, 10.0, 7.0
    c1.produced, c1.sales, c1.revenue, c1.inventory = 2.0, 1.0, 3.0, 4.0
    k0.produced, k0.sales, k0.revenue, k0.inventory = 0.0, 0.0, 0.0, 6.0

    c0.production_target, c1.production_target = 9.0, 3.0
    c0.demand_expected, c1.demand_expected = 4.0, 8.0
    c0.target_inventory, c1.target_inventory = 6.0, 5.0
    c0.investment_target, c1.investment_target = 5.0, 7.0
    c0.investment, c1.investment = 2.0, 4.0
    c0.capital, c1.capital = 20.0, 10.0
    c0.delta_K, c1.delta_K = 0.1, 0.2

    rec = compute_tick_metrics(econ)

    assert rec["production_target_total"] == pytest.approx(12.0)
    assert rec["production_realization_rate"] == pytest.approx(10.0 / 12.0)
    assert rec["demand_expected_total"] == pytest.approx(12.0)
    assert rec["inventory_gap_total"] == pytest.approx(0.0)
    assert rec["inventory_gap_ratio"] == pytest.approx(0.0)
    assert rec["investment_target_units"] == pytest.approx(12.0)
    assert rec["investment_realization_rate"] == pytest.approx(0.5)
    assert rec["private_capital_depreciation"] == pytest.approx(4.0)
    assert rec["net_private_capital_formation"] == pytest.approx(2.0)
    assert rec["inventory_to_sales"] == pytest.approx(11.0 / 6.0)
    assert rec["capital_productivity"] == pytest.approx(10.0 / 30.0)
    assert rec["active_producer_share"] == pytest.approx(2.0 / 3.0)
    assert rec["active_seller_share"] == pytest.approx(2.0 / 3.0)


def test_fiscal_and_policy_observable_metrics_use_complete_flow_and_metadata():
    econ = Economy(Config.v10(n_households=10, n_firms_c=3, n_firms_k=1, seed=7))
    for f in econ.c_firms:
        f.produced = 10.0
        f.sales = 5.0
        f.revenue = 10.0
        f.price = 2.0
        f.hired = 3.0
    econ.c_firms[-1].hired = 3.5

    econ._tax_profit = 1.0
    econ._tax_income = 2.0
    econ._tax_consumption = 3.0
    econ._tax_wealth = 4.0
    econ._benefit_paid = 5.0
    econ._gov_consumption = 6.0
    econ._jg_spending = 7.0
    econ._public_investment = 8.0
    econ._gov_interest_bill = 9.0
    econ._rate = 0.05
    econ._infl_ema = 0.02

    rec = compute_tick_metrics(econ)

    assert rec["augmented_gov_spending"] == pytest.approx(35.0)
    assert rec["cash_deficit"] == pytest.approx(25.0)
    assert rec["cash_deficit_to_gdp"] == pytest.approx(25.0 / 60.0)
    assert rec["augmented_gov_spending_share_of_gdp"] == pytest.approx(35.0 / 60.0)
    assert rec["inflation_target"] == pytest.approx(econ.policy.inflation_target)
    assert rec["inflation_gap_to_target"] == pytest.approx(0.008)
    assert rec["u_natural"] == pytest.approx(econ.cfg.u_natural)
    assert rec["unemployment_gap"] == pytest.approx(0.0)
    assert rec["taylor_rate_target"] == pytest.approx(0.0196)
    assert rec["policy_rate_gap"] == pytest.approx(0.0304)


def test_bond_market_value_and_owner_metrics_are_exported_from_lots():
    econ = Economy(Config.v123(n_households=20, n_firms_c=3, n_firms_k=2, n_banks=2, seed=13))
    household_id = econ.households[0].id
    bank_id = econ.banks[0].id
    econ._rate = 0.08
    econ._bonds = [
        {"holder": household_id, "face": 100.0, "cost": 95.0, "matures_at": econ.t + 4},
        {"holder": bank_id, "face": 50.0, "cost": 52.0, "matures_at": econ.t + 3},
        {"holder": "CB", "face": 25.0, "cost": 25.0, "matures_at": econ.t + 2},
    ]
    econ._bonds_outstanding = 175.0
    reindex_bonds(econ)

    rec = compute_tick_metrics(econ)

    hh_market = bond_market_value(econ, econ._bonds[0])
    bank_market = bond_market_value(econ, econ._bonds[1])
    cb_market = bond_market_value(econ, econ._bonds[2])
    market_total = hh_market + bank_market + cb_market

    assert rec["hh_bond_face"] == pytest.approx(100.0)
    assert rec["hh_bond_market_value"] == pytest.approx(hh_market)
    assert rec["bank_bond_market_value"] == pytest.approx(bank_market)
    assert rec["bond_owner_share_households"] == pytest.approx(hh_market / market_total)
    assert rec["bond_owner_share_banks"] == pytest.approx(bank_market / market_total)
    assert rec["bond_owner_share_cb"] == pytest.approx(cb_market / market_total)
    assert rec["bond_maturity_weighted"] == pytest.approx(
        (100.0 * 4.0 + 50.0 * 3.0 + 25.0 * 2.0) / 175.0
    )
