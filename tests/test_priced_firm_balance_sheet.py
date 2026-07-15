"""Acceptance tests for nominal firm assets and the borrowing-base proxy."""

from __future__ import annotations

import pytest

from macro_sim.behavior.planning import credit_grant
from macro_sim.config import Config
from macro_sim.diagnostics.analysis import detect_run_problems
from macro_sim.diagnostics.models import RunSpec
from macro_sim.diagnostics.probes import DeepProbeCollector
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.systems.banking import bank_rwa_exposure, refresh_loan_books
from macro_sim.systems.credit import run_credit_phase
from macro_sim.systems.equity import planned_share_issue
from macro_sim.systems.firm_balance_sheet import (
    firm_balance_sheet,
    firm_equity_book_value,
)
from macro_sim.systems.firm_demographics import (
    _capital_return_denominator,
    birth_consumption_firm,
    run_firm_demographics_phase,
)
from macro_sim.systems.firm_accounting import committed_replacement_capital_price


def _economy(**overrides) -> Economy:
    params = dict(
        seed=2306,
        n_firms_c=2,
        n_firms_k=1,
        n_households=8,
        n_ticks=2,
        priced_firm_balance_sheet=True,
        firm_capital_haircut=0.25,
        firm_inventory_haircut=0.50,
    )
    params.update(overrides)
    return Economy(Config.v3(**params))


def _set_cash(econ: Economy, account: str, target: float) -> None:
    current = econ.ledger.balance(account)
    if current > target:
        econ.ledger.transfer(account, econ.households[0].id, current - target)
    elif current < target:
        econ.ledger.transfer(econ.households[0].id, account, target - current)


def test_flag_defaults_off_frontier_on_and_explicit_false_is_bit_identical() -> None:
    assert Config().priced_firm_balance_sheet is False
    assert FULL_FRONTIER_FLAGS["priced_firm_balance_sheet"] is True

    params = dict(seed=63, n_firms_c=4, n_firms_k=2, n_households=20, n_ticks=25)
    implicit = Economy(Config.v6(**params))
    explicit = Economy(Config.v6(**params, priced_firm_balance_sheet=False))

    assert implicit.run() == explicit.run()
    assert implicit.ledger.snapshot() == explicit.ledger.snapshot()
    assert implicit.rng.getstate() == explicit.rng.getstate()
    assert "priced_firm_balance_sheet_enabled" not in implicit.records[-1]


def test_nominal_balance_sheet_prices_k_and_all_inventory_without_posting_cash() -> None:
    econ = _economy()
    firm = econ.c_firms[0]
    econ._firm_pnl_capital_price = 5.0
    firm.capital = 2.0
    firm.tech = "linear"
    firm.a = 2.0
    firm.wage = 4.0
    firm.production_target = 0.0       # observable replacement cost = wage/a = 2
    firm.inventory = 3.0
    firm.price = 10.0                  # valuation is min(posted 10, cost 2)
    firm.wip = 1.0
    firm.energy_stock = 4.0
    firm.energy_avg_cost = 3.0
    econ.ledger.create_loan(firm.id, 50.0)
    _set_cash(econ, firm.id, 100.0)
    ledger_before = econ.ledger.snapshot()

    sheet = firm_balance_sheet(econ, firm)

    assert sheet.cash == pytest.approx(100.0)
    assert sheet.debt == pytest.approx(50.0)
    assert sheet.capital_value == pytest.approx(2.0 * 5.0)
    assert sheet.output_inventory_unit_price == pytest.approx(2.0)
    assert sheet.output_inventory_value == pytest.approx(3.0 * 2.0)
    assert sheet.work_in_progress_value == pytest.approx(1.0 * 2.0)
    assert sheet.input_inventory_value == pytest.approx(4.0 * 3.0)
    assert sheet.inventory_value == pytest.approx(20.0)
    assert sheet.gross_assets == pytest.approx(130.0)
    assert sheet.book_equity == pytest.approx(80.0)
    assert sheet.eligible_collateral_value == pytest.approx(17.5)
    assert sheet.borrowing_base_proxy == pytest.approx(117.5)
    assert sheet.borrowing_base_headroom == pytest.approx(67.5)
    assert econ.ledger.snapshot() == ledger_before  # revaluation is never money/P&L


