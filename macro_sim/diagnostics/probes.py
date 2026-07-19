"""Immutable deep-state probes collected after each completed economy tick."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import bank_economic_capital, bank_rwa_exposure, loan_rate_for
from macro_sim.systems.firm_balance_sheet import firm_balance_sheet
from macro_sim.systems.planning import CAPITAL_SERVICE_PRICED_SECTORS


def _finite(value: float, default: float = 0.0) -> float:
    value = float(value)
    return value if math.isfinite(value) else default


def _mean(values) -> float:
    values = list(values)
    return float(sum(values) / len(values)) if values else 0.0


@dataclass
class DeepProbeCollector:
    """Collect quantities that the legacy metrics layer cannot safely recompute.

    The collector only reads state after ``Economy.step`` has produced its official record.
    In particular it never invokes the metrics collector, which has cross-tick side effects.
    """

    previous_prices: dict[str, tuple[float, float]] = field(default_factory=dict)
    previous_unit_value: float | None = None
    previous_inventories: dict[str, tuple[float, float]] = field(default_factory=dict)
    previous_rent_paid_total: float = 0.0

    def collect(self, econ: Any, record: dict[str, float]) -> dict[str, float]:
        ledger = econ.ledger
        c_firms = list(econ.c_firms)
        k_firms = list(getattr(econ, "k_firms", ()))
        e_firms = list(getattr(econ, "e_firms", ()))
        firms = list(econ.firms)
        pnl_firms = firms + list(getattr(econ, "_exited_firms_tick", ()))

        price_map = {f.id: (max(EPS, float(f.price)), max(0.0, float(f.sales))) for f in c_firms}
        matched_log_change = float("nan")
        if self.previous_prices:
            matched = [fid for fid in price_map if fid in self.previous_prices]
            weights = [self.previous_prices[fid][1] for fid in matched]
            total_weight = sum(weights)
            if matched and total_weight <= EPS:
                weights = [1.0] * len(matched)
                total_weight = float(len(matched))
            if total_weight > EPS:
                matched_log_change = sum(
                    weight * math.log(price_map[fid][0] / self.previous_prices[fid][0])
                    for fid, weight in zip(matched, weights)
                ) / total_weight

        unit_value = max(EPS, float(record.get("price_index", 0.0)))
        unit_value_log_change = (
            math.log(unit_value / self.previous_unit_value)
            if self.previous_unit_value is not None and self.previous_unit_value > EPS
            else float("nan")
        )
        composition_log_change = (
            unit_value_log_change - matched_log_change
            if math.isfinite(unit_value_log_change) and math.isfinite(matched_log_change)
            else float("nan")
        )

        p_k = _mean(f.price for f in k_firms if f.price > EPS)
        if p_k <= EPS:
            p_k = max(EPS, float(record.get("capital_price_index", 1.0)))

        # Housing is produced through WIP and then minted/listed; counting only the
        # builder's finished inventory gives a negative GDP contribution when an old
        # new-build sells and misses construction completed into WIP.  Exclude it from
        # the generic inventory bridge and value current construction separately.
        nonhousing_firms = [f for f in firms if getattr(f, "sells", None) != "housing"]
        builders = list(getattr(econ, "builders", ()))
        inventory_map = {
            f.id: (max(0.0, float(f.inventory)), max(EPS, float(f.price)))
            for f in nonhousing_firms
        }
        output_inventory_value = sum(quantity * price for quantity, price in inventory_map.values())
        # Asset/collateral diagnostics need a broader perimeter than national-
        # accounts inventory investment: include builders' finished homes/WIP and
        # downstream energy input inventories on their own valuation bases.
        balance_sheet_inventory_value = sum(
            max(0.0, float(f.inventory)) * max(EPS, float(f.price)) for f in firms
        ) + sum(
            max(0.0, float(getattr(f, "wip", 0.0))) * max(EPS, float(f.price))
            for f in builders
        ) + sum(
            max(0.0, float(getattr(f, "energy_stock", 0.0)))
            * max(EPS, float(getattr(f, "energy_avg_cost", 0.0)))
            for f in firms
        )
        # A value-stock difference confounds quantity accumulation with holding gains.
        # Reprice quantity changes at the current quote for surviving/new firms and
        # at the last quote for exits; keep the revaluation residual separately.
        inventory_quantity_change_value = 0.0
        if self.previous_inventories:
            for firm_id in sorted(set(inventory_map) | set(self.previous_inventories)):
                current_q, current_p = inventory_map.get(firm_id, (0.0, 0.0))
                previous_q, previous_p = self.previous_inventories.get(firm_id, (0.0, current_p))
                valuation_price = current_p if firm_id in inventory_map else previous_p
                inventory_quantity_change_value += (current_q - previous_q) * valuation_price
        previous_inventory_at_old_prices = sum(
            quantity * price for quantity, price in self.previous_inventories.values()
        )
        inventory_revaluation = (
            output_inventory_value - previous_inventory_at_old_prices - inventory_quantity_change_value
            if self.previous_inventories else 0.0
        )

        household_goods_spend = sum(max(0.0, float(h.spent)) for h in econ.households)
        housing_construction_output = sum(
            max(0.0, float(f.produced)) * max(EPS, float(f.price)) for f in builders
        )
        rental = getattr(econ, "rental_market", None)
        cumulative_rent = float(getattr(rental, "rent_paid_total", 0.0)) if rental is not None else 0.0
        market_rent_flow = max(0.0, cumulative_rent - self.previous_rent_paid_total)
        imputed_owner_rent = 0.0
        housing = getattr(econ, "housing", None)
        if rental is not None and housing is not None:
            tenanted = set(rental.tenancies)
            owner_occupied = sum(
                any(dwelling.id not in tenanted for dwelling in housing.dwellings_of(h.id))
                for h in econ.households
            )
            imputed_owner_rent = owner_occupied * max(0.0, float(rental.rent_level))
        net_product_taxes = (
            max(0.0, float(getattr(econ, "_tax_consumption", 0.0)))
            + max(0.0, float(getattr(econ, "_tax_energy", 0.0)))
        )
        final_demand_proxy = (
            household_goods_spend
            + max(0.0, float(getattr(econ, "_gov_consumption", 0.0)))
            # JG labor creates own-account public works that are capitalized directly
            # rather than purchased from K firms; compensation is its observable
            # production-cost value in the expenditure/production bridge.
            + max(0.0, float(getattr(econ, "_jg_spending", 0.0)))
            + max(0.0, float(record.get("investment_spending", 0.0)))
            + max(0.0, float(getattr(econ, "_energy_hh_spend", 0.0)))
            + housing_construction_output
            + market_rent_flow
            + imputed_owner_rent
            + net_product_taxes
            + inventory_quantity_change_value
        )

        full_firm_pnl = bool(getattr(econ.cfg, "firm_full_pnl", False))
        firm_interest_due = 0.0
        firm_debt = 0.0
        for firm in firms:
            debt = max(0.0, ledger.debt(firm.id))
            firm_debt += debt
            if full_firm_pnl:
                firm_interest_due += max(0.0, float(firm.pnl_interest_due))
            elif debt > EPS:
                firm_interest_due += max(0.0, loan_rate_for(econ, firm.id)) * debt

        if getattr(econ.cfg, "household_interest_arrears", False):
            household_interest_due = float(record.get("household_interest_due", 0.0))
        else:
            household_interest_due = 0.0
            for household in econ.households:
                debt = max(0.0, ledger.debt(household.id))
                if debt > EPS:
                    household_interest_due += max(0.0, loan_rate_for(econ, household.id)) * debt

        priced_firm_assets = bool(getattr(econ.cfg, "priced_firm_balance_sheet", False))
        firm_sheets = (
            [firm_balance_sheet(econ, firm) for firm in firms]
            if priced_firm_assets else []
        )
        if priced_firm_assets:
            capital_value = sum(sheet.capital_value for sheet in firm_sheets)
            balance_sheet_inventory_value = sum(sheet.inventory_value for sheet in firm_sheets)
        else:
            capital_value = sum(max(0.0, f.capital) * p_k for f in firms)
        depreciation_value = (
            sum(float(f.pnl_depreciation) for f in firms)
            if full_firm_pnl
            else sum(
                max(0.0, f.delta_K) * max(0.0, getattr(f, "capital_prev", f.capital)) * p_k
                for f in firms
            )
        )
        reported_profit = sum(float(f.profit) for f in firms)
        corrected_profit_proxy = (
            reported_profit
            if full_firm_pnl
            else reported_profit - firm_interest_due - depreciation_value
        )
        pnl_revenue = sum(float(f.pnl_revenue) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_intermediate = sum(float(f.pnl_intermediate_inputs) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_compensation = sum(float(f.pnl_compensation) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_ebitda = sum(float(f.pnl_ebitda) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_depreciation = sum(float(f.pnl_depreciation) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_ebit = sum(float(f.pnl_ebit) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_interest_accrued = sum(float(f.pnl_interest_accrued) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_cash_interest = sum(float(f.pnl_interest_expense) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_pre_tax = sum(float(f.pnl_pre_tax_income) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_profit_tax = sum(float(f.pnl_profit_tax) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_windfall_tax = sum(float(f.pnl_windfall_tax) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_net_income = sum(float(f.pnl_net_income) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_dividends = sum(float(f.pnl_dividends_paid) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_retained = sum(float(f.pnl_retained_earnings) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_arrears = sum(float(f.pnl_interest_arrears) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_revenue_carry = sum(float(f.pnl_revenue_carry) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_reported_profit = sum(float(f.profit) for f in pnl_firms) if full_firm_pnl else 0.0
        pnl_bridge_residuals = (
            pnl_ebitda - (pnl_revenue - pnl_intermediate - pnl_compensation),
            pnl_ebit - (pnl_ebitda - pnl_depreciation),
            pnl_pre_tax - (pnl_ebit - pnl_cash_interest),
            pnl_net_income - (pnl_pre_tax - pnl_profit_tax - pnl_windfall_tax),
            pnl_retained - (pnl_net_income - pnl_dividends),
            pnl_reported_profit - pnl_net_income,
        ) if full_firm_pnl else (0.0,) * 6
        pnl_bridge_max_residual = max(abs(value) for value in pnl_bridge_residuals)
        firm_cash_net_worth = sum(ledger.balance(f.id) - ledger.debt(f.id) for f in firms)
        firm_asset_net_worth = (
            sum(sheet.book_equity for sheet in firm_sheets)
            if priced_firm_assets
            else firm_cash_net_worth + capital_value + balance_sheet_inventory_value
        )
        eligible_collateral_value = (
            sum(sheet.eligible_collateral_value for sheet in firm_sheets)
            if priced_firm_assets else 0.0
        )
        borrowing_base_proxy = (
            sum(sheet.borrowing_base_proxy for sheet in firm_sheets)
            if priced_firm_assets else 0.0
        )

        bank_profit = sum(float(bank.profit) for bank in econ.banks)
        bank_interest_income = sum(float(bank.interest_income) for bank in econ.banks)
        bank_external_interest_expense = sum(
            float(bank.external_interest_expense) for bank in econ.banks
        )
        bank_book_capital = sum(float(ledger.balance(bank.id)) for bank in econ.banks)
        bank_econ_capital = sum(float(bank_economic_capital(econ, bank)) for bank in econ.banks)
        unified_rwa = bool(getattr(econ.cfg, "unified_bank_rwa", False))
        alive_banks = [bank for bank in econ.banks if bank.alive]
        rwa_exposures = (
            [bank_rwa_exposure(econ, bank, use_cache=False) for bank in alive_banks]
            if unified_rwa else []
        )
        rwa_ratio = max(EPS, float(getattr(econ.policy, "mortgage_min_capital_ratio", 0.0)))
        rwa_limits = (
            [max(0.0, bank_economic_capital(econ, bank)) / rwa_ratio for bank in alive_banks]
            if unified_rwa else []
        )
        rwa_headrooms = [limit - exposure for limit, exposure in zip(rwa_limits, rwa_exposures)]
        rwa_utilization = [
            exposure / limit if limit > EPS else (1.0 if exposure > EPS else 0.0)
            for exposure, limit in zip(rwa_exposures, rwa_limits)
        ]

        min_inventory = min((float(f.inventory) for f in firms), default=0.0)
        min_capital = min((float(f.capital) for f in firms), default=0.0)
        min_deposit = min((float(ledger.balance(agent.id)) for agent in [*econ.households, *firms]), default=0.0)

        # Persistent employment is person-valued.  A sector can carry positive
        # fractional demand while every individual firm's gap is below the hard
        # half-person hiring threshold.  The problem can survive consolidation when
        # even the sector total is sub-threshold, so preserve both the matching mode
        # and firm distribution instead of only the aggregate labor demand.
        k_labor_demands = [max(0.0, float(f.labor_demand_eff)) for f in k_firms]
        k_active_heads: list[float] = []
        k_active_fte: list[float] = []
        k_active_effective: list[float] = []
        labor_market = getattr(econ, "labor_market", None)
        if labor_market is not None:
            for firm in k_firms:
                roster = labor_market.rosters.get(firm.id, ())
                active = [pid for pid in roster if pid not in labor_market.suspended]
                k_active_heads.append(float(len(active)))
                k_active_fte.append(float(sum(labor_market.jobs[pid].hours for pid in active)))
                k_active_effective.append(float(sum(
                    labor_market.jobs[pid].hours * labor_market.e_of(pid) for pid in active
                )))
        else:
            k_active_heads = [max(0.0, float(f.hired)) for f in k_firms]
            k_active_fte = list(k_active_heads)
            k_active_effective = list(k_active_heads)
        fractional_hours = bool(
            labor_market is not None and labor_market.fractional_hours
        )
        gap_inputs = k_active_effective if fractional_hours else k_active_heads
        k_hiring_gaps = [
            max(0.0, demand - supplied)
            for demand, supplied in zip(k_labor_demands, gap_inputs)
        ]

        probe = {
            "t": float(record.get("t", econ.t)),
            "unit_value": unit_value,
            "equal_weight_posted_price": _mean(f.price for f in c_firms),
            "matched_price_log_change": matched_log_change,
            "unit_value_log_change": unit_value_log_change,
            "composition_log_change": composition_log_change,
            "household_goods_spend": household_goods_spend,
            "inventory_value": output_inventory_value,
            "balance_sheet_inventory_value": balance_sheet_inventory_value,
            "inventory_change_value": inventory_quantity_change_value,
            "inventory_revaluation": inventory_revaluation,
            "final_demand_proxy": final_demand_proxy,
            "housing_construction_output_proxy": housing_construction_output,
            "market_rent_flow": market_rent_flow,
            "imputed_owner_rent_proxy": imputed_owner_rent,
            "net_product_taxes_proxy": net_product_taxes,
            "reported_nominal_output": float(record.get("nominal_output", 0.0)),
            "all_sector_revenue": sum(float(f.revenue) for f in firms),
            "c_sector_revenue": sum(float(f.revenue) for f in c_firms),
            "k_sector_revenue": sum(float(f.revenue) for f in k_firms),
            "e_sector_revenue": sum(float(f.revenue) for f in e_firms),
            "reported_firm_profit": reported_profit,
            "firm_full_pnl_enabled": float(full_firm_pnl),
            "capital_service_pricing_enabled": float(
                bool(getattr(econ.cfg, "capital_service_pricing", False))
            ),
            "capital_service_cost_planned": sum(
                max(0.0, float(getattr(f, "pricing_capital_service_cost", 0.0)))
                for f in firms if f.sells in CAPITAL_SERVICE_PRICED_SECTORS
            ),
            "capital_service_cost_allocated": sum(
                max(0.0, float(getattr(f, "pricing_capital_unit_cost", 0.0)))
                * max(0.0, float(f.production_target))
                for f in firms if f.sells in CAPITAL_SERVICE_PRICED_SECTORS
            ),
            "firm_pnl_revenue": pnl_revenue,
            "firm_pnl_intermediate_inputs": pnl_intermediate,
            "firm_pnl_compensation": pnl_compensation,
            "firm_pnl_ebitda": pnl_ebitda,
            "firm_pnl_depreciation": pnl_depreciation,
            "firm_pnl_ebit": pnl_ebit,
            "firm_pnl_interest_accrued": pnl_interest_accrued,
            "firm_pnl_cash_interest": pnl_cash_interest,
            "firm_pnl_pre_tax_income": pnl_pre_tax,
            "firm_pnl_profit_tax": pnl_profit_tax,
            "firm_pnl_windfall_tax": pnl_windfall_tax,
            "firm_pnl_tax_total": pnl_profit_tax + pnl_windfall_tax,
            "firm_pnl_net_income": pnl_net_income,
            "firm_pnl_dividends_paid": pnl_dividends,
            "firm_pnl_retained_earnings": pnl_retained,
            "firm_pnl_interest_arrears": pnl_arrears,
            "firm_pnl_post_close_revenue_carry": pnl_revenue_carry,
            "firm_pnl_profit_compatibility_residual": reported_profit - pnl_net_income if full_firm_pnl else 0.0,
            "firm_pnl_bridge_max_abs_residual": pnl_bridge_max_residual,
            "firm_pnl_interest_cash_counter_residual": (
                pnl_cash_interest - float(getattr(econ, "_interest_paid", 0.0))
                if full_firm_pnl else 0.0
            ),
            "firm_bank_interest_counterparty_residual": (
                sum(float(bank.loan_interest) for bank in econ.banks)
                - pnl_cash_interest
                - float(getattr(econ, "_hh_interest", 0.0))
                if full_firm_pnl else 0.0
            ),
            "firm_interest_due_proxy": firm_interest_due,
            "household_interest_due_proxy": household_interest_due,
            "household_interest_arrears_opening": float(
                record.get("household_interest_arrears_opening", 0.0)
            ),
            "household_interest_accrued": float(
                record.get("household_interest_accrued", 0.0)
            ),
            "household_interest_due": float(
                record.get("household_interest_due", 0.0)
            ),
            "household_interest_cash_paid": float(
                record.get("household_interest_cash_paid", 0.0)
            ),
            "household_interest_arrears_closing": float(
                record.get("household_interest_arrears_closing", 0.0)
            ),
            "household_interest_arrears_extinguished": float(
                record.get("household_interest_arrears_extinguished", 0.0)
            ),
            "household_interest_arrears_stock_flow_residual": float(
                record.get("household_interest_arrears_stock_flow_residual", 0.0)
            ),
            "capital_depreciation_value_proxy": depreciation_value,
            "corrected_firm_profit_proxy": corrected_profit_proxy,
            "firm_debt": firm_debt,
            "capital_value_proxy": capital_value,
            "priced_firm_balance_sheet_enabled": float(priced_firm_assets),
            "firm_cash_net_worth": firm_cash_net_worth,
            "firm_asset_net_worth_proxy": firm_asset_net_worth,
            "firm_eligible_collateral_value": eligible_collateral_value,
            "firm_borrowing_base_proxy": borrowing_base_proxy,
            "collateral_value_excluded": (
                0.0 if priced_firm_assets
                else capital_value + balance_sheet_inventory_value
            ),
            "bank_reported_profit": bank_profit,
            "bank_interest_income": bank_interest_income,
            "bank_external_interest_expense": bank_external_interest_expense,
            "bank_book_capital": bank_book_capital,
            "bank_economic_capital": bank_econ_capital,
            "unified_bank_rwa_enabled": float(unified_rwa),
            "bank_rwa_total": sum(rwa_exposures),
            "bank_rwa_limit_total": sum(rwa_limits),
            "bank_rwa_headroom_min": min(rwa_headrooms, default=0.0),
            "bank_rwa_utilization_max": max(rwa_utilization, default=0.0),
            "writeoffs": float(record.get("writeoffs", 0.0)),
            "dividends_paid": float(record.get("dividends_paid", 0.0)),
            "investment_target_units": float(record.get("investment_target_units", 0.0)),
            "investment_units": float(record.get("investment_units", 0.0)),
            "k_output_units": sum(max(0.0, float(f.produced)) for f in k_firms),
            "k_inventory_units": sum(max(0.0, float(f.inventory)) for f in k_firms),
            "k_sales_units": sum(max(0.0, float(f.sales)) for f in k_firms),
            "k_firm_count": float(len(k_firms)),
            "persistent_labor_matching": float(labor_market is not None),
            "labor_fractional_hours": float(fractional_hours),
            "k_labor_demand_total": sum(k_labor_demands),
            "k_labor_demand_max": max(k_labor_demands, default=0.0),
            "k_active_worker_heads": sum(k_active_heads),
            "k_active_worker_fte": sum(k_active_fte),
            "k_active_effective_labor": sum(k_active_effective),
            "k_hiring_gap_total": sum(k_hiring_gaps),
            "k_firms_above_half_worker_gap": float(sum(gap > 0.5 for gap in k_hiring_gaps)),
            "energy_household_orders_proxy": float(
                getattr(econ.cfg, "energy_hh_share", 0.0)
                * getattr(econ.cfg, "w_firm0", 0.0)
                / max(EPS, getattr(econ.cfg, "p_efirm0", 1.0))
                * len(econ.households)
            ) if getattr(econ.cfg, "energy_household", False) else 0.0,
            "energy_household_filled": float(getattr(econ, "_energy_hh_units", 0.0)),
            "energy_orders_total": float(getattr(econ, "_energy_orders_total", 0.0)),
            "energy_firm_orders": float(getattr(econ, "_energy_orders_firms", 0.0)),
            "energy_household_orders": float(
                getattr(econ, "_energy_orders_households", 0.0)
            ),
            "energy_public_orders": float(getattr(econ, "_energy_orders_public", 0.0)),
            "energy_capacity_units": sum(
                max(0.0, float(f.capacity_kappa * f.capital)) for f in e_firms
            ),
            "energy_expected_demand": sum(
                max(0.0, float(f.demand_expected)) for f in e_firms
            ),
            "energy_investment_target_units": sum(
                max(0.0, float(f.investment_target)) for f in e_firms
            ),
            "energy_investment_units": sum(
                max(0.0, float(f.investment)) for f in e_firms
            ),
            "public_capital_stock": float(getattr(econ, "public_capital", 0.0)),
            "public_capital_factor": float(getattr(econ, "_pubcap_factor", 1.0)),
            "public_capital_reference": float(getattr(econ, "K_ref", 0.0)),
            "government_capital_units": float(getattr(econ, "_gov_capital_units", 0.0)),
            "job_guarantee_capital_units": float(getattr(econ, "_jg_capital_units", 0.0)),
            "job_guarantee_workers": float(getattr(econ, "_jg_employment", 0.0)),
            "credit_requested_proxy": sum(
                max(0.0, f.wage * f.labor_demand_notional
                    + f.investment_target * p_k - ledger.balance(f.id))
                for f in firms
            ),
            "firm_credit_requested": float(getattr(econ, "_firm_credit_requested", 0.0)),
            "firm_credit_leverage_allowed": float(
                getattr(econ, "_firm_credit_leverage_allowed", 0.0)
            ),
            "firm_credit_leverage_shortfall": float(
                getattr(econ, "_firm_credit_leverage_shortfall", 0.0)
            ),
            "firm_credit_leverage_constrained_share": (
                float(getattr(econ, "_firm_credit_leverage_constrained", 0.0))
                / max(1.0, float(getattr(econ, "_firm_credit_requesters", 0.0)))
            ),
            "firm_credit_bank_shortfall": float(
                getattr(econ, "_firm_credit_bank_shortfall", 0.0)
            ),
            "firm_credit_dscr_allowed": float(
                getattr(econ, "_firm_credit_dscr_allowed", 0.0)
            ),
            "firm_credit_dscr_shortfall": float(
                getattr(econ, "_firm_credit_dscr_shortfall", 0.0)
            ),
            "firm_credit_dscr_constrained_share": (
                float(getattr(econ, "_firm_credit_dscr_constrained", 0.0))
                / max(1.0, float(getattr(econ, "_firm_credit_requesters", 0.0)))
            ),
            "household_debt_service_reserved": float(
                getattr(econ, "_hh_debt_service_reserved", 0.0)
            ),
            "household_contractual_debt_service_due": float(
                record.get("household_contractual_debt_service_due", 0.0)
            ),
            "household_interest_arrears_in_goods_reservation": float(
                record.get("household_interest_arrears_in_goods_reservation", 0.0)
            ),
            "policy_rate": float(getattr(econ, "_rate", 0.0)),
            "credit_kappa": float(getattr(econ.policy, "kappa", 0.0)),
            "government_deficit_target": float(getattr(econ.policy, "gov_deficit_target", 0.0)),
            "energy_shock_active": float(getattr(econ, "_energy_shock_active", 0.0)),
            "min_inventory": min_inventory,
            "min_capital": min_capital,
            "min_nonbank_deposit": min_deposit,
            "nonfinite_official_values": float(sum(
                1 for value in record.values()
                if isinstance(value, (int, float, np.number)) and not math.isfinite(float(value))
            )),
        }

        self.previous_prices = price_map
        self.previous_unit_value = unit_value
        self.previous_inventories = inventory_map
        self.previous_rent_paid_total = cumulative_rent
        return probe
