"""Acceptance tests for replacement-cost capital service in long-run quotes."""

from __future__ import annotations

import math
import random

import pytest

from macro_sim.behavior import planning as B
from macro_sim.config import Config
from macro_sim.diagnostics.probes import DeepProbeCollector
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.domain.agents import Firm
from macro_sim.economy import Economy
from macro_sim.reporting.metrics import compute_tick_metrics
from macro_sim.systems.planning import run_planning_phase
from macro_sim.systems.settlement import run_settlement_phase


def _controlled_firm() -> Firm:
    firm = Firm.create_c_firm(0, Config())
    firm.capital = 5.0                   # physical K units
    firm.delta_K = 0.10                 # per tick
    firm.production_target = 10.0       # physical output units / tick
    firm.labor_demand_notional = 10.0
    firm.wage = 1.0
    firm.energy_intensity = 0.0
    firm.dis_slope = 0.0
    return firm


def test_replacement_price_closes_units_and_scales_service_cost_linearly():
    firm = _controlled_firm()

    total = B.capital_service_cost(
        firm, replacement_price=2.0, opportunity_rate=0.05,
    )
    unit = B.capital_service_unit_cost(
        firm, replacement_price=2.0, opportunity_rate=0.05,
    )
    doubled_price = B.capital_service_unit_cost(
        firm, replacement_price=4.0, opportunity_rate=0.05,
    )

    # (money/K) * K * (1/tick) = money/tick; dividing by output/tick = money/output.
    assert total == pytest.approx(2.0 * 5.0 * (0.10 + 0.05))
    assert unit == pytest.approx(total / 10.0)
    assert doubled_price == pytest.approx(2.0 * unit)
    assert B.unit_cost(firm, unit) == pytest.approx(1.0 + unit)


def test_zero_capital_and_zero_output_are_safe_without_epsilon_cost_explosion():
    firm = _controlled_firm()
    firm.capital = 0.0
    assert B.capital_service_cost(
        firm, replacement_price=3.0, opportunity_rate=0.10,
    ) == 0.0
    assert B.capital_service_unit_cost(
        firm, replacement_price=3.0, opportunity_rate=0.10,
    ) == 0.0

    firm.capital = 5.0
    firm.production_target = 0.0
    fixed_cost = B.capital_service_cost(
        firm, replacement_price=3.0, opportunity_rate=0.10,
    )
    allocated = B.capital_service_unit_cost(
        firm, replacement_price=3.0, opportunity_rate=0.10,
    )
    assert fixed_cost > 0.0
    assert allocated == 0.0
    B.plan_price(firm, random.Random(0), theta_price=1.0, capital_unit_cost=allocated)
    assert math.isfinite(firm.price) and firm.price > 0.0


def _planned_quote(rate: float) -> tuple[float, float, float, dict[str, float]]:
    econ = Economy(Config.v3(
        seed=31,
        n_firms_c=1,
        n_firms_k=1,
        n_households=4,
        n_ticks=1,
        theta_wage=0.0,
        theta_price=1.0,
        eta=0.0,
        dis_slope=0.0,
        capital_service_pricing=True,
    ))
    econ._rate = rate
    econ._firm_pnl_capital_price = 3.0
    run_planning_phase(econ)
    firm = econ.c_firms[0]
    record = compute_tick_metrics(econ)
    return (
        firm.pricing_capital_service_cost,
        firm.pricing_capital_unit_cost,
        firm.price,
        record,
    )


def test_live_per_tick_rate_weakly_raises_capital_unit_cost_and_quote():
    low = _planned_quote(0.01)
    high = _planned_quote(0.08)

    assert high[0] > low[0]
    assert high[1] > low[1]
    assert high[2] > low[2]
    assert high[3]["capital_service_pricing_enabled"] == 1.0
    assert high[3]["capital_service_cost_planned"] == pytest.approx(high[0])


def _planned_energy_quote(
    replacement_price: float,
    opportunity_rate: float,
) -> tuple[float, float, float, float, float, dict[str, float], dict[str, float]]:
    econ = Economy(Config.v2(
        seed=41,
        n_firms_c=1,
        n_firms_k=1,
        n_firms_e=1,
        n_households=4,
        n_ticks=1,
        energy_enabled=True,
        capital_service_pricing=True,
        theta_wage=0.0,
        theta_price=1.0,
        eta=0.0,
        dis_slope=0.0,
    ))
    firm = econ.e_firms[0]
    # Pin the E-sector plan so the two comparative statics vary only P_K or r.
    firm.capital = firm.capital_prev = 5.0
    firm.delta_K = 0.10
    firm.capacity_kappa = 100.0
    firm.phi = 0.0
    firm.lambda_d = 0.0
    firm.demand_expected = firm.sales_prev = 10.0
    firm.inventory = firm.target_inventory_prev = 0.0
    econ._firm_pnl_capital_price = replacement_price
    econ._rate = opportunity_rate

    run_planning_phase(econ)
    record = compute_tick_metrics(econ)
    probe = DeepProbeCollector().collect(econ, record)
    return (
        firm.pricing_capital_service_cost,
        firm.pricing_capital_unit_cost,
        firm.price,
        firm.production_target,
        firm.markup,
        record,
        probe,
    )


