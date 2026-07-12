"""Settlement, household fiscal flows, and capital-stock commitment."""

from __future__ import annotations

from typing import Any

from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import bank_equity_value


def _household_labor_supply(econ: Any, household: Any) -> float:
    bridge = getattr(econ, "demographic_bridge", None)
    return bridge.household_labor_supply(household.id) if bridge is not None else 1.0


def _flow_households(econ: Any) -> list[Any]:
    bridge = getattr(econ, "demographic_bridge", None)
    if bridge is None:
        return list(econ.households)
    return [household for household in econ.households if bridge.household_has_living_members(household.id)]


def run_settlement_phase(econ: Any) -> None:
    cfg = econ.cfg.settlement
    flow_households = _flow_households(econ)
    n_h = len(flow_households)
    pol, gov = econ.policy, cfg.government
    econ._tax_profit = econ._tax_income = econ._tax_wealth = econ._benefit_paid = 0.0
    econ._pension_paid = 0.0
    econ._tax_energy_windfall = 0.0      # v17.2 per-tick reset
    econ._jg_spending = econ._jg_capital_units = econ._jg_employment = 0.0   # v9.3 job guarantee

    # (i) firms pay dividends (cash-capped, A4) into the CLEARING account.
    total_div = 0.0
    div_by_firm = {}                               # firm_id -> payable (v8.4 pro-rata payout)
    for f in econ.firms:
        # investment is NOT a cost (asset swap); energy USED is opex (v17.0; 0 when off,
        # and x - 0.0 == x exactly, so the pre-energy baseline stays bit-identical)
        f.profit = f.revenue - f.wagebill - f.energy_cost_used
        f.dividend_shortfall = 0.0
        ptax = 0.0
        if gov and pol.tax_profit_rate > 0.0 and f.profit > EPS:
            ptax = min(pol.tax_profit_rate * f.profit, econ.ledger.balance(f.id))
            if ptax > EPS:
                econ.ledger.transfer(f.id, econ._fiscal, ptax)
                econ._tax_profit += ptax
        wtax = 0.0                                     # v17.2 windfall surtax on E-firms (0.0 => exact no-op)
        if gov and pol.tax_energy_windfall > 0.0 and f.sells == "energy" and f.profit > EPS:
            wtax = min(pol.tax_energy_windfall * max(0.0, f.profit - ptax), econ.ledger.balance(f.id))
            if wtax > EPS:
                econ.ledger.transfer(f.id, econ._fiscal, wtax)
                econ._tax_energy_windfall = getattr(econ, "_tax_energy_windfall", 0.0) + wtax
        div_pool = f.rho * max(0.0, f.profit - ptax - wtax)   # only positive after-tax profit pays out
        if div_pool <= EPS:
            continue
        payable = min(div_pool, econ.ledger.balance(f.id))
        f.dividend_shortfall = div_pool - payable
        if payable <= EPS:
            continue
        econ.ledger.transfer(f.id, "CLEARING", payable)
        total_div += payable
        div_by_firm[f.id] = payable

    # (ii) distribute the CLEARING pool to households. The last recipient absorbs float remainder.
    econ._dividends_paid = total_div
    if total_div > EPS and n_h > 0:
        bridge = getattr(econ, "demographic_bridge", None)
        if cfg.pro_rata_dividends and cfg.per_firm_equity:
            so = {f.id: f.shares_outstanding for f in econ.c_firms}
            for h in flow_households:
                amt = 0.0
                for fid, sh in h.holdings.items():
                    pay, tot = div_by_firm.get(fid, 0.0), so.get(fid, 0.0)
                    if pay > EPS and sh > EPS and tot > EPS:
                        amt += pay * (sh / tot)
                if amt > EPS:
                    econ.ledger.transfer("CLEARING", h.id, amt)
                    if bridge is not None:
                        bridge.post_capital_income(h.id, amt)
                    h.income_realized += amt
            residual = econ.ledger.balance("CLEARING")
            if residual > EPS:
                share = residual / n_h
                for h in flow_households[:-1]:
                    econ.ledger.transfer("CLEARING", h.id, share)
                    if bridge is not None:
                        bridge.post_capital_income(h.id, share)
                    h.income_realized += share
                last = flow_households[-1]
                rem = econ.ledger.balance("CLEARING")
                if rem > EPS:
                    econ.ledger.transfer("CLEARING", last.id, rem)
                    if bridge is not None:
                        bridge.post_capital_income(last.id, rem)
                    last.income_realized += rem
        else:
            share = total_div / n_h
            for h in flow_households[:-1]:
                econ.ledger.transfer("CLEARING", h.id, share)
                if bridge is not None:
                    bridge.post_capital_income(h.id, share)
                h.income_realized += share
            last = flow_households[-1]
            remainder = econ.ledger.balance("CLEARING")
            if remainder > EPS:
                econ.ledger.transfer("CLEARING", last.id, remainder)
                if bridge is not None:
                    bridge.post_capital_income(last.id, remainder)
                last.income_realized += remainder

    # v9 household fiscal: progressive income tax, unemployment benefit, wealth tax.
    if gov:
        run_household_fiscal_phase(econ)

    # Capital accumulation committed: productive next tick.
    for f in econ.investing_firms:
        f.capital_prev = f.capital
        f.capital = (1.0 - f.delta_K) * f.capital + f.investment
    if cfg.gov_investment_share > 0.0 or econ.policy.job_guarantee:
        econ.public_capital = (
            (1.0 - cfg.public_capital_depreciation) * econ.public_capital
            + getattr(econ, "_gov_capital_units", 0.0)
            + getattr(econ, "_jg_capital_units", 0.0)
        )