def test_interest_arrears_reduce_firm_equity_and_base_but_not_bank_rwa() -> None:
    econ = _economy()
    firm = econ.c_firms[0]
    firm.capital = 0.0
    firm.inventory = 0.0
    firm.wip = 0.0
    firm.energy_stock = 0.0
    econ.ledger.create_loan(firm.id, 50.0)
    _set_cash(econ, firm.id, 100.0)
    refresh_loan_books(econ)
    bank = econ.banks[0]
    base = firm_balance_sheet(econ, firm)
    rwa_before = bank_rwa_exposure(econ, bank)
    ledger_before = econ.ledger.snapshot()

    firm.pnl_interest_arrears = 20.0
    sheet = firm_balance_sheet(econ, firm)
    refresh_loan_books(econ)

    assert sheet.interest_arrears == pytest.approx(20.0)
    assert sheet.gross_assets == pytest.approx(base.gross_assets)
    assert sheet.book_equity == pytest.approx(base.book_equity - 20.0)
    assert sheet.borrowing_base_proxy == pytest.approx(
        base.borrowing_base_proxy - 20.0
    )
    assert sheet.borrowing_base_headroom == pytest.approx(
        base.borrowing_base_headroom - 20.0
    )
    # Arrears are a borrower memo liability until cash is paid.  They must not
    # capitalize into ledger principal, the bank loan asset, or bank RWA.
    assert econ.ledger.snapshot() == ledger_before
    assert econ.ledger.debt(firm.id) == pytest.approx(50.0)
    assert econ._loan_book[bank.id] == pytest.approx(50.0)
    assert bank_rwa_exposure(econ, bank) == pytest.approx(rwa_before)


def test_posted_price_alone_cannot_manufacture_inventory_collateral() -> None:
    econ = _economy()
    firm = econ.c_firms[0]
    firm.capital = 0.0
    firm.tech = "linear"
    firm.a = 2.0
    firm.wage = 4.0
    firm.production_target = 0.0
    firm.inventory = 10.0
    _set_cash(econ, firm.id, 0.0)

    firm.price = 2.0
    at_cost = firm_balance_sheet(econ, firm)
    firm.price = 200_000.0
    inflated_quote = firm_balance_sheet(econ, firm)
    firm.price = 1.0
    distressed_quote = firm_balance_sheet(econ, firm)

    assert at_cost.output_inventory_unit_cost == pytest.approx(2.0)
    assert inflated_quote.inventory_value == pytest.approx(at_cost.inventory_value)
    assert inflated_quote.borrowing_base_proxy == pytest.approx(at_cost.borrowing_base_proxy)
    assert distressed_quote.inventory_value < at_cost.inventory_value


def test_capital_price_and_haircuts_have_correct_units_and_monotone_credit_effect() -> None:
    low_haircut = _economy(firm_capital_haircut=0.10, firm_inventory_haircut=1.0)
    high_haircut = _economy(firm_capital_haircut=0.80, firm_inventory_haircut=1.0)
    for econ in (low_haircut, high_haircut):
        firm = econ.c_firms[0]
        firm.capital = 10.0
        firm.inventory = 0.0
        _set_cash(econ, firm.id, 0.0)
        econ._firm_pnl_capital_price = 3.0

    low = firm_balance_sheet(low_haircut, low_haircut.c_firms[0])
    high = firm_balance_sheet(high_haircut, high_haircut.c_firms[0])
    assert low.capital_value == pytest.approx(30.0)
    assert low.borrowing_base_proxy > high.borrowing_base_proxy

    low_haircut._firm_pnl_capital_price = 6.0
    doubled = firm_balance_sheet(low_haircut, low_haircut.c_firms[0])
    assert doubled.capital_value == pytest.approx(2.0 * low.capital_value)
    assert doubled.book_equity == pytest.approx(2.0 * low.book_equity)
    assert doubled.borrowing_base_proxy == pytest.approx(2.0 * low.borrowing_base_proxy)
    low_credit = credit_grant(
        999.0, deposits=0.0, debt=0.0, kappa=3.0,
        book_equity=low.book_equity,
        borrowing_base_proxy=low.borrowing_base_proxy,
    )
    doubled_credit = credit_grant(
        999.0, deposits=0.0, debt=0.0, kappa=3.0,
        book_equity=doubled.book_equity,
        borrowing_base_proxy=doubled.borrowing_base_proxy,
    )
    assert doubled_credit == pytest.approx(2.0 * low_credit)


