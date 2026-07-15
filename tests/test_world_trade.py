"""v20.2 — the first real L2: dealer-routed cross-border trade (PLAN_v20 §4, §11 v20.2).

Gates: (1) trade off ≡ closed (the goods-phase hook is a no-op); (2) the identical-economy
quiet baseline holds — symmetric economies trade but net to zero, rates flat; (3) all
economies conserve with trade on; (4) the BoP identity holds by construction.
"""

from __future__ import annotations

import hashlib

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.world import World
from macro_sim.world.fx import DEALER_ID
from macro_sim.world.trade import prepare_trade, settle_trade


def _digest(records) -> str:
    h = hashlib.sha256()
    for rec in records:
        for k in sorted(rec.keys()):
            h.update(k.encode())
            h.update(repr(rec[k]).encode())
    return h.hexdigest()


def _cfg(seed: int = 0) -> Config:
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=200, seed=seed)


def test_trade_off_is_closed_economy_identical():
    """trade=False ⇒ the goods-phase foreign-trade hook is never fed ⇒ bit-identical to a
    bare Economy (the off ≡ v20.1/closed gate)."""
    bare = Economy(_cfg())
    bare.run()
    world = World([_cfg(), _cfg()], base_seed=None, trade=False)  # trade off
    world.run()
    # economy 0 (seed 0, same as bare) must match byte-for-byte
    assert _digest(world.economies[0].records) == _digest(bare.records)


def test_clone_quiet_baseline_balanced():
    """Identical economies (clones): trade FLOWS but nets to zero — dealer inventory ~0,
    rates flat. The symmetric quiet baseline (§8)."""
    world = World([_cfg(), _cfg()], trade=True, fx_lambda=0.1)   # clones (same seed)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    last = world.world_records[-1]
    assert all(abs(x) < 1.0 for x in last["dealer_inventory"])   # ~0 (balanced)
    assert all(abs(e - 1.0) < 1e-6 for e in last["e"])           # rates flat
    gross = sum(sum(r["import_value"]) for r in world.world_records)
    assert gross > 0.0                                           # trade actually happened


def test_diverse_economies_trade_bounded_and_conserving():
    """Different draws: trade flows, the imbalance stays small and bounded (export-financed,
    groping-cleared), and every economy conserves."""
    M = None
    world = World([_cfg(), _cfg()], base_seed=9, trade=True, fx_lambda=0.1)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
        M = econ.ledger.total_money
    inv0 = [r["dealer_inventory"][0] for r in world.world_records]
    assert max(abs(x) for x in inv0) < 0.05 * M                  # imbalance < 5% of money
    assert sum(r["import_value"][0] for r in world.world_records) > 0.0


def test_bop_identity_holds():
    """The reported BoP in the numéraire equals the dealer's net worth (Σ inventory_i / e_i)
    — the multilateral balance-of-payments identity, true by construction (gate #2)."""
    world = World([_cfg(), _cfg()], base_seed=3, trade=True)
    world.run()
    rec = world.world_records[-1]
    inv, e = rec["dealer_inventory"], rec["e"]
    recomputed = sum(inv[i] / e[i] for i in range(len(inv)))
    assert abs(rec["bop_numeraire"] - recomputed) < 1e-6


def test_exports_enter_same_tick_pnl_metrics_and_sales_lag():
    """Dealer-side exports must settle before domestic P&L and record commit."""
    configs = [
        Config.v124(
            n_firms_c=8, n_firms_k=4, n_households=30, n_ticks=8,
            seed=0, a=productivity,
        )
        for productivity in (0.7, 1.3)
    ]
    world = World(configs, base_seed=9, trade=True)

    observed_export = False
    for _ in range(8):
        records = world.step()
        for i, export_value in enumerate(world._last_export_value):
            if export_value <= 1.0e-9:
                continue
            observed_export = True
            econ = world.economies[i]
            rec = records[i]
            assert rec["consumption_spending"] == pytest.approx(
                sum(f.revenue for f in econ.c_firms)
            )
            assert rec["profit_total"] == pytest.approx(sum(f.profit for f in econ.firms))
            for firm in econ.firms:
                assert firm.profit == pytest.approx(
                    firm.revenue - firm.wagebill - firm.energy_cost_used
                )
                assert firm.sales_prev == pytest.approx(firm.sales)

    assert observed_export


