"""The two abstract interfaces of the kernel (spec §7.3), at minimal defaults.

  * MatchingProtocol -- how a buyer chooses among sellers in the GOODS market.
    Default RandomMatch: buyers do NOT compare prices (spec §7.3). The deferred
    alternative PriceSortedMatch (buyers prefer cheaper sellers -> price
    competition) is the SAME interface, so swapping it in is added data, not a
    refactor (spec §5).

  * Goods -- the commodity set. Default |Goods| = 1. Code always iterates the set
    rather than hard-coding a scalar, so multi-good is added data + one demand-
    allocation rule, not a refactor (spec §7.3).

The labor market is not routed through MatchingProtocol: in the kernel there is
no wage to shop (firms post wages, households supply inelastically, short-side
rationing), so price-comparison has no meaning there. Its random ordering uses
the same seeded RNG (spec M3(a)) and lives in economy.py.

Small order/offer records used by the goods-market execution live here too, so
the market mechanics have a clean vocabulary independent of agent internals.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, List, Sequence


# Shared epsilon: below this, a quantity/budget is treated as exhausted. Keeps
# float dust from spawning meaningless sub-cent trades.
EPS = 1e-9


@dataclass
class BuyOrder:
    """A buyer's live demand in a market (goods market: a household)."""
    account: str          # ledger account that pays
    demand: float         # units wanted (upper cap)
    budget: float         # money cap; already = min(desired, live deposits) per A4
    ref: Any = None       # back-reference to the agent, for recording


@dataclass
class SellOffer:
    """A seller's live offer in a market (goods market: a firm)."""
    account: str          # ledger account that receives
    stock: float          # units available (mutated as it sells)
    price: float          # per-unit posted price (seller sets it)
    ref: Any = None
    sold: float = 0.0      # units sold this tick (accumulated)


@dataclass
class Trade:
    """A single executed goods transaction (for recording / diagnostics)."""
    buyer: str
    seller: str
    qty: float
    price: float
    value: float


