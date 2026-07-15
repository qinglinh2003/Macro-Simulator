"""Executable static checks that map macro symptoms to code-level coupling defects."""

from __future__ import annotations

import inspect
from collections.abc import Callable

from macro_sim.behavior import planning
from macro_sim.config import Config
from macro_sim.core.ledger import Ledger
from macro_sim.demographics import lifecycle
from macro_sim.diagnostics.models import Finding
from macro_sim.domain.agents import Firm
from macro_sim.economy import Economy
from macro_sim.housing.mortgage import MortgageBook
from macro_sim.markets import matching
from macro_sim.reporting import metrics
from macro_sim.systems import (
    banking,
    central_bank,
    credit,
    equity,
    firm_accounting,
    firm_balance_sheet,
    firm_demographics,
    goods,
    planning as system_planning,
    settlement,
)
from macro_sim.world import trade as trade_module
from macro_sim.world import world as world_module


def _source(obj: Callable) -> str:
    return inspect.getsource(obj)


def _finding(
    issue_id: str,
    severity: str,
    category: str,
    claim: str,
    *,
    evidence: dict,
    recommendation: str,
    probes: tuple[str, ...],
    measurement_status: str = "valid",
) -> Finding:
    return Finding(
        issue_id=issue_id,
        severity=severity,
        confidence="confirmed",
        category=category,
        claim=claim,
        evidence=evidence,
        requested_probes=probes,
        recommendation=recommendation,
        measurement_status=measurement_status,
        detector="executable_static_audit",
    )


