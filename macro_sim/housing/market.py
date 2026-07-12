"""v15.1 resale market: posted-ask listings, monthly matching sessions, atomic sales.

The secondary market IS the housing market (construction waits until v15.4). Grammar
follows the model's native markets: posted prices + inventory-pressure decay + periodic
matching (the marriage-market cadence), never a Walrasian auction.

Listing inflows in v15.1 (forced-first discipline):
  - PROBATE: empty households' dwellings are listed instead of escheated in kind;
    sale proceeds go to the fiscal account (bona vacantia -- heir participation in
    house value needs house claims in estate packages, a later refinement).
  - DISTRESS: member households whose deposits fall below a floor list one dwelling
    (selling the home for liquidity); proceeds post through the person-claim layer.

Buyers: houseless households, cheapest-first over k visible listings, budget capped
at deposits*(1-buffer). One purchase per session. With prices anchored at 3-4x annual
income and no mortgages yet, this is by design a CASH-CONSTRAINED regime: thin volume,
buyer's market -- the reference regime the v15.2 credit unlock is compared against.

Every sale is ATOMIC: ledger transfer + registry title + person-claim postings inside
this function, and the registry/claim hard gates assert after the phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from macro_sim.markets.matching import EPS


@dataclass
class Listing:
    dwelling_id: int
    seller_account: str
    ask: float
    listed_tick: int
    forced: bool = False


@dataclass
class HousingMarket:
    session_interval: int = 30
    ask_markup: float = 0.05        # voluntary listings post above the reference price
    forced_discount: float = 0.10   # probate/foreclosure listings post below it
    ask_decay: float = 0.03         # per-session cut while unsold (inventory pressure)
    search_k: int = 5               # buyer sees only the k cheapest listings
    buyer_buffer: float = 0.25      # deposits share a buyer will not spend
    distress_floor: float = 5.0     # deposits below this list the home for liquidity

    listings: dict[int, Listing] = field(default_factory=dict)   # dwelling_id -> Listing
    sales_total: int = 0
    # per-session gauges (metrics read these; refreshed each session)
    last_session_sales: int = 0
    last_session_volume: float = 0.0
    last_session_tom: float = 0.0        # mean time-on-market of the units SOLD
    forced_share: float = 0.0            # forced share of current listings

    def is_listed(self, dwelling_id: int) -> bool:
        return dwelling_id in self.listings

    def list_dwelling(self, econ: Any, dwelling_id: int, seller_account: str, *, forced: bool) -> None:
        if dwelling_id in self.listings:
            return
        reference = max(EPS, float(econ._house_price))
        ask = reference * ((1.0 - self.forced_discount) if forced else (1.0 + self.ask_markup))
        self.listings[dwelling_id] = Listing(
            dwelling_id=dwelling_id,
            seller_account=seller_account,
            ask=ask,
            listed_tick=int(econ.t),
            forced=forced,
        )


def run_housing_market_phase(econ: Any) -> None:
    market = getattr(econ, "housing_market", None)
    housing = getattr(econ, "housing", None)
    if market is None or housing is None:
        return
    rental = getattr(econ, "rental_market", None)
    if rental is not None:
        rental.collect_rents(econ)        # v15.3: tenancies pay every tick, not per session
    if getattr(econ, "builders", None):
        from macro_sim.housing.construction import run_construction_step
        run_construction_step(econ)       # v15.4: fold output, mint under permits+land fee
    if econ.t % market.session_interval != 0:
        return

    _ingest_distress_listings(econ, market, housing)
    _drop_stale_listings(econ, market, housing)
    mortgage_book = getattr(econ, "mortgage_book", None)
    if mortgage_book is not None:
        # v15.2: reconcile secured balances against the ledger, run foreclosures --
        # seized dwellings join this session's supply as forced bank listings
        mortgage_book.maintain(econ)

    # ---- matching session: buyers cheapest-first over the k cheapest listings ----
    led = econ.ledger
    bridge = getattr(econ, "demographic_bridge", None)
    fiscal = getattr(econ, "_fiscal", None)
    book = sorted(market.listings.values(), key=lambda l: (l.ask, l.dwelling_id))
    buyers = [
        h for h in econ.households
        if not housing.dwellings_of(h.id)
        and (bridge is None or bridge.household_has_living_members(h.id))
    ]
    econ.rng.shuffle(buyers)
    if rental is not None:
        # v15.3 investment demand: owner households join the buyer pool CASH-ONLY when
        # the prevailing rental yield beats the deposit rate by the premium -- landlords
        # emerge from arbitrage, they are never seeded. Need-driven buyers go first.
        deposit_rate_annual = float(getattr(econ, "_rate", 0.0)) * 365.0
        if rental.prevailing_yield(econ) > deposit_rate_annual + rental.investor_premium:
            investors = [
                h for h in econ.households
                if housing.dwellings_of(h.id)
                and (bridge is None or bridge.household_has_living_members(h.id))
            ]
            econ.rng.shuffle(investors)
            buyers.extend(investors)

    sold: list[tuple[Listing, float]] = []
    for buyer in buyers:
        if not book:
            break
        cash_budget = led.balance(buyer.id) * (1.0 - market.buyer_buffer)
        # mortgages are owner-occupier credit: investors (already housed) buy CASH-ONLY
        # in v15.3 -- buy-to-let leverage is a later, separately-gated flag
        can_borrow = (
            mortgage_book is not None
            and buyer.id not in mortgage_book.loans
            and not housing.dwellings_of(buyer.id)
        )
        window = book[: market.search_k]
        pick = None
        for listing in window:
            if listing.ask <= cash_budget:
                pick = listing
                break
            # v15.2 credit unlock: affordable with a mortgage iff the down payment
            # (price minus LTV-capped loan) fits in the cash budget
            if can_borrow and listing.ask * (1.0 - mortgage_book.ltv_cap) <= cash_budget:
                pick = listing
                break
        if pick is None:
            continue
        price = pick.ask
        loan = 0.0
        if price > cash_budget and can_borrow:
            loan = min(price - cash_budget, mortgage_book.ltv_cap * price)
        # ---- atomic sale: ledger + claims + title (+ mortgage) in one place ----
        if loan > EPS:
            # originate posts BOTH sides of loan-creates-deposit to the claims layer
            # (post_household_debt_creation mirrors +cash and +debt), so the sale posting
            # below is the FULL price -- posting loan-price here double-counts the loan
            mortgage_book.originate(econ, buyer, pick.dwelling_id, loan)
        led.transfer(buyer.id, pick.seller_account, price)
        if bridge is not None:
            buyer_hh = bridge.household_id_for_account(buyer.id)
            bridge._post_household_cash_delta(buyer_hh, -price, reason="house_purchase")
            seller_hh = bridge.account_to_household.get(pick.seller_account)
            # 'living' must be a DEMOGRAPHIC-state fact: died-out households keep dead
            # members' sheets (and orphan-moved minors) in the claims membership, which
            # would masquerade as a living seller here
            if seller_hh is not None and bridge.household_has_living_members(pick.seller_account):
                bridge._post_household_cash_delta(int(seller_hh), price, reason="house_sale")
            elif seller_hh is not None and fiscal is not None and pick.seller_account != fiscal:
                # memberless (probate) HOUSEHOLD seller: proceeds escheat immediately --
                # parking cash on a memberless account trips the claim identity next tick.
                # Institutional sellers (foreclosing banks) keep their proceeds.
                proceeds = min(price, led.balance(pick.seller_account))
                if proceeds > EPS:
                    led.transfer(pick.seller_account, fiscal, proceeds)
                    econ._escheat_flow = getattr(econ, "_escheat_flow", 0.0) + proceeds
        builder = getattr(econ, "_builder_by_account", {}).get(pick.seller_account)
        if builder is not None:
            # v15.4 primary sale: feed the native firm grammar -- realized sales drive
            # B2 demand expectations, revenue reaches settlement profit/dividends
            builder.inventory = max(0.0, builder.inventory - 1.0)
            builder.sales += 1.0
            builder.revenue += price
        housing.transfer(pick.dwelling_id, buyer.id)
        book.remove(pick)
        del market.listings[pick.dwelling_id]
        sold.append((pick, price))

    # ---- price index (transaction-weighted, hold-last) + ask decay ----
    if sold:
        econ._house_price = sum(p for _, p in sold) / len(sold)
        market.sales_total += len(sold)
        market.last_session_tom = sum(econ.t - l.listed_tick for l, _ in sold) / len(sold)
    market.last_session_sales = len(sold)
    market.last_session_volume = sum(p for _, p in sold)
    for listing in market.listings.values():
        listing.ask = max(EPS, listing.ask * (1.0 - market.ask_decay))
    n_listed = len(market.listings)
    market.forced_share = (
        sum(1 for l in market.listings.values() if l.forced) / n_listed if n_listed else 0.0
    )

    if rental is not None:
        # v15.3: after ownership settled this session -- terminate stale tenancies
        # (sweep, not hooks), then match seekers to vacancies and adjust the rent level
        rental.sweep_stale_tenancies(econ)
        rental.match_tenants(econ)


def _ingest_distress_listings(econ: Any, market: HousingMarket, housing: Any) -> None:
    led = econ.ledger
    bridge = getattr(econ, "demographic_bridge", None)
    for h in econ.households:
        if led.balance(h.id) >= market.distress_floor:
            continue
        if bridge is not None and not bridge.household_has_living_members(h.id):
            continue                      # memberless households are the probate flow's job
        owned = housing.dwellings_of(h.id)
        if not owned:
            continue
        dwelling = owned[0]
        if not market.is_listed(dwelling.id):
            market.list_dwelling(econ, dwelling.id, h.id, forced=False)


def _drop_stale_listings(econ: Any, market: HousingMarket, housing: Any) -> None:
    """A listing whose dwelling changed owner outside a sale (merge sweep, escheat)
    belongs to the new owner's decision, not the old seller's."""
    for dwelling_id, listing in list(market.listings.items()):
        if housing.owner_of(dwelling_id) != listing.seller_account:
            del market.listings[dwelling_id]