def test_no_observed_k_trade_falls_back_to_configured_genesis_price() -> None:
    econ = _economy(p_kfirm0=7.5)
    del econ._firm_pnl_capital_price
    econ.k_firms.clear()
    firm = econ.c_firms[0]
    firm.capital = 2.0

    sheet = firm_balance_sheet(econ, firm)

    assert sheet.capital_unit_price == pytest.approx(7.5)
    assert sheet.capital_value == pytest.approx(15.0)


def test_fully_haircut_assets_create_no_collateral_limit() -> None:
    econ = _economy(firm_capital_haircut=1.0, firm_inventory_haircut=1.0)
    firm = econ.c_firms[0]
    firm.capital = 100.0
    firm.inventory = 100.0
    _set_cash(econ, firm.id, 0.0)

    sheet = firm_balance_sheet(econ, firm)

    assert sheet.capital_value > 0.0
    assert sheet.inventory_value > 0.0
    assert sheet.eligible_collateral_value == 0.0
    assert sheet.borrowing_base_proxy == 0.0


def test_debt_is_deducted_once_from_each_gross_credit_ceiling() -> None:
    # E=80, existing debt=50: leverage room is 3*80-50=190.  The frozen
    # borrowing-base gross ceiling is 117.5, so its additional headroom is
    # 117.5-50=67.5.  The minimum binds; debt is neither omitted nor deducted
    # twice from that gross borrowing base.
    granted = credit_grant(
        999.0,
        deposits=100.0,
        debt=50.0,
        kappa=3.0,
        book_equity=80.0,
        borrowing_base_proxy=117.5,
    )
    assert granted == pytest.approx(67.5)
    assert credit_grant(
        999.0,
        deposits=100.0,
        debt=50.0,
        kappa=3.0,
        book_equity=80.0,
    ) == pytest.approx(190.0)


def test_productive_assets_weakly_expand_actual_firm_credit_not_ledger_cash() -> None:
    enabled = _economy()
    legacy = _economy(priced_firm_balance_sheet=False)
    for econ in (enabled, legacy):
        for firm in econ.firms:
            firm.labor_demand_notional = 0.0
            firm.investment_target = 0.0
        borrower = econ.c_firms[0]
        borrower.capital = 20.0
        borrower.inventory = 0.0
        borrower.wage = 1.0
        borrower.labor_demand_notional = 10.0
        _set_cash(econ, borrower.id, 0.0)

    run_credit_phase(enabled)
    run_credit_phase(legacy)

    assert enabled.ledger.debt(enabled.c_firms[0].id) == pytest.approx(10.0)
    assert legacy.ledger.debt(legacy.c_firms[0].id) == 0.0
    assert enabled._firm_credit_borrowing_base_proxy > 0.0


def test_priced_assets_prevent_cash_only_bankruptcy_but_true_insolvency_exits() -> None:
    econ = _economy(
        firm_dynamics=True,
        bankrupt_persist=2,
        real_entry_signal=False,
        shell_exit_ticks=0,
    )
    firm = econ.c_firms[0]
    econ._firm_pnl_capital_price = 10.0
    firm.capital = 10.0
    firm.inventory = 0.0
    econ.ledger.create_loan(firm.id, 50.0)
    _set_cash(econ, firm.id, 0.0)

    # Liquid financial net worth is -50, but replacement-value equity is +50.
    assert econ.ledger.balance(firm.id) - econ.ledger.debt(firm.id) == pytest.approx(-50.0)
    assert firm_balance_sheet(econ, firm).book_equity == pytest.approx(50.0)
    run_firm_demographics_phase(econ)
    run_firm_demographics_phase(econ)
    assert firm in econ.firms
    assert firm.insolvent_ticks == 0

    # Additional unfunded debt pushes the same priced balance sheet below zero;
    # the configured persistence rule then removes the genuinely insolvent firm.
    econ.ledger.create_loan(firm.id, 100.0)
    _set_cash(econ, firm.id, 0.0)
    assert firm_balance_sheet(econ, firm).book_equity == pytest.approx(-50.0)
    run_firm_demographics_phase(econ)
    assert firm in econ.firms
    run_firm_demographics_phase(econ)
    assert firm not in econ.firms


