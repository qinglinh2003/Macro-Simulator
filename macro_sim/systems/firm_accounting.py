"""Optional full cash-basis income statements for production firms.

The legacy simulator calls EBITDA-like operating earnings ``Firm.profit``.  The
``firm_full_pnl`` frontier flag keeps that path untouched while giving enabled
runs an explicit bridge from revenue to retained earnings.  Productive capital
and investment remain real/asset-stock quantities; only replacement-cost
depreciation is translated into a nominal expense here.
"""

from __future__ import annotations

from typing import Any

from macro_sim.markets.matching import EPS


def reset_firm_pnl_flows(firm: Any) -> None:
    """Open a firm's tick P&L while preserving its unpaid-interest stock."""
    firm.pnl_revenue = 0.0
    firm.pnl_revenue_carry_opening = 0.0
    firm.pnl_intermediate_inputs = 0.0
    firm.pnl_compensation = 0.0
    firm.pnl_ebitda = 0.0
    firm.pnl_capital_price = 0.0
    firm.pnl_depreciation = 0.0
    firm.pnl_ebit = 0.0
    firm.pnl_interest_accrued = 0.0
    firm.pnl_interest_arrears_opening = 0.0
    firm.pnl_interest_due = 0.0
    firm.pnl_interest_expense = 0.0
    firm.pnl_interest_shortfall = 0.0
    firm.pnl_pre_tax_income = 0.0
    firm.pnl_profit_tax = 0.0
    firm.pnl_windfall_tax = 0.0
    firm.pnl_net_income = 0.0
    firm.pnl_dividends_paid = 0.0
    firm.pnl_retained_earnings = 0.0


def replacement_capital_price(econ: Any) -> float:
    """Return the current transaction price of capital, otherwise hold last.

    Capital is a physical stock, so ``delta_K * capital`` cannot be subtracted
    from nominal revenue directly.  Realized K-good sales supply the current
    unit value.  A no-trade tick holds the last realized price, seeded by the
    configured genesis K price.  The state exists when full P&L or capital-service
    pricing is enabled, and is shared so accounting and pricing cannot disagree
    about the valuation unit.
    """
    quantity = sum(max(0.0, float(firm.sales)) for firm in econ.k_firms)
    if quantity > EPS:
        value = sum(max(0.0, float(firm.revenue)) for firm in econ.k_firms)
        price = value / quantity
        if price > EPS:
            econ._firm_pnl_capital_price = price
            return price
    held = float(getattr(econ, "_firm_pnl_capital_price", 0.0))
    if held > EPS:
        return held
    price = max(EPS, float(econ.cfg.p_kfirm0))
    econ._firm_pnl_capital_price = price
    return price


def committed_replacement_capital_price(econ: Any) -> float:
    """Read the last settled capital-goods unit value for synchronous planning.

    Planning must not inspect this tick's transactions.  The held price is updated
    only in settlement, after capital-market clearing, and seeded by ``p_kfirm0``.
    """
    held = float(getattr(econ, "_firm_pnl_capital_price", 0.0))
    return held if held > EPS else max(EPS, float(econ.cfg.p_kfirm0))


def prepare_firm_income_statement(firm: Any, capital_price: float) -> None:
    """Close operating and financing flows through pre-tax cash income."""
    # Transactions posted after the prior settlement cutoff (currently startup
    # capital sold during firm entry) are carried into this statement.  The
    # stock is consumed exactly once; ordinary in-window sales use ``revenue``.
    carry = max(0.0, float(firm.pnl_revenue_carry))
    firm.pnl_revenue_carry_opening = carry
    firm.pnl_revenue = float(firm.revenue) + carry
    firm.pnl_revenue_carry = 0.0
    firm.pnl_intermediate_inputs = max(0.0, float(firm.energy_cost_used))
    firm.pnl_compensation = max(0.0, float(firm.wagebill))
    firm.pnl_ebitda = (
        firm.pnl_revenue
        - firm.pnl_intermediate_inputs
        - firm.pnl_compensation
    )
    firm.pnl_capital_price = max(0.0, float(capital_price))
    firm.pnl_depreciation = (
        max(0.0, float(firm.delta_K))
        * max(0.0, float(firm.capital))
        * firm.pnl_capital_price
    )
    firm.pnl_ebit = firm.pnl_ebitda - firm.pnl_depreciation
    # Cash basis: only interest actually transferred is an expense.  Contractual
    # interest not paid is visible in the arrears stock and never becomes bank
    # income until a matching ledger transfer occurs.
    firm.pnl_pre_tax_income = firm.pnl_ebit - firm.pnl_interest_expense


def close_firm_income_statement(firm: Any, profit_tax: float, windfall_tax: float) -> None:
    """Close taxes and publish the compatibility earnings field.

    Under full P&L, ``Firm.profit`` deliberately migrates to *net income*.
    Equity residual income, entry/exit signals, sector switching and reporting
    therefore consume the same shareholder-income layer.  The named P&L fields
    remain authoritative for code that needs EBIT or pre-tax income.
    """
    firm.pnl_profit_tax = max(0.0, float(profit_tax))
    firm.pnl_windfall_tax = max(0.0, float(windfall_tax))
    firm.pnl_net_income = (
        firm.pnl_pre_tax_income
        - firm.pnl_profit_tax
        - firm.pnl_windfall_tax
    )
    firm.profit = firm.pnl_net_income


def close_firm_distributions(firm: Any, dividends_paid: float) -> None:
    """Record actual distributions and the residual retained-earnings flow."""
    firm.pnl_dividends_paid = max(0.0, float(dividends_paid))
    firm.pnl_retained_earnings = firm.pnl_net_income - firm.pnl_dividends_paid


def firm_earnings(econ: Any, firm: Any) -> float:
    """Canonical earnings read for valuation and cross-firm return signals."""
    if getattr(econ.cfg, "firm_full_pnl", False):
        return float(firm.pnl_net_income)
    return float(firm.profit)
