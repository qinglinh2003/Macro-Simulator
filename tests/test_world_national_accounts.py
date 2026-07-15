"""Integration gates between World settlement and Economy national accounts."""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.reporting.national_accounts import preview
from macro_sim.world import World
from macro_sim.world.fx import DEALER_ID
from macro_sim.world.trade import prepare_trade, settle_trade


def test_world_trade_journals_reach_same_tick_economy_national_accounts():
    configs = [
        Config.v124(
            n_firms_c=8,
            n_firms_k=4,
            n_households=30,
            n_ticks=6,
            seed=0,
            a=productivity,
            national_accounts_metrics=True,
        )
        for productivity in (0.8, 1.2)
    ]
    world = World(
        configs,
        base_seed=37,
        trade=True,
        tariff=[0.10, -0.05],
        export_subsidy=[0.20, -0.10],
    )

    observed_trade = False
    for _ in range(6):
        records = world.step()
        for index, (econ, record) in enumerate(zip(world.economies, records)):
            observed_trade |= world._prev_import_volume[index] > 0.0
            assert record["gdp_nominal_imports"] == pytest.approx(
                world._prev_import_value[index]
            )
            assert record["gdp_nominal_exports_transaction_value"] == pytest.approx(
                world._last_export_value[index]
            )
            assert record["gdp_nominal_export_policy_basic_price_bridge"] == pytest.approx(
                world._export_subsidy_cost[index]
            )
            assert record["gdp_nominal_exports"] == pytest.approx(
                world._last_export_value[index]
                + world._export_subsidy_cost[index]
            )
            assert record["gdp_external_import_volume"] == pytest.approx(
                econ._fx_import_volume_external
            )
            assert record["gdp_external_export_volume"] == pytest.approx(
                econ._fx_export_volume_external
            )
            assert record["gdp_external_export_shipped_volume"] == pytest.approx(
                world._last_export_volume[index]
            )
            assert record["gdp_external_export_delivered_volume"] == pytest.approx(
                world._last_export_delivered_volume[index]
            )
            assert record["gdp_external_iceberg_loss_volume"] == pytest.approx(
                world._iceberg_loss_volume[index]
            )
            assert world._last_export_volume[index] == pytest.approx(
                world._last_export_delivered_volume[index]
                + world._iceberg_loss_volume[index]
            )
            assert record["gdp_nominal_net_exports"] == pytest.approx(
                record["gdp_nominal_exports"] - record["gdp_nominal_imports"]
            )
            assert record["gdp_real_net_exports"] == pytest.approx(
                record["gdp_real_exports"] - record["gdp_real_imports"]
            )
            assert record["gdp_expenditure_includes_observed_net_exports"] == 1.0

    assert observed_trade


def test_disabling_trade_clears_transaction_policy_and_iceberg_flow_journals():
    cfg = Config.v124(
        n_firms_c=8,
        n_firms_k=4,
        n_households=30,
        n_ticks=2,
        seed=0,
        national_accounts_metrics=True,
    )
    world = World(
        [cfg, cfg],
        base_seed=43,
        trade=True,
        tariff=[0.10, 0.10],
        export_subsidy=[0.20, 0.20],
        fx_friction=0.25,
    )
    world.step()
    assert any(value > 0.0 for value in world._last_export_value)
    assert any(value > 0.0 for value in world._export_subsidy_cost)

    world.trade = False
    records = world.step()

    for values in (
        world._prev_import_value,
        world._prev_import_volume,
        world._last_export_value,
        world._last_export_delivered_volume,
        world._last_export_volume,
        world._iceberg_loss_volume,
        world._export_contract_basic_value,
        world._export_barrier_lot_basic_value,
        world._export_account_lot_basic_value,
        world._export_barrier_lot_contract_gap,
        world._export_lot_repricing_gap,
        world._export_inventory_withdrawal_price_adjustment,
        world._tariff_rev,
        world._export_subsidy_cost,
    ):
        assert values == pytest.approx([0.0, 0.0])
    for econ, record in zip(world.economies, records):
        assert econ._fx_import_transaction_value_external == 0.0
        assert econ._fx_import_value_external == 0.0
        assert econ._fx_import_delivered_volume_external == 0.0
        assert econ._fx_import_volume_external == 0.0
        assert econ._fx_export_transaction_value_external == 0.0
        assert econ._fx_export_value_external == 0.0
        assert econ._fx_export_delivered_volume_external == 0.0
        assert econ._fx_export_shipped_volume_external == 0.0
        assert econ._fx_export_volume_external == 0.0
        assert econ._fx_iceberg_loss_volume_external == 0.0
        assert econ._fx_export_contract_basic_value_external == 0.0
        assert econ._fx_export_barrier_lot_basic_value_external == 0.0
        assert econ._fx_export_account_lot_basic_value_external == 0.0
        assert econ._fx_export_barrier_lot_contract_gap_external == 0.0
        assert econ._fx_export_lot_repricing_gap_external == 0.0
        assert econ._fx_export_inventory_withdrawal_price_adjustment_external == 0.0
        assert econ._tariff_revenue_external == 0.0
        assert econ._export_subsidy_cost_external == 0.0
        assert record["gdp_nominal_exports_transaction_value"] == 0.0
        assert record["gdp_nominal_export_policy_basic_price_bridge"] == 0.0
        assert record["gdp_nominal_exports"] == 0.0
        assert record["gdp_nominal_imports"] == 0.0


