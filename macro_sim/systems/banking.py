"""Banking-system phase orchestration."""

from __future__ import annotations

import math
import random
from typing import Any

from macro_sim.domain.agents import Bank, InterbankClaim
from macro_sim.markets.matching import EPS


def draw_bank_kappas(cfg: Any, n: int) -> list:
    if n <= 1 or cfg.bank_leverage_disp <= 0.0:
        return [cfg.bank_leverage_mean] * max(1, n)
    rng = random.Random(cfg.seed + 71177)
    dispersion = cfg.bank_leverage_disp
    mu = -0.5 * dispersion * dispersion
    return [
        max(1.0, cfg.bank_leverage_mean * rng.lognormvariate(mu, dispersion))
        for _ in range(n)
    ]


def draw_bank_spreads(econ: Any) -> None:
    cfg = econ.cfg.banking
    if not cfg.bank_rate_competition or cfg.bank_spread_disp <= 0.0:
        econ._bank_spread = {bank.id: 0.0 for bank in econ.banks}
        return
    rng = random.Random(cfg.seed + 82301)
    raw = {bank.id: rng.gauss(0.0, cfg.bank_spread_disp) for bank in econ.banks}
    mean = sum(raw.values()) / len(raw)
    econ._bank_spread = {bank_id: spread - mean for bank_id, spread in raw.items()}


def draw_deposit_spreads(econ: Any) -> None:
    cfg = econ.cfg.banking
    if not cfg.interbank or cfg.deposit_rate_disp <= 0.0:
        econ._deposit_spread = {bank.id: 0.0 for bank in econ.banks}
        return
    rng = random.Random(cfg.seed + 51009)
    raw = {bank.id: rng.gauss(0.0, cfg.deposit_rate_disp) for bank in econ.banks}
    mean = sum(raw.values()) / len(raw)
    econ._deposit_spread = {bank_id: spread - mean for bank_id, spread in raw.items()}


def assign_banks_genesis(econ: Any) -> None:
    cfg = econ.cfg.banking
    rng = random.Random(cfg.seed + 60613)
    banks, borrowers = econ.banks, list(econ.firms) + list(econ.households)
    if cfg.bank_assignment == "by_size":
        borrowers.sort(key=lambda a: econ.ledger.balance(a.id), reverse=True)
        for i, a in enumerate(borrowers):
            econ._bank_of[a.id] = banks[i % len(banks)]
    else:
        for a in borrowers:
            econ._bank_of[a.id] = banks[rng.randrange(len(banks))]


def bank_for(econ: Any, account_id):
    if not econ.banks:
        return None
    bank = econ._bank_of.get(account_id)
    if bank is not None:
        return bank
    for candidate in econ.banks:
        if candidate.alive:
            return candidate
    return econ.banks[0]


def reset_bank_realized_pnl(econ: Any) -> None:
    """Open a tick's realized bank P&L journal before any cash flow occurs."""
    if not getattr(econ.cfg.banking, "bank_realized_pnl", False):
        return
    for bank in econ.banks:
        bank.interest_income = 0.0
        bank.loan_interest = 0.0
        bank.bond_coupon = 0.0
        bank.interbank_interest_income = 0.0
        bank.interbank_interest_expense = 0.0
        bank.external_interest_expense = 0.0
        bank.deposit_funding_cost = 0.0
        bank.realized_credit_losses = 0.0
        bank.dividends_paid = 0.0
        bank.profit = 0.0


def record_bank_credit_loss(econ: Any, bank_id: str, amount: float) -> None:
    """Journal a ledger-backed loan write-off against its creditor bank."""
    if amount <= 0.0:
        return
    banks = getattr(econ, "banks", None)
    if not banks:
        # The demographic bridge also supports ledger-only unit/standalone states
        # with no Bank objects.  The ledger loss remains authoritative there, while
        # a per-bank P&L journal cannot exist.
        return
    bank = next((candidate for candidate in banks if candidate.id == bank_id), None)
    if bank is None:
        raise AssertionError(f"credit loss references unknown bank {bank_id!r}")
    bank.realized_credit_losses += amount


def bank_constraint(econ: Any) -> bool:
    return econ.policy.bank_capital_constraint and len(econ.banks) > 1   # B4a: regime is policy


def unified_bank_rwa_enabled(econ: Any) -> bool:
    """Whether new credit shares one bank-wide risk-weighted capital envelope."""
    return bool(getattr(econ.policy, "unified_bank_rwa", False))   # B4e: live lever


def refresh_loan_books(econ: Any) -> None:
    econ._loan_book = {bank.id: 0.0 for bank in econ.banks}
    for firm in econ.firms:
        econ._loan_book[bank_for(econ, firm.id).id] += econ.ledger.debt(firm.id)
    for household in econ.households:
        econ._loan_book[bank_for(econ, household.id).id] += econ.ledger.debt(household.id)


def _sync_mortgage_creditor(econ: Any, account_id: str, bank: Bank) -> None:
    """Keep the secured shadow aligned when relationship lock-in owns migration."""
    if not getattr(econ.cfg.banking, "bank_relationship_lock_in", False):
        return
    mortgage_book = getattr(econ, "mortgage_book", None)
    mortgage = mortgage_book.loans.get(account_id) if mortgage_book is not None else None
    if mortgage is not None:
        mortgage.bank_id = bank.id


def reserve_position(econ: Any, bank_id) -> float:
    cap = econ.ledger.balance(bank_id)
    dep = sum(
        econ.ledger.balance(a.id)
        for a in list(econ.firms) + list(econ.households)
        if bank_for(econ, a.id).id == bank_id
    )
    loans = (
        econ._loan_book.get(bank_id, 0.0)
        if hasattr(econ, "_loan_book")
        else sum(
            econ.ledger.debt(a.id)
            for a in list(econ.firms) + list(econ.households)
            if bank_for(econ, a.id).id == bank_id
        )
    )
    bank = next((candidate for candidate in econ.banks if candidate.id == bank_id), None)
    interbank_assets = (
        sum(position.principal for position in bank.interbank_assets.values())
        if bank is not None else 0.0
    )
    interbank_liabilities = (
        sum(position.principal for position in bank.interbank_liabilities.values())
        if bank is not None else 0.0
    )
    # R + loans + interbank assets = capital + deposits + interbank liabilities.
    return cap + dep + interbank_liabilities - loans - interbank_assets


