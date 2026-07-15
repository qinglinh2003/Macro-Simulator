"""Exact tests for the opt-in v23 national-accounts observation layer."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict

import pytest

from macro_sim.config import Config
from macro_sim.diagnostics.registry import (
    DEFAULT_REGISTRY,
    Aggregation,
    Annualization,
    Frequency,
    TemporalType,
    TrustStatus,
)
from macro_sim.domain.agents import Firm
from macro_sim.economy import Economy
from macro_sim.markets.matching import Trade
from macro_sim.reporting.metrics import commit_tick_metrics, compute_tick_metrics
from macro_sim.reporting.national_accounts import commit, preview


def _trade(buyer: str, seller: str, quantity: float, price: float) -> Trade:
    return Trade(
        buyer=buyer,
        seller=seller,
        qty=quantity,
        price=price,
        value=quantity * price,
    )


def _small_v2(**overrides) -> Economy:
    return Economy(Config.v2(
        n_households=4,
        n_firms_c=2,
        n_firms_k=1,
        seed=912,
        national_accounts_metrics=True,
        **overrides,
    ))


def _zero_period(econ: Economy) -> None:
    for household in econ.households:
        household.spent = 0.0
        household.energy_spent = 0.0
        household.energy_units = 0.0
    for firm in econ.firms:
        firm.produced = 0.0
        firm.sales = 0.0
        firm.revenue = 0.0
        firm.wagebill = 0.0
        firm.profit = 0.0
        firm.energy_used = 0.0
        firm.energy_cost_used = 0.0
        firm.energy_bought = 0.0
    econ._gov_consumption = 0.0
    econ._public_investment = 0.0
    econ._benefit_paid = 0.0
    econ._energy_hh_spend = 0.0
    econ._energy_subsidy_paid = 0.0
    econ._energy_cap_comp = 0.0
    econ._tax_consumption = 0.0
    econ._tax_energy = 0.0
    econ._tariff_revenue_external = 0.0
    econ._export_subsidy_cost_external = 0.0
    econ._family_transfer_total = 0.0
    econ._jg_spending = 0.0
    econ._jg_employment = 0.0
    econ._jg_capital_units = 0.0


def test_flag_is_explicit_default_off_and_does_not_replace_legacy_sensors():
    assert Config().national_accounts_metrics is False
    assert Config().cb_uses_fixed_basket_cpi is False
    assert Config().fiscal_uses_national_accounts_gdp is False
    assert Config().cpi_rebase_interval_days == 365
    off = Economy(Config.v2(
        n_households=20, n_firms_c=4, n_firms_k=2, n_ticks=5, seed=44,
    ))
    observed = Economy(Config.v2(
        n_households=20, n_firms_c=4, n_firms_k=2, n_ticks=5, seed=44,
        national_accounts_metrics=True,
    ))
    assert not hasattr(off, "_national_accounts")

    for _ in range(5):
        legacy = off.step()
        augmented = observed.step()
        for key, value in legacy.items():
            assert augmented[key] == value
        assert "nominal_gdp" not in legacy
        assert augmented["national_accounts_enabled"] == 1.0

    assert off.ledger.snapshot() == observed.ledger.snapshot()
    assert off.rng.getstate() == observed.rng.getstate()
    # Behavioral lag consumers remain on the separately named legacy series.
    assert observed._prev_real_output == observed.records[-1]["real_output"]
    assert observed._price_level == observed.records[-1]["price_index"]


def test_policy_and_fiscal_consumers_are_separately_gated_to_canonical_accounts():
    econ = Economy(Config.v10(
        n_households=4,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=2,
        seed=913,
        national_accounts_metrics=True,
        cb_uses_fixed_basket_cpi=True,
        fiscal_uses_national_accounts_gdp=True,
        cb_log_inflation=True,
    ))
    econ._national_accounts.open_tick(econ)
    record = {
        "price_index": 2.0,
        "inflation": 0.50,
        "headline_inflation": 0.40,
        "cpi_fixed_basket": 1.01,
        "cpi_fixed_basket_inflation": 0.01,
        "nominal_output": 10.0,
        "nominal_gdp": 30.0,
        "unemployment_rate": 0.1,
        "tax_total": 1.0,
        "benefit_paid": 0.5,
        "real_output": 5.0,
        "avg_wage": 1.0,
    }

    commit_tick_metrics(econ, record)

    # The legacy lag remains available to historical consumers, while the fiscal
    # rail receives economy-wide GDP and the Taylor rail receives the fixed basket.
    assert econ._prev_nominal_output == pytest.approx(10.0)
    assert econ._prev_fiscal_output == pytest.approx(30.0)
    assert econ._prev_inflation == pytest.approx(__import__("math").log1p(0.01))
    assert econ._price_level == pytest.approx(2.0)


def test_policy_account_flags_reject_missing_measurement_or_institution():
    with pytest.raises(AssertionError, match="CPI policy input requires national-accounts"):
        Config.v10(cb_uses_fixed_basket_cpi=True)
    with pytest.raises(AssertionError, match="fiscal input requires national-accounts"):
        Config.v9(fiscal_uses_national_accounts_gdp=True)
    with pytest.raises(AssertionError, match="requires the central bank"):
        Config.v9(national_accounts_metrics=True, cb_uses_fixed_basket_cpi=True)
    with pytest.raises(AssertionError, match="requires government"):
        Config.v3(
            national_accounts_metrics=True,
            fiscal_uses_national_accounts_gdp=True,
        )
    with pytest.raises(AssertionError, match="positive integer"):
        Config(cpi_rebase_interval_days=0)
    with pytest.raises(AssertionError, match="positive integer"):
        Config(cpi_rebase_interval_days=1.5)


def test_fixed_basket_cpi_ignores_composition_but_unit_value_does_not():
    econ = _small_v2()
    tracker = econ._national_accounts
    h = econ.households[0]
    cheap, dear = econ.c_firms
    cheap.price, dear.price = 1.0, 2.0

    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(h.id, cheap.id, 9.0, 1.0),
        _trade(h.id, dear.id, 1.0, 2.0),
    ])
    base = preview(econ)
    assert base["consumption_unit_value"] == pytest.approx(1.1)
    assert base["cpi_fixed_basket"] == pytest.approx(1.0)
    commit(econ, base)

    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(h.id, cheap.id, 1.0, 1.0),
        _trade(h.id, dear.id, 9.0, 2.0),
    ])
    recomposed = preview(econ)
    assert recomposed["consumption_unit_value"] == pytest.approx(1.9)
    assert recomposed["cpi_fixed_basket"] == pytest.approx(1.0)
    commit(econ, recomposed)

    cheap.price, dear.price = 2.0, 4.0
    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(h.id, cheap.id, 1.0, 2.0),
        _trade(h.id, dear.id, 9.0, 4.0),
    ])
    inflation = preview(econ)
    assert inflation["cpi_fixed_basket"] == pytest.approx(2.0)
    assert inflation["cpi_fixed_basket_inflation"] == pytest.approx(1.0)


def test_cpi_zero_sales_exit_missing_price_and_entry_rules_are_explicit():
    econ = _small_v2()
    tracker = econ._national_accounts
    h = econ.households[0]
    first, exiting = econ.c_firms
    first.price, exiting.price = 1.0, 2.0

    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(h.id, first.id, 1.0, 1.0),
        _trade(h.id, exiting.id, 1.0, 2.0),
    ])
    commit(econ, preview(econ))

    # No transactions: live products use their posted prices, not a new unit value.
    first.price, exiting.price = 2.0, 4.0
    tracker.open_tick(econ)
    zero_sales = preview(econ)
    assert zero_sales["consumption_unit_value_observed"] == 0.0
    assert zero_sales["consumption_unit_value"] == 0.0
    assert zero_sales["cpi_fixed_basket"] == pytest.approx(2.0)
    commit(econ, zero_sales)

    econ.c_firms.remove(exiting)
    econ.firms.remove(exiting)
    econ.investing_firms.remove(exiting)
    entrant = Firm.create_c_firm(999, econ.cfg)
    entrant.price = 100.0
    econ.c_firms.append(entrant)
    econ.firms.append(entrant)
    econ.investing_firms.append(entrant)
    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [_trade(h.id, entrant.id, 10.0, 100.0)])
    changed_set = preview(econ)

    # Exited base item holds 4.0; the entrant's first price receives zero base weight.
    assert changed_set["cpi_fixed_basket"] == pytest.approx(2.0)
    assert changed_set["cpi_fixed_basket_entry_items_excluded"] == 1.0


def test_cpi_periodic_rebase_is_chain_linked_and_refreshes_product_weights():
    econ = _small_v2(cpi_rebase_interval_days=2)
    tracker = econ._national_accounts
    household = econ.households[0]
    continuing, exiting = econ.c_firms
    continuing.price, exiting.price = 1.0, 2.0

    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(household.id, continuing.id, 1.0, 1.0),
        _trade(household.id, exiting.id, 1.0, 2.0),
    ])
    first = preview(econ)
    commit(econ, first)

    assert tracker.cpi_rebase_count == 0
    assert tracker.cpi_observations_since_rebase == 1
    assert preview(econ)["cpi_fixed_basket_rebase_due_on_commit"] == 1.0

    # Replace one base-basket product with a consumed entrant during the second
    # observation.  Before commit, the entrant is deliberately still excluded.
    econ.c_firms.remove(exiting)
    econ.firms.remove(exiting)
    econ.investing_firms.remove(exiting)
    entrant = Firm.create_c_firm(1001, econ.cfg)
    entrant.price = 100.0
    econ.c_firms.append(entrant)
    econ.firms.append(entrant)
    econ.investing_firms.append(entrant)
    continuing.price = 2.0

    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(household.id, continuing.id, 1.0, 2.0),
        _trade(household.id, entrant.id, 10.0, 100.0),
    ])
    boundary = preview(econ)
    assert boundary["cpi_fixed_basket_entry_items_excluded"] == 1.0
    commit(econ, boundary)

    # Recomputing at identical boundary prices under the replacement basket must
    # reproduce the old basket's accepted level exactly: no rebase-day inflation.
    linked = preview(econ)
    assert linked["cpi_fixed_basket"] == pytest.approx(
        boundary["cpi_fixed_basket"]
    )
    assert linked["cpi_fixed_basket_inflation"] == pytest.approx(0.0)
    assert linked["cpi_fixed_basket_rebase_count"] == 1.0
    assert linked["cpi_fixed_basket_observations_since_rebase"] == 0.0
    assert linked["cpi_fixed_basket_items"] == 2.0
    assert _goods_key_for_test(exiting.id) not in tracker.cpi_base_quantities
    assert _goods_key_for_test(entrant.id) in tracker.cpi_base_quantities

    # The entrant now carries weight, so its next price change moves the chained
    # index instead of remaining invisible forever.
    entrant.price = 200.0
    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(household.id, continuing.id, 1.0, 2.0),
        _trade(household.id, entrant.id, 10.0, 200.0),
    ])
    moved = preview(econ)
    expected_relative = (2.0 * 2.0 + 10.0 * 200.0) / (
        2.0 * 2.0 + 10.0 * 100.0
    )
    assert moved["cpi_fixed_basket"] == pytest.approx(
        boundary["cpi_fixed_basket"] * expected_relative
    )


def _goods_key_for_test(seller: str) -> str:
    return f"goods:{seller}"


def test_cpi_rebase_keeps_imports_consumed_during_completed_window():
    econ = _small_v2(cpi_rebase_interval_days=2)
    tracker = econ._national_accounts
    household = econ.households[0]
    domestic = econ.c_firms[0]
    domestic.price = 2.0

    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(household.id, domestic.id, 1.0, 2.0),
        _trade(household.id, "FXDEALER", 9.0, 10.0),
    ])
    first = preview(econ)
    commit(econ, first)

    # The import need not trade on the boundary day.  Consumption anywhere in
    # the completed survey window is enough to keep it in the refreshed basket.
    tracker.open_tick(econ)
    tracker.observe_goods_trades(
        econ, [_trade(household.id, domestic.id, 1.0, 2.0)]
    )
    boundary = preview(econ)
    commit(econ, boundary)

    import_key = _goods_key_for_test("FXDEALER")
    assert tracker.cpi_rebase_count == 1
    assert tracker.cpi_base_quantities[import_key] == pytest.approx(9.0)
    assert preview(econ)["cpi_fixed_basket"] == pytest.approx(
        boundary["cpi_fixed_basket"]
    )

    # The retained import weight transmits the next accepted import price.
    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(household.id, domestic.id, 1.0, 2.0),
        _trade(household.id, "FXDEALER", 9.0, 20.0),
    ])
    assert preview(econ)["cpi_fixed_basket"] > boundary["cpi_fixed_basket"]


def test_cpi_import_exit_and_reentry_follow_window_consumption():
    econ = _small_v2(cpi_rebase_interval_days=1)
    tracker = econ._national_accounts
    household = econ.households[0]
    domestic = econ.c_firms[0]
    domestic.price = 1.0
    import_key = _goods_key_for_test("FXDEALER")

    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(household.id, domestic.id, 1.0, 1.0),
        _trade(household.id, "FXDEALER", 2.0, 5.0),
    ])
    commit(econ, preview(econ))
    assert import_key in tracker.cpi_base_quantities

    # A complete survey window with domestic consumption but no imports removes
    # the external item instead of retaining a one-off purchase indefinitely.
    tracker.open_tick(econ)
    tracker.observe_goods_trades(
        econ, [_trade(household.id, domestic.id, 1.0, 1.0)]
    )
    commit(econ, preview(econ))
    assert import_key not in tracker.cpi_base_quantities

    # Re-entry is excluded before commit, then receives weight at the next
    # accepted rebase boundary without an index-level jump.
    tracker.open_tick(econ)
    tracker.observe_goods_trades(econ, [
        _trade(household.id, domestic.id, 1.0, 1.0),
        _trade(household.id, "FXDEALER", 3.0, 7.0),
    ])
    boundary = preview(econ)
    assert boundary["cpi_fixed_basket_entry_items_excluded"] >= 1.0
    assert import_key not in tracker.cpi_base_quantities
    commit(econ, boundary)
    assert import_key in tracker.cpi_base_quantities
    assert preview(econ)["cpi_fixed_basket"] == pytest.approx(
        boundary["cpi_fixed_basket"]
    )


def test_real_gdp_entrant_after_inflation_inherits_common_sector_base_price():
    econ = _small_v2()
    _zero_period(econ)
    tracker = econ._national_accounts
    incumbent = econ.c_firms[0]

    tracker.open_tick(econ)
    incumbent.price = 1.0
    incumbent.produced = incumbent.sales = 10.0
    incumbent.revenue = 10.0
    reference = preview(econ)
    commit(econ, reference)

    assert reference["real_gdp"] == pytest.approx(10.0)
    assert tracker.sector_output_base_prices["c"] == pytest.approx(1.0)

    _zero_period(econ)
    incumbent.price = 2.0
    incumbent.produced = incumbent.sales = 10.0
    incumbent.revenue = 20.0
    entrant = Firm.create_c_firm(1002, econ.cfg)
    entrant.price = 2.0
    entrant.produced = entrant.sales = 5.0
    entrant.revenue = 10.0
    econ.c_firms.append(entrant)
    econ.firms.append(entrant)
    econ.investing_firms.append(entrant)
    tracker.open_tick(econ)

    observed = preview(econ)

    # Physical output grew from 10 to 15.  The entrant does not receive its
    # inflation-doubled birth price as a separate real-GDP weight.
    assert observed["nominal_gdp"] == pytest.approx(30.0)
    assert observed["real_gdp"] == pytest.approx(15.0)
    assert observed["real_gdp"] / reference["real_gdp"] == pytest.approx(1.5)
    assert observed["gdp_deflator"] == pytest.approx(2.0)
    assert observed["gdp_real_uses_common_sector_base_prices"] == 1.0


def test_real_gdp_is_continuous_when_inflated_entrant_replaces_exiting_output():
    econ = _small_v2()
    _zero_period(econ)
    tracker = econ._national_accounts
    continuing, exiting = econ.c_firms

    tracker.open_tick(econ)
    continuing.price = 1.0
    continuing.produced = continuing.sales = 4.0
    continuing.revenue = 4.0
    exiting.price = 3.0
    exiting.produced = exiting.sales = 6.0
    exiting.revenue = 18.0
    reference = preview(econ)
    commit(econ, reference)

    assert reference["real_gdp"] == pytest.approx(22.0)
    assert tracker.sector_output_base_prices["c"] == pytest.approx(2.2)

    econ.c_firms.remove(exiting)
    econ.firms.remove(exiting)
    econ.investing_firms.remove(exiting)
    entrant = Firm.create_c_firm(1003, econ.cfg)
    entrant.price = 30.0
    entrant.produced = entrant.sales = 6.0
    entrant.revenue = 180.0
    econ.c_firms.append(entrant)
    econ.firms.append(entrant)
    econ.investing_firms.append(entrant)
    continuing.price = 10.0
    continuing.produced = continuing.sales = 4.0
    continuing.revenue = 40.0
    tracker.open_tick(econ)

    replacement = preview(econ)

    # The sector still produces ten homogeneous units.  A simultaneous exit and
    # entry at prices ten times the base-period quotes changes only the deflator.
    assert replacement["nominal_gdp"] == pytest.approx(220.0)
    assert replacement["real_gdp"] == pytest.approx(reference["real_gdp"])
    assert replacement["gdp_real_gross_output_c"] == pytest.approx(22.0)
    assert replacement["gdp_deflator"] == pytest.approx(10.0)


def test_nominal_and_real_components_reconcile_inventory_and_actual_investment():
    econ = _small_v2()
    _zero_period(econ)
    tracker = econ._national_accounts
    tracker.open_tick(econ)
    c_firm = econ.c_firms[0]
    k_firm = econ.k_firms[0]

    c_firm.price = 2.0
    c_firm.produced, c_firm.sales, c_firm.revenue = 10.0, 8.0, 16.0
    c_firm.wagebill = 6.0
    k_firm.price = 4.0
    k_firm.produced, k_firm.sales, k_firm.revenue = 5.0, 3.0, 12.0
    k_firm.wagebill = 4.0
    econ.households[0].spent = 16.0
    econ._benefit_paid = 100.0

    rec = preview(econ)
    assert rec["gdp_nominal_gross_output_c"] == pytest.approx(20.0)
    assert rec["gdp_nominal_gross_output_k"] == pytest.approx(20.0)
    assert rec["nominal_gdp"] == pytest.approx(40.0)
    assert rec["real_gdp"] == pytest.approx(40.0)

    # Only the three K units actually bought are fixed investment.  The two
    # unsold units are an inventory change, not five units of investment.
    assert rec["gdp_nominal_fixed_capital_formation"] == pytest.approx(12.0)
    assert rec["gdp_nominal_inventory_change_k"] == pytest.approx(8.0)
    assert rec["gdp_nominal_inventory_change_c"] == pytest.approx(4.0)
    assert rec["gdp_nominal_expenditure_observed"] == pytest.approx(40.0)
    assert rec["gdp_nominal_expenditure_reconciliation_residual"] == pytest.approx(0.0)
    assert rec["gdp_real_expenditure_reconciliation_residual"] == pytest.approx(0.0)

    # Compatibility fields retain the cash-income view.  The new observation-only
    # bridge identifies the unsold output explicitly and produces an accrued GOS
    # without changing the production GDP anchor.
    assert rec["gdp_nominal_compensation_of_employees"] == pytest.approx(10.0)
    assert rec["gdp_nominal_cash_operating_surplus"] == pytest.approx(18.0)
    assert rec["gdp_nominal_income_observed"] == pytest.approx(28.0)
    assert rec["gdp_nominal_income_reconciliation_residual"] == pytest.approx(12.0)
    assert rec["gdp_nominal_income_output_sales_accrual_c"] == pytest.approx(4.0)
    assert rec["gdp_nominal_income_output_sales_accrual_k"] == pytest.approx(8.0)
    assert rec["gdp_nominal_income_output_sales_accrual_e"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_output_sales_accrual_housing"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_output_sales_accrual_other"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_intermediate_scope_adjustment"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_accrual_bridge"] == pytest.approx(12.0)
    assert rec["gdp_nominal_accrued_gross_operating_surplus"] == pytest.approx(30.0)
    assert rec["gdp_nominal_income_accrued_observed"] == pytest.approx(40.0)
    assert rec["gdp_nominal_income_unexplained_residual"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_unexplained_residual_share"] == pytest.approx(0.0)
    assert rec["gdp_nominal_production_reconciliation_residual"] == 0.0
    assert rec["gdp_nominal_income_reconciled"] == pytest.approx(40.0)
    assert rec["gdp_nominal_expenditure_reconciled"] == pytest.approx(40.0)
    assert rec["gdp_nominal_three_approach_raw_spread"] == pytest.approx(12.0)

    # A transfer can change household cash/income but is not current production.
    assert rec["gdp_excluded_transfer_payments"] == pytest.approx(100.0)
    assert rec["nominal_gdp"] == pytest.approx(40.0)


@pytest.mark.parametrize(
    ("produced", "sold", "expected_gdp", "expected_bridge"),
    (
        (10.0, 10.0, 20.0, 0.0),
        (10.0, 6.0, 20.0, 8.0),
        (4.0, 10.0, 8.0, -12.0),
    ),
)
def test_income_accrual_bridge_covers_full_sale_inventory_build_and_liquidation(
    produced,
    sold,
    expected_gdp,
    expected_bridge,
):
    econ = _small_v2()
    _zero_period(econ)
    econ._national_accounts.open_tick(econ)
    firm = econ.c_firms[0]
    firm.price = 2.0
    firm.produced = produced
    firm.sales = sold
    firm.revenue = sold * firm.price
    firm.wagebill = 6.0
    econ.households[0].spent = firm.revenue

    rec = preview(econ)

    assert rec["nominal_gdp"] == pytest.approx(expected_gdp)
    assert rec["gdp_nominal_income_output_sales_accrual_c"] == pytest.approx(
        expected_bridge
    )
    assert rec["gdp_nominal_income_accrual_bridge"] == pytest.approx(expected_bridge)
    assert rec["gdp_nominal_income_reconciliation_residual"] == pytest.approx(
        expected_bridge
    )
    assert rec["gdp_nominal_income_accrued_observed"] == pytest.approx(expected_gdp)
    assert rec["gdp_nominal_income_unexplained_residual"] == pytest.approx(0.0)


@pytest.mark.parametrize("tariff_rate", [0.20, -0.20])
def test_import_consumption_journal_strips_signed_tariff_from_basic_price_accounts(
    tariff_rate,
):
    econ = _small_v2()
    _zero_period(econ)
    tracker = econ._national_accounts
    tracker.open_tick(econ)
    household = econ.households[0]
    econ._fx_tariff_rate = tariff_rate
    econ._tariff_revenue_external = 10.0 * tariff_rate
    econ._fx_import_transaction_value_external = 10.0
    econ._fx_import_delivered_volume_external = 2.0
    tracker.observe_goods_trades(econ, [
        _trade(household.id, "FXDEALER", 2.0, 5.0 * (1.0 + tariff_rate)),
    ])

    rec = preview(econ)

    assert tracker.household_goods["goods:FXDEALER"].value == pytest.approx(10.0)
    assert rec["gdp_nominal_household_consumption_goods"] == pytest.approx(10.0)
    assert rec["consumption_unit_value"] == pytest.approx(5.0)
    assert rec["cpi_fixed_basket_excludes_product_taxes"] == 1.0
    assert rec["gdp_nominal_import_duty_signed"] == pytest.approx(
        10.0 * tariff_rate
    )
    assert rec["gdp_nominal_net_product_taxes_observed"] == pytest.approx(
        10.0 * tariff_rate
    )
    assert rec["gdp_nominal_basic_price_corrected_observed"] == pytest.approx(0.0)
    assert rec["gdp_nominal_market_price_observed"] == pytest.approx(
        10.0 * tariff_rate
    )


def test_economy_external_trade_journals_enter_nominal_and_real_expenditure_gdp():
    econ = _small_v2()
    _zero_period(econ)
    tracker = econ._national_accounts
    tracker.open_tick(econ)
    producer = econ.c_firms[0]
    household = econ.households[0]

    # Ten domestic units at a current price of three: seven are consumed at
    # home and three exported.  Four imported units enter household C at seven.
    producer.price = 3.0
    producer.produced = producer.sales = 10.0
    producer.revenue = 30.0
    tracker.observe_goods_trades(econ, [
        _trade(household.id, producer.id, 7.0, 3.0),
        _trade(household.id, "FXDEALER", 4.0, 7.0),
    ])
    tracker.sector_output_base_prices["c"] = 2.0
    tracker.final_use_base_prices[_goods_key_for_test("FXDEALER")] = 5.0
    econ._fx_export_value_external = 9.0
    econ._fx_export_volume_external = 3.0
    econ._fx_import_value_external = 28.0
    econ._fx_import_volume_external = 4.0

    rec = preview(econ)

    assert rec["gdp_nominal_exports"] == pytest.approx(9.0)
    assert rec["gdp_nominal_imports"] == pytest.approx(28.0)
    assert rec["gdp_nominal_net_exports"] == pytest.approx(-19.0)
    assert rec["gdp_real_exports"] == pytest.approx(6.0)
    assert rec["gdp_real_imports"] == pytest.approx(20.0)
    assert rec["gdp_real_net_exports"] == pytest.approx(-14.0)
    assert rec["gdp_real_export_base_price_c"] == pytest.approx(2.0)
    assert rec["gdp_real_import_base_price_fxdealer"] == pytest.approx(5.0)

    # C includes imported final consumption, then M removes it.  X reverses the
    # inventory/sales subtraction for exported domestic output.
    assert rec["gdp_nominal_household_consumption"] == pytest.approx(49.0)
    assert rec["gdp_nominal_expenditure_observed"] == pytest.approx(30.0)
    assert rec["gdp_nominal_production"] == pytest.approx(30.0)
    assert rec["gdp_nominal_expenditure_reconciliation_residual"] == pytest.approx(0.0)
    assert rec["gdp_real_household_consumption"] == pytest.approx(34.0)
    assert rec["gdp_real_expenditure_observed"] == pytest.approx(20.0)
    assert rec["gdp_real_production"] == pytest.approx(20.0)
    assert rec["gdp_real_expenditure_reconciliation_residual"] == pytest.approx(0.0)
    assert rec["gdp_expenditure_residual_includes_unobserved_net_exports"] == 0.0
    assert rec["gdp_expenditure_includes_observed_net_exports"] == 1.0


@pytest.mark.parametrize("export_policy_rate", [0.20, -0.20])
def test_export_policy_transaction_value_is_bridged_to_producer_basic_price(
    export_policy_rate,
):
    econ = _small_v2()
    _zero_period(econ)
    tracker = econ._national_accounts
    tracker.open_tick(econ)
    producer = econ.c_firms[0]

    delivered = 2.0
    shipped = 2.5
    loss = shipped - delivered
    basic_value = 5.0 * shipped
    transaction_value = basic_value * (1.0 - export_policy_rate)
    signed_policy_bridge = basic_value * export_policy_rate
    producer.price = 5.0
    producer.produced = producer.sales = shipped
    producer.revenue = basic_value
    tracker.sector_output_base_prices["c"] = 5.0
    econ._fx_export_value_external = transaction_value
    econ._export_subsidy_cost_external = signed_policy_bridge
    econ._fx_export_delivered_volume_external = delivered
    econ._fx_export_volume_external = shipped
    econ._fx_iceberg_loss_volume_external = loss

    rec = preview(econ)

    assert rec["gdp_nominal_exports_transaction_value"] == pytest.approx(
        transaction_value
    )
    assert rec["gdp_nominal_export_policy_basic_price_bridge"] == pytest.approx(
        signed_policy_bridge
    )
    assert rec["gdp_nominal_exports"] == pytest.approx(basic_value)
    assert rec["gdp_external_export_delivered_volume"] == pytest.approx(delivered)
    assert rec["gdp_external_export_shipped_volume"] == pytest.approx(shipped)
    assert rec["gdp_external_iceberg_loss_volume"] == pytest.approx(loss)
    assert rec["gdp_nominal_production"] == pytest.approx(basic_value)
    assert rec["gdp_nominal_expenditure_observed"] == pytest.approx(basic_value)
    assert rec["gdp_nominal_income_observed"] == pytest.approx(basic_value)
    assert rec["gdp_nominal_expenditure_reconciliation_residual"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_reconciliation_residual"] == pytest.approx(0.0)
    assert rec["gdp_nominal_three_approach_raw_spread"] == pytest.approx(0.0)
    assert rec["gdp_real_production"] == pytest.approx(basic_value)
    assert rec["gdp_real_expenditure_observed"] == pytest.approx(basic_value)
    assert rec["gdp_real_expenditure_reconciliation_residual"] == pytest.approx(0.0)
    assert rec["gdp_nominal_export_product_subsidy_signed"] == pytest.approx(
        signed_policy_bridge
    )
    assert rec["gdp_nominal_net_product_taxes_observed"] == pytest.approx(
        -signed_policy_bridge
    )
    assert rec["gdp_nominal_basic_price_corrected_observed"] == pytest.approx(
        basic_value
    )
    assert rec["gdp_nominal_market_price_observed"] == pytest.approx(
        transaction_value
    )


def test_observed_vat_and_energy_excise_bridge_basic_to_market_prices_only():
    econ = _small_v2()
    _zero_period(econ)
    econ._national_accounts.open_tick(econ)
    producer = econ.c_firms[0]
    producer.price = 2.0
    producer.produced = producer.sales = 10.0
    producer.revenue = 20.0
    econ.households[0].spent = 20.0
    econ._tax_consumption = 3.0
    econ._tax_energy = 2.0

    baseline = preview(econ)
    for name in ("_tax_profit", "_tax_income", "_tax_wealth"):
        setattr(econ, name, 100.0)
    with_direct_taxes = preview(econ)

    assert baseline["nominal_gdp"] == pytest.approx(20.0)
    assert baseline["gdp_nominal_vat_observed"] == pytest.approx(3.0)
    assert baseline["gdp_nominal_energy_excise_observed"] == pytest.approx(2.0)
    assert baseline["gdp_nominal_net_product_taxes_observed"] == pytest.approx(5.0)
    assert baseline["gdp_nominal_basic_price_corrected_observed"] == pytest.approx(
        20.0
    )
    assert baseline["gdp_nominal_market_price_observed"] == pytest.approx(25.0)
    for key in (
        "nominal_gdp",
        "gdp_nominal_net_product_taxes_observed",
        "gdp_nominal_basic_price_corrected_observed",
        "gdp_nominal_market_price_observed",
    ):
        assert with_direct_taxes[key] == pytest.approx(baseline[key])


def test_external_trade_components_default_to_observed_zero_in_closed_economy():
    econ = _small_v2()
    _zero_period(econ)
    econ._national_accounts.open_tick(econ)

    rec = preview(econ)

    for key in (
        "gdp_nominal_exports",
        "gdp_nominal_imports",
        "gdp_nominal_net_exports",
        "gdp_real_exports",
        "gdp_real_imports",
        "gdp_real_net_exports",
    ):
        assert rec[key] == 0.0
    assert rec["gdp_expenditure_includes_observed_net_exports"] == 1.0


def test_external_trade_components_are_registered_with_observed_scope_caveats():
    metric_ids = (
        "gdp_nominal_exports",
        "gdp_nominal_imports",
        "gdp_nominal_net_exports",
        "gdp_real_exports",
        "gdp_real_imports",
        "gdp_real_net_exports",
    )

    for metric_id in metric_ids:
        spec = DEFAULT_REGISTRY.get(metric_id)
        assert spec.trust_status == TrustStatus.PROXY
        assert spec.caveats
    for headline in ("real_gdp", "nominal_gdp"):
        assert not any(
            "do not yet allocate World net exports" in caveat
            for caveat in DEFAULT_REGISTRY.get(headline).caveats
        )


def test_product_tax_and_jg_satellites_have_flow_semantics_in_registry():
    product_tax_metrics = (
        "gdp_nominal_energy_cap_product_subsidy",
        "gdp_nominal_export_product_subsidy_signed",
        "gdp_nominal_import_duty_signed",
        "gdp_nominal_vat_observed",
        "gdp_nominal_energy_excise_observed",
        "gdp_nominal_net_product_taxes_observed",
        "gdp_nominal_basic_price_corrected_observed",
        "gdp_nominal_market_price_observed",
    )
    jg_candidates = (
        "gdp_nominal_jg_own_account_capital_at_cost",
        "gdp_real_jg_own_account_capital_units",
        "gdp_nominal_expanded_production_candidate",
        "gdp_nominal_expanded_fixed_capital_formation_candidate",
        "gdp_nominal_expanded_public_fixed_capital_formation_candidate",
        "gdp_nominal_expanded_compensation_candidate",
    )

    for metric_id in product_tax_metrics + jg_candidates:
        spec = DEFAULT_REGISTRY.get(metric_id)
        assert spec.native_frequency == Frequency.DAILY
        assert spec.temporal_type == TemporalType.FLOW
        assert spec.aggregation == Aggregation.SUM
        assert spec.annualization == Annualization.SUM_DAILY_FLOWS
        assert spec.caveats
    assert all(
        DEFAULT_REGISTRY.get(metric_id).trust_status == TrustStatus.PROXY
        for metric_id in product_tax_metrics
    )
    assert all(
        DEFAULT_REGISTRY.get(metric_id).trust_status == TrustStatus.EXPERIMENTAL
        for metric_id in jg_candidates
    )


def test_energy_intermediate_input_is_subtracted_once_and_stocks_reconcile():
    econ = _small_v2(energy_enabled=True, energy_household=True, n_firms_e=1)
    _zero_period(econ)
    tracker = econ._national_accounts
    tracker.open_tick(econ)
    household = econ.households[0]
    c_firm = econ.c_firms[0]
    e_firm = econ.e_firms[0]

    c_firm.price = 3.0
    c_firm.produced, c_firm.sales, c_firm.revenue = 10.0, 10.0, 30.0
    c_firm.energy_used, c_firm.energy_cost_used = 2.0, 8.0
    e_firm.price = 4.0
    e_firm.produced, e_firm.sales, e_firm.revenue = 5.0, 3.0, 12.0
    household.spent = 30.0
    household.energy_spent = 4.0
    household.energy_units = 1.0
    econ._energy_hh_spend = 4.0
    tracker.observe_energy_trades(econ, [
        _trade(c_firm.id, e_firm.id, 2.0, 4.0),
        _trade(household.id, e_firm.id, 1.0, 4.0),
    ])

    rec = preview(econ)
    assert rec["gdp_nominal_gross_output_c"] == pytest.approx(30.0)
    assert rec["gdp_nominal_gross_output_e"] == pytest.approx(20.0)
    assert rec["gdp_nominal_intermediate_energy"] == pytest.approx(8.0)
    assert rec["nominal_gdp"] == pytest.approx(42.0)
    assert rec["real_gdp"] == pytest.approx(42.0)
    assert rec["gdp_nominal_household_consumption"] == pytest.approx(34.0)
    assert rec["gdp_nominal_inventory_change_e"] == pytest.approx(8.0)
    assert rec["gdp_nominal_inventory_change_energy_inputs"] == pytest.approx(0.0)
    assert rec["gdp_nominal_expenditure_observed"] == pytest.approx(42.0)
    assert rec["gdp_nominal_expenditure_reconciliation_residual"] == pytest.approx(0.0)
    assert rec["gdp_real_expenditure_reconciliation_residual"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("producer_cap_compensation", "household_rebate"),
    ((40.0, 0.0), (0.0, 40.0)),
)
def test_energy_cap_product_subsidy_is_distinct_from_household_rebate(
    producer_cap_compensation,
    household_rebate,
):
    econ = _small_v2(energy_enabled=True, energy_household=True, n_firms_e=1)
    _zero_period(econ)
    tracker = econ._national_accounts
    tracker.open_tick(econ)
    household = econ.households[0]
    producer = econ.e_firms[0]
    producer.price = 10.0
    producer.produced = producer.sales = 10.0
    # The producer receives the capped transaction price as revenue.  Producer
    # compensation and a household rebate settle on separate fiscal rails.
    producer.revenue = 60.0
    household.energy_spent = 60.0
    household.energy_units = 10.0
    econ._energy_hh_spend = 60.0
    econ._energy_cap_comp = producer_cap_compensation
    econ._energy_subsidy_paid = household_rebate
    tracker.observe_energy_trades(econ, [
        _trade(household.id, producer.id, 10.0, 6.0),
    ])

    rec = preview(econ)

    # Compatibility GDP remains exactly on its old capped-price path in both
    # cases.  Only the producer payment repairs the basic-price observation.
    assert rec["nominal_gdp"] == pytest.approx(60.0)
    assert rec["gdp_nominal_production"] == pytest.approx(60.0)
    assert rec["gdp_nominal_energy_cap_product_subsidy"] == pytest.approx(
        producer_cap_compensation
    )
    assert rec["gdp_nominal_basic_price_corrected_observed"] == pytest.approx(
        60.0 + producer_cap_compensation
    )
    assert rec["gdp_nominal_net_product_taxes_observed"] == pytest.approx(
        -producer_cap_compensation
    )
    assert rec["gdp_nominal_market_price_observed"] == pytest.approx(60.0)
    assert rec["gdp_excluded_transfer_payments"] == pytest.approx(household_rebate)
    assert rec["gdp_price_basis_is_basic_prices"] == float(
        producer_cap_compensation == 0.0
    )


@pytest.mark.parametrize(
    (
        "productivity",
        "capital_units",
        "expected_own_account_cost",
        "expected_income_floor_transfer",
        "expected_observed",
    ),
    (
        (0.5, 1.0, 10.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 10.0, 0.0),
        (0.5, 0.0, 0.0, 0.0, 0.0),
    ),
)
def test_jg_satellite_requires_productivity_and_observed_capital_units(
    productivity,
    capital_units,
    expected_own_account_cost,
    expected_income_floor_transfer,
    expected_observed,
):
    econ = _small_v2(jg_productivity=productivity)
    _zero_period(econ)
    econ._national_accounts.open_tick(econ)
    econ._jg_spending = 10.0
    econ._jg_employment = 2.0
    econ._jg_capital_units = capital_units

    rec = preview(econ)

    assert rec["nominal_gdp"] == pytest.approx(0.0)
    assert rec["gdp_nominal_fixed_capital_formation"] == pytest.approx(0.0)
    assert rec["gdp_nominal_public_fixed_capital_formation"] == pytest.approx(0.0)
    assert rec["gdp_nominal_compensation_of_employees"] == pytest.approx(0.0)
    assert rec["gdp_jg_public_works_output_observed"] == expected_observed
    assert rec["gdp_nominal_jg_own_account_capital_at_cost"] == pytest.approx(
        expected_own_account_cost
    )
    assert rec["gdp_real_jg_own_account_capital_units"] == pytest.approx(
        capital_units if expected_observed else 0.0
    )
    assert rec["gdp_nominal_jg_income_floor_transfer"] == pytest.approx(
        expected_income_floor_transfer
    )
    assert rec["gdp_nominal_expanded_production_candidate"] == pytest.approx(
        expected_own_account_cost
    )
    assert rec[
        "gdp_nominal_expanded_fixed_capital_formation_candidate"
    ] == pytest.approx(expected_own_account_cost)
    assert rec[
        "gdp_nominal_expanded_public_fixed_capital_formation_candidate"
    ] == pytest.approx(expected_own_account_cost)
    assert rec["gdp_nominal_expanded_compensation_candidate"] == pytest.approx(
        expected_own_account_cost
    )
    assert rec["gdp_unpriced_jg_compensation"] == pytest.approx(10.0)


def test_builder_work_is_residential_investment_and_not_c_output_or_resale():
    econ = _small_v2()
    _zero_period(econ)
    builder = Firm.create(777, econ.cfg)
    builder.id = "BLD_TEST"
    builder.sells = "housing"
    builder.price = 100.0
    builder.produced = 0.25
    builder.wagebill = 25.0
    builder.sales = 0.0
    builder.revenue = 0.0
    econ.firms.append(builder)
    econ._national_accounts.open_tick(econ)

    rec = preview(econ)
    assert rec["gdp_nominal_gross_output_c"] == 0.0
    assert rec["gdp_nominal_gross_output_housing"] == pytest.approx(25.0)
    assert rec["gdp_nominal_residential_fixed_capital_formation"] == pytest.approx(25.0)
    assert rec["gdp_nominal_inventory_change"] == 0.0
    assert rec["nominal_gdp"] == pytest.approx(25.0)
    assert rec["gdp_nominal_expenditure_observed"] == pytest.approx(25.0)
    assert rec["gdp_nominal_expenditure_reconciliation_residual"] == 0.0
    assert rec["gdp_nominal_income_output_sales_accrual_housing"] == pytest.approx(25.0)
    assert rec["gdp_nominal_income_accrual_bridge"] == pytest.approx(25.0)
    assert rec["gdp_nominal_income_accrued_observed"] == pytest.approx(25.0)
    assert rec["gdp_nominal_income_unexplained_residual"] == pytest.approx(0.0)


def test_existing_housing_asset_sale_is_removed_by_income_accrual_bridge():
    econ = _small_v2()
    _zero_period(econ)
    builder = Firm.create(778, econ.cfg)
    builder.id = "BLD_RESALE"
    builder.sells = "housing"
    builder.price = 20.0
    builder.produced = 0.0
    builder.wagebill = 0.0
    builder.sales = 1.0
    builder.revenue = 20.0
    econ.firms.append(builder)
    econ._national_accounts.open_tick(econ)

    rec = preview(econ)

    assert rec["nominal_gdp"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_observed"] == pytest.approx(20.0)
    assert rec["gdp_nominal_income_output_sales_accrual_housing"] == pytest.approx(-20.0)
    assert rec["gdp_nominal_income_accrual_bridge"] == pytest.approx(-20.0)
    assert rec["gdp_nominal_accrued_gross_operating_surplus"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_accrued_observed"] == pytest.approx(0.0)
    assert rec["gdp_nominal_income_unexplained_residual"] == pytest.approx(0.0)


def test_gross_gdp_and_accrued_gos_exclude_cfc_interest_and_profit_tax():
    econ = _small_v2()
    _zero_period(econ)
    econ._national_accounts.open_tick(econ)
    firm = econ.c_firms[0]
    firm.price = 2.0
    firm.produced = firm.sales = 10.0
    firm.revenue = 20.0
    firm.wagebill = 6.0
    econ.households[0].spent = 20.0
    baseline = preview(econ)

    firm.pnl_depreciation = 100.0
    firm.pnl_interest_accrued = 200.0
    firm.pnl_interest_expense = 150.0
    firm.pnl_profit_tax = 300.0
    econ._tax_profit = 300.0
    with_below_gos_flows = preview(econ)

    for key in (
        "nominal_gdp",
        "gdp_nominal_production",
        "gdp_nominal_accrued_gross_operating_surplus",
        "gdp_nominal_income_accrued_observed",
        "gdp_nominal_income_unexplained_residual",
    ):
        assert with_below_gos_flows[key] == pytest.approx(baseline[key])
    assert with_below_gos_flows["nominal_gdp"] == pytest.approx(20.0)
    assert with_below_gos_flows[
        "gdp_nominal_accrued_gross_operating_surplus"
    ] == pytest.approx(14.0)


def test_preview_is_repeatable_and_does_not_advance_price_bases():
    econ = _small_v2()
    for _ in range(3):
        econ.step()
    tracker = econ._national_accounts
    before = asdict(tracker)
    econ_before = (
        econ.rng.getstate(),
        econ.ledger.snapshot(),
        tuple(
            (
                firm.id,
                firm.produced,
                firm.sales,
                firm.revenue,
                firm.wagebill,
                firm.energy_cost_used,
            )
            for firm in econ.firms
        ),
    )
    first = compute_tick_metrics(econ)
    middle = asdict(tracker)
    econ_middle = (
        econ.rng.getstate(),
        econ.ledger.snapshot(),
        tuple(
            (
                firm.id,
                firm.produced,
                firm.sales,
                firm.revenue,
                firm.wagebill,
                firm.energy_cost_used,
            )
            for firm in econ.firms
        ),
    )
    second = compute_tick_metrics(econ)
    after = asdict(tracker)
    econ_after = (
        econ.rng.getstate(),
        econ.ledger.snapshot(),
        tuple(
            (
                firm.id,
                firm.produced,
                firm.sales,
                firm.revenue,
                firm.wagebill,
                firm.energy_cost_used,
            )
            for firm in econ.firms
        ),
    )

    assert first == second
    assert before == middle == after
    assert econ_before == econ_middle == econ_after


def test_empirical_stock_flow_ratios_use_national_accounts_gdp_and_explicit_annualisation():
    econ = Economy(Config.v9(
        n_households=20,
        n_firms_c=4,
        n_firms_k=2,
        n_banks=2,
        n_ticks=1,
        seed=914,
        national_accounts_metrics=True,
    ))
    rec = econ.step()

    assert rec["nominal_gdp"] > 0.0
    assert rec["credit_to_annual_gdp"] == pytest.approx(
        rec["total_credit"] / (365.0 * rec["nominal_gdp"])
    )
    assert rec["credit_to_annualized_daily_gdp"] == pytest.approx(
        rec["credit_to_annual_gdp"]
    )
    assert rec["nominal_gdp_trailing_365d_observed"] == 0.0
    assert rec["credit_to_best_available_annual_gdp"] == pytest.approx(
        rec["credit_to_annualized_daily_gdp"]
    )
    assert rec["total_debt_service_to_nominal_gdp"] == pytest.approx(
        (rec["total_interest_paid"] + rec["total_principal_repaid"])
        / rec["nominal_gdp"]
    )
    assert rec["cash_deficit_to_nominal_gdp"] == pytest.approx(
        rec["cash_deficit"] / rec["nominal_gdp"]
    )
    assert rec["gov_debt_to_annual_gdp"] == pytest.approx(
        rec["gov_debt"] / (365.0 * rec["nominal_gdp"])
    )

    # Compatibility ratios remain bound to the historical C-sector proxy.
    assert rec["credit_to_gdp"] == pytest.approx(
        rec["total_credit"] / rec["nominal_output"]
    )

    # Once a complete daily window exists, the preferred denominator is the
    # realized trailing flow rather than 365 times the current day.
    econ._nominal_gdp_history = deque(
        [2.0] * 364,
        maxlen=365,
    )
    trailing = compute_tick_metrics(econ)
    expected_denominator = 364.0 * 2.0 + trailing["nominal_gdp"]
    assert trailing["nominal_gdp_trailing_365d_observed"] == 1.0
    assert trailing["nominal_gdp_trailing_365d"] == pytest.approx(expected_denominator)
    assert trailing["credit_to_trailing_365d_gdp"] == pytest.approx(
        trailing["total_credit"] / expected_denominator
    )
    assert trailing["credit_to_best_available_annual_gdp"] == pytest.approx(
        trailing["credit_to_trailing_365d_gdp"]
    )


def test_fiscal_cash_account_includes_sectoral_and_external_policy_flows():
    econ = Economy(Config.v9(
        n_households=20,
        n_firms_c=4,
        n_firms_k=2,
        n_banks=2,
        n_ticks=1,
        seed=915,
        national_accounts_metrics=True,
    ))
    econ.step()
    for name, value in {
        "_tax_profit": 1.0,
        "_tax_income": 2.0,
        "_tax_consumption": 3.0,
        "_tax_wealth": 4.0,
        "_tax_energy": 5.0,
        "_tax_energy_windfall": 6.0,
        "_property_tax_paid": 7.0,
        "_transfer_tax_paid": 8.0,
        "_tariff_revenue_external": 9.0,
        "_remittance_tax_revenue_external": 10.0,
        "_outward_remittance_tax_revenue": 11.0,
        "_export_subsidy_cost_external": 12.0,
        "_soe_dividends": 13.0,
        "_land_fee_paid_tick": 14.0,
        "_escheat_flow": 15.0,
        "_spr_sale_revenue": 16.0,
        "_benefit_paid": 1.0,
        "_gov_consumption": 2.0,
        "_jg_spending": 3.0,
        "_public_investment": 4.0,
        "_gov_interest_bill": 5.0,
        "_energy_subsidy_paid": 6.0,
        "_energy_cap_comp": 7.0,
        "_external_interest_fiscal": 8.0,
        "_bank_resolution_fund_paid": 9.0,
        "_spr_purchase_paid": 10.0,
    }.items():
        setattr(econ, name, value)
    econ._fiscal_opening_balance = econ.ledger.balance(econ._fiscal) + 10.0

    rec = compute_tick_metrics(econ)

    assert rec["tax_total"] == pytest.approx(66.0)
    assert rec["fiscal_soe_dividends"] == pytest.approx(13.0)
    assert rec["fiscal_land_fee_revenue"] == pytest.approx(14.0)
    assert rec["fiscal_escheat_revenue"] == pytest.approx(15.0)
    assert rec["fiscal_spr_sale_revenue"] == pytest.approx(16.0)
    assert rec["fiscal_non_tax_revenue"] == pytest.approx(58.0)
    assert rec["fiscal_revenue_total"] == pytest.approx(124.0)
    assert rec["gov_spending"] == pytest.approx(6.0)
    assert rec["bank_resolution_fund_paid"] == pytest.approx(9.0)
    assert rec["fiscal_spr_purchase_paid"] == pytest.approx(10.0)
    assert rec["augmented_gov_spending"] == pytest.approx(67.0)
    assert rec["gov_deficit"] == pytest.approx(-118.0)
    assert rec["cash_deficit"] == pytest.approx(-57.0)
    assert rec["treasury_account_net_outflow"] == pytest.approx(10.0)
    assert rec["treasury_implied_financing_and_unclassified_inflow"] == pytest.approx(-67.0)
