"""Priced firm assets, equity-market book value, and lending-base proxy.

The productive stocks on :class:`~macro_sim.domain.agents.Firm` are physical
quantities and never ledger money.  This module is the single conversion seam
between those quantities and nominal balance-sheet values:

* productive capital is measured at the last committed replacement-capital
  transaction price;
* finished output and work in progress are measured at the lower of posted
  realizable value and observable current unit replacement cost;
* energy-input inventory is measured at its carried average purchase cost;
* loan principal is a ledger liability, while unpaid contractual interest is
  a separate firm memo liability; both are subtracted exactly once from book
  equity, but only principal remains a bank loan asset/RWA exposure;
* the lending surface applies explicit haircuts and is deliberately named a
  ``borrowing_base_proxy``.  The simulator does not yet model liens, priority,
  seizure, or collateral sale on default, so this is not a recovery model.

``priced_firm_balance_sheet=False`` keeps the historical equity formula behind
one compatibility branch.  All equity consumers call the same helper, so the
legacy dimensional shortcut cannot be copied into genesis, entry, and the live
equity phase independently again.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from macro_sim.behavior import planning as behavior_planning
from macro_sim.systems.firm_accounting import committed_replacement_capital_price


@dataclass(frozen=True)
class FirmBalanceSheet:
    """One read-only, nominal replacement-cost view of a firm's assets."""

    cash: float
    debt: float
    interest_arrears: float

    capital_units: float
    capital_unit_price: float
    capital_value: float

    output_inventory_units: float
    output_inventory_posted_price: float
    output_inventory_unit_cost: float
    output_inventory_unit_price: float
    output_inventory_value: float
    work_in_progress_units: float
    work_in_progress_unit_price: float
    work_in_progress_value: float
    input_inventory_units: float
    input_inventory_unit_cost: float
    input_inventory_value: float
    inventory_value: float

    gross_assets: float
    book_equity: float

    capital_haircut: float
    inventory_haircut: float
    eligible_collateral_value: float
    borrowing_base_proxy: float
    borrowing_base_headroom: float


def _observable_output_inventory_cost(firm: Any) -> float:
    """Return a conservative, current replacement-cost proxy per output unit.

    The model does not carry historical finished-goods cost lots.  Its pricing
    rule does expose the planned variable unit cost and, when enabled, the
    allocated capital-service term.  If those inputs cannot produce a finite,
    positive cost (for example a zero-capital shell), the conservative fallback
    is zero rather than letting an unaudited posted quote collateralize stock.
    """

    try:
        capital_unit_cost = max(
            0.0,
            float(getattr(firm, "pricing_capital_unit_cost", 0.0)),
        )
        cost = float(behavior_planning.unit_cost(firm, capital_unit_cost))
    except (AssertionError, TypeError, ValueError, ZeroDivisionError):
        return 0.0
    return cost if math.isfinite(cost) and cost > 0.0 else 0.0