def rate_competition(econ: Any) -> bool:
    return econ.cfg.banking.bank_rate_competition and len(econ.banks) > 1


def loan_rate_for(econ: Any, borrower_id) -> float:
    if not rate_competition(econ):
        return econ._rate
    return max(0.0, econ._rate + econ._bank_spread.get(bank_for(econ, borrower_id).id, 0.0))


def bank_economic_capital(econ: Any, bank: Bank) -> float:
    cfg = econ.cfg.banking
    cap = econ.ledger.balance(bank.id)
    if cfg.bonds and econ._bonds:
        from macro_sim.systems.securities import bank_bond_capital_deltas

        # cached per-lot (market - cost) for this bank, replayed as the same += sequence the
        # full-lot scan produced (this runs per loan grant -- O(N_lots) per call before).
        for delta in bank_bond_capital_deltas(econ, bank.id):
            cap += delta
    return cap


def _bank_gross_loan_exposure(econ: Any, bank: Bank, *, use_cache: bool = True) -> float:
    """Read gross principal from the intra-credit cache or live ledger."""
    cached = getattr(econ, "_loan_book", None)
    if use_cache and isinstance(cached, dict) and bank.id in cached:
        return max(0.0, float(cached.get(bank.id, 0.0)))
    return sum(
        max(0.0, float(econ.ledger.debt(agent.id)))
        for agent in list(econ.firms) + list(econ.households)
        if bank_for(econ, agent.id).id == bank.id
    )


def bank_rwa_exposure(econ: Any, bank: Bank, *, use_cache: bool = True) -> float:
    """Current bank RWA from ordinary credit and mortgages.

    The ledger's loan book is the principal authority.  The mortgage book is a
    collateralisation shadow over part of household ledger debt, so subtract that
    secured slice once before applying its lower risk weight.  A direct scan is used
    before the credit phase has opened ``_loan_book``; normal sequential grants use
    the refreshed O(1) cache and update it at each mutation boundary.
    """
    gross_loans = _bank_gross_loan_exposure(econ, bank, use_cache=use_cache)
    mortgage_book = getattr(econ, "mortgage_book", None)
    secured = (
        max(0.0, float(mortgage_book.bank_balance_total(bank.id)))
        if mortgage_book is not None else 0.0
    )
    unsecured = max(0.0, gross_loans - secured)
    risk_weight = max(0.0, float(econ.policy.mortgage_risk_weight))   # B4b
    return unsecured + risk_weight * secured


def bank_rwa_capacity(
    econ: Any,
    bank: Bank,
    *,
    new_loan_risk_weight: float = 1.0,
    min_capital_ratio: float | None = None,
    use_cache: bool = True,
) -> float:
    """Principal headroom for one new loan inside the common RWA envelope."""
    if bank is None or not bank.alive:
        return 0.0
    weight = max(0.0, float(new_loan_risk_weight))
    ratio = float(
        econ.policy.mortgage_min_capital_ratio
        if min_capital_ratio is None else min_capital_ratio
    )
    # A zero risk weight would make principal capacity unbounded, while a missing
    # capital ratio cannot define an envelope.  Config validation excludes both on
    # normal runs; conservative zeros keep standalone/mocked states safe.
    if weight <= EPS or ratio <= EPS:
        return 0.0
    capital = max(0.0, bank_economic_capital(econ, bank))
    rwa_room = capital / ratio - bank_rwa_exposure(econ, bank, use_cache=use_cache)
    return max(0.0, rwa_room / weight)


def bank_capacity(econ: Any, bank: Bank) -> float:
    if not bank.alive:
        return 0.0
    capital = max(0.0, bank_economic_capital(econ, bank))
    # Preserve the historical gross-loan hard gate exactly when the unified
    # envelope is off.  With both regimes active, the tighter incremental principal
    # headroom wins; mortgages therefore consume RWA here without being treated as
    # unsecured principal a second time.
    if not unified_bank_rwa_enabled(econ):
        kb = bank.kappa_bank
        if econ.policy.bank_leverage_cap > 0.0:      # B4a [N]: regulatory ceiling over the appetite draw
            kb = min(kb, econ.policy.bank_leverage_cap)
        return kb * capital - econ._loan_book.get(bank.id, 0.0)
    rwa_headroom = bank_rwa_capacity(econ, bank)
    if not bank_constraint(econ):
        return rwa_headroom
    kb_g = bank.kappa_bank
    if econ.policy.bank_leverage_cap > 0.0:
        kb_g = min(kb_g, econ.policy.bank_leverage_cap)
    gross_headroom = kb_g * capital - _bank_gross_loan_exposure(econ, bank)
    return min(gross_headroom, rwa_headroom)


def shop_bank(econ: Any, borrower_id, amount: float) -> None:
    """Choose a relationship bank, optionally locking it after origination.

    Moving an existing borrower would reattribute the ledger's entire debt stock
    (including any mortgage shadow) without a loan sale, payoff, or refinance cash
    flow between the two banks.  Until those contract/asset-transfer rails exist,
    an incumbent relationship bank remains the creditor for every top-up.  A
    debt-free borrower can still compare banks before the new loan is originated.
    That safer behavior is opt-in so historical presets retain their trajectories.
    """
    cfg = econ.cfg.banking
    cur = bank_for(econ, borrower_id)
    debt = econ.ledger.debt(borrower_id)
    if getattr(cfg, "bank_relationship_lock_in", False):
        mortgage_book = getattr(econ, "mortgage_book", None)
        mortgage = mortgage_book.loans.get(borrower_id) if mortgage_book is not None else None
        if debt > EPS or (mortgage is not None and mortgage.balance > EPS):
            return
    need = debt + amount
    rate_of = lambda bank: max(0.0, econ._rate + econ._bank_spread.get(bank.id, 0.0))
    best, best_rate = cur, rate_of(cur)
    rivals = [bank for bank in econ.banks if bank.alive and bank is not cur]
    sample_size = min(cfg.bank_search_m, len(rivals))
    sample = rivals if sample_size >= len(rivals) else econ._bank_rng.sample(rivals, sample_size)
    for bank in sample:
        if bank_capacity(econ, bank) + EPS < need:
            continue
        if rate_of(bank) < best_rate - EPS:
            best, best_rate = bank, rate_of(bank)
    if best is not cur:
        econ._loan_book[cur.id] = econ._loan_book.get(cur.id, 0.0) - debt
        econ._loan_book[best.id] = econ._loan_book.get(best.id, 0.0) + debt
        if cfg.interbank:
            econ.ledger.move_reserves(
                cur.id,
                best.id,
                econ.ledger.balance(borrower_id) - econ.ledger.debt(borrower_id),
            )
        econ._bank_of[borrower_id] = best
        _sync_mortgage_creditor(econ, borrower_id, best)
        econ._node_of.pop(borrower_id, None)