def test_export_inventory_withdrawal_uses_contract_price_after_barrier_repricing():
    cfg = Config.v124(
        n_firms_c=2,
        n_firms_k=1,
        n_households=10,
        n_ticks=1,
        seed=0,
        national_accounts_metrics=True,
    )
    world = World(
        [cfg, cfg],
        base_seed=47,
        trade=True,
        fx_friction=0.25,
        fx_trade_cap=1.0,
        tariff=[0.10, 0.0],
        export_subsidy=[0.0, 0.20],
    )
    importer, source = world.economies
    for econ in world.economies:
        econ._national_accounts.open_tick(econ)
        for household in econ.households:
            household.spent = 0.0
        for firm in econ.firms:
            firm.produced = firm.sales = firm.revenue = firm.wagebill = 0.0
            firm.inventory = 0.0
            if hasattr(firm, "energy_cost_used"):
                firm.energy_cost_used = 0.0
            if hasattr(firm, "energy_used"):
                firm.energy_used = 0.0
    first, second = source.c_firms
    first.price, first.inventory = 5.0, 1.0
    second.price, second.inventory = 6.0, 1.0
    source._price_level = 4.0
    importer._price_level = 20.0

    prepare_trade(world)

    offer = importer._fx_import_offer
    assert offer is not None
    # The old inventory was contracted at 5 and 6. Current production is posted
    # later at 7 and 8 and replenishes the two units withdrawn for export.
    first.price, second.price = 7.0, 8.0
    first.produced = second.produced = 1.0
    first.inventory += 1.0
    second.inventory += 1.0
    offer.sold = offer.stock
    gross = offer.sold * offer.price
    importer.ledger.transfer(importer.households[0].id, DEALER_ID, gross)

    settle_trade(world)
    record = preview(source)

    assert source._fx_export_contract_basic_value_external == pytest.approx(11.0)
    assert source._fx_export_barrier_lot_basic_value_external == pytest.approx(11.0)
    assert source._fx_export_account_lot_basic_value_external == pytest.approx(15.0)
    assert source._fx_export_barrier_lot_contract_gap_external == pytest.approx(0.0)
    assert source._fx_export_lot_repricing_gap_external == pytest.approx(4.0)
    assert source._fx_export_inventory_withdrawal_price_adjustment_external == pytest.approx(
        4.0
    )
    assert record["gdp_nominal_exports_transaction_value"] == pytest.approx(8.8)
    assert record["gdp_nominal_export_policy_basic_price_bridge"] == pytest.approx(2.2)
    assert record["gdp_nominal_exports"] == pytest.approx(11.0)
    assert record[
        "gdp_nominal_inventory_change_c_before_export_withdrawal_adjustment"
    ] == pytest.approx(0.0)
    assert record[
        "gdp_nominal_export_inventory_withdrawal_transaction_price_adjustment"
    ] == pytest.approx(4.0)
    assert record["gdp_nominal_inventory_change_c"] == pytest.approx(4.0)
    assert record["gdp_nominal_production"] == pytest.approx(15.0)
    assert record["gdp_nominal_expenditure_observed"] == pytest.approx(15.0)
    assert record["gdp_nominal_expenditure_reconciliation_residual"] == pytest.approx(0.0)
    assert record["gdp_nominal_income_observed"] == pytest.approx(11.0)
    assert record["gdp_nominal_income_accrual_bridge"] == pytest.approx(4.0)
    assert record["gdp_nominal_income_accrued_observed"] == pytest.approx(15.0)
    assert record["gdp_nominal_income_unexplained_residual"] == pytest.approx(0.0)
    assert record["gdp_real_expenditure_reconciliation_residual"] == pytest.approx(0.0)
