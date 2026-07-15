"""v23 C-sector unmet-demand attribution.

The signal is an isolated protocol-consistent failed-visit estimator, not an
equal/market-share split of aggregate unspent money or a claim about the
transaction path.  It is physical, expectations-only, and opt-in.
"""

from __future__ import annotations

import random

import pytest

from macro_sim.config import Config
from macro_sim.core.ledger import Ledger
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.markets.matching import (
    BuyOrder,
    MarketTrace,
    PriceSortedMatch,
    SampledCompareMatch,
    SellOffer,
    execute_market,
)
from macro_sim.systems.goods import _necessity_need_for, run_goods_phase


def test_unmet_is_attributed_to_the_protocol_selected_quote_not_spread() -> None:
    ledger = Ledger({"H0": 8.0, "H1": 12.0, "CHEAP": 0.0, "EXPENSIVE": 0.0})
    orders = [
        BuyOrder("H0", demand=float("inf"), budget=8.0),
        BuyOrder("H1", demand=float("inf"), budget=12.0),
    ]
    offers = [
        SellOffer("CHEAP", stock=0.0, price=2.0),
        SellOffer("EXPENSIVE", stock=0.0, price=4.0),
    ]
    trace = MarketTrace()

    trades = execute_market(
        orders, offers, protocol=PriceSortedMatch(), rng=random.Random(7),
        ledger=ledger, unmet_trace=trace,
    )

    assert trades == []
    # The full-information diagnostic rule selects the cheapest unavailable seller.
    # No signal is fabricated for the unseen/unselected expensive firm.
    assert trace.by_seller == {"CHEAP": pytest.approx(10.0)}
    assert trace.attributable_qty == pytest.approx(10.0)
    assert sum(visit.affordable_value for visit in trace.visits) == pytest.approx(20.0)
    assert ledger.snapshot() == {"H0": 8.0, "H1": 12.0, "CHEAP": 0.0, "EXPENSIVE": 0.0}


def test_trace_quantity_conserves_the_protocol_defined_unmet_total() -> None:
    ledger = Ledger({"H0": 5.0, "H1": 5.0, "F0": 0.0, "F1": 0.0})
    orders = [
        BuyOrder("H0", demand=float("inf"), budget=5.0),
        BuyOrder("H1", demand=float("inf"), budget=5.0),
    ]
    offers = [SellOffer("F0", 0.0, 1.0), SellOffer("F1", 0.0, 1.0)]
    trace = MarketTrace()

    execute_market(
        orders, offers, protocol=SampledCompareMatch(1), rng=random.Random(11),
        ledger=ledger, unmet_trace=trace,
    )

    # At a common observed quote of 1, physical unmet demand equals unspent
    # nominal intent.  Each order produces one visit, never multiple claims.
    assert len(trace.visits) == 2
    assert sum(trace.by_seller.values()) == pytest.approx(10.0)
    assert trace.attributable_qty == pytest.approx(10.0)
    assert trace.unattributed_orders == 0


def test_no_visited_seller_leaves_residual_unattributed() -> None:
    ledger = Ledger({"H": 7.0})
    trace = MarketTrace()

    execute_market(
        [BuyOrder("H", demand=3.0, budget=7.0)], [],
        protocol=SampledCompareMatch(1), rng=random.Random(3), ledger=ledger,
        unmet_trace=trace,
    )

    assert trace.visits == []
    assert trace.by_seller == {}
    assert trace.attributable_qty == 0.0
    assert trace.unattributed_orders == 1
    assert trace.unattributed_budget == pytest.approx(7.0)
    assert trace.unattributed_finite_demand == pytest.approx(3.0)


def _market_with_optional_trace(enabled: bool):
    ledger = Ledger({"H0": 5.0, "H1": 5.0, "F0": 0.0, "F1": 0.0})
    orders = [
        BuyOrder("H0", demand=float("inf"), budget=5.0),
        BuyOrder("H1", demand=float("inf"), budget=5.0),
    ]
    offers = [SellOffer("F0", 1.0, 1.0), SellOffer("F1", 1.0, 1.0)]
    rng = random.Random(19)
    trace = MarketTrace() if enabled else None
    trades = execute_market(
        orders, offers, protocol=SampledCompareMatch(1), rng=rng, ledger=ledger,
        unmet_trace=trace,
    )
    return trades, ledger.snapshot(), [(o.stock, o.sold) for o in offers], rng.getstate(), trace


