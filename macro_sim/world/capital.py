"""The international capital layer (PLAN_v21): persistent cross-border positions.

v20 mean-reverts the dealer's inventory (trade balances). v21 relaxes that: the interest
differential offsets the trade-balance pressure on the rate, so a persistent position — a
net foreign asset position — accumulates, financed by yield-seeking capital. The held
position earns the domestic interest rate: a cross-border interest flow = the current
account's factor-income line = the GNP≠GDP wedge (Layer B emerging from Layer A). All flows
route through the ledger, so each economy conserves; the capital flag off ⇒ v20 exactly.
"""

from __future__ import annotations

from macro_sim.markets.matching import EPS
from macro_sim.world.fx import DEALER_ID


def _funder(econ):
    """The domestic account that funds/receives cross-border interest — the banking system
    (deposit interest on foreign-held deposits) or, failing that, the fiscal account. None
    ⇒ no funder ⇒ factor income skipped for this economy."""
    if getattr(econ, "bank", None) is not None:
        return econ.bank.id
    if econ.cfg.government:
        return econ._fiscal
    return None


def capital_interest(world) -> None:
    """Factor income (the GNP≠GDP wedge): the dealer's position in currency i earns economy
    i's rate. A positive dealer position (foreigners' claim on i) ⇒ economy i PAYS interest
    abroad (GNP < GDP); a negative position ⇒ it EARNS it. Recorded as a GAUGE on the NFA
    position (curr_i, i's outflow); the money flow is a v21.2 refinement (compounding it
    into the trading position destabilises the NFA dynamics — kept out of the first cut)."""
    dt = 1.0 / max(1.0, world.periods_per_year)
    factor = [0.0] * world.n
    for i, econ in enumerate(world.economies):
        pos = econ.ledger.balance(DEALER_ID)                     # dealer's i-position (curr_i)
        rate = float(getattr(econ, "_rate", econ.cfg.r_interest))
        factor[i] = pos * rate * dt                              # i's factor-income OUTFLOW (curr_i)
    world._factor_income = factor


def target_positions(world):
    """Portfolio-balance target: foreigners want to hold ``mobility·(rate_i − r_mean)·M_i``
    of currency i. A high rate ⇒ positive ⇒ foreigners accumulate i-claims ⇒ economy i is a
    net DEBTOR (the dealer's target i-position is positive). Fixed economy-id order (§9)."""
    rates = [float(getattr(e, "_rate", e.cfg.r_interest)) for e in world.economies]
    r_mean = sum(rates) / world.n
    return [world.capital_mobility * (rates[i] - r_mean) * world.economies[i].ledger.total_money
            for i in range(world.n)]


def capital_financing(world, i, best_price) -> float:
    """Capital RELAXES the balanced-trade constraint: net NFA = cumulative current-account
    imbalance, so a persistent position needs a persistent trade deficit financed by
    yield-seeking capital toward the portfolio target (§1). The per-tick inflow closes the
    gap to target; it finances EXTRA imports (a deficit) that accumulate the dealer's
    i-position toward target. At target the inflow stops and the NFA is stable. Returns the
    extra import budget (curr_i); negative for a low-rate economy (outflow). off ⇒ 0."""
    if not world.capital or world.capital_mobility == 0.0 or best_price <= 0.0:
        return 0.0
    target = target_positions(world)[i]
    current = world.economies[i].ledger.balance(DEALER_ID)
    return world.capital_adjust * (target - current)


def capital_grope_signal(world, scaled):
    """When capital is on, the rate gropes toward the capital-SUSTAINED position, not zero:
    signal_i = (inventory_i − target_i)/M_i. At the target the rate is stable and the NFA
    persists (else a nonzero equilibrium position would depreciate the rate forever).
    off ⇒ signal unchanged ⇒ v20 mean-to-zero groping ⇒ bit-identical."""
    if not world.capital or world.capital_mobility == 0.0:
        return scaled
    target = target_positions(world)
    return [scaled[i] - target[i] / max(1.0, world.economies[i].ledger.total_money)
            for i in range(world.n)]
