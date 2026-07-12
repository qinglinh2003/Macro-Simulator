"""Consumption-firm entry and bankruptcy orchestration."""

from __future__ import annotations

from typing import Any

from macro_sim.domain.agents import Firm
from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import bank_for


def apply_gibrat_shock(econ: Any) -> None:
    cfg = econ.cfg.firm_demographics
    if not cfg.gibrat_growth or cfg.gibrat_sigma <= 0.0:
        return
    dispersion = cfg.gibrat_sigma
    mu = -0.5 * dispersion * dispersion
    rng = econ._gibrat_rng
    for firm in econ.c_firms:
        firm.attractiveness = max(EPS, firm.attractiveness * rng.lognormvariate(mu, dispersion))


def run_firm_demographics_phase(econ: Any) -> None:
    econ._births = econ._deaths = 0
    econ._writeoffs = 0.0
    cfg = econ.cfg.firm_demographics
    if not cfg.firm_dynamics:
        return

    dead = []
    idle_exits = []
    for f in econ.c_firms:
        nw = econ.ledger.balance(f.id) - econ.ledger.debt(f.id)
        f.insolvent_ticks = f.insolvent_ticks + 1 if nw < -EPS else 0
        if f.insolvent_ticks >= cfg.bankrupt_persist:
            dead.append(f)
            continue
        if cfg.shell_exit_ticks > 0:
            # a shell never trips the insolvency rule (indexed startup cash, no debt, no trades):
            # exit on sustained idleness instead, so the firm count cannot ratchet upward forever
            if f.produced <= EPS and f.sales <= EPS:
                f.idle_ticks += 1
                if f.idle_ticks >= cfg.shell_exit_ticks:
                    idle_exits.append(f)
            else:
                f.idle_ticks = 0
    for f in dead:
        bankrupt_firm(econ, f)
    for f in idle_exits:
        liquidate_idle_firm(econ, f)

    # v16-L6 subscale exit: whole-person employment imposes a MINIMUM VIABLE FIRM
    # SCALE. A firm whose expected demand (footfall included) cannot justify the
    # viability line in WORKERS for the grace period exits by liquidation at a daily
    # HAZARD -- staggered deaths, so survivors inherit the demand share and the
    # consolidation self-terminates above the line. C and K firms; builders are
    # EXEMPT (hard-cyclical demand; their demography belongs to the housing grammar).
    # K-firm ENTRY does not exist yet (documented): the consolidation is one-way
    # down to the viable count, floored at one firm per sector.
    if econ.cfg.firm_subscale_exit:
        from macro_sim.behavior import planning as B
        subscale_exits = []
        for f in list(econ.c_firms) + list(econ.k_firms):
            need = B.labor_demand_notional(f, f.demand_expected, econ._pubcap_factor)
            if need < econ.cfg.subscale_viability_workers:
                f.subscale_ticks += 1
                if (f.subscale_ticks >= econ.cfg.subscale_grace_days
                        and econ._subscale_rng.random() < econ.cfg.subscale_exit_hazard):
                    subscale_exits.append(f)
            else:
                f.subscale_ticks = 0
        for f in subscale_exits:
            sector = econ.k_firms if f in econ.k_firms else econ.c_firms
            if len(sector) <= 1:
                continue                     # never extinguish a whole sector
            liquidate_idle_firm(econ, f)

    enter_consumption_firms(econ)
    if econ.cfg.capital_firm_entry:
        enter_capital_firms(econ)


def bankrupt_firm(econ: Any, firm: Firm) -> None:
    cfg = econ.cfg.firm_demographics
    led = econ.ledger
    pay = min(led.balance(firm.id), led.debt(firm.id))
    if pay > EPS:
        led.repay(firm.id, pay)
    bad = led.debt(firm.id)
    if bad > EPS:
        led.write_off(firm.id, bank_for(econ, firm.id).id, bad)
        econ._writeoffs += bad
    residual = led.balance(firm.id)
    if residual > EPS:
        led.transfer(firm.id, bank_for(econ, firm.id).id, residual)
    if cfg.per_firm_equity:
        bridge = getattr(econ, "demographic_bridge", None)
        for h in econ.households:
            shares = h.holdings.pop(firm.id, None)
            if bridge is not None and shares:
                bridge.post_household_equity_trade(
                    h.id,
                    firm.id,
                    cash_delta=0.0,
                    share_delta=-shares,
                )
            if firm.id in h.watchlist:
                h.watchlist.remove(firm.id)
    if getattr(econ, "labor_market", None) is not None:
        # v16-L1: firm exit is a MASS LAYOFF -- the whole roster enters the pool
        # (the credit-crunch -> bankruptcy -> unemployment chain becomes explicit)
        econ.labor_market.on_firm_exit(firm.id, getattr(econ, "labor_accounts", None))
    if firm in econ.c_firms:
        econ.c_firms.remove(firm)
    elif firm in econ.k_firms:              # v16-L6: subscale exit reaches K-firms too
        econ.k_firms.remove(firm)
    econ.firms.remove(firm)
    if firm in econ.investing_firms:
        econ.investing_firms.remove(firm)
    led.remove_account(firm.id)
    econ._deaths += 1


