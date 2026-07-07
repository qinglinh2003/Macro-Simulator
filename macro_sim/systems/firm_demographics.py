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
    for f in econ.c_firms:
        nw = econ.ledger.balance(f.id) - econ.ledger.debt(f.id)
        f.insolvent_ticks = f.insolvent_ticks + 1 if nw < -EPS else 0
        if f.insolvent_ticks >= cfg.bankrupt_persist:
            dead.append(f)
    for f in dead:
        bankrupt_firm(econ, f)

    enter_consumption_firms(econ)


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
        for h in econ.households:
            h.holdings.pop(firm.id, None)
            if firm.id in h.watchlist:
                h.watchlist.remove(firm.id)
    econ.c_firms.remove(firm)
    econ.firms.remove(firm)
    if firm in econ.investing_firms:
        econ.investing_firms.remove(firm)
    led.remove_account(firm.id)
    econ._deaths += 1


def enter_consumption_firms(econ: Any) -> None:
    cfg = econ.cfg.firm_demographics
    rates = sorted(f.profit / f.capital for f in econ.c_firms if f.profit > EPS and f.capital > EPS)
    if not rates:
        return
    profit_rate = rates[len(rates) // 2]
    excess = profit_rate - econ._rate
    if excess <= 0.0:
        return
    desired_entries = cfg.entry_beta * excess * len(econ.c_firms)
    n_enter = int(desired_entries)
    if econ.rng.random() < (desired_entries - n_enter):
        n_enter += 1
    n_enter = min(cfg.entry_max, n_enter)
    startup_deposits = startup_cash(econ)
    for _ in range(n_enter):
        funder = pick_funder(econ, startup_deposits)
        if funder is None:
            break
        birth_consumption_firm(econ, funder, startup_deposits)


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


def birth_consumption_firm(econ: Any, funder: Any, startup_deposits: float = None) -> None:
    cfg = econ.cfg.firm_demographics
    if startup_deposits is None:
        startup_deposits = startup_cash(econ)
    idx = econ._next_c_id
    econ._next_c_id += 1
    firm = Firm.create_c_firm(idx, econ.cfg)
    firm.capital = cfg.startup_capital
    firm.capital_prev = cfg.startup_capital
    if cfg.gibrat_growth:
        firm.attractiveness = cfg.gibrat_entry_a0
    econ.ledger.add_account(firm.id)
    if len(econ.banks) > 1:
        econ._bank_of[firm.id] = bank_for(econ, funder.id)
    econ.ledger.transfer(funder.id, firm.id, startup_deposits)
    econ.c_firms.append(firm)
    econ.firms.append(firm)
    econ.investing_firms.append(firm)
    if cfg.per_firm_equity:
        firm.shares_outstanding = cfg.shares_per_firm
        book = startup_deposits + cfg.startup_capital
        firm.share_price = firm.share_last_price = max(EPS, book / cfg.shares_per_firm)
        firm.equity_fundamental = firm.share_price
        funder.holdings[firm.id] = funder.holdings.get(firm.id, 0.0) + cfg.shares_per_firm
        if firm.id not in funder.watchlist:
            funder.watchlist.append(firm.id)
    econ._births += 1
