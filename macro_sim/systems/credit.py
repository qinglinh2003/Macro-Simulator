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
    unified_bank_rwa_enabled,
    update_bank_valuation,
)
from macro_sim.systems.firm_balance_sheet import firm_balance_sheet


def _flow_households(econ: Any) -> list[Any]:
    bridge = getattr(econ, "demographic_bridge", None)
    if bridge is None:
        return list(econ.households)
    return [household for household in econ.households if bridge.household_has_living_members(household.id)]


def run_credit_phase(econ: Any) -> None:
    """Firms and households borrow before markets clear."""
    cfg = econ.cfg.credit
    econ._credit_wage = econ._credit_investment = econ._new_loans = 0.0
    # Diagnostic stock-flow bridge for the two sequential firm-credit constraints.
    # These counters are observability only: they preserve the existing decisions and
    # make it possible to distinguish a non-binding leverage cap from a binding bank-
    # capital/concentration cap.
    econ._firm_credit_requesters = 0
    econ._firm_credit_requested = 0.0
    econ._firm_credit_leverage_allowed = 0.0
    econ._firm_credit_leverage_shortfall = 0.0
    econ._firm_credit_leverage_constrained = 0
    econ._firm_credit_bank_shortfall = 0.0
    econ._firm_credit_dscr_allowed = 0.0
    econ._firm_credit_dscr_shortfall = 0.0
    econ._firm_credit_dscr_constrained = 0
    econ._firm_credit_borrowing_base_proxy = 0.0
    econ._firm_credit_borrowing_base_headroom = 0.0
    econ._firm_credit_borrowing_base_shortfall = 0.0
    econ._firm_credit_borrowing_base_constrained = 0
    if not cfg.bank_enabled:
        return
    if bank_constraint(econ) or unified_bank_rwa_enabled(econ):
        refresh_loan_books(econ)
    p_k_est = (sum(f.price for f in econ.k_firms) / len(econ.k_firms)) if econ.k_firms else 0.0
    for f in econ.firms:
        deposits = econ.ledger.balance(f.id)
        debt = econ.ledger.debt(f.id)
        requested = B.credit_request(f, deposits, p_k_est)
        # CAMPAIGN FIX leg 3 (relocated): a builder whose WIP will complete this
        # tick requests the LAND FEE alongside its wage need, so the development
        # loan flows through the one sanctioned credit channel (the earlier
        # completion-time grant_loan bypassed the CA/NFA reconciliation journals).
        if (
            getattr(econ.cfg, "builder_land_fee_credit", False)
            and getattr(f, "sells", None) == "housing"
            and getattr(f, "wip", 0.0) >= 1.0
        ):
            housing = getattr(econ, "housing", None)
            if housing is not None:
                stock0 = max(1, getattr(econ, "_genesis_dwellings", housing.count()))
                fee = (
                    econ.policy.land_fee_share * econ._house_price
                    * (housing.count() / stock0) ** econ.policy.land_fee_stock_elasticity
                )
                units = int(getattr(f, "wip", 0.0))
                need = max(0.0, fee * units - max(0.0, deposits - requested))
                requested += need
        if requested > EPS:
            econ._firm_credit_requesters += 1
            econ._firm_credit_requested += requested
            book_equity = None
            borrowing_base_proxy = None
            leverage_only = None
            if econ.cfg.priced_firm_balance_sheet:
                balance_sheet = firm_balance_sheet(econ, f)
                book_equity = balance_sheet.book_equity
                borrowing_base_proxy = balance_sheet.borrowing_base_proxy
                econ._firm_credit_borrowing_base_proxy += borrowing_base_proxy
                econ._firm_credit_borrowing_base_headroom += balance_sheet.borrowing_base_headroom
                leverage_only = B.credit_grant(
                    requested,
                    deposits,
                    debt,
                    econ.policy.kappa,
                    book_equity=book_equity,
                )
            leverage_allowed = B.credit_grant(
                requested,
                deposits,
                debt,
                econ.policy.kappa,
                book_equity=book_equity,
                borrowing_base_proxy=borrowing_base_proxy,
            )
            if leverage_only is not None:
                base_shortfall = max(0.0, leverage_only - leverage_allowed)
                econ._firm_credit_borrowing_base_shortfall += base_shortfall
                if base_shortfall > EPS:
                    econ._firm_credit_borrowing_base_constrained += 1
            econ._firm_credit_leverage_allowed += leverage_allowed
            leverage_shortfall = max(0.0, requested - leverage_allowed)
            econ._firm_credit_leverage_shortfall += leverage_shortfall
            if leverage_shortfall > EPS:
                econ._firm_credit_leverage_constrained += 1
            granted = leverage_allowed
            if cfg.monetary_direct_transmission and granted > EPS:
                expected_revenue = max(0.0, f.price) * max(0.0, f.demand_expected)
                expected_wage_cost = max(0.0, f.wage * f.labor_demand_notional)
                expected_energy_cost = max(
                    0.0,
                    f.energy_intensity * f.production_target * f.energy_avg_cost,
                )
                expected_operating_cash_flow = max(
                    0.0,
                    expected_revenue - expected_wage_cost - expected_energy_cost,
                )
                granted = B.credit_grant(
                    requested,
                    deposits,
                    debt,
                    econ.policy.kappa,
                    book_equity=book_equity,
                    borrowing_base_proxy=borrowing_base_proxy,
                    expected_operating_cash_flow=expected_operating_cash_flow,
                    loan_rate=loan_rate_for(econ, f.id),
                    amort=cfg.amort,
                    min_dscr=econ.policy.firm_credit_min_dscr,
                )
                econ._firm_credit_dscr_allowed += granted
                dscr_shortfall = max(0.0, leverage_allowed - granted)
                econ._firm_credit_dscr_shortfall += dscr_shortfall
                if dscr_shortfall > EPS:
                    econ._firm_credit_dscr_constrained += 1
            if granted > EPS:
                leverage_allowed = granted
                granted = grant_loan(econ, f.id, leverage_allowed)
                econ._firm_credit_bank_shortfall += max(0.0, leverage_allowed - granted)
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
        bridge = getattr(econ, "demographic_bridge", None)
        for h in _flow_households(econ):
            deposits = econ.ledger.balance(h.id)
            target, requested = B.household_credit_request(h, deposits, cfg.hh_subsistence)
            h.consumption_budget = target
            if requested > EPS:
                headroom = econ.policy.hh_credit_limit * h.y_expected - econ.ledger.debt(h.id)
                granted = min(requested, max(0.0, headroom))
                if granted > EPS:
                    granted = grant_loan(econ, h.id, granted)
                    if bridge is not None and granted > EPS:
                        bridge.post_household_debt_creation(h.id, granted)
                    econ._hh_credit_new += granted
            # Debt-service cash is deliberately not reserved here.  Credit precedes
            # labor and family transfers, so the authoritative cap belongs at goods
            # ordering where both cash and debt are live and final for consumption.