def liquidate_idle_firm(econ: Any, firm: Firm) -> None:
    """Voluntary wind-up of an idle shell: settle debts, return the residual deposits to the
    SHAREHOLDERS pro rata (a bankruptcy hands the residual to the bank -- fine for insolvency,
    but a shell's residual is the founder's indexed startup cash, and routing it to the bank
    would be a systematic household->bank wealth transfer), then reuse the bankruptcy cleanup
    for the share/watchlist/account teardown."""
    cfg = econ.cfg.firm_demographics
    led = econ.ledger
    pay = min(led.balance(firm.id), led.debt(firm.id))
    if pay > EPS:
        led.repay(firm.id, pay)
    residual = led.balance(firm.id) - led.debt(firm.id)
    if cfg.per_firm_equity and residual > EPS and firm.shares_outstanding > EPS:
        bridge = getattr(econ, "demographic_bridge", None)
        holders = [(h, h.holdings.get(firm.id, 0.0)) for h in econ.households]
        total_shares = sum(s for _, s in holders)
        if total_shares > EPS:
            for h, shares in holders:
                if shares <= 0.0:
                    continue
                amount = residual * shares / total_shares
                if amount > EPS:
                    led.transfer(firm.id, h.id, amount)
                    if bridge is not None:
                        bridge.post_household_equity_trade(h.id, firm.id, cash_delta=amount, share_delta=0.0)
    bankrupt_firm(econ, firm)


