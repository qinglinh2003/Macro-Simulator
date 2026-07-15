"""Fast dynamic checks for the open-economy diagnostic probes."""

from __future__ import annotations

import math

import pytest

import macro_sim.diagnostics.world_probes as world_probes
import macro_sim.world.world as world_module
from macro_sim.config import Config
from macro_sim.diagnostics.world_probes import (
    WorldProbeCollector,
    build_small_world,
    diagnose_world,
    run_small_world_diagnostic,
)
from macro_sim.world import World
from macro_sim.world.fx import BalanceOfPaymentsError, DEALER_ID
from macro_sim.world.trade import _ship_exports, prepare_trade, settle_trade


def _ids(result):
    return {finding.issue_id for finding in result.findings}


def test_three_country_probe_collects_bilateral_and_external_accounts():
    result = run_small_world_diagnostic(n=3, ticks=8, population=30)

    assert len(result.records) == 8
    last = result.records[-1]
    assert len(last["bilateral_imports_numeraire"]) == 3
    assert all(len(row) == 3 for row in last["bilateral_exports_numeraire"])
    assert len(last["current_account"]) == 3
    assert len(last["nfa"]) == 3
    assert len(last["factor_income"]) == 3
    assert len(last["factor_income_cash"]) == 3
    assert len(last["factor_income_accrued"]) == 3
    assert len(last["factor_income_arrears"]) == 3
    assert len(last["factor_income_unpaid_tick"]) == 3
    assert len(last["factor_income_arrears_cured_tick"]) == 3
    assert len(last["factor_income_arrears_bilateral"]) == 3
    assert all(len(row) == 3 for row in last["factor_income_arrears_bilateral"])
    assert len(last["augmented_nfa"]) == 3
    assert len(last["remittances"]) == 3
    for field in (
        "import_delivered_volume",
        "export_delivered_volume",
        "export_shipped_volume",
        "iceberg_loss_volume",
        "export_contract_basic_value",
        "export_barrier_lot_basic_value",
        "export_account_lot_basic_value",
        "export_barrier_lot_contract_gap",
        "export_lot_repricing_gap",
        "export_inventory_withdrawal_price_adjustment",
    ):
        assert len(last[field]) == 3
    for shipped, delivered, loss in zip(
        last["export_shipped_volume"],
        last["export_delivered_volume"],
        last["iceberg_loss_volume"],
    ):
        assert shipped == pytest.approx(delivered + loss)
    assert "dealer_net_worth_numeraire" in last
    assert sum(sum(row["imports_numeraire"]) for row in result.records) > 0.0


def test_direct_export_helper_is_bounded_by_available_inventory():
    world = build_small_world(n=2, ticks=1, population=12)
    econ = world.economies[0]
    available_units = sum(float(f.inventory) for f in econ.c_firms)
    current_production = sum(float(f.produced) for f in econ.c_firms)
    sales_before = sum(float(f.sales) for f in econ.c_firms)
    inventory_value = sum(float(f.inventory * f.price) for f in econ.c_firms)
    target = inventory_value + 10.0 * max(float(f.price) for f in econ.c_firms)

    shipped = _ship_exports(econ, target)
    export_units = sum(float(f.sales) for f in econ.c_firms) - sales_before

    assert shipped < target
    assert export_units == pytest.approx(available_units)
    assert export_units <= available_units + current_production
    assert all(f.inventory >= -1e-12 for f in econ.c_firms)


def test_world_probe_confirms_every_export_has_physical_backing():
    result = run_small_world_diagnostic(
        n=2, ticks=3, population=20, fx_friction=0.25,
    )

    assert result.checks["export_physical_backing"]["passed"]
    assert result.checks["export_physical_backing"]["cumulative_unbacked_export_volume"] == 0.0
    assert result.checks["iceberg_physical_identity"]["passed"]
    assert result.checks["export_lot_contract_valuation"]["passed"]
    shipped = sum(sum(row["export_shipped_volume"]) for row in result.records)
    delivered = sum(sum(row["import_delivered_volume"]) for row in result.records)
    loss = sum(sum(row["iceberg_loss_volume"]) for row in result.records)
    assert result.checks["export_physical_backing"][
        "cumulative_realized_export_volume"
    ] == pytest.approx(shipped)
    assert shipped == pytest.approx(delivered + loss)
    assert shipped > delivered
    assert loss > 0.0
    assert "world.exports_unbacked_by_goods" not in _ids(result)
    assert "world.iceberg_physical_identity_broken" not in _ids(result)
    assert "world.export_lot_contract_valuation_broken" not in _ids(result)