def grant_loan(econ: Any, borrower_id, amount: float) -> float:
    cfg = econ.cfg.banking
    has_gross_gate = bank_constraint(econ)
    has_rwa_gate = unified_bank_rwa_enabled(econ)
    if not (has_gross_gate or has_rwa_gate):
        econ.ledger.create_loan(borrower_id, amount)
        return amount
    if not isinstance(getattr(econ, "_loan_book", None), dict):
        refresh_loan_books(econ)
    if rate_competition(econ):
        shop_bank(econ, borrower_id, amount)
    bank = bank_for(econ, borrower_id)
    headroom = bank_capacity(econ, bank)
    if has_gross_gate and econ.policy.bank_exposure_limit > 0.0:
        capital = max(0.0, bank_economic_capital(econ, bank))
        concentration_room = econ.policy.bank_exposure_limit * capital - econ.ledger.debt(borrower_id)
        headroom = min(headroom, concentration_room)
    granted = min(amount, max(0.0, headroom))
    if granted > EPS:
        econ.ledger.create_loan(borrower_id, granted)
        econ._loan_book[bank.id] += granted
    return granted


def setup_bank_equity(econ: Any) -> None:
    cfg = econ.cfg.banking
    rng = random.Random(cfg.seed + 43117)
    pool_n = max(1, int(cfg.genesis_founder_pool * len(econ.households)))
    founders = rng.sample(econ.households, min(pool_n, len(econ.households)))
    shares = 100.0
    for i, bank in enumerate(econ.banks):
        founder = founders[i % len(founders)]
        bank.shares_outstanding = shares
        bank.owners = {founder.id: shares}
        capital = max(0.0, econ.ledger.balance(bank.id))
        bank.share_price = bank.share_last_price = bank.share_peak = capital / shares
        bank.earnings_ema = 0.0


def pay_bank_dividends(econ: Any, bank: Bank, payable: float) -> float:
    owners = bank.owners or {}
    total = sum(owners.values())
    if total <= 0.0:
        return 0.0
    bridge = getattr(econ, "demographic_bridge", None)
    paid = 0.0
    for household_id, shares in owners.items():
        household = econ._hh_by_id.get(household_id)
        if household is None:
            continue
        if bridge is not None and not bridge.household_has_living_members(household.id):
            continue
        amount = min(payable * shares / total, econ.ledger.balance(bank.id))
        if amount > EPS:
            econ.ledger.transfer(bank.id, household.id, amount)
            if bridge is not None:
                bridge.post_capital_income(household.id, amount)
            household.income_realized += amount
            paid += amount
    return paid


def bank_fundamental(econ: Any, bank: Bank, rate: float) -> float:
    if not bank.alive or bank.shares_outstanding <= 0.0:
        return 0.0
    return (max(0.0, econ.ledger.balance(bank.id)) + bank.earnings_ema / rate) / bank.shares_outstanding


def update_bank_valuation(econ: Any) -> None:
    cfg = econ.cfg.banking
    if not cfg.bank_equity:
        return
    if econ.cfg.monetary_direct_transmission:
        from macro_sim.systems.valuation import valuation_discount_rate

        rate = valuation_discount_rate(econ)
    else:
        rate = max(econ._rate, 0.01)
    lam = cfg.bank_equity_lambda
    for bank in econ.banks:
        bank.earnings_ema = (1.0 - lam) * bank.earnings_ema + lam * max(0.0, bank.profit)
    if cfg.bank_equity_trading:
        bank_stock_market(econ, rate)
    else:
        for bank in econ.banks:
            bank.share_last_price = bank.share_price
            bank.share_price = bank_fundamental(econ, bank, rate)
            if bank.alive:
                bank.share_peak = max(bank.share_peak * 0.999, bank.share_price)


