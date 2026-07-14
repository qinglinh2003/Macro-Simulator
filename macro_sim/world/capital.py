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

# The pegging CB's FX reserves: an account holding the ANCHOR's currency, inside the anchor
# economy's ledger (a real foreign asset, not a scalar). Reserves cannot go negative — that
# is the crisis.
CBRES_ID = "CBRES"


def seed_reserves(world, amount_foreign: float) -> None:
    """Genesis: the pegging CB ACQUIRES its FX reserves through a conserving swap — its
    fiscus pays domestic currency to the dealer, which delivers foreign currency into the
    reserve account (the government borrowed at home to buy foreign assets, as CBs do).
    Numéraire-equal on both legs ⇒ a passthrough ⇒ the BoP gate holds from tick 0."""
    anchor = world.peg_anchor
    home, host = world.economies[0], world.economies[anchor]
    host.ledger.add_account(CBRES_ID)
    fiscal = getattr(home, "_fiscal", None)
    if fiscal is None or not home.ledger.has_account(fiscal) or amount_foreign <= EPS:
        return
    amount_dom = amount_foreign * world.rates.bilateral(0, anchor)
    home.ledger.transfer(fiscal, DEALER_ID, amount_dom)     # fiscus pays domestic (goes into debt)
    host.ledger.transfer(DEALER_ID, CBRES_ID, amount_foreign)   # dealer delivers the foreign asset


def _funder(econ):
    """The domestic account that funds/receives cross-border interest — the banking system
    (deposit interest on foreign-held deposits) or, failing that, the fiscal account. None
    ⇒ no funder ⇒ factor income skipped for this economy."""
    if getattr(econ, "bank", None) is not None:
        return econ.bank.id
    if econ.cfg.government:
        return econ._fiscal
    return None


def peg_defense(world, scaled):
    """The trilemma (PLAN_v21 §3). Under a PEG the exchange rate is FIXED and the central
    bank absorbs the imbalance onto FX reserves (the CB becomes the dealer of last resort).
    Open capital + an INDEPENDENT interest rate ⇒ persistent pressure ⇒ reserves drift
    monotonically ⇒ the peg is unsustainable: the CB has lost monetary autonomy (fixed rate
    + open capital + independent policy — pick two). Reserves hitting zero BREAKS the peg
    (the rate floats and devalues — a currency crisis, the reserve-drain analog of a bank
    run). Returns the (frozen while the peg holds) grope signal. peg off ⇒ unchanged."""
    if not world.peg:
        return scaled
    if world._peg_intact:
        # The trilemma proper: the pegged economy (0) runs an interest rate that differs
        # from the anchor. With open capital that mismatch is a CONTINUOUS one-way flow the
        # CB must keep offsetting from reserves. A LOWER rate ⇒ capital flees ⇒ the CB sells
        # FX reserves to defend. The POLICY rate (cfg.r_interest) — the deliberate choice,
        # not the endogenous Taylor path — is what defines "independent policy".
        rates = [float(e.cfg.r_interest) for e in world.economies]
        r_mean = sum(rates) / world.n
        mismatch = r_mean - rates[0]                  # >0 ⇒ econ0 rate too LOW ⇒ outflow ⇒ drain
        M0 = world.economies[0].ledger.total_money
        # POLICY: capital controls throttle the flow that drains reserves — closing the
        # account lets the peg + an independent rate BOTH survive (the trilemma's 3rd corner).
        pressure = world.capital_mobility * mismatch * M0 * (1.0 - world.capital_control)
        drain_for = pressure * world.peg_reserve_scale        # foreign currency to sell
        _defend_peg(world, drain_for)                          # a REAL, conserving FX swap
        world._pent_up += pressure                             # suppressed depreciation accumulates
        if world.reserves() <= EPS:
            world._peg_intact = False                 # reserves exhausted ⇒ peg breaks
            release = [0.0] * world.n                 # release pent-up pressure = DEVALUATION
            release[0] = max(0.0, world._pent_up / max(1.0, M0))
            return release
        return [0.0] * world.n                        # rate frozen — the peg holds
    return scaled                                     # peg already broken ⇒ free float