def test_entry_return_and_startup_trade_use_replacement_capital_price() -> None:
    econ = _economy(real_entry_signal=True)
    firm = econ.c_firms[0]
    firm.capital = 4.0
    econ._price_level = 999.0
    econ._firm_pnl_capital_price = 3.0
    assert _capital_return_denominator(econ, firm) == pytest.approx(12.0)

    seller = econ.k_firms[0]
    seller.inventory = 2.0
    seller.price = 7.0
    founder = max(econ.households, key=lambda h: econ.ledger.balance(h.id))
    birth_consumption_firm(
        econ,
        founder,
        startup_deposits=0.0,
        capital_lots=[(seller, 1.0)],
    )

    assert committed_replacement_capital_price(econ) == pytest.approx(7.0)


def test_genesis_live_equity_and_entry_share_one_priced_book_value() -> None:
    aggregate = Economy(Config.v6(
        seed=11,
        n_firms_c=3,
        n_firms_k=1,
        n_households=12,
        n_ticks=1,
        priced_firm_balance_sheet=True,
    ))
    assert aggregate.equity.book_value == pytest.approx(sum(
        firm_equity_book_value(aggregate, firm) for firm in aggregate.c_firms
    ))

    per_firm = Economy(Config.v61a(
        seed=12,
        n_firms_c=3,
        n_firms_k=1,
        n_households=12,
        n_ticks=1,
        priced_firm_balance_sheet=True,
    ))
    for firm in per_firm.c_firms:
        assert firm.share_price == pytest.approx(
            firm_equity_book_value(per_firm, firm) / firm.shares_outstanding
        )

    founder = per_firm.households[0]
    birth_consumption_firm(per_firm, founder)
    entrant = per_firm.c_firms[-1]
    assert entrant.share_price == pytest.approx(
        firm_equity_book_value(per_firm, entrant) / entrant.shares_outstanding
    )
    assert founder.holdings[entrant.id] == pytest.approx(entrant.shares_outstanding)


def test_enabled_metrics_export_priced_assets_and_preserve_a5() -> None:
    econ = _economy(n_ticks=1)
    record = econ.step()

    for key in (
        "firm_replacement_cost_capital_value",
        "firm_priced_inventory_value",
        "firm_book_equity_priced",
        "firm_eligible_collateral_value",
        "firm_borrowing_base_proxy",
        "firm_borrowing_base_headroom",
        "firm_credit_borrowing_base_proxy",
        "firm_credit_borrowing_base_headroom",
    ):
        assert key in record
    assert record["priced_firm_balance_sheet_enabled"] == 1.0
    assert record["conservation_drift"] < 1e-8


def test_diagnostics_retire_cash_only_finding_but_keep_recovery_scope_limit() -> None:
    econ = _economy(n_ticks=4)
    collector = DeepProbeCollector()
    records = []
    probes = []
    for _ in range(4):
        record = econ.step()
        records.append(record)
        probes.append(collector.collect(econ, record))
    spec = RunSpec(
        name="priced-assets",
        seed=econ.cfg.seed,
        ticks=4,
        population=econ.cfg.n_households,
        n_firms_c=econ.cfg.n_firms_c,
        n_firms_k=econ.cfg.n_firms_k,
        n_banks=econ.cfg.n_banks,
    )

    issue_ids = {
        finding.issue_id
        for finding in detect_run_problems(records, probes, spec)
    }
    assert "credit.productive_assets_excluded" not in issue_ids
    assert "credit.collateral_recovery_missing" in issue_ids


def test_share_issuance_uses_each_issuer_own_price_without_loop_state() -> None:
    econ = Economy(Config.v62(
        seed=91,
        n_firms_c=2,
        n_firms_k=1,
        n_households=8,
        n_ticks=1,
        lambda_issue=0.20,
    ))
    first, second = econ.c_firms
    for firm in (first, second):
        firm.tobin_q = 2.0
        firm.shares_outstanding = 100.0
    first.share_price = 2.0
    second.share_price = 10.0

    # Cash offer is 0.2*(q-1)*book = 20.  Share units therefore differ only
    # by each issuer's own price.  Calling the first issuer directly proves no
    # household/previous-firm loop variable is required or can be reused.
    first_issue = planned_share_issue(first, 100.0, econ.cfg.equity_market)
    second_issue = planned_share_issue(second, 100.0, econ.cfg.equity_market)
    assert first_issue == pytest.approx(10.0)
    assert second_issue == pytest.approx(2.0)
    assert planned_share_issue(
        first,
        100.0,
        econ.cfg.equity_market,
        issue_price=second.share_price,
    ) == pytest.approx(2.0)