def _post_firm_interest(econ: Any, firm: Any, interest: float) -> None:
    """Post the one cash leg shared by borrower P&L, bank P&L and ledger."""
    if interest <= EPS:
        return
    bank = bank_for(econ, firm.id)
    econ.ledger.transfer(firm.id, bank.id, interest)
    econ._interest_paid += interest
    bank.interest_income += interest
    bank.loan_interest += interest


def _household_for_account(econ: Any, account_id: str) -> Any | None:
    return next((household for household in econ.households if household.id == account_id), None)


def _open_household_interest_journal(econ: Any, household: Any) -> None:
    """Open one household's memo-interest bridge exactly once per model tick."""
    if household.credit_interest_journal_tick == econ.t:
        return
    household.credit_interest_arrears_opening = max(
        0.0, float(household.credit_interest_arrears)
    )
    household.credit_interest_accrued = 0.0
    household.credit_interest_due = 0.0
    household.credit_interest_cash_paid = 0.0
    household.credit_interest_arrears_extinguished = 0.0
    household.credit_interest_journal_tick = econ.t


def _reconcile_household_mortgage_after_principal_reduction(
    econ: Any,
    household: Any,
) -> None:
    """Clamp the secured shadow immediately after an out-of-band write-off."""
    mortgage_book = getattr(econ, "mortgage_book", None)
    if mortgage_book is None:
        return
    loan = mortgage_book.loans.get(household.id)
    if loan is None:
        return
    debt = max(0.0, float(econ.ledger.debt(household.id)))
    household.margin_debt = min(debt, max(0.0, float(household.margin_debt)))
    ordinary_debt = max(0.0, debt - household.margin_debt)
    loan.balance = min(max(0.0, float(loan.balance)), ordinary_debt)
    if loan.balance <= EPS:
        del mortgage_book.loans[household.id]