def run_static_audit() -> tuple[Finding, ...]:
    findings: list[Finding] = []

    metric_source = _source(metrics._compute_tick_metrics)
    state_writes = sorted({
        name for name in (
            "_prev_inflation", "_prev_u", "_prev_nominal_output", "_prev_tax_total",
            "_prev_benefit", "_price_level", "_prev_real_output", "_prev_avg_wage",
        )
        if f"econ.{name} =" in metric_source
    })
    if state_writes:
        findings.append(_finding(
            "diagnostics.metrics_not_pure", "critical", "diagnostics",
            "The official metric collector mutates cross-tick state consumed by policy and behavior.",
            evidence={"state_fields_written": state_writes,
                      "function": "macro_sim.reporting.metrics.compute_tick_metrics"},
            recommendation="Split pure snapshot construction from one authoritative end-of-tick state commit.",
            probes=("metric_purity_state_digest", "repeat_collection_idempotence"),
            measurement_status="collector_side_effect",
        ))

    # C-sector expectations may only consume unmet demand that the market can
    # identify at firm level.  Merely having an aggregate unspent-budget ratio,
    # or spreading it equally/with market share, is not an observational link.
    market_source = "\n".join((
        _source(matching.execute_market),
        _source(matching._trace_supply_constrained_residual),
    ))
    protocol_source = _source(matching.MatchingProtocol.unavailable_seller_visit)
    goods_source = "\n".join((
        _source(goods.run_goods_phase),
        _source(goods._run_split_sessions),
        _source(goods._finalize_goods),
    ))
    expectation_source = _source(planning.update_demand_expectation)
    has_attributable_c_footfall = (
        hasattr(Config(), "consumption_rationed_signal")
        and "unmet_trace" in market_source
        and "unavailable_seller_visit" in market_source
        and "return None" in protocol_source  # no fabricated generic allocation fallback
        and "rationed_signal" in goods_source
        and "trace.by_seller" in goods_source
        and "firm.rationed_demand" in goods_source
        and "firm.rationed_prev" in expectation_source
    )
    if not has_attributable_c_footfall:
        findings.append(_finding(
            "planning.c_sector_unmet_demand_blind", "high", "planning",
            "Consumption firms cannot observe their own supply-constrained buyer visits, so stock-outs bias firm demand expectations downward.",
            evidence={
                "aggregate_gauge_only": "Economy._unsat_ratio",
                "required_data_flow": "protocol quote visit -> seller trace -> Firm.rationed_demand -> next-period B2",
            },
            recommendation=(
                "Trace protocol-defined unsuccessful seller visits and feed only attributable "
                "physical demand to the visited C-firm; retain unidentifiable residuals in aggregate."
            ),
            probes=("c_firm_attributable_footfall", "c_unattributed_unmet_budget"),
        ))

    # Execute paired local decisions instead of searching function names/signatures.
    # This proves the actual sign of each direct channel and catches a parameter that
    # is present but unused (or wired with the wrong sign).
    low_firm = Firm.create_c_firm(0, Config())
    high_firm = Firm.create_c_firm(0, Config())
    for firm in (low_firm, high_firm):
        firm.demand_expected = 30.0
    investment_kwargs = dict(
        expected_inflation=0.0,
        neutral_nominal_rate=0.02,
        inflation_target=0.0,
        user_cost_elasticity=0.5,
        user_cost_multiplier_min=0.5,
        user_cost_multiplier_max=1.5,
        user_cost_floor=1.0e-9,
    )
    planning.plan_investment(low_firm, nominal_loan_rate=0.0, **investment_kwargs)
    planning.plan_investment(high_firm, nominal_loan_rate=0.08, **investment_kwargs)
    low_credit = planning.credit_grant(
        500.0, 200.0, 50.0, 10.0,
        expected_operating_cash_flow=20.0,
        loan_rate=0.01, amort=0.05, min_dscr=1.25,
    )
    high_credit = planning.credit_grant(
        500.0, 200.0, 50.0, 10.0,
        expected_operating_cash_flow=20.0,
        loan_rate=0.10, amort=0.05, min_dscr=1.25,
    )
    low_debtor_budget = planning.reserve_household_debt_service(
        100.0, deposits=100.0, debt=100.0, margin_debt=0.0, loan_rate=0.01, amort=0.05,
    )
    high_debtor_budget = planning.reserve_household_debt_service(
        100.0, deposits=100.0, debt=100.0, margin_debt=0.0, loan_rate=0.10, amort=0.05,
    )
    low_saver_budget = planning.reserve_household_debt_service(
        100.0, deposits=100.0, debt=0.0, margin_debt=0.0, loan_rate=0.01, amort=0.05,
    )
    high_saver_budget = planning.reserve_household_debt_service(
        100.0, deposits=100.0, debt=0.0, margin_debt=0.0, loan_rate=0.10, amort=0.05,
    )
    direct_channels = {
        "investment_user_cost": low_firm.investment_target > high_firm.investment_target,
        "firm_debt_service_capacity": low_credit > high_credit,
        "debtor_consumption_reservation": low_debtor_budget > high_debtor_budget,
        "no_fictitious_saver_return": low_saver_budget == high_saver_budget,
    }
    missing_channels = sorted(name for name, passed in direct_channels.items() if not passed)
    if missing_channels:
        findings.append(_finding(
            "monetary.direct_demand_channels_missing", "critical", "monetary",
            "One or more core investment, debtor-consumption, or firm-credit decisions lack the required direct rate response.",
            evidence={
                "failed_channels": missing_channels,
                "paired_decisions": {
                    "investment_low_high": [low_firm.investment_target, high_firm.investment_target],
                    "credit_low_high": [low_credit, high_credit],
                    "debtor_budget_low_high": [low_debtor_budget, high_debtor_budget],
                    "debt_free_budget_low_high": [low_saver_budget, high_saver_budget],
                },
            },
            recommendation="Repair the failed local decision derivative and keep rates on one per-tick clock.",
            probes=("paired_rate_irf", "local_decision_derivatives"),
        ))

    # Capital is physical, so a valid pricing channel must first value it at a
    # capital-goods replacement price and then allocate a per-tick service flow
    # over planned physical output.  Execute the local price/rate derivatives to
    # catch dimensional shortcuts such as adding raw K directly to money costs.
    service_firm = Firm.create_c_firm(0, Config())
    service_firm.capital = 20.0
    service_firm.delta_K = 0.10
    service_firm.production_target = 10.0
    service_at_one = planning.capital_service_unit_cost(
        service_firm, replacement_price=1.0, opportunity_rate=0.02,
    )
    service_at_two = planning.capital_service_unit_cost(
        service_firm, replacement_price=2.0, opportunity_rate=0.02,
    )
    service_at_high_rate = planning.capital_service_unit_cost(
        service_firm, replacement_price=1.0, opportunity_rate=0.08,
    )
    system_planning_source = _source(system_planning.run_planning_phase)
    has_capital_service_pricing = (
        hasattr(Config(), "capital_service_pricing")
        and "energy" in system_planning.CAPITAL_SERVICE_PRICED_SECTORS
        and "f.sells in CAPITAL_SERVICE_PRICED_SECTORS" in system_planning_source
        and "CAPITAL_SERVICE_PRICED_SECTORS" in metric_source
        and service_at_one > 0.0
        and abs(service_at_two - 2.0 * service_at_one) <= 1.0e-12
        and service_at_high_rate > service_at_one
    )
    if not has_capital_service_pricing:
        findings.append(_finding(
            "pricing.capital_service_cost_missing", "high", "pricing",
            "Cost-plus quotes omit replacement-cost depreciation and the financing/opportunity cost of productive capital.",
            evidence={
                "priced_sectors": sorted(system_planning.CAPITAL_SERVICE_PRICED_SECTORS),
                "replacement_price_derivative": [service_at_one, service_at_two],
                "rate_derivative": [service_at_one, service_at_high_rate],
            },
            recommendation=(
                "Value opening physical capital at the committed capital-goods price, "
                "apply per-tick depreciation plus opportunity cost, and allocate it over planned output."
            ),
            probes=("capital_service_cost_planned", "capital_service_cost_allocated"),
        ))

    # Physical K/inventory may enter a nominal valuation only through the shared
    # price-and-haircut seam.  Check every historically divergent consumer:
    # genesis, live aggregate/per-firm equity, entry, and firm credit.
    balance_sheet_source = _source(firm_balance_sheet.firm_balance_sheet)
    equity_sources = "\n".join((
        _source(equity.setup_per_firm_equity),
        _source(equity.run_equity_phase),
        _source(equity.run_per_firm_equity_phase),
    ))
    has_priced_firm_assets = (
        hasattr(Config(), "priced_firm_balance_sheet")
        and "committed_replacement_capital_price" in balance_sheet_source
        and "output_inventory_value" in balance_sheet_source
        and "input_inventory_value" in balance_sheet_source
        and "book_equity = gross_assets - debt" in balance_sheet_source
        and "borrowing_base_proxy" in balance_sheet_source
        and "firm_equity_book_value" in equity_sources
        and "firm_equity_book_value" in _source(Economy.__init__)
        and "entrant_equity_book_value" in _source(firm_demographics.birth_consumption_firm)
        and "borrowing_base_proxy" in _source(credit.run_credit_phase)
    )
    if not has_priced_firm_assets:
        findings.append(_finding(
            "accounting.firm_assets_mix_physical_and_nominal", "critical", "balance_sheet",
            "Firm equity or lending consumers mix physical capital/inventory units with nominal cash and debt.",
            evidence={
                "required_seam": "committed P_K*K + priced inventories + cash - debt",
                "required_consumers": ["genesis", "equity", "entry", "firm credit"],
            },
            recommendation=(
                "Route every consumer through one nominal firm balance sheet and call "
                "the haircut-limited lending surface a borrowing-base proxy until "
                "priority and recovery are modeled."
            ),
            probes=("capital_price_scaling", "inventory_value_scaling", "borrowing_base_headroom"),
        ))

    firm_pnl_source = _source(settlement.run_settlement_phase)
    full_pnl_source = _source(firm_accounting.prepare_firm_income_statement)
    full_pnl_close_source = _source(firm_accounting.close_firm_income_statement)
    has_full_pnl = (
        "firm_full_pnl" in firm_pnl_source
        and all(token in full_pnl_source for token in (
            "pnl_ebitda", "pnl_depreciation", "pnl_ebit",
            "pnl_interest_expense", "pnl_pre_tax_income",
        ))
        and "pnl_net_income" in full_pnl_close_source
    )
    if not has_full_pnl:
        findings.append(_finding(
            "accounting.firm_profit_is_ebitda", "critical", "pnl",
            "The field named firm profit is revenue less wages and energy, before depreciation and interest.",
            evidence={"assignment": "revenue - wagebill - energy_cost_used"},
            recommendation="Introduce a staged firm P&L and migrate tax, dividends, entry, valuation, and income accounts.",
            probes=("firm_profit_bridge", "interest_counterparty_reconciliation"),
            measurement_status="legacy_invalid",
        ))

    bank_pnl_source = _source(credit.run_debt_service_phase)
    if "bk.profit = bk.interest_income" in bank_pnl_source:
        findings.append(_finding(
            "accounting.bank_profit_is_gross_interest", "critical", "pnl",
            "Bank profit equals gross interest income and omits contractual funding cost and credit-loss flow.",
            evidence={"assignment": "bk.profit = bk.interest_income"},
            recommendation="Record deposit/interbank funding costs, writeoffs/provisions, tax, net income, and a capital bridge.",
            probes=("bank_profit_bridge", "writeoff_dividend_timeline"),
            measurement_status="legacy_invalid",
        ))

    interbank_source = _source(banking.run_interbank_phase)
    if "_interbank_volume" in interbank_source and "ledger.transfer" in interbank_source and not any(
        token in interbank_source for token in ("interbank_loan", "principal", "interbank_asset")
    ):
        findings.append(_finding(
            "banking.interbank_principal_missing", "critical", "banking",
            "The interbank phase reports loan volume but transfers only interest, not reserve principal or a claim.",
            evidence={"function": "macro_sim.systems.banking.run_interbank_phase"},
            recommendation="Create overnight interbank assets/liabilities, move reserve principal, and model maturity/default.",
            probes=("reserve_deficit_before_after_interbank", "interbank_stock_flow_identity"),
        ))

    omo_source = _source(central_bank.run_omo_phase)
    # A reserve retirement is a swap only when the bank receives an explicit
    # per-holder CB claim and a hard gate closes it to the CB liability.
    if "retire_reserves" in omo_source and not all(
        token in omo_source for token in ("_cb_omo_claims", "assert_omo_balance_sheet")
    ):
        findings.append(_finding(
            "central_bank.omo_counterasset_missing", "critical", "central_bank",
            "OMO drains reserves without giving banks a security/repo claim or recording a full CB counterpart.",
            evidence={"function": "macro_sim.systems.central_bank.run_omo_phase"},
            recommendation="Implement a bond sale or an interest-bearing CB bill/repo liability and include both balance sheets.",
            probes=("omo_balance_sheet_bridge", "bank_reserve_position_identity"),
        ))

    mortgage_source = _source(MortgageBook.originate)
    if "ledger.create_loan" in mortgage_source and not all(
        token in mortgage_source for token in ("self.underwrite", "decision", "bank_id")
    ):
        findings.append(_finding(
            "housing.mortgage_bypasses_underwriting", "high", "housing",
            "Mortgage origination bypasses bank capacity, income/DSTI, and rate underwriting.",
            evidence={"function": "macro_sim.housing.mortgage.MortgageBook.originate"},
            recommendation="Route mortgages through a dedicated underwriter sharing bank constraints and adding LTV/DSTI stress tests.",
            probes=("zero_income_mortgage", "zero_bank_headroom_mortgage"),
        ))

    mortgage_capacity_source = _source(MortgageBook.bank_capacity)
    ordinary_capacity_source = _source(banking.bank_capacity)
    if not (
        "bank_rwa_capacity" in mortgage_capacity_source
        and "bank_rwa_capacity" in ordinary_capacity_source
        and "bank_rwa_exposure" in _source(banking.bank_rwa_capacity)
    ):
        findings.append(_finding(
            "banking.credit_capital_envelopes_double_count", "high", "banking",
            "Mortgage and ordinary lending can each allocate the same bank capital through separate capacity envelopes.",
            evidence={
                "mortgage_capacity": "macro_sim.housing.mortgage.MortgageBook.bank_capacity",
                "ordinary_capacity": "macro_sim.systems.banking.bank_capacity",
            },
            recommendation=("Compute firm/consumer RWA at 100% and mortgage RWA at its secured risk weight "
                            "inside one per-bank capital envelope, updating it after every grant."),
            probes=("corporate_then_mortgage_capacity", "mortgage_then_corporate_capacity"),
        ))

    margin_source = _source(equity.run_per_firm_equity_phase)
    if "led.create_loan" in margin_source and "grant_loan" not in margin_source:
        findings.append(_finding(
            "banking.margin_credit_bypasses_capacity", "high", "banking",
            "Margin loans are created directly and can bypass the bank-wide capital envelope.",
            evidence={"function": "macro_sim.systems.equity.run_per_firm_equity_phase"},
            recommendation="Route margin borrowing through the same sequential bank grant boundary as other household credit.",
            probes=("margin_credit_rwa_headroom", "sequential_margin_grants"),
        ))

    lifecycle_source = _source(lifecycle.household_lifecycle_consumption_budget)
    if "need_scale * alpha_income * income_budget" in lifecycle_source:
        findings.append(_finding(
            "consumption.lifecycle_household_size_double_count", "high", "consumption",
            "Lifecycle consumption multiplies already aggregated permanent income by household need scale.",
            evidence={"expression": "need_scale * alpha_income * income_budget"},
            recommendation="Apply equivalence scaling to per-person resources or aggregate person-level budgets exactly once.",
            probes=("household_merge_budget_invariance", "budget_scaling_by_member_count"),
        ))

    world_step_source = _source(world_module.World.step)
    world_pre = world_step_source.find("_run_pre_settlement_phases")
    world_cross_border = world_step_source.find("_dealer_update()")
    world_commit = world_step_source.find("_run_settlement_and_commit_phases")
    if not (0 <= world_pre < world_cross_border < world_commit):
        findings.append(_finding(
            "world.cross_border_settlement_after_domestic_commit", "critical", "external",
            "Cross-border settlement occurs after domestic P&L, metrics, and cross-tick state have committed.",
            evidence={
                "required_order": [
                    "Economy._run_pre_settlement_phases",
                    "World._dealer_update",
                    "Economy._run_settlement_and_commit_phases",
                ],
            },
            recommendation="Insert cross-border market settlement before domestic settlement/metrics, with explicit phase hooks.",
            probes=("world_phase_timeline", "recorded_vs_live_revenue_after_trade"),
        ))

    export_source = _source(trade_module._ship_exports)
    if "val = remaining" in export_source and "max(0.0, f.inventory - q)" in export_source:
        findings.append(_finding(
            "world.exports_unbacked_by_goods", "critical", "external",
            "The final exporter fills any residual order even when physical inventory is exhausted.",
            evidence={"function": "macro_sim.world.trade._ship_exports"},
            recommendation=(
                "Reserve and allocate exporter inventory before import clearing, or add "
                "synchronous export production with explicit real inputs."
            ),
            probes=("export_inventory_stock_flow", "unbacked_export_volume"),
        ))

    goods_source = _source(goods.run_goods_phase)
    split_goods_source = _source(goods._run_split_sessions)
    split_pos = goods_source.find("_run_split_sessions")
    trade_pos = goods_source.find("_inject_foreign_trade")
    return_pos = goods_source.find("return", split_pos)
    split_has_foreign_offer = "_fx_import_offer" in split_goods_source
    if split_pos >= 0 and trade_pos > return_pos > split_pos and not split_has_foreign_offer:
        findings.append(_finding(
            "world.trade_disabled_by_consumption_strata", "critical", "external",
            "The split necessity/luxury goods path returns before foreign trade is injected.",
            evidence={"function": "macro_sim.systems.goods.run_goods_phase"},
            recommendation="Define which stratum is tradable and inject foreign orders/offers into the appropriate sessions.",
            probes=("strata_trade_nonzero", "bilateral_trade_reconciliation"),
        ))

    # Known structural boundaries must remain visible even after the executable
    # bug checks above go green.  Otherwise a clean static report incorrectly
    # implies that contract timing, funding cost and loss recovery are modeled.
    loan_source = _source(Ledger.create_loan)
    rate_source = _source(banking.loan_rate_for)
    if "contract" not in loan_source and "econ._rate" in rate_source:
        findings.append(_finding(
            "finance.loan_contract_vintages_missing", "high", "finance",
            "All outstanding principal reprices from the current policy-linked loan rate; loans have no origination vintage, fixed/floating term, reset date, or contractual arrears schedule.",
            evidence={
                "principal_storage": "one scalar per borrower in Ledger._loans",
                "rate_boundary": "macro_sim.systems.banking.loan_rate_for",
            },
            recommendation=(
                "Introduce typed loan contracts with lender, purpose, origination, "
                "rate type, reset schedule, maturity and arrears before treating "
                "monetary IRFs as realistic repricing dynamics."
            ),
            probes=("loan_vintage_distribution", "fixed_floating_repricing_irf"),
            measurement_status="known_scope_limit",
        ))

    bank_close_source = _source(credit.finalize_bank_pnl)
    if "deposit_interest_expense" not in bank_close_source:
        findings.append(_finding(
            "banking.deposit_funding_cost_missing", "high", "banking",
            "Bank net income has no contractual deposit-interest or operating-cost expense; deposit competition redistributes customers but does not price funding.",
            evidence={
                "pnl_boundary": "macro_sim.systems.credit.finalize_bank_pnl",
                "missing_leg": "deposit_interest_expense",
            },
            recommendation=(
                "Post deposit interest by account and bank, then close loan income, "
                "wholesale funding, deposit funding, provisions and operating cost "
                "through one bank capital bridge."
            ),
            probes=("deposit_rate_cash_postings", "bank_net_interest_margin_bridge"),
            measurement_status="known_scope_limit",
        ))

    bankruptcy_source = _source(firm_demographics.bankrupt_firm)
    if "eligible_collateral_value" not in bankruptcy_source:
        findings.append(_finding(
            "credit.collateral_recovery_missing", "high", "credit",
            "Priced collateral constrains lending and solvency, but firm default still has no lien priority, asset seizure, sale proceeds, or recovery allocation.",
            evidence={
                "valuation_boundary": "macro_sim.systems.firm_balance_sheet.firm_balance_sheet",
                "default_boundary": "macro_sim.systems.firm_demographics.bankrupt_firm",
            },
            recommendation=(
                "Implement a conserving liquidation journal separating collateral "
                "recovery from residual write-off before interpreting bank LGD."
            ),
            probes=("default_recovery", "claim_priority", "collateral_disposal"),
            measurement_status="known_scope_limit",
        ))

    if "ledger.create_loan" in mortgage_source and "self.loans" in mortgage_source:
        findings.append(_finding(
            "housing.typed_household_debt_missing", "high", "housing",
            "Mortgage, unsecured consumer and margin principal share one borrower ledger scalar; the mortgage book is only a collateral shadow and generic repayment must be approximated pro rata.",
            evidence={
                "cash_debt_rail": "Ledger._loans[household]",
                "secured_shadow": "MortgageBook.loans[household].balance",
            },
            recommendation=(
                "Move household obligations to typed per-contract subledgers and "
                "aggregate them only for cash and capital reporting."
            ),
            probes=("household_debt_type_reconciliation", "mortgage_consumer_repayment_order"),
            measurement_status="known_scope_limit",
        ))

    if has_full_pnl and "inventory" not in full_pnl_source:
        findings.append(_finding(
            "accounting.inventory_cogs_matching_missing", "medium", "pnl",
            "The full firm income statement remains cash-basis for production costs and does not capitalize inventory or match cost of goods sold to sales.",
            evidence={"income_statement": "prepare_firm_income_statement"},
            recommendation=(
                "Add inventory cost lots or a documented weighted-average cost roll-forward "
                "before using period profit for calibrated tax, exit or valuation moments."
            ),
            probes=("inventory_cost_rollforward", "cogs_sales_matching"),
            measurement_status="known_scope_limit",
        ))

    return tuple(sorted(findings, key=lambda item: (item.issue_id,)))
