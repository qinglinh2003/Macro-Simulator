"""Banking-system phase orchestration."""

from __future__ import annotations

import random
from typing import Any

from macro_sim.domain.agents import Bank
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


def bank_constraint(econ: Any) -> bool:
    return econ.cfg.banking.bank_capital_constraint and len(econ.banks) > 1


def refresh_loan_books(econ: Any) -> None:
    econ._loan_book = {bank.id: 0.0 for bank in econ.banks}
    for firm in econ.firms:
        econ._loan_book[bank_for(econ, firm.id).id] += econ.ledger.debt(firm.id)
    for household in econ.households:
        econ._loan_book[bank_for(econ, household.id).id] += econ.ledger.debt(household.id)


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
    return cap + dep - loans


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
        from macro_sim.systems.securities import bond_market_value

        for lot in econ._bonds:
            if lot["holder"] == bank.id:
                cap += bond_market_value(econ, lot) - lot["cost"]
    return cap


def bank_capacity(econ: Any, bank: Bank) -> float:
    if not bank.alive:
        return 0.0
    capital = max(0.0, bank_economic_capital(econ, bank))
    return bank.kappa_bank * capital - econ._loan_book.get(bank.id, 0.0)


def shop_bank(econ: Any, borrower_id, amount: float) -> None:
    cfg = econ.cfg.banking
    cur = bank_for(econ, borrower_id)
    debt = econ.ledger.debt(borrower_id)
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


def grant_loan(econ: Any, borrower_id, amount: float) -> float:
    cfg = econ.cfg.banking
    if not bank_constraint(econ):
        econ.ledger.create_loan(borrower_id, amount)
        return amount
    if rate_competition(econ):
        shop_bank(econ, borrower_id, amount)
    bank = bank_for(econ, borrower_id)
    headroom = bank_capacity(econ, bank)
    if cfg.bank_exposure_limit > 0.0:
        capital = max(0.0, bank_economic_capital(econ, bank))
        concentration_room = cfg.bank_exposure_limit * capital - econ.ledger.debt(borrower_id)
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


def pay_bank_dividends(econ: Any, bank: Bank, payable: float) -> None:
    owners = bank.owners or {}
    total = sum(owners.values())
    if total <= 0.0:
        return
    for household_id, shares in owners.items():
        household = econ._hh_by_id.get(household_id)
        if household is None:
            continue
        amount = min(payable * shares / total, econ.ledger.balance(bank.id))
        if amount > EPS:
            econ.ledger.transfer(bank.id, household.id, amount)
            household.income_realized += amount


def bank_fundamental(econ: Any, bank: Bank, rate: float) -> float:
    if not bank.alive or bank.shares_outstanding <= 0.0:
        return 0.0
    return (max(0.0, econ.ledger.balance(bank.id)) + bank.earnings_ema / rate) / bank.shares_outstanding


def update_bank_valuation(econ: Any) -> None:
    cfg = econ.cfg.banking
    if not cfg.bank_equity:
        return
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
            sellers = [(household, -delta * sell_scale) for household, delta in order_book if delta < 0.0]
            for household, quantity in sellers:
                bank.owners[household.id] = bank.owners.get(household.id, 0.0) - quantity
                ledger.transfer("CLEARING", household.id, quantity * price)
            remainder = ledger.balance("CLEARING")
            if remainder > EPS and sellers:
                ledger.transfer("CLEARING", sellers[-1][0].id, remainder)
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
    if econ.ledger.balance(founder.id) < capital:
        redeem_household_bonds(econ, founder.id, capital - econ.ledger.balance(founder.id))
    econ.ledger.transfer(founder.id, bank_id, capital)
    econ._bank_spread[bank_id] = -abs(econ._bank_entry_rng.gauss(0.0, cfg.bank_spread_disp))
    econ._deposit_spread[bank_id] = 0.0
    shares = 100.0
    bank.shares_outstanding = shares
    bank.owners = {founder.id: shares}
    price = max(0.0, econ.ledger.balance(bank_id)) / shares
    bank.share_price = bank.share_last_price = bank.share_peak = price
    econ._bank_births += 1


def bank_equity_value(econ: Any, household_id) -> float:
    if not econ.cfg.banking.bank_equity:
        return 0.0
    value = 0.0
    for bank in econ.banks:
        shares = (bank.owners or {}).get(household_id, 0.0)
        if shares > 0.0:
            value += shares * bank.share_price
    return value


def settlement_node(econ: Any, account_id):
    if account_id == econ._fiscal:
        return "CB"
    if account_id == "CLEARING" or account_id in econ._bank_ids:
        return account_id
    return bank_for(econ, account_id).id