def test_energy_quote_has_controlled_replacement_price_and_rate_derivatives():
    base = _planned_energy_quote(2.0, 0.03)
    high_price = _planned_energy_quote(4.0, 0.03)
    high_rate = _planned_energy_quote(2.0, 0.08)

    # E firms own physical capacity and depreciate/invest through the K market, so
    # their quote must recover P_K*K*(delta+r), just like other capital users.
    assert base[0] == pytest.approx(2.0 * 5.0 * (0.10 + 0.03))
    assert high_price[0] - base[0] == pytest.approx(2.0 * 5.0 * (0.10 + 0.03))
    assert high_rate[0] - base[0] == pytest.approx(2.0 * 5.0 * (0.08 - 0.03))
    assert high_price[1] - base[1] == pytest.approx((high_price[0] - base[0]) / 10.0)
    assert high_rate[1] - base[1] == pytest.approx((high_rate[0] - base[0]) / 10.0)

    markup_multiplier = 1.0 + base[4]
    assert high_price[2] - base[2] == pytest.approx(
        markup_multiplier * (high_price[1] - base[1])
    )
    assert high_rate[2] - base[2] == pytest.approx(
        markup_multiplier * (high_rate[1] - base[1])
    )
    assert base[5]["energy_capital_service_cost_planned"] == pytest.approx(base[0])
    assert base[5]["energy_capital_service_cost_allocated"] == pytest.approx(base[0])
    assert base[6]["capital_service_cost_planned"] == pytest.approx(
        base[5]["capital_service_cost_planned"]
    )


def test_flag_is_default_off_frontier_on_and_explicit_off_is_bit_identical():
    assert Config().capital_service_pricing is False
    assert FULL_FRONTIER_FLAGS["capital_service_pricing"] is True

    params = dict(
        seed=17, n_ticks=25, n_households=12, n_firms_c=4, n_firms_k=2,
        n_firms_e=2, energy_enabled=True,
    )
    implicit = Economy(Config.v3(**params))
    explicit = Economy(Config.v3(**params, capital_service_pricing=False))

    assert implicit.run() == explicit.run()
    assert implicit.ledger.snapshot() == explicit.ledger.snapshot()
    assert implicit.rng.getstate() == explicit.rng.getstate()


def test_non_pnl_mode_commits_realized_capital_price_for_next_planning_tick():
    econ = Economy(Config.v2(
        seed=9,
        n_firms_c=1,
        n_firms_k=1,
        n_households=4,
        n_ticks=1,
        theta_price=0.0,
        capital_service_pricing=True,
        firm_full_pnl=False,
    ))
    seller = econ.k_firms[0]
    seller.sales = 2.0
    seller.revenue = 14.0

    run_settlement_phase(econ)
    assert econ._firm_pnl_capital_price == pytest.approx(7.0)

    run_planning_phase(econ)
    assert econ.c_firms[0].pricing_capital_price == pytest.approx(7.0)


def _closed_pnl(capital_service_pricing: bool) -> tuple[float, ...]:
    econ = Economy(Config.v3(
        seed=5,
        n_firms_c=1,
        n_firms_k=1,
        n_households=4,
        n_ticks=1,
        firm_full_pnl=True,
        capital_service_pricing=capital_service_pricing,
        rho=0.0,
    ))
    firm = econ.c_firms[0]
    econ._firm_pnl_capital_price = 5.0
    firm.revenue = 100.0
    firm.wagebill = 30.0
    firm.energy_cost_used = 10.0
    firm.capital = 20.0
    firm.delta_K = 0.10
    # Even a populated planning gauge is not an accounting journal entry.
    firm.pricing_capital_service_cost = 999.0

    run_settlement_phase(econ)
    return (
        firm.pnl_depreciation,
        firm.pnl_ebit,
        firm.pnl_pre_tax_income,
        firm.pnl_net_income,
        firm.pnl_retained_earnings,
    )


def test_full_pnl_recognizes_depreciation_once_and_never_expenses_pricing_gauge():
    legacy_quote = _closed_pnl(False)
    capital_service_quote = _closed_pnl(True)

    assert capital_service_quote == legacy_quote
    assert capital_service_quote[0] == pytest.approx(0.10 * 20.0 * 5.0)
    assert capital_service_quote[1] == pytest.approx(50.0)
    assert capital_service_quote[2:] == pytest.approx((50.0, 50.0, 50.0))