def test_shared_source_inventory_is_reserved_once_and_unsold_lots_are_returned():
    world = build_small_world(n=3, ticks=1, population=12)
    source = world.economies[0]
    source._price_level = 0.1
    world.economies[1]._price_level = 2.0
    world.economies[2]._price_level = 3.0
    for firm in source.c_firms:
        firm.inventory = 0.0
    source.c_firms[0].inventory = 2.0
    opening = sum(f.inventory for f in source.c_firms)
    world._last_export_value = [100.0, 100.0, 100.0]

    prepare_trade(world)

    source_reservations = [
        reservation for reservation in world._export_reservations
        if reservation is not None and reservation["source"] == 0
    ]
    reserved = sum(
        lot["units"] for reservation in source_reservations
        for lot in reservation["lots"]
    )
    assert reserved == pytest.approx(opening)
    assert sum(f.inventory for f in source.c_firms) == pytest.approx(0.0)
    # Economy id is the deterministic allocation order. Importer 1 takes its cap
    # first and importer 2 receives only the residual, never a duplicate copy.
    assert world._export_reservations[1] is not None
    assert world._export_reservations[2] is not None
    reserved_1 = sum(lot["units"] for lot in world._export_reservations[1]["lots"])
    reserved_2 = sum(lot["units"] for lot in world._export_reservations[2]["lots"])
    assert reserved_1 > reserved_2
    for importer in (1, 2):
        reservation = world._export_reservations[importer]
        reserved_shipped = sum(lot["units"] for lot in reservation["lots"])
        assert world.economies[importer]._fx_import_offer.stock * reservation[
            "iceberg_multiplier"
        ] == pytest.approx(reserved_shipped)

    # No importing market has run, hence every reserved unit is unsold and must be
    # restored to the exact source firms during settlement.
    settle_trade(world)
    assert sum(f.inventory for f in source.c_firms) == pytest.approx(opening)
    assert all(reservation is None for reservation in world._export_reservations)


def test_world_probe_flags_a_broken_iceberg_quantity_identity():
    world = build_small_world(
        n=2, ticks=2, population=20, fx_friction=0.25,
    )
    baseline = WorldProbeCollector(world).run(2)
    broken_rows = [dict(row) for row in baseline.records]
    broken_rows[0]["iceberg_loss_volume"] = list(
        broken_rows[0]["iceberg_loss_volume"]
    )
    broken_rows[0]["iceberg_loss_volume"][0] += 1.0

    broken = diagnose_world(world, broken_rows)

    assert not broken.checks["iceberg_physical_identity"]["passed"]
    assert "world.iceberg_physical_identity_broken" in _ids(broken)


def test_world_probe_flags_a_contract_not_backed_by_barrier_lots():
    world = build_small_world(n=2, ticks=3, population=20)
    baseline = WorldProbeCollector(world).run(3)
    broken_rows = [dict(row) for row in baseline.records]
    active = next(
        row for row in broken_rows if sum(row["export_contract_basic_value"]) > 0.0
    )
    active["export_barrier_lot_contract_gap"] = list(
        active["export_barrier_lot_contract_gap"]
    )
    active["export_barrier_lot_contract_gap"][0] += 1.0

    broken = diagnose_world(world, broken_rows)

    assert not broken.checks["export_lot_contract_valuation"]["passed"]
    assert "world.export_lot_contract_valuation_broken" in _ids(broken)