def extinguish_household_interest_arrears_for_writeoff(
    econ: Any,
    account_id: str,
    *,
    principal_before: float,
    principal_reduction: float,
) -> float:
    """Extinguish memo interest in proportion to a principal write-off.

    The returned amount is observability only: no ledger loan, bank asset, RWA or
    credit-loss posting is created for the memo claim.  Callers post the principal
    loss through the existing ledger/bank rail before invoking this hook.
    """
    credit_cfg = getattr(getattr(econ, "cfg", None), "credit", None)
    if not getattr(credit_cfg, "household_interest_arrears", False):
        return 0.0
    household = _household_for_account(econ, account_id)
    if household is None:
        return 0.0
    _open_household_interest_journal(econ, household)
    denominator = max(0.0, float(principal_before))
    reduction = min(denominator, max(0.0, float(principal_reduction)))
    arrears_before = max(0.0, float(household.credit_interest_arrears))
    if denominator <= EPS or reduction <= EPS or arrears_before <= EPS:
        _reconcile_household_mortgage_after_principal_reduction(econ, household)
        return 0.0
    extinguished = min(arrears_before, arrears_before * reduction / denominator)
    household.credit_interest_arrears = max(0.0, arrears_before - extinguished)
    household.credit_interest_arrears_extinguished += extinguished
    _reconcile_household_mortgage_after_principal_reduction(econ, household)
    econ._hh_interest_arrears_extinguished = sum(
        item.credit_interest_arrears_extinguished
        for item in econ.households
        if item.credit_interest_journal_tick == econ.t
    )
    return extinguished


def run_firm_debt_service_phase(econ: Any, *, reset: bool = True) -> None:
    """Settle firm principal and interest, optionally opening the firm journal.

    Full-P&L runs carry unpaid contractual interest explicitly but recognize an
    expense and bank income only for the amount actually transferred.  The
    legacy branch is intentionally the historical implementation verbatim.
    """
    cfg = econ.cfg.credit
    if reset:
        econ._interest_paid = econ._principal_repaid = 0.0
    if not cfg.bank_enabled:
        return

    if cfg.firm_full_pnl:
        econ._firm_interest_accrued = 0.0
        econ._firm_interest_due = 0.0
        econ._firm_interest_shortfall = 0.0
        for firm in econ.firms:
            debt = econ.ledger.debt(firm.id)
            deposits = econ.ledger.balance(firm.id)
            rate = loan_rate_for(econ, firm.id)
            accrued = max(0.0, rate * debt)
            arrears_open = max(0.0, float(firm.pnl_interest_arrears))
            due = arrears_open + accrued
            # Contractual waterfall: cure old arrears and service current
            # interest before returning principal.  The former principal-first
            # order could report a successful amortization while rolling every
            # cent of interest even though the borrower had cash available.
            interest = min(due, deposits)
            principal = (
                min(cfg.amort * debt, max(0.0, deposits - interest))
                if debt > EPS else 0.0
            )

            firm.pnl_interest_accrued = accrued
            firm.pnl_interest_arrears_opening = arrears_open
            firm.pnl_interest_due = due
            firm.pnl_interest_expense = interest
            firm.pnl_interest_shortfall = max(0.0, due - interest)
            firm.pnl_interest_arrears = firm.pnl_interest_shortfall
            econ._firm_interest_accrued += accrued
            econ._firm_interest_due += due
            econ._firm_interest_shortfall += firm.pnl_interest_shortfall

            # Post in contractual priority order as well as computing it that
            # way.  `_post_firm_interest` recognizes bank income only for this
            # actual cash transfer; the remaining memo arrears never become a
            # bank asset or RWA exposure.
            _post_firm_interest(econ, firm, interest)
            if principal > EPS:
                econ.ledger.repay(firm.id, principal)
                econ._principal_repaid += principal
        return

    for f in econ.firms:
        debt = econ.ledger.debt(f.id)
        deposits = econ.ledger.balance(f.id)
        principal, interest = B.debt_service_amounts(debt, deposits, loan_rate_for(econ, f.id), cfg.amort)
        if principal > EPS:
            econ.ledger.repay(f.id, principal)
            econ._principal_repaid += principal
        _post_firm_interest(econ, f, interest)