def enter_consumption_firms(econ: Any) -> None:
    cfg = econ.cfg.firm_demographics
    if cfg.real_entry_signal:
        # v13: two fixes to a signal that pinned entry at entry_max for ten straight years.
        # (1) deflate by the price level so inflation cannot masquerade as a real return;
        # (2) take the median over ALL capitalized firms, not just the profitable ones --
        # conditioning on profit > 0 is survivor bias, so the median was positive by
        # construction and entry never turned off.
        p = max(EPS, econ._price_level)
        rates = sorted(f.profit / (f.capital * p) for f in econ.c_firms if f.capital > EPS)
    else:
        rates = sorted(f.profit / f.capital for f in econ.c_firms if f.profit > EPS and f.capital > EPS)
    if not rates:
        return
    profit_rate = rates[len(rates) // 2]
    excess = profit_rate - (econ._rate + cfg.entry_hurdle)
    if excess <= 0.0:
        return
    desired_entries = cfg.entry_beta * excess * len(econ.c_firms)
    n_enter = int(desired_entries)
    if econ.rng.random() < (desired_entries - n_enter):
        n_enter += 1
    n_enter = min(cfg.entry_max, n_enter)
    startup_deposits = startup_cash(econ)
    for _ in range(n_enter):
        capital_lots = None
        need_cash = startup_deposits
        if cfg.real_entry_signal:
            # v13: the startup CAPITAL is not conjured -- it is BOUGHT from K-firm inventory
            # at posted prices. Free entrant capital compounded into a supply glut (the smoke
            # economy's capital stock doubled through entry alone while measured investment ran
            # ~1 unit/tick, and unit costs collapsed 3.5x into a deflation trap). When the
            # capital-goods market cannot supply a viable stock, the entry does not happen.
            capital_lots, available, capital_cost = _quote_startup_capital(econ, cfg.startup_capital)
            if available < 0.5 * cfg.startup_capital:
                break
            need_cash = startup_deposits + capital_cost
        funder = pick_funder(econ, need_cash)
        if funder is None:
            break
        birth_consumption_firm(econ, funder, startup_deposits, capital_lots=capital_lots)


def enter_capital_firms(econ: Any) -> None:
    """v16-L6 demand-driven K entry (the expanding half of consolidation).

    Trigger: EVERY incumbent K-firm's notional labor demand sits above
    k_entry_demand x the viability line (the sector is visibly capacity-short --
    footfall makes this observable even at zero inventory). Then, at a daily
    hazard, one K-firm enters: market-anchored price/wage/expectations, no free
    inventory, seeded from the cash-richest incumbent's retained earnings (the
    spin-off shortcut -- K-sector founder equity is deferred with the rest of
    K equity). Subscale exit prunes any overshoot, so the K-firm count is an
    emergent equilibrium of the two hazards, not a config constant."""
    from macro_sim.behavior import planning as B
    cfg = econ.cfg
    incumbents = list(econ.k_firms)
    if not incumbents:
        return
    line = cfg.k_entry_demand * cfg.subscale_viability_workers
    if any(B.labor_demand_notional(f, f.demand_expected, econ._pubcap_factor) < line
           for f in incumbents):
        return
    if econ._subscale_rng.random() >= cfg.k_entry_hazard:
        return
    deposits = startup_cash(econ)
    funder = max(incumbents, key=lambda f: econ.ledger.balance(f.id))
    if econ.ledger.balance(funder.id) < 2.0 * deposits:
        return                              # the sector cannot finance expansion yet
    idx = getattr(econ, "_next_k_id", cfg.n_firms_k)   # genesis takes K0..K{n-1}
    econ._next_k_id = idx + 1
    firm = Firm.create_k_firm(idx, econ.cfg)
    n = len(incumbents)
    firm.inventory = 0.0                    # entrants produce before they sell
    firm.price = sum(f.price for f in incumbents) / n
    firm.wage = sum(f.wage for f in incumbents) / n
    firm.demand_expected = sum(f.demand_expected for f in incumbents) / n
    firm.sales_prev = firm.demand_expected  # neutral first B2 update
    firm.target_inventory_prev = firm.phi * firm.demand_expected
    econ.ledger.add_account(firm.id)
    if len(econ.banks) > 1:
        econ._bank_of[firm.id] = bank_for(econ, funder.id)
        econ._node_of.pop(firm.id, None)
    econ.ledger.transfer(funder.id, firm.id, deposits)
    econ.k_firms.append(firm)
    econ.firms.append(firm)
    if firm.invests:
        econ.investing_firms.append(firm)
    econ._births += 1


def _quote_startup_capital(econ: Any, need: float):
    """Cheapest-first quote for `need` capital units from K-firm inventories.
    Returns (lots, total_units, total_cost) with lots = [(k_firm, units)]."""
    lots = []
    total = 0.0
    cost = 0.0
    for kf in sorted((k for k in econ.k_firms if k.inventory > EPS), key=lambda k: k.price):
        q = min(kf.inventory, need - total)
        if q <= EPS:
            break
        lots.append((kf, q))
        total += q
        cost += q * kf.price
        if total >= need - EPS:
            break
    return lots, total, cost


def startup_cash(econ: Any) -> float:
    cfg = econ.cfg.firm_demographics
    if not cfg.index_startup:
        return cfg.startup_deposits
    return cfg.startup_deposits * (econ._price_level / cfg.p_firm0)


def pick_funder(econ: Any, need: float) -> Any:
    for _ in range(12):
        h = econ.households[econ.rng.randrange(len(econ.households))]
        if econ.ledger.balance(h.id) >= need:
            return h
    return None


def birth_consumption_firm(econ: Any, funder: Any, startup_deposits: float = None,
                           capital_lots: Any = None) -> None:
    cfg = econ.cfg.firm_demographics
    if startup_deposits is None:
        startup_deposits = startup_cash(econ)
    idx = econ._next_c_id
    econ._next_c_id += 1
    firm = Firm.create_c_firm(idx, econ.cfg)
    firm.capital = cfg.startup_capital
    firm.capital_prev = cfg.startup_capital
    if cfg.real_entry_signal:
        # entrants have produced nothing: giving them cfg.inv_firm0 free units created ~0.45%
        # of cumulative real output ex nihilo at the 10k x 3650t scale (3 entrants x 10 units
        # per tick). Genesis firms keep inv_firm0 as the standing initial condition.
        firm.inventory = 0.0
        firm.price = max(firm.price, econ._price_level)
        firm.capital = 0.0
        firm.capital_prev = 0.0
    if cfg.gibrat_growth:
        firm.attractiveness = cfg.gibrat_entry_a0
    econ.ledger.add_account(firm.id)
    if len(econ.banks) > 1:
        econ._bank_of[firm.id] = bank_for(econ, funder.id)
        econ._node_of.pop(firm.id, None)
    capital_cost = 0.0
    if capital_lots:
        capital_cost = sum(q * kf.price for kf, q in capital_lots)
    econ.ledger.transfer(funder.id, firm.id, startup_deposits + capital_cost)
    if capital_lots:
        # execute the startup-capital purchase quoted in enter_consumption_firms: a REAL
        # capital-goods transaction (units leave K inventory, revenue reaches the K-firm,
        # and K demand expectations see the sale via the sales counter)
        for kf, q in capital_lots:
            pay = q * kf.price
            take = min(q, kf.inventory)
            kf.inventory -= take
            kf.sales += take
            kf.revenue += pay
            kf.profit += pay
            econ.ledger.transfer(firm.id, kf.id, pay)
            firm.capital += take
        firm.capital_prev = firm.capital
    bridge = getattr(econ, "demographic_bridge", None)
    econ.c_firms.append(firm)
    econ.firms.append(firm)
    econ.investing_firms.append(firm)
    if cfg.per_firm_equity:
        firm.shares_outstanding = cfg.shares_per_firm
        book = startup_deposits + (capital_cost if capital_lots else cfg.startup_capital)
        firm.share_price = firm.share_last_price = max(EPS, book / cfg.shares_per_firm)
        firm.equity_fundamental = firm.share_price
        funder.holdings[firm.id] = funder.holdings.get(firm.id, 0.0) + cfg.shares_per_firm
        if bridge is not None:
            bridge.post_household_equity_trade(
                funder.id,
                firm.id,
                cash_delta=-(startup_deposits + capital_cost),
                share_delta=cfg.shares_per_firm,
            )
        if firm.id not in funder.watchlist:
            funder.watchlist.append(firm.id)
    econ._births += 1