def bank_stock_market(econ: Any, rate: float) -> None:
    cfg, ledger = econ.cfg.banking, econ.ledger
    bridge = getattr(econ, "demographic_bridge", None)
    banks = [bank for bank in econ.banks if bank.alive and bank.shares_outstanding > EPS]
    for bank in econ.banks:
        if not bank.alive:
            bank.share_last_price, bank.share_price = bank.share_price, 0.0
    if not banks:
        return
    fundamental = {bank.id: bank_fundamental(econ, bank, rate) for bank in banks}
    orders = {bank.id: [] for bank in banks}
    for household in econ.households:
        equity_value = sum((bank.owners or {}).get(household.id, 0.0) * bank.share_price for bank in banks)
        deposits = ledger.balance(household.id)
        attractiveness = []
        for bank in banks:
            price = bank.share_price
            if price > EPS:
                price_response = (
                    cfg.w_fundamental * (fundamental[bank.id] - price) / price
                    + cfg.w_chartist * bank.share_trend
                )
            else:
                price_response = 0.0
            attractiveness.append(max(0.0, 1.0 + price_response))
        total_attractiveness = sum(attractiveness)
        target_equity = cfg.bank_theta_equity * (deposits + equity_value)
        deltas = []
        for bank, attr in zip(banks, attractiveness):
            weight = (attr / total_attractiveness) if total_attractiveness > EPS else (1.0 / len(banks))
            desired = (target_equity * weight / bank.share_price) if bank.share_price > EPS else 0.0
            current = (bank.owners or {}).get(household.id, 0.0)
            deltas.append((bank, (desired - current) * cfg.portfolio_adjust))
        buy_cash = sum(delta * bank.share_price for bank, delta in deltas if delta > 0.0)
        scale = min(1.0, deposits / buy_cash) if buy_cash > EPS else 1.0
        for bank, delta in deltas:
            delta = delta * scale if delta > 0.0 else max(delta, -(bank.owners or {}).get(household.id, 0.0))
            if abs(delta) > EPS:
                orders[bank.id].append((household, delta))
    turnover = 0.0
    for bank in banks:
        order_book = orders[bank.id]
        buy = sum(delta for _, delta in order_book if delta > 0.0)
        sell = -sum(delta for _, delta in order_book if delta < 0.0)
        executed = min(buy, sell)
        price = bank.share_price
        if executed > EPS:
            buy_scale, sell_scale = executed / buy, executed / sell
            for household, delta in order_book:
                if delta > 0.0:
                    quantity = delta * buy_scale
                    ledger.transfer(household.id, "CLEARING", quantity * price)
                    bank.owners[household.id] = bank.owners.get(household.id, 0.0) + quantity
                    if bridge is not None:
                        bridge.post_household_bank_equity_trade(
                            household.id,
                            bank.id,
                            cash_delta=-(quantity * price),
                            share_delta=quantity,
                        )
            sellers = [(household, -delta * sell_scale) for household, delta in order_book if delta < 0.0]
            for household, quantity in sellers:
                bank.owners[household.id] = bank.owners.get(household.id, 0.0) - quantity
                ledger.transfer("CLEARING", household.id, quantity * price)
                if bridge is not None:
                    bridge.post_household_bank_equity_trade(
                        household.id,
                        bank.id,
                        cash_delta=quantity * price,
                        share_delta=-quantity,
                    )
            remainder = ledger.balance("CLEARING")
            if remainder > EPS and sellers:
                ledger.transfer("CLEARING", sellers[-1][0].id, remainder)
                if bridge is not None:
                    bridge.post_household_cash_delta(sellers[-1][0].id, remainder, reason="bank_equity_trade")
            turnover += executed
        excess = (buy - sell) / bank.shares_outstanding if bank.shares_outstanding > EPS else 0.0
        new_price = max(EPS, price * (1.0 + cfg.lambda_p * max(-0.5, min(0.5, excess))))
        bank.share_trend += cfg.trend_lambda * ((new_price - price) / price - bank.share_trend)
        bank.share_last_price, bank.share_price = price, new_price
        bank.share_peak = max(bank.share_peak * 0.999, bank.share_price)
    econ._bank_equity_turnover = turnover / max(EPS, sum(bank.shares_outstanding for bank in banks))


def find_bank_founder(econ: Any, need: float):
    from macro_sim.systems.securities import household_bond_value

    for _ in range(8):
        household = econ.households[econ._bank_entry_rng.randrange(len(econ.households))]
        if econ.ledger.balance(household.id) + household_bond_value(econ, household.id) >= need + EPS:
            return household
    return None


def found_bank(econ: Any, founder, capital: float) -> None:
    from macro_sim.systems.securities import redeem_household_bonds

    cfg = econ.cfg.banking
    # FUND FIRST, charter second: eligibility valued the founder's bonds at MARKET, but
    # redemption PROCEEDS can fall slightly short of that valuation -- creating the bank
    # before verifying the cash tripped A4 mid-charter with a zombie bank already on the
    # books (rare-event exposure grows once housing/rents thin out founder cash)
    if econ.ledger.balance(founder.id) < capital:
        redeem_household_bonds(econ, founder.id, capital - econ.ledger.balance(founder.id))
    if econ.ledger.balance(founder.id) < capital:
        return                            # proceeds fell short: no charter this attempt
    bank_id = f"BANK_{econ._next_bank_id}"
    econ._next_bank_id += 1
    dispersion = cfg.bank_leverage_disp
    kappa = max(
        1.0,
        cfg.bank_leverage_mean
        * (econ._bank_entry_rng.lognormvariate(-0.5 * dispersion * dispersion, dispersion) if dispersion > 0 else 1.0),
    )
    bank = Bank(id=bank_id, rho=cfg.rho, kappa_bank=kappa)
    econ.banks.append(bank)
    econ._bank_ids.add(bank_id)
    econ.ledger.add_account(bank_id)
    econ.ledger.allow_negative(bank_id)
    econ.ledger.transfer(founder.id, bank_id, capital)
    bridge = getattr(econ, "demographic_bridge", None)
    econ._bank_spread[bank_id] = -abs(econ._bank_entry_rng.gauss(0.0, cfg.bank_spread_disp))
    econ._deposit_spread[bank_id] = 0.0
    shares = 100.0
    bank.shares_outstanding = shares
    bank.owners = {founder.id: shares}
    if bridge is not None:
        bridge.post_household_bank_equity_trade(
            founder.id,
            bank_id,
            cash_delta=-capital,
            share_delta=shares,
        )
    price = max(0.0, econ.ledger.balance(bank_id)) / shares
    bank.share_price = bank.share_last_price = bank.share_peak = price
    econ._bank_births += 1


def bank_equity_value(econ: Any, household_id) -> float:
    # NOTE: read the flat Config field -- `econ.cfg.banking` BUILDS the frozen view dataclass per
    # access, and this helper runs per household per tick in settlement + metrics (hot path).
    if not econ.cfg.bank_equity:
        return 0.0
    value = 0.0
    for bank in econ.banks:
        shares = (bank.owners or {}).get(household_id, 0.0)
        if shares > 0.0:
            value += shares * bank.share_price
    return value