def run_household_debt_service_phase(econ: Any, *, reset: bool = True) -> None:
    """Settle household credit at the scheduler's borrower-service point."""
    cfg = econ.cfg.credit
    if reset:
        econ._hh_interest = econ._hh_principal = 0.0
    if not cfg.bank_enabled:
        return

    if getattr(cfg, "household_interest_arrears", False):
        # Open every household, including one emptied earlier in this tick.  The
        # tick tag preserves any probate write-off already posted before service.
        for household in econ.households:
            _open_household_interest_journal(econ, household)
        bridge = getattr(econ, "demographic_bridge", None)
        for household in _flow_households(econ):
            debt = max(0.0, float(econ.ledger.debt(household.id)))
            arrears = max(0.0, float(household.credit_interest_arrears))
            if debt <= EPS and arrears <= EPS:
                continue
            deposits = max(0.0, float(econ.ledger.balance(household.id)))
            accrued = max(0.0, loan_rate_for(econ, household.id) * debt)
            due = arrears + accrued
            # Contractual priority: old memo interest and current interest receive
            # cash before ordinary (consumer + mortgage) principal.  Margin
            # principal remains callable only in the equity phase.
            cash_interest = min(due, deposits)
            ordinary_debt = max(0.0, debt - household.margin_debt)
            principal = min(
                cfg.hh_amort * ordinary_debt,
                max(0.0, deposits - cash_interest),
            )

            household.credit_interest_accrued = accrued
            household.credit_interest_due = due
            household.credit_interest_cash_paid = cash_interest
            household.credit_interest_arrears = max(0.0, due - cash_interest)

            if cash_interest > EPS:
                bank = bank_for(econ, household.id)
                econ.ledger.transfer(household.id, bank.id, cash_interest)
                if bridge is not None:
                    bridge.post_household_cash_delta(
                        household.id,
                        -cash_interest,
                        reason="interest_payment",
                    )
                econ._hh_interest += cash_interest
                # Banks recognize only the cash leg.  Closing memo arrears never
                # enter bank income, principal, loan books or RWA.
                bank.interest_income += cash_interest
                bank.loan_interest += cash_interest
            if principal > EPS:
                mortgage_book = getattr(econ, "mortgage_book", None)
                if mortgage_book is not None:
                    mortgage_book.apply_ordinary_principal_repayment(
                        household.id,
                        principal,
                        ordinary_debt,
                    )
                econ.ledger.repay(household.id, principal)
                if bridge is not None:
                    bridge.post_household_debt_repayment(household.id, principal)
                econ._hh_principal += principal

        current = [
            household for household in econ.households
            if household.credit_interest_journal_tick == econ.t
        ]
        econ._hh_interest_arrears_opening = sum(
            household.credit_interest_arrears_opening for household in current
        )
        econ._hh_interest_accrued = sum(
            household.credit_interest_accrued for household in current
        )
        econ._hh_interest_due = sum(
            household.credit_interest_due for household in current
        )
        econ._hh_interest_arrears = sum(
            household.credit_interest_arrears for household in current
        )
        econ._hh_interest_arrears_extinguished = sum(
            household.credit_interest_arrears_extinguished for household in current
        )
        return

    if cfg.household_credit or cfg.margin_credit:
        bridge = getattr(econ, "demographic_bridge", None)
        for h in _flow_households(econ):
            debt = econ.ledger.debt(h.id)
            if debt <= EPS:
                continue
            deposits = econ.ledger.balance(h.id)
            cons_debt = max(0.0, debt - h.margin_debt)
            principal = min(cfg.hh_amort * cons_debt, deposits)
            interest = min(loan_rate_for(econ, h.id) * debt, deposits - principal)
            if principal > EPS:
                mortgage_book = getattr(econ, "mortgage_book", None)
                if mortgage_book is not None:
                    mortgage_book.apply_ordinary_principal_repayment(
                        h.id,
                        principal,
                        cons_debt,
                    )
                econ.ledger.repay(h.id, principal)
                if bridge is not None:
                    bridge.post_household_debt_repayment(h.id, principal)
                econ._hh_principal += principal
            if interest > EPS:
                bk = bank_for(econ, h.id)
                econ.ledger.transfer(h.id, bk.id, interest)
                if bridge is not None:
                    bridge.post_household_cash_delta(h.id, -interest, reason="interest_payment")
                econ._hh_interest += interest
                bk.interest_income += interest
                bk.loan_interest += interest