def test_observed_identity_failures_are_linked_to_structured_findings():
    result = run_small_world_diagnostic(n=2, ticks=14, population=30)
    ids = _ids(result)
    assert result.checks["domestic_world_settlement_alignment"]["passed"]
    assert "world.cross_border_settlement_after_domestic_commit" not in ids

    # The current implementation has material cross-border activity, so this test is
    # genuinely exercising the identities rather than passing on an all-zero world.
    assert result.checks["bilateral_trade_mirror"]["gross_trade_numeraire"] > 0.0
    assert result.checks["dealer_full_tick_passthrough"]["passed"]
    assert result.checks["dealer_flow_valuation_separation"]["passed"]
    assert result.checks["dealer_flow_valuation_separation"]["status"] == "identified"
    assert result.checks["nfa_flow_revaluation_decomposition"]["passed"]
    assert result.checks["external_position_stock_identity"]["passed"]
    assert result.checks["factor_income_counterparty"]["passed"]
    assert result.checks["factor_income_accrual_counterparty"]["passed"]
    assert result.checks["factor_income_counterparty"]["gross_factor_income"] > 0.0
    assert result.checks["current_account_zero_sum"]["passed"]
    assert result.checks["current_account_accrual_zero_sum"]["passed"]
    assert result.checks["current_account_transaction_rate_basis"]["passed"]
    assert result.checks["nfa_ca_valuation_reconciliation"]["passed"]
    assert result.checks["augmented_nfa_flow_revaluation_decomposition"]["passed"]
    assert result.checks["augmented_nfa_accrual_ca_reconciliation"]["passed"]
    assert result.checks["remittance_current_account_counterparty"]["passed"]
    assert "world.dealer_valuation_includes_transactions" not in ids
    assert "world.remittance_counterflow_missing" not in ids
    assert "world.current_account_uses_post_grope_fx" not in ids
    assert "world.remittance_account_counterparty_missing" not in ids


def test_full_tick_flow_and_revaluation_checks_are_not_vacuous():
    world = build_small_world(n=2, ticks=5, population=24)
    collector = WorldProbeCollector(world)
    result = collector.run(5)

    assert result.checks["dealer_full_tick_passthrough"]["passed"]
    assert result.checks["dealer_flow_valuation_separation"]["passed"]

    # The native hard gate prevents a bad live tick from returning.  Corrupt a persisted
    # probe row to prove the offline detector itself still turns red on a leaked flow.
    broken_rows = [dict(row) for row in result.records]
    broken_rows[0]["dealer_flow_numeraire"] = 1.0
    broken = diagnose_world(world, broken_rows)
    assert not broken.checks["dealer_full_tick_passthrough"]["passed"]
    assert "world.dealer_flow_not_passthrough" in _ids(broken)


def test_real_fx_reserves_enter_nfa_and_full_tick_passthrough():
    world = build_small_world(
        n=2, ticks=16, population=24,
        peg=True, peg_reserves0=100.0, peg_reserve_scale=0.02,
    )
    result = WorldProbeCollector(world).run(16)
    stock = result.checks["external_position_stock_identity"]

    assert stock["passed"]
    assert stock["max_fx_reserves"] > 0.0
    assert stock["reserve_change"] > 0.0
    assert result.checks["dealer_full_tick_passthrough"]["passed"]
    assert result.checks["nfa_flow_revaluation_decomposition"]["passed"]
    assert result.checks["peg_reserve_flow_gate_order"]["passed"]
    assert "world.peg_reserve_flow_after_bop_gate" not in _ids(result)


def test_native_gate_catches_a_leaking_peg_reserve_leg(monkeypatch):

    import macro_sim.world.capital as capital

    honest_defence = capital._defend_peg

    def leaky_defence(world, drain_for):
        honest_defence(world, drain_for)
        home = world.economies[0]
        home.ledger.transfer(home._fiscal, DEALER_ID, 1.0)

    monkeypatch.setattr(capital, "_defend_peg", leaky_defence)
    world = build_small_world(
        n=2, ticks=2, population=24,
        peg=True, peg_reserves0=100.0, peg_reserve_scale=0.02,
    )
    with pytest.raises(BalanceOfPaymentsError):
        WorldProbeCollector(world).step()


def test_consumption_strata_trade_channel_is_live():
    result = run_small_world_diagnostic(
        n=2, ticks=8, population=30, consumption_strata=True
    )
    check = result.checks["consumption_strata_trade_channel"]
    assert check["passed"]
    assert check["gross_trade_numeraire"] > 0.0
    assert "world.trade_disabled_by_consumption_strata" not in _ids(result)
    # A source is selected at the coupling barrier, distinguishing a dead goods-path
    # channel from deliberate autarky/sanctions.
    assert check["active_sources"]