def enable_reserves(econ: Any) -> None:
    reserves = {bank.id: econ.ledger.balance(bank.id) for bank in econ.banks}
    for account in list(econ.firms) + list(econ.households):
        reserves[bank_for(econ, account.id).id] += econ.ledger.balance(account.id)
    reserves["CLEARING"] = 0.0
    reserves["CB"] = 0.0
    econ.ledger.enable_reserves(lambda account_id: settlement_node(econ, account_id), reserves)
    econ._reserve_M0 = econ.ledger.total_reserves


def fail_bank(econ: Any, bank: Bank) -> None:
    cfg = econ.cfg.banking
    bank.alive = False
    econ._bank_failures_total += 1
    econ._bank_deaths += 1
    alive = [candidate for candidate in econ.banks if candidate.alive]
    if cfg.bank_migrate_on_failure and alive:
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
    if cfg.bank_resolution_fund:
        # v12.4-fix: a DEPOSIT-INSURANCE / RESOLUTION backstop. The STATE absorbs the failed bank's residual
        # negative capital (transfer fiscal→bank, A5-safe, financed into the deficit) instead of SOCIALISING the
        # loss onto surviving banks' capital. The legacy pro-rata socialisation (the `elif` below) dumped one deep
        # insolvency onto every bank's balance, which `resolve_bank_failures` then failed in turn -- a runaway
        # INSOLVENCY-CONTAGION cascade that wiped the whole sector in one tick and was irreversible (seen at
        # NH5000). Depositors are made whole; the fiscal cost is the realistic price of the backstop.
        loss = -econ.ledger.balance(bank.id)
        if loss > EPS:
            econ.ledger.transfer(econ._fiscal, bank.id, loss)
    elif cfg.interbank and alive:
        loss = -econ.ledger.balance(bank.id)
        lenders = {
            candidate.id: econ.ledger.reserves(candidate.id)
            for candidate in alive
            if econ.ledger.reserves(candidate.id) > EPS
        }
        total = sum(lenders.values())
        if loss > EPS and total > EPS:
            for lender_id, lender_reserves in lenders.items():
                amount = min(loss * lender_reserves / total, max(0.0, -econ.ledger.balance(bank.id)))
                if amount > EPS:
                    econ.ledger.transfer(lender_id, bank.id, amount)
            econ._interbank_contagion_loss += loss


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


def run_interbank_phase(econ: Any) -> None:
    cfg = econ.cfg.banking
    econ._interbank_volume = 0.0
    econ._interbank_rate = econ._rate
    econ._payments_blocked = 0.0
    econ._interbank_contagion_loss = 0.0
    if not (cfg.interbank and len(econ.banks) > 1):
        return
    alive = [b for b in econ.banks if b.alive]
    if cfg.reserve_floor_frac > 0.0:
        for bank in alive:
            floor = -cfg.reserve_floor_frac * max(0.0, econ.ledger.balance(bank.id))
            if econ.ledger.reserve_min(bank.id) < floor - EPS:
                econ._payments_blocked += 1.0
    deficits = {b.id: -econ.ledger.reserves(b.id) for b in alive if econ.ledger.reserves(b.id) < -EPS}
    surplus = {b.id: econ.ledger.reserves(b.id) for b in alive if econ.ledger.reserves(b.id) > EPS}
    total_deficit, total_surplus = sum(deficits.values()), sum(surplus.values())
    if total_deficit <= EPS or total_surplus <= EPS:
        return
    tightness = min(1.0, total_deficit / total_surplus)
    ib_rate = max(0.0, econ._rate + cfg.interbank_rate_base + cfg.interbank_tightness * tightness)
    econ._interbank_rate = ib_rate
    econ._interbank_volume = total_deficit
    for deficit_id, deficit_value in deficits.items():
        interest = min(ib_rate * deficit_value, max(0.0, econ.ledger.balance(deficit_id)))
        if interest <= EPS:
            continue
        for surplus_id, surplus_value in surplus.items():
            amount = min(interest * surplus_value / total_surplus, econ.ledger.balance(deficit_id))
            if amount > EPS:
                econ.ledger.transfer(deficit_id, surplus_id, amount)


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
    if not bank_constraint(econ):
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
    total_capital = sum(max(0.0, econ.ledger.balance(b.id)) for b in alive)
    total_income = sum(b.interest_income for b in alive)
    if total_capital > EPS:
        roe = total_income / total_capital
        rate = max(econ._rate, 1e-4)
        probability = max(0.0, min(1.0, cfg.bank_entry_beta * (roe / rate - 1.0)))
        probability *= max(0.0, 1.0 - len(alive) / (2.0 * max(1, cfg.n_banks)))
    elif not alive and cfg.bank_resolution_fund:
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
        founder = find_bank_founder(econ, cfg.bank_min_capital)
        if founder is None:
            break
        found_bank(econ, founder, cfg.bank_min_capital)