def _defend_peg(world, drain_for: float) -> None:
    """The CB defends the peg with a REAL foreign-exchange swap, routed through the dealer.

    Selling reserves (``drain_for`` > 0): the CB hands FOREIGN currency to the dealer (from
    its reserve account in the anchor economy's ledger) and takes back DOMESTIC currency —
    it is buying up its own currency to hold the peg. Buying reserves (< 0) is the reverse.
    Numéraire-equal on both legs ⇒ a passthrough ⇒ the multilateral BoP gate holds.
    """
    anchor = world.peg_anchor
    home, host = world.economies[0], world.economies[anchor]
    fiscal = getattr(home, "_fiscal", None)
    if fiscal is None or not home.ledger.has_account(fiscal):
        return
    e = world.rates.e
    if drain_for > EPS:                                # SELL reserves (defend a weak currency)
        drain_for = min(drain_for, host.ledger.balance(CBRES_ID))   # cannot sell what it lacks
        if drain_for <= EPS:
            return
        drain_dom = drain_for * world.rates.bilateral(0, anchor)    # curr_anchor → curr_0
        host.ledger.transfer(CBRES_ID, DEALER_ID, drain_for)        # CB → dealer (foreign)
        home.ledger.transfer(DEALER_ID, fiscal, drain_dom)          # dealer → CB (domestic)
    elif drain_for < -EPS:                             # BUY reserves (resist appreciation)
        buy_for = -drain_for
        buy_dom = buy_for * world.rates.bilateral(0, anchor)
        home.ledger.transfer(fiscal, DEALER_ID, buy_dom)            # CB pays domestic
        host.ledger.transfer(DEALER_ID, CBRES_ID, buy_for)          # dealer → CB (foreign)


def _pay_households(econ, amount: float) -> None:
    """The dealer pays `amount` into the economy's households, split equally."""
    if amount <= EPS:
        return
    per = amount / len(econ.households)
    for h in econ.households:
        econ.ledger.transfer(DEALER_ID, h.id, per)


def capital_interest(world) -> None:
    """Factor income — a REAL conserving cross-border flow (the GNP≠GDP wedge).

    A positive dealer position in currency i means foreigners hold claims on economy i: i is
    a net DEBTOR and PAYS interest abroad (GNP < GDP). A negative position means the economy
    is a net CREDITOR. The interest is not parked in the dealer (that would compound the
    principal); it is REPATRIATED — the dealer routes it, in numéraire-equal value, to the
    creditor economies' households as investment income (GNP > GDP for them).

    Collected numéraire ≡ distributed numéraire, so the flow is a PASSTHROUGH and the
    multilateral BoP gate holds. It is a true current-account item: the debtor's NFA
    deteriorates by what it pays, the creditor's improves by what it receives.
    """
    dt = 1.0 / max(1.0, world.periods_per_year)
    n = world.n
    rates = world.rates
    e = rates.e
    factor = [0.0] * n

    positions = [econ.ledger.balance(DEALER_ID) for econ in world.economies]
    # creditor weights (numéraire) — the interest must have somewhere to go, else collecting
    # it would leave value stranded in the dealer and break the passthrough identity.
    weights = [max(0.0, -positions[j]) / e[j] for j in range(n)]
    total_w = sum(weights)
    if total_w <= EPS:
        world._factor_income = factor
        return

    collected_num = 0.0
    for i, econ in enumerate(world.economies):
        if positions[i] <= EPS:
            continue                                   # not a debtor
        rate = float(getattr(econ, "_rate", econ.cfg.r_interest))
        interest = positions[i] * rate * dt
        funder = _funder(econ)
        if interest <= EPS or funder is None:
            continue
        econ.ledger.transfer(funder, DEALER_ID, interest)   # the DEBTOR pays interest abroad
        factor[i] = interest                                # i's factor-income OUTFLOW (curr_i)
        collected_num += interest / e[i]

    if collected_num <= EPS:
        world._factor_income = factor
        return

    for j, econ in enumerate(world.economies):           # repatriate to the CREDITORS
        if weights[j] <= EPS:
            continue
        amount_j = collected_num * (weights[j] / total_w) * e[j]   # numéraire → curr_j
        _pay_households(econ, amount_j)
        factor[j] -= amount_j                            # j's factor-income INFLOW
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
    # POLICY: capital controls throttle the flow (0 = free mobility, 1 = closed account).
    # Closing the account lets a peg keep monetary autonomy — the trilemma's third corner.
    return world.capital_adjust * (target - current) * (1.0 - world.capital_control)


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
