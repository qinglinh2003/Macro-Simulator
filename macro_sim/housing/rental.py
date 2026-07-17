"""v15.3 rental market: tenancies as persistent flows, tenure choice, emergent landlords.

A tenancy is not a transaction, it is a CONTRACT: formed at a session, it then pays a
fixed per-tick rent (household -> household, posted through the person-claim layer on
both sides) until something ends it. Endings are enforced by a per-session SWEEP, not
per-event hooks -- the household-emptying lesson: tenant death, tenant purchase,
landlord loss of title and forced listings all invalidate tenancies through paths no
single hook sees.

Tenure choice is behavioral and minimal: a houseless household first tries to BUY in
the sale session; if it cannot, it takes the cheapest vacancy whose rent fits a burden
cap on its realized income. Landlords are not seeded: an owner-occupier household with
spare cash buys a SECOND dwelling in the sale session when the prevailing rental yield
beats the deposit rate by a premium -- the investment demand face, measurable against
the need-driven face.

Owner-occupiers' imputed rent is a metrics concept only (no money moves); tenants'
rent is a real transfer, and its drag on deposits reaches goods consumption through
the existing alpha2 wealth term with zero new behavioral code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from macro_sim.markets.matching import EPS


@dataclass
class Tenancy:
    dwelling_id: int
    landlord: str
    tenant: str
    rent_per_tick: float
    missed: int = 0            # consecutive shortfall ticks (eviction counter)


@dataclass
class RentalMarket:
    rent_yield0: float = 0.05          # GENESIS annual rent as a fraction of the price anchor
    rent_adjust: float = 0.02          # per-session rent-level step under excess demand/supply
    rent_burden_cap: float = 0.40      # tenant accepts rent <= cap x realized income
    eviction_arrears: int = 30         # consecutive shortfall ticks before eviction
    investor_premium: float = 0.02     # landlords buy when yield > deposit rate + premium
    # v24 portrait finding A1 (rent ratchet): the legacy rule cuts the rent whenever ANY
    # vacancy is left unfilled -- a one-way multiplicative decay to zero under any structural
    # surplus (heirs accumulate extras faster than new households form), which then kills the
    # rental yield and takes the investors' house-price anchor down with it (house prices
    # /750 across all six 30y-portrait economies). vacancy_deadband treats up to that SHARE
    # of the rentable stock as frictional (no cut); rent_floor is an absolute per-tick floor
    # wired from the average wage (housing services are never literally free). Both default
    # 0.0 = legacy behaviour, bit-identical.
    vacancy_deadband: float = 0.0
    rent_floor: float = 0.0

    # rent level is an independent MARKET STATE (per unit, per tick): vacancy pressure
    # cuts it, unhoused excess demand raises it -- so rent-to-price and the rental
    # yield are emergent, not anchored identities, and the investors' signal is real
    rent_level: float = 0.0            # set at wiring time from the genesis price anchor
    tenancies: dict[int, Tenancy] = field(default_factory=dict)   # dwelling_id -> Tenancy
    evictions_total: int = 0
    rent_paid_total: float = 0.0

    # ------------------------------------------------------------------
    # per-tick rent flow
    # ------------------------------------------------------------------
    def collect_rents(self, econ: Any) -> None:
        led = econ.ledger
        bridge = getattr(econ, "demographic_bridge", None)
        for tenancy in list(self.tenancies.values()):
            if bridge is not None and (
                not bridge.household_has_living_members(tenancy.landlord)
                or not bridge.household_has_living_members(tenancy.tenant)
            ):
                # a party died mid-cycle (the session sweep will terminate the tenancy):
                # money must NOT flow meanwhile -- rent landing on a memberless account
                # has no claim sheet to post to and trips the identity gate within ticks
                continue
            pay = min(tenancy.rent_per_tick, led.balance(tenancy.tenant))
            if pay > EPS:
                led.transfer(tenancy.tenant, tenancy.landlord, pay)
                if bridge is not None:
                    tenant_hh = bridge.account_to_household.get(tenancy.tenant)
                    landlord_hh = bridge.account_to_household.get(tenancy.landlord)
                    if tenant_hh is not None:
                        bridge._post_household_cash_delta(int(tenant_hh), -pay, reason="rent_paid")
                    if landlord_hh is not None:
                        bridge._post_household_cash_delta(int(landlord_hh), pay, reason="rent_income")
                self.rent_paid_total += pay
            if pay + EPS < tenancy.rent_per_tick:
                tenancy.missed += 1
                if tenancy.missed >= self.eviction_arrears:
                    del self.tenancies[tenancy.dwelling_id]
                    self.evictions_total += 1
            else:
                tenancy.missed = 0

    # ------------------------------------------------------------------
    # session logic (called from the housing session)
    # ------------------------------------------------------------------
    def sweep_stale_tenancies(self, econ: Any) -> None:
        """Sweep-based termination: a tenancy dies when its dwelling changed owner into
        the tenant's hands (they bought a home -- possibly this one), its landlord lost
        title (probate/foreclosure listing sold it), or either household stopped having
        living members."""
        housing = econ.housing
        market = econ.housing_market
        bridge = getattr(econ, "demographic_bridge", None)
        for dwelling_id, tenancy in list(self.tenancies.items()):
            owner = housing.owner_of(dwelling_id)
            tenant_owns_home = bool(housing.dwellings_of(tenancy.tenant))
            landlord_lost_title = owner != tenancy.landlord
            listed_forced = market is not None and market.is_listed(dwelling_id)
            dead_party = False
            if bridge is not None:
                dead_party = not bridge.household_has_living_members(tenancy.tenant) or (
                    owner == tenancy.landlord and not bridge.household_has_living_members(tenancy.landlord)
                )
            if tenant_owns_home or landlord_lost_title or listed_forced or dead_party:
                del self.tenancies[dwelling_id]

    def vacancies(self, econ: Any) -> list[int]:
        """Rentable units: owned by a household beyond its own home, not tenanted, not
        listed for sale. The owner's FIRST dwelling is their home; extras are stock."""
        housing = econ.housing
        market = econ.housing_market
        vacant: list[int] = []
        for h in econ.households:
            owned = housing.dwellings_of(h.id)
            for dwelling in owned[1:]:
                if dwelling.id in self.tenancies:
                    continue
                if market is not None and market.is_listed(dwelling.id):
                    continue
                vacant.append(dwelling.id)
        return vacant

    def match_tenants(self, econ: Any) -> None:
        led = econ.ledger
        housing = econ.housing
        bridge = getattr(econ, "demographic_bridge", None)
        vacant = self.vacancies(econ)
        tenanted = {t.tenant for t in self.tenancies.values()}
        seekers = [
            h for h in econ.households
            if not housing.dwellings_of(h.id)
            and h.id not in tenanted
            and (bridge is None or bridge.household_has_living_members(h.id))
        ]
        econ.rng.shuffle(seekers)
        matched = 0
        priced_out = 0
        for h in seekers:
            if not vacant:
                break
            income = max(0.0, float(getattr(h, "income_realized", 0.0)))
            if self.rent_level > self.rent_burden_cap * max(income, led.balance(h.id) / 30.0):
                priced_out += 1             # burden cap against income (or a month of savings)
                continue
            dwelling_id = vacant.pop(0)
            self.tenancies[dwelling_id] = Tenancy(
                dwelling_id=dwelling_id,
                landlord=housing.owner_of(dwelling_id),
                tenant=h.id,
                rent_per_tick=self.rent_level,
            )
            matched += 1
        # rent level moves with the imbalance: unfilled vacancies cut it, unhoused
        # affordable demand (seekers left with no stock) raises it
        unhoused_excess = max(0, len(seekers) - matched - priced_out - len(vacant))
        if self.vacancy_deadband > 0.0:
            # v24 A1 fix: only an unfilled-vacancy SHARE beyond the frictional deadband
            # cuts the rent, and never below the wage-anchored floor.
            stock = len(self.tenancies) + len(vacant)
            vacancy_rate = len(vacant) / stock if stock else 0.0
            if vacancy_rate > self.vacancy_deadband:
                self.rent_level = max(self.rent_floor,
                                      self.rent_level * (1.0 - self.rent_adjust))
            elif unhoused_excess > 0:
                self.rent_level *= 1.0 + self.rent_adjust
        elif vacant:
            self.rent_level *= 1.0 - self.rent_adjust
        elif unhoused_excess > 0:
            self.rent_level *= 1.0 + self.rent_adjust

    def prevailing_yield(self, econ: Any) -> float:
        """Annualized rental yield at current prices -- the investors' signal."""
        if econ._house_price <= EPS:
            return 0.0
        return self.rent_level * 365.0 / econ._house_price
