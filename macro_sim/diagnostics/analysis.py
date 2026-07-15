"""Problem detectors over official series and immutable deep probes."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np

from macro_sim.diagnostics.models import Finding, RunSpec


TICKS_PER_YEAR = 365.0


def _col(rows: list[dict[str, Any]], key: str) -> np.ndarray:
    values = []
    for row in rows:
        value = row.get(key, float("nan"))
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            values.append(float("nan"))
    return np.asarray(values, dtype=float)


def _finite(values: np.ndarray) -> np.ndarray:
    return values[np.isfinite(values)]


def _mean(rows: list[dict[str, Any]], key: str, start: int = 0) -> float:
    values = _finite(_col(rows[start:], key))
    return float(np.mean(values)) if values.size else float("nan")


def _median(rows: list[dict[str, Any]], key: str, start: int = 0) -> float:
    values = _finite(_col(rows[start:], key))
    return float(np.median(values)) if values.size else float("nan")


def _percentile(rows: list[dict[str, Any]], key: str, percentile: float, start: int = 0) -> float:
    values = _finite(_col(rows[start:], key))
    return float(np.percentile(values, percentile)) if values.size else float("nan")


def _max(rows: list[dict[str, Any]], key: str, start: int = 0) -> float:
    values = _finite(_col(rows[start:], key))
    return float(np.max(values)) if values.size else float("nan")


def _max_abs(rows: list[dict[str, Any]], key: str) -> float:
    values = _finite(_col(rows, key))
    return float(np.max(np.abs(values))) if values.size else 0.0


def _annualized_log_growth(values: np.ndarray) -> float:
    values = _finite(values)
    if values.size < 2 or values[0] <= 0.0 or values[-1] <= 0.0:
        return float("nan")
    periods = values.size - 1
    return float(math.expm1(math.log(values[-1] / values[0]) * TICKS_PER_YEAR / periods))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if math.isfinite(denominator) and abs(denominator) > 1e-12 else float("nan")


def summarize_run(
    records: list[dict[str, Any]], probes: list[dict[str, Any]], spec: RunSpec
) -> dict[str, Any]:
    burn = max(1, len(records) // 2)
    has_national_accounts = bool(records) and all(
        float(row.get("national_accounts_enabled", 0.0)) >= 0.5 for row in records
    )
    real_per_capita_key = (
        "real_gdp_per_capita" if has_national_accounts else "real_output_per_capita"
    )
    price_level_key = "cpi_fixed_basket" if has_national_accounts else "price_index"
    keys = (
        "inflation_yoy", "unemployment_rate", "person_unemployment_rate",
        "effective_unemployment", "jg_employment_rate",
        "cpi_fixed_basket", "cpi_fixed_basket_inflation_yoy",
        "cpi_fixed_basket_inflation_yoy_observed",
        "nominal_gdp", "real_gdp", "real_gdp_per_capita",
        "gdp_nominal_energy_cap_product_subsidy",
        "gdp_nominal_export_product_subsidy_signed",
        "gdp_nominal_import_duty_signed",
        "gdp_nominal_vat_observed",
        "gdp_nominal_energy_excise_observed",
        "gdp_nominal_net_product_taxes_observed",
        "gdp_nominal_basic_price_corrected_observed",
        "gdp_nominal_market_price_observed",
        "gdp_jg_public_works_output_observed",
        "gdp_nominal_jg_own_account_capital_at_cost",
        "gdp_real_jg_own_account_capital_units",
        "gdp_nominal_jg_income_floor_transfer",
        "gdp_nominal_expanded_production_candidate",
        "gdp_nominal_expanded_fixed_capital_formation_candidate",
        "gdp_nominal_expanded_public_fixed_capital_formation_candidate",
        "gdp_nominal_expanded_compensation_candidate",
        "gdp_nominal_expenditure_reconciliation_residual",
        "gdp_nominal_income_reconciliation_residual",
        "gdp_nominal_income_output_sales_accrual_c",
        "gdp_nominal_income_output_sales_accrual_k",
        "gdp_nominal_income_output_sales_accrual_e",
        "gdp_nominal_income_output_sales_accrual_housing",
        "gdp_nominal_income_output_sales_accrual_other",
        "gdp_nominal_income_intermediate_scope_adjustment",
        "gdp_nominal_income_accrual_bridge",
        "gdp_nominal_income_accrual_bridge_share",
        "gdp_nominal_accrued_gross_operating_surplus",
        "gdp_nominal_income_accrued_observed",
        "gdp_nominal_income_unexplained_residual",
        "gdp_nominal_income_unexplained_residual_share",
        "real_output_per_capita", "real_output", "real_consumption",
        "production_realization_rate", "investment_realization_rate",
        "inventory_to_sales", "unsatisfied_demand_ratio", "savings_rate",
        "poverty_rate", "deprivation_below100_share", "fuel_poverty_share",
        "market_share_hhi_output", "bank_loanbook_hhi", "credit_to_gdp",
        "credit_to_annual_gdp", "credit_to_annualized_daily_gdp",
        "credit_to_trailing_365d_gdp", "credit_to_best_available_annual_gdp",
        "total_debt_service_ratio",
        "total_debt_service_to_nominal_gdp", "policy_rate",
        "cash_deficit_to_gdp", "cash_deficit_to_nominal_gdp",
        "firm_count_c", "banks_alive", "writeoffs", "n_bank_failures",
        "conservation_drift", "reserve_conservation_drift", "shares_conservation_drift",
    )
    tail = {
        key: {
            "mean": _mean(records, key, burn),
            "median": _median(records, key, burn),
        }
        for key in keys
        if any(key in row for row in records)
    }
    probe_keys = (
        "composition_log_change", "final_demand_proxy", "reported_nominal_output",
        "market_rent_flow", "imputed_owner_rent_proxy", "net_product_taxes_proxy",
        "inventory_change_value", "inventory_revaluation", "balance_sheet_inventory_value",
        "reported_firm_profit", "corrected_firm_profit_proxy",
        "capital_depreciation_value_proxy", "firm_interest_due_proxy",
        "capital_service_pricing_enabled", "capital_service_cost_planned",
        "capital_service_cost_allocated",
        "firm_full_pnl_enabled", "firm_pnl_revenue",
        "firm_pnl_intermediate_inputs", "firm_pnl_compensation",
        "firm_pnl_ebitda", "firm_pnl_depreciation", "firm_pnl_ebit",
        "firm_pnl_interest_accrued", "firm_pnl_cash_interest",
        "firm_pnl_pre_tax_income", "firm_pnl_tax_total",
        "firm_pnl_net_income", "firm_pnl_dividends_paid",
        "firm_pnl_retained_earnings", "firm_pnl_interest_arrears",
        "firm_pnl_post_close_revenue_carry",
        "firm_pnl_profit_compatibility_residual",
        "firm_pnl_bridge_max_abs_residual",
        "firm_pnl_interest_cash_counter_residual",
        "firm_bank_interest_counterparty_residual",
        "bank_external_interest_expense",
        "collateral_value_excluded", "firm_cash_net_worth", "credit_requested_proxy",
        "priced_firm_balance_sheet_enabled", "firm_eligible_collateral_value",
        "firm_borrowing_base_proxy",
        "firm_credit_requested", "firm_credit_leverage_allowed",
        "firm_credit_leverage_shortfall", "firm_credit_leverage_constrained_share",
        "firm_credit_bank_shortfall",
        "unified_bank_rwa_enabled", "bank_rwa_total", "bank_rwa_limit_total",
        "bank_rwa_headroom_min", "bank_rwa_utilization_max",
        "k_output_units", "k_inventory_units", "k_firm_count",
        "persistent_labor_matching", "labor_fractional_hours",
        "k_labor_demand_total",
        "k_labor_demand_max", "k_active_worker_heads", "k_hiring_gap_total",
        "k_active_worker_fte", "k_active_effective_labor",
        "k_firms_above_half_worker_gap", "energy_household_orders_proxy",
        "energy_household_filled", "energy_orders_total", "energy_firm_orders",
        "energy_household_orders", "energy_public_orders", "energy_capacity_units",
        "energy_expected_demand", "energy_investment_target_units",
        "energy_investment_units",
        "public_capital_stock", "public_capital_factor", "public_capital_reference",
        "government_capital_units", "job_guarantee_capital_units",
        "job_guarantee_workers",
    )
    probe_tail = {
        key: {"mean": _mean(probes, key, burn), "median": _median(probes, key, burn)}
        for key in probe_keys
        if any(key in row for row in probes)
    }
    return {
        "n_ticks": len(records),
        "burn_in_tick": burn,
        "tail": tail,
        "probe_tail": probe_tail,
        "annualized_real_output_per_capita_growth": _annualized_log_growth(
            _col(records[burn:], real_per_capita_key)
        ),
        "annualized_price_level_growth": _annualized_log_growth(
            _col(records[burn:], price_level_key)
        ),
        "national_accounts_basis": "v23" if has_national_accounts else "legacy",
        "max_conservation_drift": _max_abs(records, "conservation_drift"),
        "max_reserve_drift": _max_abs(records, "reserve_conservation_drift"),
        "max_share_drift": _max_abs(records, "shares_conservation_drift"),
        "deprivation_boundary_ever": bool(np.nanmax(_col(records, "deprivation_boundary")) >= 1.0)
        if records and any("deprivation_boundary" in row for row in records) else False,
        "scenario": spec.scenario,
        "seed": spec.seed,
    }


def detect_run_problems(
    records: list[dict[str, Any]], probes: list[dict[str, Any]], spec: RunSpec
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    burn = max(1, len(records) // 2)
    scale = max(1.0, float(records[0].get("genesis_money", records[0].get("total_money", 1.0))))
    has_national_accounts = bool(records) and all(
        float(row.get("national_accounts_enabled", 0.0)) >= 0.5 for row in records
    )

    def add(**kwargs) -> None:
        findings.append(Finding(**kwargs))

    # Hard validity and accounting gates.
    nonfinite = _max_abs(probes, "nonfinite_official_values")
    if nonfinite > 0.0:
        add(
            issue_id="validity.nonfinite_metrics", severity="critical", confidence="confirmed",
            category="validity", detector="finite_values",
            claim="Official tick records contain non-finite numeric values.",
            evidence={"max_nonfinite_fields_per_tick": nonfinite},
            requested_probes=("first_bad_tick", "metric_schema"),
            recommendation="Stop interpreting the run and isolate the first non-finite field and phase.",
        )

    for key, issue, label in (
        ("conservation_drift", "accounting.a5_drift", "A5 net-financial-worth"),
        ("reserve_conservation_drift", "accounting.reserve_drift", "reserve"),
        ("shares_conservation_drift", "accounting.share_drift", "share"),
    ):
        drift = _max_abs(records, key)
        if drift > 1e-7 * scale:
            add(
                issue_id=issue, severity="critical", confidence="confirmed", category="accounting",
                detector="conservation_gate", claim=f"{label} conservation drifts beyond tolerance.",
                evidence={"max_abs_drift": drift, "relative_to_genesis_money": drift / scale},
                requested_probes=("phase_timeline", "ledger_journal"),
                recommendation="Locate the first phase that changes the conserved stock without a paired entry.",
            )

    if has_national_accounts:
        # A balancing residual may be economically informative and need not be zero.
        # The *reconciled* totals, however, are an accounting identity.  Check that
        # collector or refactor changes have not allowed the three approaches to
        # disagree after their explicitly reported residuals are applied.
        identity_pairs = (
            ("nominal_gdp", "gdp_nominal_production", "nominal production headline"),
            ("nominal_gdp", "gdp_nominal_expenditure_reconciled", "nominal expenditure"),
            ("nominal_gdp", "gdp_nominal_income_reconciled", "nominal income"),
            ("real_gdp", "gdp_real_production", "real production headline"),
            ("real_gdp", "gdp_real_expenditure_reconciled", "real expenditure"),
        )
        identity_series = [
            (_col(records, left_key), _col(records, right_key), label)
            for left_key, right_key, label in identity_pairs
        ]
        bridge_components = (
            _col(records, "gdp_nominal_income_output_sales_accrual_c")
            + _col(records, "gdp_nominal_income_output_sales_accrual_k")
            + _col(records, "gdp_nominal_income_output_sales_accrual_e")
            + _col(records, "gdp_nominal_income_output_sales_accrual_housing")
            + _col(records, "gdp_nominal_income_output_sales_accrual_other")
            + _col(records, "gdp_nominal_income_intermediate_scope_adjustment")
        )
        identity_series.extend((
            (
                _col(records, "gdp_nominal_income_accrual_bridge"),
                bridge_components,
                "income accrual bridge components",
            ),
            (
                _col(records, "gdp_nominal_income_accrued_observed"),
                _col(records, "gdp_nominal_income_observed")
                + _col(records, "gdp_nominal_income_accrual_bridge"),
                "cash income plus accrual bridge",
            ),
            (
                _col(records, "nominal_gdp"),
                _col(records, "gdp_nominal_income_accrued_observed")
                + _col(records, "gdp_nominal_income_unexplained_residual"),
                "accrued income plus unexplained residual",
            ),
            (
                _col(records, "gdp_nominal_net_product_taxes_observed"),
                _col(records, "gdp_nominal_vat_observed")
                + _col(records, "gdp_nominal_energy_excise_observed")
                + _col(records, "gdp_nominal_import_duty_signed")
                - _col(records, "gdp_nominal_export_product_subsidy_signed")
                - _col(records, "gdp_nominal_energy_cap_product_subsidy"),
                "observed net product-tax components",
            ),
            (
                _col(records, "gdp_nominal_basic_price_corrected_observed"),
                _col(records, "nominal_gdp")
                + _col(records, "gdp_nominal_energy_cap_product_subsidy"),
                "energy-cap corrected basic-price GDP",
            ),
            (
                _col(records, "gdp_nominal_market_price_observed"),
                _col(records, "gdp_nominal_basic_price_corrected_observed")
                + _col(records, "gdp_nominal_net_product_taxes_observed"),
                "observed market-price GDP",
            ),
            (
                _col(records, "gdp_nominal_expanded_production_candidate"),
                _col(records, "gdp_nominal_basic_price_corrected_observed")
                + _col(records, "gdp_nominal_jg_own_account_capital_at_cost"),
                "expanded production candidate",
            ),
            (
                _col(
                    records,
                    "gdp_nominal_expanded_fixed_capital_formation_candidate",
                ),
                _col(records, "gdp_nominal_fixed_capital_formation")
                + _col(records, "gdp_nominal_jg_own_account_capital_at_cost"),
                "expanded fixed-capital-formation candidate",
            ),
            (
                _col(
                    records,
                    "gdp_nominal_expanded_public_fixed_capital_formation_candidate",
                ),
                _col(records, "gdp_nominal_public_fixed_capital_formation")
                + _col(records, "gdp_nominal_jg_own_account_capital_at_cost"),
                "expanded public fixed-capital-formation candidate",
            ),
            (
                _col(records, "gdp_nominal_expanded_compensation_candidate"),
                _col(records, "gdp_nominal_compensation_of_employees")
                + _col(records, "gdp_nominal_jg_own_account_capital_at_cost"),
                "expanded compensation candidate",
            ),
        ))
        worst_abs = 0.0
        worst_relative = 0.0
        worst_identity = ""
        for left, right, label in identity_series:
            valid_pair = np.isfinite(left) & np.isfinite(right)
            if not np.any(valid_pair):
                continue
            gaps = np.abs(left[valid_pair] - right[valid_pair])
            denominators = np.maximum(
                1.0, np.maximum(np.abs(left[valid_pair]), np.abs(right[valid_pair]))
            )
            relative = gaps / denominators
            index = int(np.argmax(relative))
            if float(relative[index]) > worst_relative:
                worst_relative = float(relative[index])
                worst_abs = float(gaps[index])
                worst_identity = label
        if worst_relative > 1e-9:
            add(
                issue_id="accounting.national_accounts_reconciliation_drift",
                severity="critical",
                confidence="confirmed",
                category="national_accounts",
                detector="three_approach_identity_gate",
                claim="A reconciled national-accounts total no longer equals its GDP anchor.",
                evidence={
                    "worst_identity": worst_identity,
                    "max_abs_gap": worst_abs,
                    "max_relative_gap": worst_relative,
                    "relative_tolerance": 1e-9,
                },
                requested_probes=("national_accounts_tick_journal", "first_identity_break"),
                recommendation=(
                    "Locate the first tick where an observed component plus its explicit "
                    "reconciliation residual does not reproduce the production GDP anchor."
                ),
                measurement_status="invalid_run",
            )

        # Reconciliation is an explicit balancing bridge, not independent
        # validation.  The legacy income residual and raw three-approach spread
        # compare production accruals with firm cash revenue; inventory/WIP and
        # existing-asset sales can therefore make both large without revealing an
        # unknown accounting gap.  Only the income remainder *after* the explicit
        # output-sales accrual bridge is eligible for a scope finding.
        threshold_residual_keys = {
            "nominal_expenditure": "gdp_nominal_expenditure_residual_share",
            "nominal_income_unexplained": (
                "gdp_nominal_income_unexplained_residual_share"
            ),
            "real_expenditure": "gdp_real_expenditure_residual_share",
        }
        # Preserve the established evidence labels as compatibility context, but
        # never feed them into the material-scope thresholds: both compare an
        # accrual production anchor with the legacy cash-income observation.
        compatibility_context_keys = {
            "nominal_income": "gdp_nominal_income_residual_share",
            "three_approach_spread": (
                "gdp_nominal_three_approach_raw_spread_share"
            ),
        }
        evidence_residual_keys = {
            **threshold_residual_keys,
            **compatibility_context_keys,
        }
        residual_medians = {
            label: _median(records, key, burn)
            for label, key in evidence_residual_keys.items()
        }
        residual_p95 = {
            label: _percentile(records, key, 95.0, burn)
            for label, key in evidence_residual_keys.items()
        }
        residual_maxima = {
            label: _max(records, key, burn)
            for label, key in evidence_residual_keys.items()
        }
        threshold_p95 = {
            label: residual_p95[label] for label in threshold_residual_keys
        }
        threshold_maxima = {
            label: residual_maxima[label] for label in threshold_residual_keys
        }
        persistent_material = max(threshold_p95.values(), default=0.0) > 0.05
        episodic_material = max(threshold_maxima.values(), default=0.0) > 0.20
        if persistent_material or episodic_material:
            add(
                issue_id="accounting.national_accounts_material_scope_residual",
                severity="high",
                confidence="confirmed",
                category="national_accounts",
                detector="three_approach_coverage",
                claim=(
                    "The GDP approaches reconcile only after a material balancing "
                    "residual, so the account is unsuitable for level validation."
                ),
                evidence={
                    "tail_median_residual_shares": residual_medians,
                    "tail_p95_residual_shares": residual_p95,
                    "tail_max_residual_shares": residual_maxima,
                    "threshold_eligible_residuals": tuple(
                        threshold_residual_keys
                    ),
                    "explained_cash_accrual_bridge": {
                        "tail_median_share": _median(
                            records, "gdp_nominal_income_accrual_bridge_share", burn
                        ),
                        "tail_p95_share": _percentile(
                            records,
                            "gdp_nominal_income_accrual_bridge_share",
                            95.0,
                            burn,
                        ),
                        "tail_max_share": _max(
                            records, "gdp_nominal_income_accrual_bridge_share", burn
                        ),
                        "legacy_cash_gap_tail_max_share": _max(
                            records, "gdp_nominal_income_residual_share", burn
                        ),
                    },
                    "persistent_p95_threshold": 0.05,
                    "episodic_max_threshold": 0.20,
                },
                requested_probes=(
                    "national_accounts_component_coverage",
                    "net_exports_and_tax_basis_bridge",
                ),
                recommendation=(
                    "Trace the missing expenditure components or the income remainder "
                    "left after the reported accrual bridge, and keep GDP at proxy "
                    "status until unexplained coverage gaps are materially complete."
                ),
                measurement_status="scope_incomplete",
            )

    for key, issue, label in (
        ("min_inventory", "feasibility.negative_inventory", "inventory"),
        ("min_capital", "feasibility.negative_capital", "capital"),
    ):
        values = _finite(_col(probes, key))
        minimum = float(np.min(values)) if values.size else 0.0
        if minimum < -1e-8:
            add(
                issue_id=issue, severity="critical", confidence="confirmed", category="feasibility",
                detector="nonnegative_real_stock", claim=f"A real {label} stock becomes negative.",
                evidence={"minimum": minimum}, requested_probes=("first_bad_entity", "phase_timeline"),
                recommendation="Clamp only after locating and fixing the over-allocation or double-decrement path.",
            )

    if any(row.get("deprivation_boundary", 0.0) >= 1.0 for row in records):
        add(
            issue_id="welfare.deprivation_domain_boundary", severity="critical", confidence="confirmed",
            category="welfare", detector="deprivation_boundary",
            claim="Acute deprivation crosses the model's declared validity boundary.",
            evidence={"first_tick": next(row.get("t") for row in records if row.get("deprivation_boundary", 0.0) >= 1.0)},
            requested_probes=("household_resource_constraints", "safety_net_ablation"),
            recommendation="Treat all later demographic/long-run conclusions as out of domain and diagnose the resource shortfall.",
        )

    # Measurement defects: confirmed by alternate immutable probes, not by macro targets.
    reported = _col(probes[burn:], "reported_nominal_output")
    proxy = _col(probes[burn:], "final_demand_proxy")
    valid = np.isfinite(reported) & np.isfinite(proxy)
    if np.any(valid) and not has_national_accounts:
        gap = np.abs(reported[valid] - proxy[valid]) / np.maximum(1.0, np.maximum(np.abs(reported[valid]), np.abs(proxy[valid])))
        median_gap = float(np.median(gap))
        if median_gap > 0.10:
            add(
                issue_id="measurement.gdp_scope_mismatch", severity="critical", confidence="confirmed",
                category="national_accounts", detector="expenditure_proxy_gap",
                claim="The headline nominal_output is not an economy-wide final-expenditure aggregate.",
                evidence={"median_relative_gap": median_gap,
                          "reported_tail_mean": float(np.mean(reported[valid])),
                          "final_demand_proxy_tail_mean": float(np.mean(proxy[valid]))},
                suspected_mechanisms=("C-sector-only production valuation", "missing investment/energy/final demand", "inventory valuation"),
                requested_probes=("three_way_gdp", "sector_flow_of_funds"),
                recommendation="Build expenditure, production, and income accounts and reconcile them before using GDP ratios.",
                measurement_status="legacy_invalid",
            )

    comp_raw = _col(probes[burn:], "composition_log_change")
    unit_raw = _col(probes[burn:], "unit_value_log_change")
    price_pair_valid = np.isfinite(comp_raw) & np.isfinite(unit_raw)
    comp = comp_raw[price_pair_valid]
    unit = unit_raw[price_pair_valid]
    if comp.size and not has_national_accounts:
        annual_comp = float(np.mean(comp) * TICKS_PER_YEAR)
        comp_abs = float(np.mean(np.abs(comp)))
        unit_abs = float(np.mean(np.abs(unit))) if unit.size else float("nan")
        share = _safe_ratio(comp_abs, unit_abs)
        if abs(annual_comp) > 0.005 or (math.isfinite(share) and share > 0.25):
            add(
                issue_id="measurement.price_composition", severity="critical", confidence="confirmed",
                category="prices", detector="matched_price_decomposition",
                claim="Sales composition materially contaminates the headline unit-value inflation measure.",
                evidence={"annualized_mean_composition_log_change": annual_comp,
                          "mean_abs_composition_share_of_unit_change": share},
                suspected_mechanisms=("sales-weighted unit value", "entry/exit and stockout mix"),
                requested_probes=("fixed_basket_cpi", "price_mix_counterfactual"),
                recommendation="Keep unit value as a market statistic and give CPI fixed/chain weights plus missing-price rules.",
                measurement_status="legacy_invalid",
            )

    retained = _finite(_col(records, "retained_total"))
    if retained.size and float(np.min(retained)) < -1e-8:
        add(
            issue_id="measurement.negative_retained_earnings", severity="high", confidence="confirmed",
            category="pnl", detector="retained_nonnegative_definition",
            claim="The reported retained_total becomes negative because profits are aggregated before truncation.",
            evidence={"minimum_retained_total": float(np.min(retained))},
            suspected_mechanisms=("max(0, aggregate profit) - aggregate dividends",),
            requested_probes=("firm_level_profit_bridge",),
            recommendation="Sum firm-level retained earnings under an explicit distributable-income definition.",
            measurement_status="legacy_invalid",
        )

    full_pnl_enabled = _median(probes, "firm_full_pnl_enabled", burn) >= 0.5
    gross_profit = abs(_median(probes, "reported_firm_profit", burn))
    omitted_cost = _median(probes, "capital_depreciation_value_proxy", burn) + _median(probes, "firm_interest_due_proxy", burn)
    pnl_gap = _safe_ratio(omitted_cost, max(1.0, gross_profit))
    if not full_pnl_enabled and math.isfinite(pnl_gap) and pnl_gap > 0.05:
        add(
            issue_id="accounting.firm_pnl_omits_capital_cost", severity="critical", confidence="confirmed",
            category="pnl", detector="firm_profit_bridge",
            claim="The firm profit field omits economically material depreciation and interest costs.",
            evidence={"omitted_cost_to_abs_reported_profit": pnl_gap,
                      "tail_omitted_cost": omitted_cost, "tail_abs_reported_profit": gross_profit},
            suspected_mechanisms=("profit is EBITDA-like", "interest recorded only as cash transfer"),
            requested_probes=("firm_bank_pnl", "capital_replacement_cost"),
            recommendation="Introduce EBITDA, EBIT, pre-tax income, net income, and distributable income as distinct fields.",
            measurement_status="legacy_invalid",
        )
    elif full_pnl_enabled:
        bridge_residual = max(
            _max_abs(probes, "firm_pnl_bridge_max_abs_residual"),
            _max_abs(probes, "firm_pnl_interest_cash_counter_residual"),
            _max_abs(probes, "firm_bank_interest_counterparty_residual"),
        )
        pnl_scale = max(1.0, abs(_median(probes, "firm_pnl_revenue", burn)))
        if bridge_residual > 1e-8 * pnl_scale:
            add(
                issue_id="accounting.firm_pnl_bridge_broken", severity="critical", confidence="confirmed",
                category="pnl", detector="firm_profit_bridge",
                claim="The enabled full firm P&L does not reconcile its named income or interest counterparty legs.",
                evidence={"maximum_absolute_bridge_residual": bridge_residual,
                          "tail_revenue_scale": pnl_scale},
                suspected_mechanisms=("income-statement layer mismatch", "interest transfer not mirrored"),
                requested_probes=("firm_pnl_named_legs", "interest_counterparty_reconciliation"),
                recommendation="Stop the run and reconcile the per-firm bridge before interpreting earnings or tax results.",
                measurement_status="invalid_accounting",
            )

    priced_balance_sheet = _median(
        probes, "priced_firm_balance_sheet_enabled", burn
    ) >= 0.5
    cash_nw = abs(_median(probes, "firm_cash_net_worth", burn))
    excluded = _median(probes, "collateral_value_excluded", burn)
    collateral_ratio = _safe_ratio(excluded, max(1.0, cash_nw))
    if (
        not priced_balance_sheet
        and math.isfinite(collateral_ratio)
        and collateral_ratio > 0.25
    ):
        add(
            issue_id="credit.productive_assets_excluded", severity="high", confidence="confirmed",
            category="credit", detector="borrowing_base_gap",
            claim="Productive capital and inventory are economically material but absent from the firm borrowing base.",
            evidence={"excluded_asset_value_to_cash_net_worth": collateral_ratio},
            suspected_mechanisms=("cash-only net worth", "no collateral valuation/haircut"),
            requested_probes=("collateral_counterfactual", "default_recovery"),
            recommendation="Define priced eligible collateral, haircuts, priority, and recovery before changing the lending cap.",
            measurement_status="proxy",
        )
    elif priced_balance_sheet and _median(probes, "firm_eligible_collateral_value", burn) > 0.0:
        add(
            issue_id="credit.collateral_recovery_missing", severity="high", confidence="confirmed",
            category="credit", detector="borrowing_base_scope",
            claim=(
                "Asset prices now govern credit and solvency, but collateral priority, "
                "seizure, sale, and bank recovery remain outside the modeled default path; "
                "loss-given-default is therefore not interpretable."
            ),
            evidence={
                "tail_eligible_collateral_value": _median(
                    probes, "firm_eligible_collateral_value", burn
                ),
                "tail_borrowing_base_proxy": _median(
                    probes, "firm_borrowing_base_proxy", burn
                ),
            },
            suspected_mechanisms=("borrowing-base proxy only", "no collateral recovery journal"),
            requested_probes=("default_recovery", "claim_priority", "collateral_disposal"),
            recommendation=(
                "Keep the proxy label; implement lien priority and a three-leg "
                "borrower-asset/bank-recovery/residual-writeoff journal before interpreting LGD."
            ),
            measurement_status="known_scope_limit",
        )

    # Macro plausibility detectors.  These are broad triage bands, never calibration targets.
    inflation_key = (
        "cpi_fixed_basket_inflation_yoy" if has_national_accounts else "inflation_yoy"
    )
    if has_national_accounts:
        inflation_values = _col(records[burn:], inflation_key)
        observed = _col(records[burn:], "cpi_fixed_basket_inflation_yoy_observed")
        inflation_values = inflation_values[
            np.isfinite(inflation_values) & np.isfinite(observed) & (observed >= 0.5)
        ]
        inflation = float(np.median(inflation_values)) if inflation_values.size else float("nan")
    else:
        inflation = _median(records, inflation_key, burn)
    if math.isfinite(inflation) and (inflation < -0.02 or inflation > 0.08):
        add(
            issue_id="macro.persistent_price_instability", severity="high", confidence="medium",
            category="macro", detector="broad_plausibility_band",
            claim="Tail annual inflation lies outside a broad stable-economy plausibility band.",
            evidence={"tail_median_inflation_yoy": inflation, "band": [-0.02, 0.08]},
            suspected_mechanisms=("cost-side pressure", "nominal anchor", "supply constraints"),
            requested_probes=("price_decomposition", "nominal_anchor_ablation"),
            recommendation="Attribute fixed-basket inflation with paired demand, cost, and supply interventions.",
            measurement_status="valid" if has_national_accounts else "blocked_by_price_index",
        )

    # With a job guarantee, the legacy person/private unemployment series counts JG
    # workers as unemployed even though the five-state labor account classifies them
    # separately.  Use the explicit effective rate for open unemployment and diagnose
    # an oversized buffer stock as its own institutional symptom.
    unemployment = _mean(records, "effective_unemployment", burn)
    if not math.isfinite(unemployment):
        unemployment = _mean(records, "person_unemployment_rate", burn)
    if not math.isfinite(unemployment):
        unemployment = _mean(records, "unemployment_rate", burn)
    if math.isfinite(unemployment) and unemployment > 0.15:
        severity = "critical" if unemployment > 0.30 else "high"
        add(
            issue_id="labor.chronic_slack", severity=severity, confidence="medium", category="labor",
            detector="broad_plausibility_band", claim="The production frontier has chronically high unemployment.",
            evidence={"tail_mean_person_unemployment": unemployment},
            suspected_mechanisms=("demand shortfall", "firm cash constraint", "matching friction", "sector bottleneck"),
            requested_probes=("labor_constraint_decomposition", "demand_stimulus_twin"),
            recommendation="Decompose vacancies, searchers, cash caps, energy caps, and desired output before tuning matching.",
        )

    jg_rate = _mean(records, "jg_employment_rate", burn)
    if math.isfinite(jg_rate) and jg_rate > 0.10:
        add(
            issue_id="labor.large_job_guarantee_buffer", severity="high",
            confidence="high", category="labor", detector="jg_labor_share",
            claim="The job-guarantee buffer persistently employs more than ten per cent of labor supply.",
            evidence={"tail_mean_jg_employment_rate": jg_rate,
                      "tail_mean_effective_unemployment": unemployment},
            suspected_mechanisms=("weak private demand", "whole-person matching", "JG wage/fiscal feedback"),
            requested_probes=("jg_off_twin", "private_vacancy_and_cash_constraint_decomposition"),
            recommendation="Treat JG and open unemployment as separate states and attribute the persistent private-employment gap.",
        )

    fractional_mode = _mean(probes, "labor_fractional_hours", burn)
    underemployment_hours = _mean(records, "labor_underemployment_hours", burn)
    underemployed_heads = _mean(records, "labor_underemployed_heads", burn)
    labor_vacancies = _mean(records, "labor_vacancies", burn)
    labor_supply = _mean(records, "person_labor_supply", burn)
    if (
        fractional_mode >= 0.5
        and math.isfinite(underemployment_hours)
        and underemployment_hours > 0.02 * max(1.0, labor_supply)
        and math.isfinite(labor_vacancies)
        and labor_vacancies > 0.10 * max(1.0, labor_supply)
    ):
        add(
            issue_id="labor.fractional_single_job_fragmentation", severity="high",
            confidence="confirmed", category="labor",
            detector="underemployed_hours_with_open_vacancies",
            claim=("Workers retain material unused hours while firms report large open "
                   "vacancies because fractional mode permits only one private Job per person."),
            evidence={
                "tail_underemployment_hours": underemployment_hours,
                "tail_underemployed_heads": underemployed_heads,
                "tail_open_vacancies": labor_vacancies,
                "tail_labor_supply": labor_supply,
                "one_job_storage": "LaborMarket.jobs: dict[person_id, Job]",
            },
            suspected_mechanisms=(
                "part-time incumbent excluded from new-hire pool",
                "residual hours routed to JG despite private vacancies",
                "job ladder transfers rather than combines relationships",
            ),
            requested_probes=("multi_job_hours_twin", "underemployment_by_firm_gap"),
            recommendation=("Represent multiple concurrent employer-hour contracts or an "
                            "explicit residual-hours matching pass, with wage, tax and "
                            "separation accounting reconciled per contract."),
        )

    output_key = "real_gdp_per_capita" if has_national_accounts else "real_output_per_capita"
    output_growth = _annualized_log_growth(_col(records[burn:], output_key))
    if math.isfinite(output_growth) and (output_growth < -0.03 or output_growth > 0.10):
        add(
            issue_id="macro.implausible_per_capita_growth", severity="high", confidence="medium",
            category="growth", detector="broad_plausibility_band",
            claim="Per-capita real-output growth is persistently contracting or explosive.",
            evidence={"annualized_growth": output_growth, "band": [-0.03, 0.10]},
            suspected_mechanisms=("capital dynamics", "TFP pass-through", "demand constraint"),
            requested_probes=("growth_accounting", "sector_output_decomposition"),
            recommendation="Decompose real GDP growth into sector volumes, capital, labor, and TFP contributions.",
            measurement_status="valid" if has_national_accounts else "blocked_by_gdp",
        )

    pub_factors = _finite(_col(probes, "public_capital_factor"))
    pub_stocks = _finite(_col(probes, "public_capital_stock"))
    jg_capital_flow = _mean(probes, "job_guarantee_capital_units", burn)
    gov_capital_flow = _mean(probes, "government_capital_units", burn)
    if (
        pub_factors.size >= 2
        and pub_stocks.size >= 2
        and pub_factors[-1] > 1.5
        and pub_stocks[-1] > 2.0 * max(1.0, pub_stocks[0])
    ):
        total_public_flow = max(0.0, jg_capital_flow) + max(0.0, gov_capital_flow)
        add(
            issue_id="growth.public_capital_scale_explosion", severity="critical",
            confidence="high", category="growth", detector="public_capital_stock_flow",
            claim="The public-capital productivity multiplier rises above 1.5 within the diagnostic horizon.",
            evidence={
                "initial_public_capital": float(pub_stocks[0]),
                "final_public_capital": float(pub_stocks[-1]),
                "initial_productivity_factor": float(pub_factors[0]),
                "final_productivity_factor": float(pub_factors[-1]),
                "tail_job_guarantee_capital_units_per_tick": jg_capital_flow,
                "tail_government_capital_units_per_tick": gov_capital_flow,
                "jg_share_of_public_capital_flow": _safe_ratio(jg_capital_flow, total_public_flow),
            },
            suspected_mechanisms=(
                "abstract-period JG construction productivity carried into a daily clock",
                "strong public-capital elasticity",
                "self-reinforcing GDP-sized public investment",
            ),
            requested_probes=("jg_productivity_zero_twin", "public_capital_gamma_zero_twin", "time_unit_audit"),
            recommendation="Calibrate construction output per labor-day and validate the public-capital stock against an annual flow/stock ratio.",
        )

    production_rate = _mean(records, "production_realization_rate", burn)
    if math.isfinite(production_rate) and production_rate < 0.70:
        add(
            issue_id="production.plan_realization_failure", severity="high", confidence="high",
            category="production", detector="plan_realization",
            claim="Firms realize less than 70% of planned production for a sustained period.",
            evidence={"tail_mean_realization_rate": production_rate},
            suspected_mechanisms=("labor fill", "cash cap", "energy rationing", "whole-person scale"),
            requested_probes=("production_constraint_decomposition",),
            recommendation="Attribute every unit of the target-output gap to labor, cash, energy, or technical feasibility.",
        )

    investment_rate = _mean(records, "investment_realization_rate", burn)
    investment_target = _mean(records, "investment_target_units", burn)
    if math.isfinite(investment_rate) and investment_target > 1e-6 and investment_rate < 0.40:
        add(
            issue_id="investment.plan_realization_failure", severity="high", confidence="high",
            category="investment", detector="plan_realization",
            claim="Most desired investment fails to become installed capital.",
            evidence={"tail_mean_realization_rate": investment_rate,
                      "tail_mean_target_units": investment_target},
            suspected_mechanisms=("capital-goods stockout", "firm liquidity", "credit cap", "K-sector scale"),
            requested_probes=("investment_order_remainders", "K_sector_footfall"),
            recommendation="Separate cash-, credit-, matching-, and supply-rationed investment quantities.",
        )

    # Whole-person persistent matching uses a hard half-worker eligibility edge at
    # each firm.  Positive K labor demand can therefore be stranded either because it
    # is dispersed across firms or because even a consolidated sector stays below the
    # daily threshold.  The latter is important: subscale exit cannot cure it.
    k_output = _mean(probes, "k_output_units", burn)
    k_inventory = _mean(probes, "k_inventory_units", burn)
    k_firm_count = _mean(probes, "k_firm_count", burn)
    persistent_matching = _mean(probes, "persistent_labor_matching", burn)
    fractional_hours = _mean(probes, "labor_fractional_hours", burn)
    k_demand_total = _mean(probes, "k_labor_demand_total", burn)
    k_demand_max = _mean(probes, "k_labor_demand_max", burn)
    k_heads = _mean(probes, "k_active_worker_heads", burn)
    k_eligible = _mean(probes, "k_firms_above_half_worker_gap", burn)
    if (
        persistent_matching >= 0.5
        and fractional_hours < 0.5
        and investment_target > 1e-6
        and k_output <= 1e-9
        and k_inventory <= 1e-9
        and k_demand_total > 1e-9
        and k_demand_max <= 0.5 + 1e-9
        and k_heads <= 1e-9
        and k_eligible <= 1e-9
    ):
        add(
            issue_id="labor.whole_person_k_sector_deadlock", severity="critical",
            confidence="confirmed", category="labor", detector="firm_gap_distribution",
            claim=("The persistent K sector has investment orders and positive planned labor "
                   "demand, but every firm's gap stays below the half-person hiring edge; "
                   "no worker is hired and no capital good is produced."),
            evidence={
                "tail_k_firm_count": k_firm_count,
                "tail_k_labor_demand_total": k_demand_total,
                "tail_mean_max_firm_demand": k_demand_max,
                "tail_k_active_worker_heads": k_heads,
                "tail_k_output": k_output,
                "tail_investment_target": investment_target,
                "aggregate_demand_above_hiring_edge": k_demand_total > 0.5,
            },
            suspected_mechanisms=(
                "fractional sector demand dispersed across small firms",
                "sector-wide daily demand below one whole-person job",
                "hard >0.5 person hiring threshold",
                "no hours or sector-level vacancy pooling",
            ),
            requested_probes=("spot_vs_persistent_twin", "K_firm_count_scale_sweep"),
            recommendation=("Represent hours/part-time work and accumulate or pool small orders "
                            "across time; do not tune firm count or investment demand merely to "
                            "cross a daily discontinuity."),
        )

    inventory_days = _median(records, "inventory_to_sales", burn)
    if math.isfinite(inventory_days) and inventory_days > 60.0:
        add(
            issue_id="production.excess_inventory", severity="high", confidence="high",
            category="production", detector="inventory_days",
            claim="Consumption-firm inventory exceeds sixty days of sales in a daily-tick economy.",
            evidence={"tail_median_inventory_to_sales": inventory_days},
            suspected_mechanisms=("expectation bias", "inventory gap closure", "demand leakage", "sector mix"),
            requested_probes=("firm_inventory_distribution", "sales_expectation_errors"),
            recommendation="Inspect the firm distribution and expectation errors before changing the aggregate target.",
        )

    energy_unfilled = _mean(records, "energy_unfilled", burn)
    energy_sold = _mean(records, "energy_sold", burn)
    energy_gap = _safe_ratio(energy_unfilled, energy_unfilled + energy_sold)
    if math.isfinite(energy_gap) and energy_gap > 0.05:
        add(
            issue_id="energy.structural_rationing", severity="high", confidence="high", category="energy",
            detector="energy_fill_rate", claim="More than five per cent of energy demand is persistently rationed.",
            evidence={
                "tail_unfilled_share": energy_gap,
                "tail_capacity_utilization": _mean(records, "e_capacity_utilization", burn),
                "tail_restock_share": _mean(records, "energy_restock_share", burn),
                "tail_total_orders": _mean(probes, "energy_orders_total", burn),
                "tail_firm_orders": _mean(probes, "energy_firm_orders", burn),
                "tail_household_orders": _mean(probes, "energy_household_orders", burn),
                "tail_public_orders": _mean(probes, "energy_public_orders", burn),
                "tail_capacity_units": _mean(probes, "energy_capacity_units", burn),
                "tail_expected_demand": _mean(probes, "energy_expected_demand", burn),
                "tail_energy_investment_target": _mean(
                    probes, "energy_investment_target_units", burn,
                ),
                "tail_energy_investment_realized": _mean(
                    probes, "energy_investment_units", burn,
                ),
            },
            suspected_mechanisms=(
                "capacity calibration", "restocking bullwhip",
                "household/industry priority", "buyer affordability",
            ),
            requested_probes=("budget_feasible_energy_demand", "coverage_distribution"),
            recommendation=(
                "Separate supply-constrained demand from buyer affordability, then compare "
                "sector orders with capacity and realized energy-sector investment."
            ),
        )

    if _max_abs(records, "n_bank_failures") > 0.0 or _mean(records, "bank_insolvent", burn) > 0.0:
        add(
            issue_id="banking.solvency_events", severity="high", confidence="confirmed", category="banking",
            detector="bank_failure_flow", claim="Banks fail or remain insolvent in the baseline production environment.",
            evidence={"total_failures": float(np.nansum(_col(records, "n_bank_failures"))),
                      "tail_mean_insolvent": _mean(records, "bank_insolvent", burn)},
            suspected_mechanisms=("writeoffs", "duration losses", "free-funding P&L", "run dynamics"),
            requested_probes=("bank_capital_bridge", "failure_timeline"),
            recommendation="Reconcile each bank's opening capital, earnings, valuation, writeoffs, dividends, and closing capital.",
        )

    if _median(probes, "unified_bank_rwa_enabled", burn) >= 0.5:
        rwa_headroom = _finite(_col(probes[burn:], "bank_rwa_headroom_min"))
        breach_share = float(np.mean(rwa_headroom < -1e-8)) if rwa_headroom.size else 0.0
        if breach_share > 0.05:
            add(
                issue_id="banking.rwa_capital_breach", severity="high", confidence="high",
                category="banking", detector="unified_rwa_headroom",
                claim="At least one live bank remains above its shared risk-weighted asset envelope.",
                evidence={
                    "tail_breach_share": breach_share,
                    "tail_min_rwa_headroom": float(np.min(rwa_headroom)),
                    "tail_mean_max_utilization": _mean(probes, "bank_rwa_utilization_max", burn),
                },
                suspected_mechanisms=("capital loss after origination", "legacy opening exposure", "slow deleveraging"),
                requested_probes=("per_bank_rwa_timeline", "capital_loss_and_repayment_bridge"),
                recommendation=("Separate grandfathered stock breaches from new-credit decisions, then trace "
                                "capital losses, amortization and rejected originations by bank."),
            )

    return tuple(sorted(
        findings,
        key=lambda item: (-{"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}[item.severity], item.issue_id),
    ))