def run_household_fiscal_phase(econ: Any) -> None:
    cfg = econ.cfg.settlement
    pol, led, hh = econ.policy, econ.ledger, _flow_households(econ)
    n_h = len(hh)
    bridge = getattr(econ, "demographic_bridge", None)

    if pol.tax_income_rate > 0.0:
        mean_inc = sum(h.income_realized for h in hh) / max(1, n_h)
        allowance = pol.income_allowance * mean_inc
        for h in hh:
            base = max(0.0, h.income_realized - allowance)
            tax = min(pol.tax_income_rate * base, led.balance(h.id))
            if tax > EPS:
                led.transfer(h.id, econ._fiscal, tax)
                if bridge is not None:
                    bridge.post_household_tax_payment(h.id, tax)
                h.income_realized -= tax
                econ._tax_income += tax

    if pol.job_guarantee and pol.jg_wage_ratio > 0.0:
        wage_ref = sum(f.wage for f in econ.firms) / max(1, len(econ.firms))
        jg_wage = max(pol.jg_wage_ratio * wage_ref, pol.min_wage)
        for h in hh:
            resid = max(0.0, _household_labor_supply(econ, h) - h.labor_sold)
            pay = jg_wage * resid
            if pay > EPS:
                led.transfer(econ._fiscal, h.id, pay)
                if bridge is not None:
                    bridge.post_transfer_income(h.id, pay, reason="job_guarantee")
                h.income_realized += pay
                h.jg_labor = resid
                econ._jg_spending += pay
                econ._jg_employment += resid
        econ._jg_capital_units = cfg.jg_productivity * econ._jg_employment

    if pol.benefit_replacement > 0.0:
        wage_ref = sum(f.wage for f in econ.firms) / max(1, len(econ.firms))
        for h in hh:
            ben = pol.benefit_replacement * wage_ref * max(
                0.0,
                _household_labor_supply(econ, h) - h.labor_sold - h.jg_labor,
            )
            if ben > EPS:
                led.transfer(econ._fiscal, h.id, ben)
                if bridge is not None:
                    bridge.post_transfer_income(h.id, ben, reason="unemployment_benefit")
                h.income_realized += ben
                econ._benefit_paid += ben

    if getattr(pol, "pension_replacement", 0.0) > 0.0 and bridge is not None:
        # v13 old-age pension: the demographic economy's only transfer to non-workers. The JG
        # and unemployment benefit both key off labor supply, so elders received NOTHING --
        # savings-poor elder households sat on the consumption floor for entire runs.
        wage_ref = sum(f.wage for f in econ.firms) / max(1, len(econ.firms))
        for h in hh:
            elders = bridge.household_profile(h.id).elder_count
            if elders <= 0:
                continue
            pen = pol.pension_replacement * wage_ref * elders
            if pen > EPS:
                led.transfer(econ._fiscal, h.id, pen)
                bridge.post_transfer_income(h.id, pen, reason="pension")
                h.income_realized += pen
                econ._pension_paid = getattr(econ, "_pension_paid", 0.0) + pen
                econ._benefit_paid += pen

    if pol.tax_wealth_rate > 0.0:
        po = {f.id: getattr(f, "share_price", 0.0) for f in econ.c_firms}
        housing = getattr(econ, "housing", None)
        include_housing = housing is not None and getattr(pol, "housing_in_wealth_tax", False)
        nw_of = {}
        for h in hh:
            eq = sum(sh * po.get(fid, 0.0) for fid, sh in h.holdings.items())
            nw_of[h.id] = led.balance(h.id) + eq + bank_equity_value(econ, h.id) - led.debt(h.id)
            if include_housing:
                # v15.5 live lever: dwellings enter the wealth-tax base at market value
                # (exempt by default -- the real-world owner-occupier exemption)
                nw_of[h.id] += housing.units_of(h.id) * econ._house_price
        allowance = pol.wealth_allowance * (sum(max(0.0, v) for v in nw_of.values()) / max(1, n_h))
        for h in hh:
            base = max(0.0, nw_of[h.id] - allowance)
            wtax = min(pol.tax_wealth_rate * base, led.balance(h.id))
            if wtax > EPS:
                led.transfer(h.id, econ._fiscal, wtax)
                if bridge is not None:
                    bridge.post_household_tax_payment(h.id, wtax)
                econ._tax_wealth += wtax