def _realize_reserved_imports(world, quantity=0.25):
    gross = [0.0] * world.n
    volume = [0.0] * world.n
    for i, econ in enumerate(world.economies):
        offer = econ._fx_import_offer
        assert offer is not None
        volume[i] = min(float(quantity), float(offer.stock))
        offer.sold = volume[i]
        gross[i] = volume[i] * offer.price
        econ.ledger.transfer(econ.households[0].id, DEALER_ID, gross[i])
    return gross, volume


def test_asymmetric_tariffs_settle_at_barrier_rates_and_write_exact_trade_journals():
    cfg = Config.v124(
        n_firms_c=8, n_firms_k=4, n_households=20, n_ticks=2, seed=0,
    )
    rates = [0.10, -0.20]
    export_rates = [0.20, -0.10]
    world = World(
        [cfg, cfg], base_seed=101, trade=True,
        tariff=rates, export_subsidy=export_rates,
    )
    inv0 = world.dealer.inventory()
    e0 = world.rates.e
    firm_inventory_before = [
        sum(firm.inventory for firm in econ.c_firms) for econ in world.economies
    ]
    firm_sales_before = [
        sum(firm.sales for firm in econ.c_firms) for econ in world.economies
    ]
    firm_revenue_before = [
        sum(firm.revenue for firm in econ.c_firms) for econ in world.economies
    ]

    prepare_trade(world)
    quoted = [econ._fx_import_offer.price for econ in world.economies]
    for i, econ in enumerate(world.economies):
        source = world._import_source[i]
        untaxed = (
            world.economies[source]._price_level
            * world.rates.bilateral(i, source)
            * (1.0 + world.fx_friction)
        )
        assert quoted[i] == pytest.approx(
            untaxed * (1.0 - export_rates[source]) * (1.0 + rates[i])
        )
        assert econ._fx_tariff_rate == pytest.approx(rates[i])

    gross, import_volume = _realize_reserved_imports(world)
    fiscal_before = [econ.ledger.balance(econ._fiscal) for econ in world.economies]
    expected_import = [gross[i] / (1.0 + rates[i]) for i in range(world.n)]
    expected_tax = [gross[i] - expected_import[i] for i in range(world.n)]
    expected_export = [0.0] * world.n
    expected_export_delivered = [0.0] * world.n
    expected_export_shipped = [0.0] * world.n
    expected_iceberg_loss = [0.0] * world.n
    iceberg_multiplier = 1.0 + world.fx_friction
    for importer, source in enumerate(world._import_source):
        expected_export[source] += (
            expected_import[importer] * world.rates.bilateral(source, importer)
        )
        delivered = import_volume[importer]
        shipped = delivered * iceberg_multiplier
        expected_export_delivered[source] += delivered
        expected_export_shipped[source] += shipped
        expected_iceberg_loss[source] += shipped - delivered
    expected_export_policy_cost = [
        expected_export[i] * export_rates[i] / (1.0 - export_rates[i])
        for i in range(world.n)
    ]

    # Policy mutations after quotation must not change this tick's tax/subsidy split.
    world.tariff = [0.90, 0.90]
    world.export_subsidy = [0.50, 0.50]
    world.fx_friction = 0.90
    settle_trade(world)

    assert world._prev_import_value == pytest.approx(expected_import)
    assert world._prev_import_volume == pytest.approx(import_volume)
    assert world._last_export_value == pytest.approx(expected_export)
    assert world._last_export_delivered_volume == pytest.approx(
        expected_export_delivered
    )
    assert world._last_export_volume == pytest.approx(expected_export_shipped)
    assert world._iceberg_loss_volume == pytest.approx(expected_iceberg_loss)
    assert world._tariff_rev == pytest.approx(expected_tax)
    assert world._export_subsidy_cost == pytest.approx(expected_export_policy_cost)
    for i, econ in enumerate(world.economies):
        assert econ.ledger.balance(econ._fiscal) - fiscal_before[i] == pytest.approx(
            expected_tax[i] - expected_export_policy_cost[i]
        )
        assert econ._fx_import_value_external == pytest.approx(expected_import[i])
        assert econ._fx_import_volume_external == pytest.approx(import_volume[i])
        assert econ._fx_export_value_external == pytest.approx(expected_export[i])
        assert econ._fx_export_delivered_volume_external == pytest.approx(
            expected_export_delivered[i]
        )
        assert econ._fx_export_volume_external == pytest.approx(
            expected_export_shipped[i]
        )
        assert econ._fx_iceberg_loss_volume_external == pytest.approx(
            expected_iceberg_loss[i]
        )
        assert sum(firm.inventory for firm in econ.c_firms) == pytest.approx(
            firm_inventory_before[i] - expected_export_shipped[i]
        )
        assert sum(firm.sales for firm in econ.c_firms) == pytest.approx(
            firm_sales_before[i] + expected_export_shipped[i]
        )
        assert sum(firm.revenue for firm in econ.c_firms) == pytest.approx(
            firm_revenue_before[i]
            + expected_export[i]
            + expected_export_policy_cost[i]
        )
        econ.ledger.assert_conserved()
    world.dealer.assert_flow_is_passthrough(inv0, e0)

    # A following zero-sale tick overwrites, rather than carries or accumulates, journals.
    prepare_trade(world)
    settle_trade(world)
    for econ in world.economies:
        assert econ._fx_import_value_external == 0.0
        assert econ._fx_import_volume_external == 0.0
        assert econ._fx_export_value_external == 0.0
        assert econ._fx_export_delivered_volume_external == 0.0
        assert econ._fx_export_volume_external == 0.0
        assert econ._fx_iceberg_loss_volume_external == 0.0