def test_daily_config_uses_per_tick_factor_income_rate_contract():
    world = build_small_world(n=2, ticks=1, population=12, daily=True)
    result = diagnose_world(world, [])
    check = result.checks["factor_income_rate_convention"]

    assert check["policy_rate_unit"] == "per_tick"
    assert check["configured_periods_per_year"] == 12.0
    assert not check["factor_income_uses_periods_per_year"]
    assert check["passed"]
    assert "world.daily_time_scale_mismatch" not in _ids(result)
    assert "world.factor_income_rate_double_scaled" not in _ids(result)


def test_factor_income_rate_probe_rejects_a_second_frequency_scaling(monkeypatch):
    def double_scaled_factor_income(world):
        return world.periods_per_year

    monkeypatch.setattr(world_probes, "capital_interest", double_scaled_factor_income)
    world = build_small_world(n=2, ticks=1, population=12, daily=True)
    result = diagnose_world(world, [])
    check = result.checks["factor_income_rate_convention"]

    assert not check["passed"]
    assert check["factor_income_uses_periods_per_year"]
    assert "world.factor_income_rate_double_scaled" in _ids(result)


def test_collector_does_not_recompute_or_append_domestic_metrics():
    world = build_small_world(n=2, ticks=2, population=20)
    collector = WorldProbeCollector(world)
    collector.step()

    assert all(len(econ.records) == 1 for econ in world.economies)
    assert len(world.world_records) == 1
    assert len(collector.records) == 1


def test_cross_border_household_receipts_are_posted_before_domestic_close(monkeypatch):
    world = build_small_world(n=2, ticks=12, population=24)
    original_update = world._dealer_update
    observed: list[tuple[list[float], list[float], list[float]]] = []

    def update_with_income_snapshot():
        before = [
            sum(float(h.income_realized) for h in econ.households)
            for econ in world.economies
        ]
        original_update()
        expected = [
            max(0.0, -float(world._factor_income[i]))
            + float(world._remittances[i])
            for i in range(world.n)
        ]
        after = [
            sum(float(h.income_realized) for h in econ.households)
            for econ in world.economies
        ]
        observed.append((before, after, expected))

    monkeypatch.setattr(world, "_dealer_update", update_with_income_snapshot)
    world.run(12)

    assert any(sum(expected) > 1.0e-9 for _, _, expected in observed)
    for before, after, expected in observed:
        for i in range(world.n):
            assert after[i] - before[i] == pytest.approx(expected[i])


def test_daily_world_cross_border_cash_keeps_person_claims_reconciled():
    world = build_small_world(n=2, ticks=10, population=12, daily=True)
    world.run(10)

    assert sum(sum(row["remittances"]) for row in world.world_records) > 0.0
    for econ in world.economies:
        econ.demographic_bridge.assert_all_claim_identities(econ)


def _rows_with_arrears(stocks):
    world = build_small_world(n=2, ticks=len(stocks), population=12)
    baseline = WorldProbeCollector(world).run(len(stocks))
    rows = []
    for index, stock in enumerate(stocks):
        row = dict(baseline.records[index])
        row["factor_income_arrears"] = [float(stock), 0.0]
        row["factor_income_arrears_bilateral"] = [
            [0.0, float(stock)], [0.0, 0.0],
        ]
        row["factor_income_arrears_unallocated"] = [0.0, 0.0]
        row["factor_income_unpaid_tick"] = [
            float(stock) if index == 0 else 0.0, 0.0,
        ]
        row["factor_income_arrears_cured_tick"] = [0.0, 0.0]
        rows.append(row)
    return world, rows


def test_external_interest_diagnostic_does_not_sum_repeated_arrears_stock():
    world, rows = _rows_with_arrears([2.0, 2.0, 2.0])
    result = diagnose_world(world, rows)
    service = result.checks["external_interest_service"]

    assert service["closing_arrears_numeraire"] == pytest.approx(2.0)
    assert service["peak_arrears_numeraire"] == pytest.approx(2.0)
    assert service["ticks_with_arrears"] == 3
    assert service["cumulative_new_arrears_numeraire"] == pytest.approx(2.0)
    assert "cumulative_arrears_numeraire" not in service
    assert service["payer"] == "consolidated_fiscal_or_external_issuer"
    assert service["creditor_allocation"] == "bilateral_locked"