def settlement_node(econ: Any, account_id):
    if account_id in (econ._fiscal, "EXTISSUER", "CBRES"):
        return "CB"
    # The FX dealer represents the external sector, not an unassigned customer
    # deposit at whichever commercial bank happens to appear first.  Settle its
    # currency leg through the neutral clearing node so bank failures and list
    # order cannot change its reserve counterparty.
    if account_id in ("CLEARING", "FXDEALER") or account_id in econ._bank_ids:
        if account_id == "FXDEALER":
            return "CLEARING"
        return account_id
    return bank_for(econ, account_id).id


class _ReserveResolver:
    """account -> settlement-node resolver for the RTGS overlay.

    A module-level class instance (not a closure) so the ledger -- and therefore
    the whole engine object graph -- stays picklable for checkpoints. Behaviour is
    identical to the previous closure: memoised via ``econ._node_of`` (resolution
    is stable between ``_bank_of`` writes, and every write site drops its key, so
    a hit == a fresh resolve)."""

    def __init__(self, econ: Any) -> None:
        self.econ = econ

    def __call__(self, account_id):
        node_of = self.econ._node_of
        node = node_of.get(account_id)
        if node is None:
            node = settlement_node(self.econ, account_id)
            node_of[account_id] = node
        return node


def enable_reserves(econ: Any) -> None:
    reserves = {bank.id: econ.ledger.balance(bank.id) for bank in econ.banks}
    for account in list(econ.firms) + list(econ.households):
        reserves[bank_for(econ, account.id).id] += econ.ledger.balance(account.id)
    reserves["CLEARING"] = 0.0
    reserves["CB"] = 0.0
    econ.ledger.enable_reserves(_ReserveResolver(econ), reserves)
    econ._reserve_M0 = econ.ledger.total_reserves


def fail_bank(econ: Any, bank: Bank) -> None:
    cfg = econ.cfg.banking
    bank.alive = False
    econ._bank_failures_total += 1
    econ._bank_deaths += 1
    alive = sorted(
        (candidate for candidate in econ.banks if candidate.alive),
        key=lambda candidate: candidate.id,
    )
    if cfg.interbank:
        # Close the failed bank's wholesale balance sheet before any fiscal or
        # mutual resolution payment is sized.  Otherwise the fund can fill its
        # negative ledger capital now and a delayed liability cancellation can
        # create a positive dead-bank balance next tick.
        assert_interbank_positions(econ)
        _default_interbank_liabilities(econ, bank)
        _transfer_failed_interbank_assets(econ, bank, alive)
        assert_interbank_positions(econ)
    if econ.policy.bank_migrate_on_failure and alive:
        movers = [account_id for account_id, assigned_bank in econ._bank_of.items() if assigned_bank is bank]
        for i, account_id in enumerate(movers):
            new_bank = alive[i % len(alive)]
            if cfg.interbank and econ.ledger.has_account(account_id):
                econ.ledger.move_reserves(
                    bank.id,
                    new_bank.id,
                    econ.ledger.balance(account_id) - econ.ledger.debt(account_id),
                )
            econ._bank_of[account_id] = new_bank
            _sync_mortgage_creditor(econ, account_id, new_bank)
            econ._node_of.pop(account_id, None)

    # A solvent-but-illiquid failure, or liability forgiveness larger than its
    # pre-resolution hole, can leave positive estate capital.  The bridge bank
    # receives it now; no dead settlement account remains able to collect later.
    if econ.ledger.balance(bank.id) > EPS:
        if alive:
            estate_receiver = alive[0].id
        elif econ.ledger.has_account(econ._fiscal):
            estate_receiver = econ._fiscal
        else:
            estate_receiver = econ.households[0].id
        econ.ledger.transfer(bank.id, estate_receiver, econ.ledger.balance(bank.id))
    if econ.policy.bank_resolution_fund:
        # v12.4-fix: a DEPOSIT-INSURANCE / RESOLUTION backstop. The STATE absorbs the failed bank's residual
        # negative capital (transfer fiscal→bank, A5-safe, financed into the deficit) instead of SOCIALISING the
        # loss onto surviving banks' capital. The legacy pro-rata socialisation (the `elif` below) dumped one deep
        # insolvency onto every bank's balance, which `resolve_bank_failures` then failed in turn -- a runaway
        # INSOLVENCY-CONTAGION cascade that wiped the whole sector in one tick and was irreversible (seen at
        # NH5000). Depositors are made whole; the fiscal cost is the realistic price of the backstop.
        loss = -econ.ledger.balance(bank.id)
        if loss > EPS:
            econ.ledger.transfer(econ._fiscal, bank.id, loss)
            econ._bank_resolution_fund_paid = (
                getattr(econ, "_bank_resolution_fund_paid", 0.0) + loss
            )
    elif cfg.interbank and alive:
        # Legacy no-fund resolution mutualises the failed deposit franchise's
        # residual negative equity so its closed settlement node does not carry
        # a permanent reserve overdraft.  This is a resolution levy, NOT an
        # interbank-credit loss: `_interbank_contagion_loss` is now reserved for
        # defaults on the explicit bilateral claims below.
        loss = max(0.0, -econ.ledger.balance(bank.id))
        contributors = {
            candidate.id: econ.ledger.reserves(candidate.id)
            for candidate in alive
            if econ.ledger.reserves(candidate.id) > EPS
        }
        total = sum(contributors.values())
        if loss > EPS and total > EPS:
            for contributor_id, contributor_reserves in contributors.items():
                amount = min(
                    loss * contributor_reserves / total,
                    max(0.0, -econ.ledger.balance(bank.id)),
                )
                if amount > EPS:
                    econ.ledger.transfer(contributor_id, bank.id, amount)
    if cfg.interbank:
        assert_interbank_positions(econ)


