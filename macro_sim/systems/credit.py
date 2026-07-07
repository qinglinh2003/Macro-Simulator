"""Credit creation and debt-service phase orchestration."""

from __future__ import annotations

from typing import Any

from macro_sim.behavior import planning as B
from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import (
    bank_constraint,
    bank_for,
    grant_loan,
    loan_rate_for,
    pay_bank_dividends,
    refresh_loan_books,
    update_bank_valuation,
)


def run_credit_phase(econ: Any) -> None:
    """Firms and households borrow before markets clear."""
    cfg = econ.cfg.credit
    econ._credit_wage = econ._credit_investment = econ._new_loans = 0.0
    if not cfg.bank_enabled:
        return
    if bank_constraint(econ):
        refresh_loan_books(econ)
    p_k_est = (sum(f.price for f in econ.k_firms) / len(econ.k_firms)) if econ.k_firms else 0.0
    for f in econ.firms:
        deposits = econ.ledger.balance(f.id)
        debt = econ.ledger.debt(f.id)
        requested = B.credit_request(f, deposits, p_k_est)
        if requested > EPS:
            granted = B.credit_grant(requested, deposits, debt, econ.policy.kappa)
            if granted > EPS:
                granted = grant_loan(econ, f.id, granted)
            if granted > EPS:
                econ._new_loans += granted
                wage_need = f.wage * f.labor_demand_notional
                inv_need = f.investment_target * max(0.0, p_k_est)
                tot = wage_need + inv_need
                if tot > EPS:
                    econ._credit_wage += granted * wage_need / tot
                    econ._credit_investment += granted * inv_need / tot
        f.labor_demand_eff = max(0.0, min(f.labor_demand_notional, econ.ledger.balance(f.id) / f.wage))

    econ._hh_credit_new = 0.0
    if cfg.household_credit:
        for h in econ.households:
            deposits = econ.ledger.balance(h.id)
            target, requested = B.household_credit_request(h, deposits, cfg.hh_subsistence)
            h.consumption_budget = target
            if requested > EPS:
                headroom = econ.policy.hh_credit_limit * h.y_expected - econ.ledger.debt(h.id)
                granted = min(requested, max(0.0, headroom))
                if granted > EPS:
                    granted = grant_loan(econ, h.id, granted)
                    econ._hh_credit_new += granted


def run_debt_service_phase(econ: Any) -> None:
    """Borrowers repay principal and interest; banks distribute interest income."""
    cfg = econ.cfg.credit
    econ._interest_paid = econ._principal_repaid = 0.0
    if not cfg.bank_enabled:
        return
    for bk in econ.banks:
        bk.interest_income = 0.0

    for f in econ.firms:
        debt = econ.ledger.debt(f.id)
        deposits = econ.ledger.balance(f.id)
        principal, interest = B.debt_service_amounts(debt, deposits, loan_rate_for(econ, f.id), cfg.amort)
        if principal > EPS:
            econ.ledger.repay(f.id, principal)
            econ._principal_repaid += principal
        if interest > EPS:
            bk = bank_for(econ, f.id)
            econ.ledger.transfer(f.id, bk.id, interest)
            econ._interest_paid += interest
            bk.interest_income += interest

    econ._hh_interest = econ._hh_principal = 0.0
    if cfg.household_credit or cfg.margin_credit:
        for h in econ.households:
            debt = econ.ledger.debt(h.id)
            if debt <= EPS:
                continue
            deposits = econ.ledger.balance(h.id)
            cons_debt = max(0.0, debt - h.margin_debt)
            principal = min(cfg.hh_amort * cons_debt, deposits)
            interest = min(loan_rate_for(econ, h.id) * debt, deposits - principal)
            if principal > EPS:
                econ.ledger.repay(h.id, principal)
                econ._hh_principal += principal
            if interest > EPS:
                bk = bank_for(econ, h.id)
                econ.ledger.transfer(h.id, bk.id, interest)
                econ._hh_interest += interest
                bk.interest_income += interest

    ratio = cfg.bank_target_capital_ratio
    if ratio > 0.0 and len(econ.banks) > 1:
        refresh_loan_books(econ)
    comp = cfg.interbank and cfg.deposit_rate_disp > 0.0 and len(econ.banks) > 1
    for bk in econ.banks:
        bk.profit = bk.interest_income
        capital = econ.ledger.balance(bk.id)
        if ratio > 0.0 and len(econ.banks) > 1:
            target = ratio * econ._loan_book.get(bk.id, 0.0)
            payable = max(0.0, capital - target)
        else:
            payable = min(bk.rho * max(0.0, bk.profit), capital)
        if payable <= EPS:
            continue
        if cfg.bank_equity:
            pay_bank_dividends(econ, bk, payable)
        elif comp:
            own = [
                (h, max(0.0, econ.ledger.balance(h.id)))
                for h in econ.households
                if bank_for(econ, h.id).id == bk.id
            ]
            total_dep = sum(d for _, d in own)
            if total_dep > EPS:
                for h, d in own:
                    amt = min(payable * d / total_dep, econ.ledger.balance(bk.id))
                    if amt > EPS:
                        econ.ledger.transfer(bk.id, h.id, amt)
                        h.income_realized += amt
        elif cfg.interest_by_deposits:
            dep = {h.id: max(0.0, econ.ledger.balance(h.id)) for h in econ.households}
            total_dep = sum(dep.values())
            if total_dep > EPS:
                for h in econ.households:
                    amt = min(payable * dep[h.id] / total_dep, econ.ledger.balance(bk.id))
                    if amt > EPS:
                        econ.ledger.transfer(bk.id, h.id, amt)
                        h.income_realized += amt
        else:
            share = payable / len(econ.households)
            for h in econ.households:
                econ.ledger.transfer(bk.id, h.id, share)
                h.income_realized += share

    update_bank_valuation(econ)