def test_trade_policy_without_fiscal_account_is_inert_not_a_foreign_transfer():
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
    )
    neutral = World([cfg, cfg], base_seed=103, trade=True)
    policy = World(
        [cfg, cfg], base_seed=103, trade=True,
        tariff=[0.40, -0.20], export_subsidy=[0.25, -0.30],
    )

    prepare_trade(neutral)
    prepare_trade(policy)
    assert [econ._fx_import_offer.price for econ in policy.economies] == pytest.approx(
        [econ._fx_import_offer.price for econ in neutral.economies]
    )
    assert all(econ._fx_tariff_rate == 0.0 for econ in policy.economies)
    assert all(econ._fx_export_subsidy_rate == 0.0 for econ in policy.economies)

    inv0 = policy.dealer.inventory()
    e0 = policy.rates.e
    gross, volumes = _realize_reserved_imports(policy)
    expected_export = [0.0] * policy.n
    expected_export_delivered = [0.0] * policy.n
    for importer, source in enumerate(policy._import_source):
        expected_export[source] += (
            gross[importer] * policy.rates.bilateral(source, importer)
        )
        expected_export_delivered[source] += volumes[importer]
    settle_trade(policy)
    assert policy._tariff_rev == pytest.approx([0.0, 0.0])
    assert policy._prev_import_value == pytest.approx(gross)
    assert policy._last_export_value == pytest.approx(expected_export)
    for importer, source in enumerate(policy._import_source):
        assert policy.economies[importer]._fx_import_value_external == pytest.approx(
            gross[importer]
        )
    for source, econ in enumerate(policy.economies):
        delivered = expected_export_delivered[source]
        shipped = delivered * (1.0 + policy.fx_friction)
        assert econ._fx_export_delivered_volume_external == pytest.approx(delivered)
        assert econ._fx_export_volume_external == pytest.approx(shipped)
        assert econ._fx_iceberg_loss_volume_external == pytest.approx(
            shipped - delivered
        )
    policy.dealer.assert_flow_is_passthrough(inv0, e0)