def run_deposit_competition(econ: Any) -> None:
    cfg = econ.cfg.banking
    if not (cfg.interbank and cfg.deposit_rate_disp > 0.0 and len(econ.banks) > 1):
        return
    ds = econ._deposit_spread
    alive = [b for b in econ.banks if b.alive]
    if len(alive) < 2:
        return
    deposits_by_bank = {b.id: 0.0 for b in alive}
    for h in econ.households:
        bid = bank_for(econ, h.id).id
        if bid in deposits_by_bank:
            deposits_by_bank[bid] += max(0.0, econ.ledger.balance(h.id))
    total_deposits = sum(deposits_by_bank.values()) or 1.0
    congestion = cfg.deposit_rate_disp * len(alive)
    effective_rate = {
        bid: ds.get(bid, 0.0) - congestion * (deposits_by_bank[bid] / total_deposits)
        for bid in deposits_by_bank
    }
    for h in econ.households:
        if econ.ledger.debt(h.id) > EPS:
            continue
        current = bank_for(econ, h.id)
        best, best_rate = current, effective_rate.get(current.id, 0.0)
        rivals = [b for b in alive if b is not current]
        sample_size = min(cfg.deposit_search_m, len(rivals))
        sample = rivals if sample_size >= len(rivals) else econ._bank_rng.sample(rivals, sample_size)
        for bank in sample:
            candidate_rate = effective_rate.get(bank.id, 0.0)
            if candidate_rate > best_rate + EPS:
                best, best_rate = bank, candidate_rate
        if best is not current:
            econ.ledger.move_reserves(
                current.id,
                best.id,
                econ.ledger.balance(h.id) - econ.ledger.debt(h.id),
            )
            econ._bank_of[h.id] = best
            econ._node_of.pop(h.id, None)


def _set_interbank_claim(
    lender: Bank,
    borrower: Bank,
    principal: float,
    rate: float,
    accrued_interest: float,
) -> None:
    """Write one immutable bilateral position to both balance sheets."""
    principal = max(0.0, principal)
    accrued_interest = max(0.0, accrued_interest)
    if principal <= EPS and accrued_interest <= EPS:
        lender.interbank_assets.pop(borrower.id, None)
        borrower.interbank_liabilities.pop(lender.id, None)
        return
    claim = InterbankClaim(
        principal=principal,
        rate=max(0.0, rate) if principal > EPS else 0.0,
        accrued_interest=accrued_interest,
    )
    lender.interbank_assets[borrower.id] = claim
    borrower.interbank_liabilities[lender.id] = claim


def _merge_interbank_claim(
    lender: Bank,
    borrower: Bank,
    incoming: InterbankClaim,
) -> None:
    """Merge a claim transferred in resolution without moving new reserves."""
    old = lender.interbank_assets.get(borrower.id)
    old_principal = old.principal if old is not None else 0.0
    principal = old_principal + incoming.principal
    rate_value = (
        old_principal * old.rate if old is not None else 0.0
    ) + incoming.principal * incoming.rate
    _set_interbank_claim(
        lender,
        borrower,
        principal,
        rate_value / principal if principal > EPS else 0.0,
        (old.accrued_interest if old is not None else 0.0) + incoming.accrued_interest,
    )


def _add_interbank_principal(
    lender: Bank,
    borrower: Bank,
    principal: float,
    rate: float,
) -> None:
    """Add newly advanced reserves, preserving rolled arrears and rate value."""
    if principal <= EPS:
        return
    _merge_interbank_claim(
        lender,
        borrower,
        InterbankClaim(principal=principal, rate=rate),
    )


def _default_interbank_liabilities(econ: Any, borrower: Bank) -> None:
    """Cancel every wholesale liability and charge each contractual creditor once."""
    by_id = {bank.id: bank for bank in econ.banks}
    for lender_id, claim in list(sorted(borrower.interbank_liabilities.items())):
        lender = by_id[lender_id]
        if claim.principal > EPS:
            econ.ledger.write_off_interbank_claim(lender.id, borrower.id, claim.principal)
            lender.realized_credit_losses += claim.principal
            # Normal tick scheduling resolves failures before final P&L.  Keep
            # this snapshot adjustment as a defensive guarantee for direct or
            # externally orchestrated ``fail_bank`` calls; finalization later
            # recomputes the same net amount from the named loss leg.
            lender.profit -= claim.principal
            econ._interbank_contagion_loss += claim.principal
        _set_interbank_claim(lender, borrower, 0.0, 0.0, 0.0)


def _transfer_failed_interbank_assets(
    econ: Any,
    failed: Bank,
    alive: list[Bank],
) -> None:
    """Move a failed lender's surviving claims into a deterministic bridge bank.

    Principal book value moves from failed-bank equity to bridge-bank equity
    without a reserve payment.  If the only bridge is itself the claim debtor,
    acquisition extinguishes the now-self-held asset and liability immediately.
    With no surviving bank, the claim is closed against the debtor rather than
    being left to collect into a dead settlement account.
    """
    by_id = {bank.id: bank for bank in econ.banks}
    for borrower_id, claim in list(sorted(failed.interbank_assets.items())):
        borrower = by_id[borrower_id]
        _set_interbank_claim(failed, borrower, 0.0, 0.0, 0.0)
        if not alive:
            if claim.principal > EPS:
                econ.ledger.write_off_interbank_claim(failed.id, borrower.id, claim.principal)
            continue
        alternatives = [candidate for candidate in alive if candidate is not borrower]
        receiver = alternatives[0] if alternatives else alive[0]
        if claim.principal > EPS:
            econ.ledger.reallocate_bank_capital(failed.id, receiver.id, claim.principal)
        if receiver is not borrower:
            _merge_interbank_claim(receiver, borrower, claim)


def _pro_rata_allocations(values: dict[str, float], budget: float) -> dict[str, float]:
    """Deterministically allocate no more than ``budget`` across positive dues."""
    positive = [
        (key, max(0.0, value))
        for key, value in sorted(values.items())
        if value > EPS
    ]
    total = sum(value for _, value in positive)
    remaining_budget = min(max(0.0, budget), total)
    remaining_due = total
    result = {key: 0.0 for key in values}
    for key, due in positive:
        if remaining_budget <= EPS:
            break
        amount = (
            min(due, remaining_budget * due / remaining_due)
            if remaining_due > EPS else 0.0
        )
        result[key] = amount
        remaining_budget -= amount
        remaining_due -= due
    return result