def run_debt_service_phase(econ: Any) -> None:
    """Historical combined borrower phase (the default-off scheduling path)."""
    econ._interest_paid = econ._principal_repaid = 0.0
    if not econ.cfg.credit.bank_enabled:
        return
    if not getattr(econ.cfg.credit, "bank_realized_pnl", False):
        # Exact historical journal-opening point.  The realized-P&L frontier
        # instead opens all named income/loss legs at tick start.
        for bank in econ.banks:
            bank.interest_income = 0.0
            bank.loan_interest = 0.0
            bank.dividends_paid = 0.0
    run_firm_debt_service_phase(econ, reset=False)
    run_household_debt_service_phase(econ, reset=True)
    if not getattr(econ.cfg.credit, "bank_realized_pnl", False):
        # Preserve the pre-v23 phase order: gross-interest distribution and
        # bank valuation occurred immediately after borrower service, before
        # firm entry, equity trading, interbank settlement and failure handling.
        _finalize_bank_pnl_legacy(econ, econ.cfg.credit)


def _finalize_bank_pnl_legacy(econ: Any, cfg: Any) -> None:
    """Certified pre-v23 gross-interest payout and valuation path.

    This deliberately preserves the historical target-capital rule, including
    its distribution of capital above target rather than only current earnings.
    It is a compatibility surface, not the economically preferred accounting
    model; production diagnostics enable ``bank_realized_pnl`` below.
    """
    ratio = econ.policy.bank_target_capital_ratio   # B4a
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
            bridge = getattr(econ, "demographic_bridge", None)
            own = [
                (h, max(0.0, econ.ledger.balance(h.id)))
                for h in _flow_households(econ)
                if bank_for(econ, h.id).id == bk.id
            ]
            total_dep = sum(d for _, d in own)
            if total_dep > EPS:
                for h, d in own:
                    amt = min(payable * d / total_dep, econ.ledger.balance(bk.id))
                    if amt > EPS:
                        econ.ledger.transfer(bk.id, h.id, amt)
                        if bridge is not None:
                            bridge.post_capital_income(h.id, amt)
                        h.income_realized += amt
        elif cfg.interest_by_deposits:
            bridge = getattr(econ, "demographic_bridge", None)
            households = _flow_households(econ)
            dep = {h.id: max(0.0, econ.ledger.balance(h.id)) for h in households}
            total_dep = sum(dep.values())
            if total_dep > EPS:
                for h in households:
                    amt = min(payable * dep[h.id] / total_dep, econ.ledger.balance(bk.id))
                    if amt > EPS:
                        econ.ledger.transfer(bk.id, h.id, amt)
                        if bridge is not None:
                            bridge.post_capital_income(h.id, amt)
                        h.income_realized += amt
        else:
            bridge = getattr(econ, "demographic_bridge", None)
            households = _flow_households(econ)
            if households:
                share = payable / len(households)
                for h in households:
                    econ.ledger.transfer(bk.id, h.id, share)
                    if bridge is not None:
                        bridge.post_capital_income(h.id, share)
                    h.income_realized += share
    update_bank_valuation(econ)