@pytest.mark.parametrize("friction", [0.0, 0.25])
def test_iceberg_reservation_separates_delivered_shipped_and_returned_units(friction):
    cfg = Config.v124(
        n_firms_c=2, n_firms_k=1, n_households=10, n_ticks=1, seed=0,
    )
    world = World(
        [cfg, cfg], base_seed=107, trade=True, fx_friction=friction,
        fx_trade_cap=1.0,
    )
    importer, source = world.economies
    for econ in world.economies:
        for firm in econ.c_firms:
            firm.inventory = 0.0
            firm.sales = 0.0
            firm.revenue = 0.0
    first, second = source.c_firms
    first.price, first.inventory = 5.0, 1.0
    second.price, second.inventory = 6.0, 2.0
    source._price_level = 5.0
    importer._price_level = 15.0
    initial_inventory = first.inventory + second.inventory
    dealer_inv0 = world.dealer.inventory()
    e0 = world.rates.e

    prepare_trade(world)

    multiplier = 1.0 + friction
    offer = importer._fx_import_offer
    assert offer is not None
    assert offer.stock == pytest.approx(initial_inventory / multiplier)
    reserved_basic = 1.0 * 5.0 + 2.0 * 6.0
    assert offer.price == pytest.approx(
        reserved_basic / initial_inventory * multiplier
    )
    assert first.inventory + second.inventory == pytest.approx(0.0)
    delivered = min(1.6, offer.stock)
    gross = delivered * offer.price
    importer.ledger.transfer(importer.households[0].id, DEALER_ID, gross)
    offer.sold = delivered

    settle_trade(world)

    shipped = delivered * multiplier
    loss = shipped - delivered
    fill_fraction = shipped / initial_inventory
    assert first.sales == pytest.approx(1.0 * fill_fraction)
    assert second.sales == pytest.approx(2.0 * fill_fraction)
    assert first.revenue == pytest.approx(first.sales * 5.0)
    assert second.revenue == pytest.approx(second.sales * 6.0)
    used_barrier_value = fill_fraction * reserved_basic
    assert first.inventory + second.inventory == pytest.approx(
        initial_inventory - shipped
    )
    assert first.sales + second.sales == pytest.approx(shipped)
    assert first.revenue + second.revenue == pytest.approx(gross)
    assert world._prev_import_volume == pytest.approx([delivered, 0.0])
    assert world._last_export_delivered_volume == pytest.approx([0.0, delivered])
    assert world._last_export_volume == pytest.approx([0.0, shipped])
    assert world._iceberg_loss_volume == pytest.approx([0.0, loss])
    assert world._export_contract_basic_value == pytest.approx(
        [0.0, used_barrier_value]
    )
    assert world._export_barrier_lot_basic_value == pytest.approx(
        [0.0, used_barrier_value]
    )
    assert world._export_account_lot_basic_value == pytest.approx(
        [0.0, used_barrier_value]
    )
    assert world._export_barrier_lot_contract_gap == pytest.approx([0.0, 0.0])
    assert world._export_lot_repricing_gap == pytest.approx([0.0, 0.0])
    assert world._export_inventory_withdrawal_price_adjustment == pytest.approx(
        [0.0, 0.0]
    )
    assert source._fx_export_delivered_volume_external == pytest.approx(delivered)
    assert source._fx_export_volume_external == pytest.approx(shipped)
    assert source._fx_iceberg_loss_volume_external == pytest.approx(loss)
    assert shipped == pytest.approx(delivered + loss)
    world.dealer.assert_flow_is_passthrough(dealer_inv0, e0)