def firm_balance_sheet(econ: Any, firm: Any) -> FirmBalanceSheet:
    """Build the authoritative priced view without posting any ledger entry.

    Revaluation changes observation and decision inputs only.  It never creates
    deposits, retires debt, or books a gain into cash P&L.
    """

    cash = max(0.0, float(econ.ledger.balance(firm.id)))
    debt = max(0.0, float(econ.ledger.debt(firm.id)))
    # Contractual interest that could not be paid is a real liability of the
    # borrower even though the cash-basis bank journal has not recognized it as
    # income.  Keep it outside the ledger loan stock: capitalizing this memo into
    # principal would manufacture a bank asset, RWA and broad-money/debt entry
    # without a matching cash or loan transaction.
    interest_arrears = max(
        0.0,
        float(getattr(firm, "pnl_interest_arrears", 0.0)),
    )

    capital_units = max(0.0, float(getattr(firm, "capital", 0.0)))
    capital_unit_price = max(0.0, float(committed_replacement_capital_price(econ)))
    capital_value = capital_units * capital_unit_price

    output_inventory_units = max(0.0, float(getattr(firm, "inventory", 0.0)))
    output_inventory_posted_price = max(0.0, float(getattr(firm, "price", 0.0)))
    output_inventory_unit_cost = _observable_output_inventory_cost(firm)
    output_inventory_unit_price = min(
        output_inventory_posted_price,
        output_inventory_unit_cost,
    )
    output_inventory_value = output_inventory_units * output_inventory_unit_price

    work_in_progress_units = max(0.0, float(getattr(firm, "wip", 0.0)))
    work_in_progress_unit_price = output_inventory_unit_price
    work_in_progress_value = work_in_progress_units * work_in_progress_unit_price

    input_inventory_units = max(0.0, float(getattr(firm, "energy_stock", 0.0)))
    input_inventory_unit_cost = max(0.0, float(getattr(firm, "energy_avg_cost", 0.0)))
    input_inventory_value = input_inventory_units * input_inventory_unit_cost

    inventory_value = (
        output_inventory_value
        + work_in_progress_value
        + input_inventory_value
    )
    gross_assets = cash + capital_value + inventory_value
    book_equity = gross_assets - debt - interest_arrears

    cfg = econ.cfg
    capital_haircut = float(cfg.firm_capital_haircut)
    inventory_haircut = float(cfg.firm_inventory_haircut)
    eligible_collateral_value = (
        (1.0 - capital_haircut) * capital_value
        + (1.0 - inventory_haircut) * inventory_value
    )
    # Gross-principal ceiling at the pre-origination snapshot.  Interest
    # arrears consume otherwise available cash/collateral before a new lender
    # can rely on it, but remain outside principal and bank RWA.  Existing loan
    # principal is deducted exactly once below to obtain additional headroom.
    borrowing_base_proxy = max(
        0.0,
        cash + eligible_collateral_value - interest_arrears,
    )
    borrowing_base_headroom = max(0.0, borrowing_base_proxy - debt)

    return FirmBalanceSheet(
        cash=cash,
        debt=debt,
        interest_arrears=interest_arrears,
        capital_units=capital_units,
        capital_unit_price=capital_unit_price,
        capital_value=capital_value,
        output_inventory_units=output_inventory_units,
        output_inventory_posted_price=output_inventory_posted_price,
        output_inventory_unit_cost=output_inventory_unit_cost,
        output_inventory_unit_price=output_inventory_unit_price,
        output_inventory_value=output_inventory_value,
        work_in_progress_units=work_in_progress_units,
        work_in_progress_unit_price=work_in_progress_unit_price,
        work_in_progress_value=work_in_progress_value,
        input_inventory_units=input_inventory_units,
        input_inventory_unit_cost=input_inventory_unit_cost,
        input_inventory_value=input_inventory_value,
        inventory_value=inventory_value,
        gross_assets=gross_assets,
        book_equity=book_equity,
        capital_haircut=capital_haircut,
        inventory_haircut=inventory_haircut,
        eligible_collateral_value=eligible_collateral_value,
        borrowing_base_proxy=borrowing_base_proxy,
        borrowing_base_headroom=borrowing_base_headroom,
    )


def firm_equity_book_value(econ: Any, firm: Any) -> float:
    """Return the equity market's book-value input.

    The opt-in branch is dimensionally nominal.  The compatibility branch is
    intentionally the historical expression so an explicit ``False`` remains
    bit-identical to an omitted flag while every caller shares one migration
    point.
    """

    if getattr(econ.cfg, "priced_firm_balance_sheet", False):
        return firm_balance_sheet(econ, firm).book_equity
    return (
        float(econ.ledger.balance(firm.id))
        - float(econ.ledger.debt(firm.id))
        + float(firm.capital)
    )


def entrant_equity_book_value(
    econ: Any,
    firm: Any,
    *,
    legacy_startup_deposits: float,
    legacy_capital_value: float,
) -> float:
    """Return an entrant's initial equity book input through the same seam.

    Historical entry happened to use the purchase cash cost when real startup
    capital was available, while genesis/live equity added physical units.  The
    explicit legacy arguments preserve that difference only while the migration
    flag is off; enabled runs use the same balance sheet as every other consumer.
    """

    if getattr(econ.cfg, "priced_firm_balance_sheet", False):
        return firm_balance_sheet(econ, firm).book_equity
    return float(legacy_startup_deposits) + float(legacy_capital_value)


def firm_return_asset_base(econ: Any, firm: Any) -> float:
    """Denominator for firm return metrics, with a legacy compatibility path."""

    if getattr(econ.cfg, "priced_firm_balance_sheet", False):
        return firm_balance_sheet(econ, firm).gross_assets
    return (
        float(econ.ledger.balance(firm.id))
        + float(econ.ledger.debt(firm.id))
        + float(firm.capital)
    )