def _pay_deposit_funding_cost(econ: Any, cfg: Any) -> None:
    """v23: contractual deposit interest -- the bank's cost of funds.

    Each depositor is paid `deposit_rate * their deposit` by THEIR OWN bank, capped by that
    bank's live cash (A4). It is a real, money-conserving transfer (bank -> household), booked
    as `bk.deposit_funding_cost` so it reduces realized profit before dividends. This is the leg
    the P&L was missing: without it deposits are free, a bank cannot suffer a net-interest-margin
    squeeze, and a higher policy rate only ever raises bank profit. deposit_rate = 0 => no
    transfer => bit-identical.
    """
    # [N] deposit_rate_floor: a regulatory floor over the config (technology) rate
    rate = max(float(getattr(cfg, "deposit_rate", 0.0)), econ.policy.deposit_rate_floor)
    track_arrears = bool(getattr(econ.cfg, "deposit_interest_arrears", False))
    if rate <= 0.0 and not track_arrears:
        return
    bridge = getattr(econ, "demographic_bridge", None)
    led = econ.ledger

    # -- pass 1: CURRENT interest, cash-capped; any shortfall becomes an IOU --
    # CAMPAIGN FIX (X8 silent default): the cash cap used to make unpaid interest
    # VANISH -- a cash-starved bank stiffed depositors with no record (owed ~167/tick,
    # paid 0.23, zero liability anywhere). With deposit_interest_arrears=True the
    # shortfall accrues on the bank as a pooled arrears stock. Flag off = bit-identical.
    holders: dict = {}
    for h in _flow_households(econ):
        dep = led.balance(h.id)
        if dep <= EPS:
            continue
        bk = bank_for(econ, h.id)
        if bk is None:
            continue
        owed = rate * dep
        interest = min(owed, max(0.0, led.balance(bk.id)))
        if track_arrears and owed - interest > EPS:
            bk.deposit_interest_arrears = (
                getattr(bk, "deposit_interest_arrears", 0.0) + (owed - interest)
            )
        if interest > EPS:
            led.transfer(bk.id, h.id, interest)
            bk.deposit_funding_cost += interest
            if bridge is not None:
                bridge.post_capital_income(h.id, interest)
            h.income_realized += interest
        holders.setdefault(bk.id, []).append((h, dep))

    # -- pass 2: arrears repayment, PRIORITY over dividends (runs before P&L close),
    # pro-rata by current deposits (the pooled-IOU approximation; per-creditor
    # ledgers are a later refinement, documented) --
    if track_arrears:
        for bk in econ.banks:
            arrears = getattr(bk, "deposit_interest_arrears", 0.0)
            if arrears <= EPS:
                continue
            cash = max(0.0, led.balance(bk.id))
            pay_total = min(arrears, cash)
            if pay_total <= EPS:
                continue
            entries = holders.get(bk.id, ())
            dep_sum = sum(d for _, d in entries)
            if dep_sum <= EPS:
                continue
            paid = 0.0
            for h, dep in entries:
                share = pay_total * (dep / dep_sum)
                if share <= EPS:
                    continue
                led.transfer(bk.id, h.id, share)
                bk.deposit_funding_cost += share
                if bridge is not None:
                    bridge.post_capital_income(h.id, share)
                h.income_realized += share
                paid += share
            bk.deposit_interest_arrears = max(0.0, arrears - paid)