@pytest.mark.parametrize(
    ("tariff_rate", "export_policy_rate"),
    [(0.10, 0.20), (-0.10, -0.20)],
)
def test_lot_contract_partial_fill_preserves_signed_policy_cash_and_basic_receipts(
    tariff_rate,
    export_policy_rate,
):
    cfg = Config.v124(
        n_firms_c=2, n_firms_k=1, n_households=10, n_ticks=1, seed=0,
    )
    world = World(
        [cfg, cfg],
        base_seed=109,
        trade=True,
        fx_friction=0.25,
        fx_trade_cap=1.0,
        tariff=[tariff_rate, 0.0],
        export_subsidy=[0.0, export_policy_rate],
    )
    importer, source = world.economies
    for econ in world.economies:
        for firm in econ.c_firms:
            firm.inventory = 0.0
            firm.sales = 0.0
            firm.revenue = 0.0
    first, second = source.c_firms
    first.price, first.inventory = 5.0, 1.0
    second.price, second.inventory = 6.0, 1.0
    # This stale country quote selects the source only; it must set neither the
    # cold-start budget nor the binding contract price.
    source._price_level = 0.01
    importer._price_level = 20.0
    dealer_inv0 = world.dealer.inventory()
    e0 = world.rates.e

    prepare_trade(world)

    offer = importer._fx_import_offer
    assert offer is not None
    multiplier = 1.25
    reserved_basic = 11.0
    assert offer.stock == pytest.approx(2.0 / multiplier)
    assert offer.price == pytest.approx(
        (reserved_basic / 2.0)
        * multiplier
        * (1.0 - export_policy_rate)
        * (1.0 + tariff_rate)
    )
    delivered = 0.5 * offer.stock
    shipped = delivered * multiplier
    used_basic = 0.5 * reserved_basic
    gross = delivered * offer.price
    importer_fiscal0 = importer.ledger.balance(importer._fiscal)
    source_fiscal0 = source.ledger.balance(source._fiscal)
    importer.ledger.transfer(importer.households[0].id, DEALER_ID, gross)
    offer.sold = delivered

    settle_trade(world)

    transaction_value = used_basic * (1.0 - export_policy_rate)
    tariff_flow = gross - transaction_value
    policy_flow = used_basic * export_policy_rate
    assert first.sales == pytest.approx(0.5)
    assert second.sales == pytest.approx(0.5)
    assert first.revenue == pytest.approx(2.5)
    assert second.revenue == pytest.approx(3.0)
    assert world._prev_import_value == pytest.approx([transaction_value, 0.0])
    assert world._last_export_value == pytest.approx([0.0, transaction_value])
    assert world._export_subsidy_cost == pytest.approx([0.0, policy_flow])
    assert world._export_contract_basic_value == pytest.approx([0.0, used_basic])
    assert world._export_barrier_lot_basic_value == pytest.approx([0.0, used_basic])
    assert world._export_barrier_lot_contract_gap == pytest.approx([0.0, 0.0])
    assert importer.ledger.balance(importer._fiscal) - importer_fiscal0 == pytest.approx(
        tariff_flow
    )
    assert source.ledger.balance(source._fiscal) - source_fiscal0 == pytest.approx(
        -policy_flow
    )
    assert shipped == pytest.approx(1.0)
    assert world._last_export_volume == pytest.approx([0.0, shipped])
    world.dealer.assert_flow_is_passthrough(dealer_inv0, e0)


@pytest.mark.parametrize(
    ("tariff", "export_subsidy", "match"),
    [
        ([-1.0, 0.0], None, "1 \\+ rate > 0"),
        ([0.0], None, "one value per economy"),
        (0.0, [0.0, 1.0], "1 - rate > 0"),
        (0.0, [0.0], "one value per economy"),
    ],
)
def test_invalid_trade_policy_fails_before_reserving_inventory(
    tariff, export_subsidy, match,
):
    cfg = Config.v124(
        n_firms_c=4, n_firms_k=2, n_households=10, n_ticks=1,
    )
    world = World(
        [cfg, cfg], trade=True, tariff=tariff, export_subsidy=export_subsidy,
    )
    inventories = [[firm.inventory for firm in econ.c_firms] for econ in world.economies]

    with pytest.raises(ValueError, match=match):
        prepare_trade(world)

    assert world._export_reservations == [None, None]
    assert [
        [firm.inventory for firm in econ.c_firms] for econ in world.economies
    ] == inventories