def assert_interbank_positions(econ: Any) -> None:
    """Hard-gate bilateral claims and aggregate interbank assets/liabilities."""
    by_id = {bank.id: bank for bank in econ.banks}
    total_assets = 0.0
    total_liabilities = 0.0
    for lender in econ.banks:
        for borrower_id, claim in lender.interbank_assets.items():
            if borrower_id == lender.id or borrower_id not in by_id:
                raise AssertionError(f"invalid interbank asset {lender.id!r}->{borrower_id!r}")
            if not all(math.isfinite(value) and value >= 0.0 for value in (
                claim.principal, claim.rate, claim.accrued_interest,
            )):
                raise AssertionError(f"invalid interbank claim {lender.id!r}->{borrower_id!r}: {claim!r}")
            mirror = by_id[borrower_id].interbank_liabilities.get(lender.id)
            if mirror != claim:
                raise AssertionError(
                    f"unmirrored interbank claim {lender.id!r}->{borrower_id!r}: "
                    f"asset={claim!r}, liability={mirror!r}"
                )
            total_assets += claim.principal
        for lender_id, claim in lender.interbank_liabilities.items():
            if lender_id == lender.id or lender_id not in by_id:
                raise AssertionError(f"invalid interbank liability {lender_id!r}->{lender.id!r}")
            mirror = by_id[lender_id].interbank_assets.get(lender.id)
            if mirror != claim:
                raise AssertionError(
                    f"unmirrored interbank liability {lender_id!r}->{lender.id!r}: "
                    f"asset={mirror!r}, liability={claim!r}"
                )
            total_liabilities += claim.principal
    scale = max(1.0, total_assets, total_liabilities)
    if abs(total_assets - total_liabilities) > 1e-9 * scale:
        raise AssertionError(
            f"interbank assets/liabilities differ: {total_assets!r} vs {total_liabilities!r}"
        )


def _settle_mature_interbank_claims(econ: Any) -> None:
    """Settle the previous phase's overnight claims or carry them explicitly.

    Cash interest is paid before principal and alone enters realized P&L.  An
    alive but illiquid borrower rolls unpaid principal/interest.  A failed bank
    defaults: principal is cancelled against creditor capital without a reserve
    movement, while never-realized interest is simply removed from the claim.
    """
    by_id = {bank.id: bank for bank in econ.banks}
    for borrower in sorted(econ.banks, key=lambda bank: bank.id):
        positions = list(sorted(borrower.interbank_liabilities.items()))
        if not positions:
            continue
        if not borrower.alive:
            # Defensive cleanup for externally constructed/de-serialized states.
            # Normal failures close these synchronously inside ``fail_bank``.
            _default_interbank_liabilities(econ, borrower)
            continue

        interest_due = {
            lender_id: claim.accrued_interest + claim.principal * claim.rate
            for lender_id, claim in positions
        }
        interest_budget = min(
            sum(interest_due.values()),
            max(0.0, econ.ledger.balance(borrower.id)),
            max(0.0, econ.ledger.reserves(borrower.id)),
        )
        interest_paid = _pro_rata_allocations(interest_due, interest_budget)
        for lender_id, amount in interest_paid.items():
            if amount <= EPS:
                continue
            lender = by_id[lender_id]
            econ.ledger.transfer(borrower.id, lender.id, amount)
            borrower.interbank_interest_expense += amount
            lender.interbank_interest_income += amount

        principal_due = {lender_id: claim.principal for lender_id, claim in positions}
        principal_budget = min(
            sum(principal_due.values()),
            max(0.0, econ.ledger.reserves(borrower.id)),
        )
        principal_paid = _pro_rata_allocations(principal_due, principal_budget)
        for lender_id, amount in principal_paid.items():
            if amount > EPS:
                econ.ledger.move_reserves(borrower.id, lender_id, amount)

        for lender_id, claim in positions:
            lender = by_id[lender_id]
            _set_interbank_claim(
                lender,
                borrower,
                claim.principal - principal_paid.get(lender_id, 0.0),
                claim.rate,
                interest_due[lender_id] - interest_paid.get(lender_id, 0.0),
            )


def run_interbank_phase(econ: Any) -> None:
    cfg = econ.cfg.banking
    econ._interbank_volume = 0.0
    econ._interbank_rate = econ._rate
    econ._payments_blocked = 0.0
    econ._interbank_contagion_loss = 0.0
    if not (cfg.interbank and len(econ.banks) > 1):
        return
    assert_interbank_positions(econ)
    # Overnight means one money-market phase: mature the old stock before any
    # new reserves are advanced.  A residual claim is an explicit rollover.
    _settle_mature_interbank_claims(econ)
    alive = [
        bank for bank in econ.banks
        if bank.alive and bank_economic_capital(econ, bank) >= -EPS
    ]
    if econ.policy.reserve_floor_frac > 0.0:
        for bank in alive:
            floor = -econ.policy.reserve_floor_frac * max(0.0, econ.ledger.balance(bank.id))
            if econ.ledger.reserve_min(bank.id) < floor - EPS:
                econ._payments_blocked += 1.0
    deficits = {b.id: -econ.ledger.reserves(b.id) for b in alive if econ.ledger.reserves(b.id) < -EPS}
    surplus = {b.id: econ.ledger.reserves(b.id) for b in alive if econ.ledger.reserves(b.id) > EPS}
    total_deficit, total_surplus = sum(deficits.values()), sum(surplus.values())
    if total_deficit <= EPS or total_surplus <= EPS:
        assert_interbank_positions(econ)
        return
    tightness = min(1.0, total_deficit / total_surplus)
    ib_rate = max(0.0, econ._rate + cfg.interbank_rate_base + cfg.interbank_tightness * tightness)
    econ._interbank_rate = ib_rate
    by_id = {bank.id: bank for bank in econ.banks}
    actual_volume = 0.0
    # Ration scarce lender supply across deficit banks pro rata first.  Sorting
    # remains only a deterministic execution order, never an id-based priority.
    borrower_funding = _pro_rata_allocations(
        deficits,
        min(total_deficit, total_surplus),
    )
    for deficit_id, funding in sorted(borrower_funding.items()):
        if funding <= EPS:
            continue
        available = sum(max(0.0, value) for value in surplus.values())
        allocations = _pro_rata_allocations(surplus, min(funding, available))
        for surplus_id, principal in allocations.items():
            if principal <= EPS:
                continue
            econ.ledger.move_reserves(surplus_id, deficit_id, principal)
            surplus[surplus_id] = max(0.0, surplus[surplus_id] - principal)
            _add_interbank_principal(by_id[surplus_id], by_id[deficit_id], principal, ib_rate)
            actual_volume += principal
    econ._interbank_volume = actual_volume
    assert_interbank_positions(econ)