def finalize_bank_pnl(econ: Any) -> None:
    """Close realized bank P&L, distribute only net earnings, then value banks.

    The journal contains cash legs that already exist in the model: loan interest,
    government-bond coupons and interbank interest, less interbank and external
    interest paid and ledger-backed credit write-offs.  No synthetic deposit funding
    or operating cost is accrued here.
    """
    cfg = econ.cfg.credit
    if not cfg.bank_enabled:
        return
    if not getattr(cfg, "bank_realized_pnl", False):
        # The compatibility branch already closed at its historical scheduler
        # position in ``run_debt_service_phase``.
        return

    ratio = econ.policy.bank_target_capital_ratio   # B4a
    if ratio > 0.0 and len(econ.banks) > 1:
        refresh_loan_books(econ)
    # v23 COST OF FUNDS: pay contractual interest to depositors BEFORE forming profit. Until now
    # bk.profit was gross interest income with NO funding cost -- deposits were free money, so a
    # bank could never suffer a net-interest-margin squeeze and a rising policy rate only ever
    # RAISED bank profit. `interest_by_deposits` looked related but is a DISTRIBUTION rule (it
    # splits leftover DIVIDENDS by deposit share); it is not a cost that hits the P&L. This pays a
    # real, money-conserving deposit rate and books it as the missing expense leg. rate 0 => no
    # payment => bit-identical.
    _pay_deposit_funding_cost(econ, cfg)
    comp = cfg.interbank and cfg.deposit_rate_disp > 0.0 and len(econ.banks) > 1
    for bk in econ.banks:
        # Keep the legacy field as the loan-interest alias while exposing every
        # realized leg separately on Bank.
        bk.interest_income = bk.loan_interest
        bk.profit = (
            bk.loan_interest
            + bk.bond_coupon
            + bk.interbank_interest_income
            - bk.interbank_interest_expense
            - bk.external_interest_expense
            - bk.deposit_funding_cost
            - bk.realized_credit_losses
        )
        capital = max(0.0, econ.ledger.balance(bk.id))
        if not bk.alive or bk.profit <= EPS or capital <= EPS:
            continue
        if ratio > 0.0 and len(econ.banks) > 1:
            target = ratio * econ._loan_book.get(bk.id, 0.0)
            # Target-capital mode may distribute current positive earnings only to
            # the extent that post-loss capital exceeds the target.  Capital itself
            # is never reclassified as profit.
            payable = min(bk.profit, max(0.0, capital - target), capital)
        else:
            payable = min(bk.rho * max(0.0, bk.profit), capital)
        if payable <= EPS:
            continue
        if cfg.bank_equity:
            bk.dividends_paid += pay_bank_dividends(econ, bk, payable)
        elif comp:
            bridge = getattr(econ, "demographic_bridge", None)
            own = [
                (h, max(0.0, econ.ledger.balance(h.id)))
                for h in _flow_households(econ)
                if bank_for(econ, h.id).id == bk.id
            ]
            total_dep = sum(d for _, d in own)
            if total_dep > EPS:
                for h, d in own:
                    amt = min(payable * d / total_dep, econ.ledger.balance(bk.id))
                    if amt > EPS:
                        econ.ledger.transfer(bk.id, h.id, amt)
                        if bridge is not None:
                            bridge.post_capital_income(h.id, amt)
                        h.income_realized += amt
                        bk.dividends_paid += amt
        elif cfg.interest_by_deposits:
            bridge = getattr(econ, "demographic_bridge", None)
            households = _flow_households(econ)
            dep = {h.id: max(0.0, econ.ledger.balance(h.id)) for h in households}
            total_dep = sum(dep.values())
            if total_dep > EPS:
                for h in households:
                    amt = min(payable * dep[h.id] / total_dep, econ.ledger.balance(bk.id))
                    if amt > EPS:
                        econ.ledger.transfer(bk.id, h.id, amt)
                        if bridge is not None:
                            bridge.post_capital_income(h.id, amt)
                        h.income_realized += amt
                        bk.dividends_paid += amt
        else:
            bridge = getattr(econ, "demographic_bridge", None)
            households = _flow_households(econ)
            if households:
                share = payable / len(households)
                for h in households:
                    econ.ledger.transfer(bk.id, h.id, share)
                    if bridge is not None:
                        bridge.post_capital_income(h.id, share)
                    h.income_realized += share
                    bk.dividends_paid += share

    update_bank_valuation(econ)