def test_trace_is_observational_for_current_trades_money_and_rng() -> None:
    plain = _market_with_optional_trace(False)
    observed = _market_with_optional_trace(True)

    assert observed[:4] == plain[:4]
    assert observed[4] is not None
    assert observed[4].attributable_qty == pytest.approx(8.0)


def test_goods_flag_assigns_only_next_period_signal() -> None:
    params = dict(seed=23, n_households=2, n_firms=2)
    legacy = Economy(Config(**params, consumption_rationed_signal=False))
    enabled = Economy(Config(**params, consumption_rationed_signal=True))
    for econ in (legacy, enabled):
        for household in econ.households:
            household.consumption_budget = 10.0
        for firm in econ.c_firms:
            firm.inventory = 1.0
            firm.price = 1.0

    expectations_before = [firm.demand_expected for firm in enabled.c_firms]
    run_goods_phase(legacy)
    run_goods_phase(enabled)

    assert [firm.sales for firm in enabled.c_firms] == [firm.sales for firm in legacy.c_firms]
    assert [firm.revenue for firm in enabled.c_firms] == [firm.revenue for firm in legacy.c_firms]
    assert enabled.ledger.snapshot() == legacy.ledger.snapshot()
    assert enabled.rng.getstate() == legacy.rng.getstate()
    assert [firm.demand_expected for firm in enabled.c_firms] == expectations_before
    assert sum(firm.rationed_demand for firm in legacy.c_firms) == 0.0
    assert sum(firm.rationed_demand for firm in enabled.c_firms) == pytest.approx(18.0)
    assert enabled._c_firm_footfall == pytest.approx(18.0)


def test_stratified_sessions_do_not_cross_assign_necessity_footfall() -> None:
    econ = Economy(Config(
        seed=29, n_households=2, n_firms=2, consumption_strata=True,
        consumption_rationed_signal=True,
    ))
    assert len(econ.n_firms) == len(econ.l_firms) == 1
    for household in econ.households:
        household.consumption_budget = 10.0
    for firm in econ.n_firms:
        firm.inventory = 0.0
        firm.price = 1.0
    for firm in econ.l_firms:
        firm.inventory = 100.0
        firm.price = 1.0
    expected_necessity = sum(_necessity_need_for(econ, household) for household in econ.households)

    run_goods_phase(econ)

    assert sum(firm.rationed_demand for firm in econ.n_firms) == pytest.approx(expected_necessity)
    assert sum(firm.rationed_demand for firm in econ.l_firms) == 0.0


def test_stratified_unmet_signals_do_not_double_count_one_budget() -> None:
    econ = Economy(Config(
        seed=30,
        n_households=2,
        n_firms=2,
        consumption_strata=True,
        consumption_rationed_signal=True,
    ))
    for household in econ.households:
        household.consumption_budget = 10.0
    for firm in econ.c_firms:
        firm.inventory = 0.0
        firm.price = 1.0
    expected_necessity = sum(
        _necessity_need_for(econ, household) for household in econ.households
    )

    run_goods_phase(econ)

    assert sum(firm.rationed_demand for firm in econ.n_firms) == pytest.approx(
        expected_necessity
    )
    assert sum(firm.rationed_demand for firm in econ.l_firms) == 0.0
    assert econ._c_firm_footfall == pytest.approx(expected_necessity)


def test_default_is_off_full_frontier_is_on_and_explicit_off_is_identical() -> None:
    assert Config().consumption_rationed_signal is False
    assert FULL_FRONTIER_FLAGS["consumption_rationed_signal"] is True

    params = dict(seed=31, n_households=8, n_firms=3, n_ticks=4)
    default = Economy(Config(**params))
    explicit = Economy(Config(**params, consumption_rationed_signal=False))
    assert default.run() == explicit.run()
    assert default.ledger.snapshot() == explicit.ledger.snapshot()
    assert default.rng.getstate() == explicit.rng.getstate()
    assert all(firm.rationed_demand == 0.0 for firm in default.c_firms)