def run_bank_runs_phase(econ: Any) -> None:
    cfg = econ.cfg.banking
    econ._run_flight_volume = 0.0
    if not (cfg.bank_runs and cfg.interbank and len(econ.banks) > 1):
        return
    econ._bank_fear *= cfg.run_fear_persistence
    alive = [b for b in econ.banks if b.alive]
    if len(alive) < 2:
        return
    refresh_loan_books(econ)
    health = {}
    for bank in alive:
        loan_book = econ._loan_book.get(bank.id, 0.0)
        book_health = (
            min(1.0, (econ.ledger.balance(bank.id) / loan_book) / max(EPS, cfg.run_health_ref))
            if loan_book > EPS
            else 1.0
        )
        market_health = min(1.0, bank.share_price / bank.share_peak) if bank.share_peak > EPS else 1.0
        health[bank.id] = cfg.run_market_weight * market_health + (1.0 - cfg.run_market_weight) * book_health
    safe = max(alive, key=lambda bank: health[bank.id])
    depositors_by_bank = {}
    for h in econ.households:
        if econ.ledger.debt(h.id) <= EPS:
            depositors_by_bank.setdefault(bank_for(econ, h.id).id, []).append(h)
    for bank in alive:
        if bank is safe:
            continue
        pressure = max(0.0, 0.5 - health[bank.id])
        intensity = min(1.0, cfg.run_sensitivity * pressure + econ._bank_fear)
        if intensity <= EPS:
            continue
        queue = [
            h
            for h in depositors_by_bank.get(bank.id, [])
            if econ._run_rng.random() < intensity
        ]
        if not queue:
            continue
        econ._run_rng.shuffle(queue)
        liquid = econ.ledger.reserves(bank.id)
        suspended = False
        for h in queue:
            withdrawal = econ.ledger.balance(h.id)
            if withdrawal <= EPS:
                continue
            if liquid < withdrawal - EPS and econ.policy.lolr and bank_economic_capital(econ, bank) > EPS:
                need = withdrawal - liquid
                econ.ledger.issue_reserves(bank.id, need)
                econ._lolr_advances += need
                liquid += need
            if liquid >= withdrawal - EPS:
                econ.ledger.move_reserves(bank.id, safe.id, withdrawal)
                econ._bank_of[h.id] = safe
                econ._node_of.pop(h.id, None)
                liquid -= withdrawal
                econ._run_flight_volume += withdrawal
            else:
                suspended = True
                break
        if suspended:
            econ._bank_fear = min(1.0, econ._bank_fear + 0.25)
            fail_bank(econ, bank)
        else:
            econ._bank_fear = min(1.0, econ._bank_fear + 0.02 * len(queue) / len(econ.households))


def resolve_bank_failures(econ: Any) -> None:
    # Both capital regimes can create an economically binding insolvency state.
    # In particular, the unified RWA envelope is deliberately usable with the
    # historical gross-loan constraint off, so that configuration must not leave a
    # negative-equity bank alive merely because the legacy switch is false.
    if not (bank_constraint(econ) or unified_bank_rwa_enabled(econ)):
        return
    while True:
        newly_failed = [
            bank
            for bank in econ.banks
            if bank.alive and bank_economic_capital(econ, bank) < -EPS
        ]
        if not newly_failed:
            break
        for bank in newly_failed:
            fail_bank(econ, bank)


def run_bank_entry_phase(econ: Any) -> None:
    cfg = econ.cfg.banking
    if not (cfg.bank_dynamics and cfg.bank_equity):
        return
    alive = [b for b in econ.banks if b.alive]
    # A potential entrant observes the return earned by viable incumbent
    # franchises, not a gross-interest proxy and not the legacy losses of failed
    # business models it need not acquire. This keeps the entry signal on net
    # income without letting one loss-making incumbent mask every healthy bank.
    profitable = [
        b for b in alive
        if b.profit > EPS and econ.ledger.balance(b.id) > EPS
    ]
    total_capital = sum(max(0.0, econ.ledger.balance(b.id)) for b in profitable)
    total_income = sum(b.profit for b in profitable)
    if total_capital > EPS:
        roe = total_income / total_capital
        rate = max(econ._rate, 1e-4)
        probability = max(0.0, min(1.0, cfg.bank_entry_beta * (roe / rate - 1.0)))
        probability *= max(0.0, 1.0 - len(alive) / (2.0 * max(1, cfg.n_banks)))
    elif not alive and econ.policy.bank_resolution_fund:
        # v12.4-fix: BOOTSTRAP a fully WIPED-OUT sector (no alive banks at all). Banking is maximally profitable
        # then (all credit demand is unmet), so a founder should be able to charter one -- else a total wipeout is
        # IRREVERSIBLE (the ROE gate returned early, so births froze forever). Enter at a modest fixed rate
        # (congestion term = 1). Gated on `not alive` -- NOT `total_capital<=EPS`, which can transiently hit 0 when
        # alive banks have negative balances -- and on the resolution-fund flag, so legacy configs keep the old
        # "return, no entry" behaviour in BOTH cases ⇒ bit-identical.
        probability = min(1.0, cfg.bank_entry_beta * 5.0)
    else:
        return
    for _ in range(cfg.bank_entry_max):
        if econ._bank_entry_rng.random() >= probability:
            continue
        founder = find_bank_founder(econ, econ.policy.bank_min_capital)
        if founder is None:
            break
        found_bank(econ, founder, econ.policy.bank_min_capital)