def execute_market(orders: "List[BuyOrder]", offers: "List[SellOffer]", *,
                   protocol: "MatchingProtocol", rng: random.Random, ledger) -> "List[Trade]":
    """Run one decentralized market to exhaustion (M1). Reused by the consumption
    market (Phase 3) and the capital-goods market (Phase 3.5).

    Buyers are processed in random order (M3(a)); each consults ``protocol`` for the
    order to try sellers, and trades ``min(remaining demand, remaining budget/price,
    seller stock)`` at the seller's posted price, moving money via ``ledger.transfer``.
    A buyer with ``demand=inf`` (consumption: budget binds) and one with a finite
    ``demand`` (investment: unit demand I* binds) are both handled by the same min().
    """
    trades: List[Trade] = []
    buy_order = list(orders)
    rng.shuffle(buy_order)

    if isinstance(protocol, PreferentialMatch):
        # v8.1 Gibrat/Zipf path: a buyer picks a live seller with probability ∝ attractiveness^β
        # (size-biased demand). With multiplicative attractiveness shocks + entry/exit this yields
        # a Pareto firm-size distribution (Simon 1955). Exhausted sellers are swap-popped.
        beta = protocol.beta
        eps_price = getattr(protocol, "price_elasticity", 0.0)   # v9.1: price competition (ε=0 ⇒ pure pref)
        live = [o for o in offers if o.stock > EPS and o.price > 0]
        for bo in buy_order:
            rem_budget, rem_demand, acct = bo.budget, bo.demand, bo.account
            while rem_budget > EPS and rem_demand > EPS and live:
                weights = [max(EPS, getattr(o.ref, "attractiveness", 1.0)) ** beta / o.price ** eps_price
                           for o in live]
                r = rng.random() * sum(weights)
                chosen, c = 0, 0.0
                for j, w in enumerate(weights):
                    c += w
                    if r <= c:
                        chosen = j
                        break
                so = live[chosen]
                if so.account == acct:                        # no self-trade (K-market)
                    alt = next((j for j in range(len(live)) if live[j].account != acct), -1)
                    if alt < 0:
                        break
                    chosen, so = alt, live[alt]
                qty = min(rem_demand, rem_budget / so.price, so.stock)
                if qty <= EPS:
                    break
                value = qty * so.price
                ledger.transfer(acct, so.account, value)
                so.stock -= qty
                so.sold += qty
                rem_budget -= value
                rem_demand -= qty
                trades.append(Trade(acct, so.account, qty, so.price, value))
                if so.stock <= EPS:
                    live[chosen] = live[-1]
                    live.pop()
        return trades

    if isinstance(protocol, SampledCompareMatch):
        # Information-transparency fast path (§ buyer price comparison). Each buyer
        # samples m random live sellers and buys from the CHEAPEST of them; exhausted
        # sellers are swap-popped. m=1 is zero transparency (a single random pick =
        # RandomMatch, identical randrange draw); m >= #sellers is full transparency
        # (perfect price comparison). Amortized O(N_buyers*m + N_sellers).
        m = protocol.m
        live = [o for o in offers if o.stock > EPS and o.price > 0]
        for bo in buy_order:
            rem_budget = bo.budget
            rem_demand = bo.demand
            acct = bo.account
            while rem_budget > EPS and rem_demand > EPS and live:
                L = len(live)
                if m == 1:
                    chosen = rng.randrange(L)
                    if live[chosen].account == acct:          # no self-trade (v2.5)
                        if L == 1:
                            break
                        chosen = next((j for j in range(L) if live[j].account != acct), -1)
                        if chosen < 0:
                            break
                else:
                    k = m if m < L else L                     # sample size (clamp to full)
                    idxs = range(L) if k >= L else rng.sample(range(L), k)
                    chosen = -1
                    best_price = float("inf")
                    for j in idxs:
                        o = live[j]
                        if o.account == acct:
                            continue
                        if o.price < best_price:              # buy from the cheapest sampled
                            best_price = o.price
                            chosen = j
                    if chosen < 0:
                        break
                so = live[chosen]
                qty = min(rem_demand, rem_budget / so.price, so.stock)
                if qty <= EPS:
                    break                                     # buyer's budget is dust -> done
                value = qty * so.price
                ledger.transfer(acct, so.account, value)
                so.stock -= qty
                so.sold += qty
                rem_budget -= value
                rem_demand -= qty
                trades.append(Trade(acct, so.account, qty, so.price, value))
                if so.stock <= EPS:
                    live[chosen] = live[-1]                   # swap-pop the exhausted seller
                    live.pop()
        return trades

    # Generic path (e.g. PriceSortedMatch): consult the protocol's per-buyer ordering.
    for bo in buy_order:
        rem_budget = bo.budget
        rem_demand = bo.demand
        for so in protocol.seller_order(bo, offers, rng):
            if rem_budget <= EPS or rem_demand <= EPS:
                break
            if so.stock <= EPS or so.price <= 0 or so.account == bo.account:
                continue
            qty = min(rem_demand, rem_budget / so.price, so.stock)
            if qty <= EPS:
                continue
            value = qty * so.price
            ledger.transfer(bo.account, so.account, value)
            so.stock -= qty
            so.sold += qty
            rem_budget -= value
            rem_demand -= qty
            trades.append(Trade(bo.account, so.account, qty, so.price, value))
    return trades


class MatchingProtocol:
    """Interface: given a buyer and the live offers, order the sellers to try."""

    name = "abstract"

    def seller_order(self, buyer: BuyOrder, offers: Sequence[SellOffer],
                     rng: random.Random) -> List[SellOffer]:
        raise NotImplementedError