def test_cured_arrears_are_not_reported_as_unresolved():
    world, rows = _rows_with_arrears([2.0, 2.0, 0.0])
    rows[-1]["factor_income_arrears_cured_tick"] = [2.0, 0.0]
    result = diagnose_world(world, rows)
    service = result.checks["external_interest_service"]

    assert service["passed"]
    assert service["closing_arrears_numeraire"] == pytest.approx(0.0)
    assert service["peak_arrears_numeraire"] == pytest.approx(2.0)
    assert service["cumulative_cured_arrears_numeraire"] == pytest.approx(2.0)
    assert "world.external_interest_arrears_without_resolution" not in _ids(result)


def test_world_reports_arrears_stock_at_closing_fx_and_flows_at_opening_fx(monkeypatch):
    world = build_small_world(n=2, ticks=1, population=12)
    world.fx_lambda = 1.0

    def expose_arrears(w):
        w._factor_income = [0.0, 0.0]
        w._factor_income_cash = [0.0, 0.0]
        w._factor_income_accrued = [10.0, -10.0]
        w._factor_income_cash_bilateral = [[0.0, 0.0], [0.0, 0.0]]
        w._factor_income_accrued_bilateral = [[0.0, 10.0], [0.0, 0.0]]
        w._factor_income_accrued_unallocated = [0.0, 0.0]
        w._factor_income_arrears_bilateral = [[0.0, 10.0], [0.0, 0.0]]
        w._factor_income_arrears_unallocated = [0.0, 0.0]
        w._factor_income_arrears = [10.0, 0.0]
        w._factor_income_unpaid_tick = [10.0, 0.0]
        w._factor_income_arrears_cured_tick = [0.0, 0.0]

    monkeypatch.setattr(world_module, "capital_interest", expose_arrears)
    monkeypatch.setattr(
        world_module, "rate_grope_signal",
        lambda _world: [math.log(2.0), math.log(0.5)],
    )

    world.step()
    record = world.world_records[-1]

    assert record["flow_e"] == pytest.approx([1.0, 1.0])
    assert record["e"] == pytest.approx([2.0, 0.5])
    assert record["factor_income_arrears"] == pytest.approx([5.0, 0.0])
    assert record["factor_income_arrears_bilateral"][0] == pytest.approx([0.0, 5.0])
    assert record["factor_income_arrears_assets"] == pytest.approx([0.0, 5.0])
    assert record["factor_income_unpaid_tick"] == pytest.approx([10.0, 0.0])
    assert record["factor_income_arrears_revaluation"] == pytest.approx([5.0, -5.0])


def test_partial_settlement_diagnostic_reconciles_accrual_ca_to_augmented_nfa():
    debtor_cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=2, r_interest=0.1,
    )
    creditor_cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=2, r_interest=0.0,
    )
    world = World(
        [debtor_cfg, creditor_cfg, creditor_cfg],
        base_seed=83,
        couple=True,
        capital=True,
        fx_lambda=0.0,
        external_interest_settlement_fraction=[0.25, 1.0, 1.0],
    )
    debtor, creditor_1, creditor_2 = world.economies
    debtor.ledger.transfer(debtor.households[0].id, DEALER_ID, 10.0)
    creditor_1.ledger.transfer(DEALER_ID, creditor_1.households[0].id, 4.0)
    creditor_2.ledger.transfer(DEALER_ID, creditor_2.households[0].id, 6.0)
    world._factor_interest_principal = [10.0, -4.0, -6.0]

    result = WorldProbeCollector(world).run(2)

    assert result.checks["external_interest_service"]["peak_arrears_numeraire"] > 0.0
    assert result.checks["factor_income_counterparty"]["passed"]
    assert result.checks["factor_income_accrual_counterparty"]["passed"]
    assert result.checks["current_account_zero_sum"]["passed"]
    assert result.checks["current_account_accrual_zero_sum"]["passed"]
    assert result.checks["augmented_nfa_flow_revaluation_decomposition"]["passed"]
    assert result.checks["augmented_nfa_accrual_ca_reconciliation"]["passed"]