class SampledCompareMatch(MatchingProtocol):
    """Continuous information transparency (§ buyer price comparison). A buyer samples
    ``m`` random sellers (with stock) and buys from the **cheapest** of them. ``m`` is a
    single dial spanning the whole competition axis:

      * m = 1            -> zero transparency: one random seller, no comparison (RandomMatch).
      * 1 < m < #sellers -> partial transparency: "compare m, take the cheapest" ("货比三家").
      * m >= #sellers    -> full transparency: perfect price comparison (PriceSortedMatch).

    So RandomMatch and PriceSortedMatch are not separate protocols but the two endpoints
    of this axis (more parsimonious). Sweeping m lets one study how competition strength
    (and the monopoly->oligopoly transition) varies with information transparency — the
    standard limited-search framing (Stigler). execute_market fast-paths this directly.
    """

    def __init__(self, m: int = 1):
        assert m >= 1, "search sample size m must be >= 1"
        self.m = m
        self.name = f"sampled_m{m}" if m > 1 else "random"

    def seller_order(self, buyer: BuyOrder, offers: Sequence[SellOffer],
                     rng: random.Random) -> List[SellOffer]:
        # Fallback ordering (execute_market fast-paths this class; kept for completeness):
        # cheapest of a random m-sample first, then the rest in random order.
        live = [o for o in offers if o.stock > EPS and o.price > 0]
        rng.shuffle(live)
        k = min(self.m, len(live))
        return sorted(live[:k], key=lambda o: o.price) + live[k:]


class RandomMatch(SampledCompareMatch):
    """Zero-transparency special case (m=1): buyers do not compare prices. Kept as a
    named alias; RandomMatch() == SampledCompareMatch(1)."""

    def __init__(self):
        super().__init__(m=1)


class PreferentialMatch(MatchingProtocol):
    """v8.1: size-biased (preferential-attachment) demand. A buyer chooses a seller with probability
    proportional to ``attractiveness**beta / price**price_elasticity``. beta≈1 (linear preferential
    attachment) with multiplicative attractiveness shocks + entry/exit gives a Zipf firm-size
    distribution (Simon 1955); beta>1 tips to winner-take-all, beta<1 to over-equal. execute_market
    fast-paths it. v9.1: `price_elasticity` (ε) adds PRICE competition on top of the brand pull -- a
    cheaper firm attracts more demand -- keeping Zipf while restoring the demand-side price brake.
    ε=0 ⇒ pure preferential (bit-identical), since price**0 == 1."""

    def __init__(self, beta: float = 1.0, price_elasticity: float = 0.0):
        assert beta >= 0.0, "preferential-attachment beta must be >= 0"
        assert price_elasticity >= 0.0, "price elasticity must be >= 0"
        self.beta = beta
        self.price_elasticity = price_elasticity
        self.name = f"preferential_b{beta}_e{price_elasticity}"

    def seller_order(self, buyer: BuyOrder, offers: Sequence[SellOffer],
                     rng: random.Random) -> List[SellOffer]:
        live = [o for o in offers if o.stock > EPS and o.price > 0]
        rng.shuffle(live)      # fallback; execute_market fast-paths the weighted selection
        return live


class PriceSortedMatch(MatchingProtocol):
    """Deferred alternative (spec §5, §7.3): buyers prefer cheaper sellers, which
    introduces price competition. Same interface; NOT used in round 1. Ties are
    broken randomly (seeded) so equal-priced sellers do not get a fixed advantage.
    """

    name = "price_sorted"

    def seller_order(self, buyer: BuyOrder, offers: Sequence[SellOffer],
                     rng: random.Random) -> List[SellOffer]:
        live = [o for o in offers if o.stock > EPS and o.price > 0]
        rng.shuffle(live)                     # randomize ties first...
        live.sort(key=lambda o: o.price)      # ...then stable-sort by price
        return live


@dataclass
class Goods:
    """The commodity set (spec §7.3). Default: a single good indexed 0.

    Kept as a set so all consumption/production code iterates rather than assuming
    a scalar. Kernel demand allocation is trivial (all budget -> the one good);
    multi-good adds an allocation rule here, not a refactor upstream.
    """
    names: List[str] = field(default_factory=lambda: ["good"])

    def __len__(self) -> int:
        return len(self.names)

    @property
    def single(self) -> str:
        assert len(self.names) == 1, "kernel is single-good; multi-good not wired yet"
        return self.names[0]
