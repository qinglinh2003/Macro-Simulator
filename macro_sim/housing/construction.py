"""v15.4 construction: the primary market, and the long-run price anchor.

Builders are ordinary firms (linear tech, sells="housing") riding the NATIVE firm
grammar: they hire in the labor market, B2 demand expectations track realized dwelling
sales, and the B1 inventory gap regulates output -- no bespoke planning. What is new
is the conversion of produced UNITS into indivisible dwellings, and the two scarcity
devices that keep the long-run price from being pinned to construction cost:

  - LAND FEE, paid to the fiscal account at minting: land_share x reference price x
    (stock / genesis stock)^convexity. Cumulative land consumption raises the marginal
    cost of the next dwelling => secular real appreciation is possible, and land rent
    is fiscal revenue (a zoning-adjacent handle for free).
  - PERMIT QUOTA per year (housing_permits): the explicit zoning policy handle.

Minted dwellings enter the registry owned by the builder and are LISTED on the
existing resale market as primary supply (institutional seller: proceeds stay with the
builder and flow through the ordinary settlement/dividend machinery). The registry
count invariant is unchanged -- builders are exactly the "minted by mint() only" path.
"""

from __future__ import annotations

from typing import Any

from macro_sim.domain.agents import Firm
from macro_sim.markets.matching import EPS


def create_builders(econ: Any, cfg: Any) -> None:
    econ.builders = []
    econ._builder_by_account = {}
    for idx in range(cfg.n_builders):
        firm = Firm(
            id=f"BLD{idx}",
            lambda_d=cfg.lambda_d, phi=cfg.phi, eta=cfg.eta,
            mu_min=cfg.mu_min, mu_max=cfg.mu_max, omega=cfg.omega,
            a=cfg.builder_productivity, rho=cfg.rho, dis_slope=cfg.dis_slope,
            inventory=0.0, price=econ._house_price, wage=cfg.w_firm0,
            markup=cfg.mu_firm0, demand_expected=cfg.builder_demand_seed,
            target_inventory_prev=cfg.phi * cfg.builder_demand_seed,
            sales_prev=cfg.builder_demand_seed,
            sells="housing", tech="linear", invests=False,
            A=cfg.A, alpha=cfg.alpha, v=0.0, lambda_I=0.0, delta_K=0.0,
        )
        econ.ledger.add_account(firm.id)
        # A5-safe seed capital: the state funds the builder (fiscal may run negative);
        # genesis money is already fixed, so this is a conserving transfer, not creation.
        # Sized to the FULL FIRST-UNIT GESTATION: buffer + the wage bill of one whole
        # dwelling (wage/a labor-ticks) + one land fee. Static sizing (buffer + fee
        # only) starved the builder mid-gestation at production productivity: the
        # first dwelling FINISHED as WIP but the account hit zero before the land fee
        # -- a zombie holding an unmintable house (found via the integrated portrait;
        # the hot-productivity acceptance test had masked it). Revenue from the first
        # sale funds every later round.
        fiscal = getattr(econ, "_fiscal", None)
        if fiscal is not None:
            gestation_wages = cfg.w_firm0 / max(cfg.builder_productivity, 1e-12)
            seed = cfg.d_firm0 + gestation_wages + econ.policy.land_fee_share * econ._house_price
            econ.ledger.transfer(fiscal, firm.id, seed)
        # no explicit bank assignment: bank_for() falls back to the first alive bank,
        # and _bank_of does not exist yet at this point in Economy.__init__
        econ.firms.append(firm)
        econ.builders.append(firm)
        econ._builder_by_account[firm.id] = firm


def run_construction_step(econ: Any) -> None:
    """Per tick: fold today's production into unit inventory, then mint whole dwellings
    while permits and the land fee allow. Minted dwellings list at the next session."""
    builders = getattr(econ, "builders", None)
    if not builders:
        return
    housing = econ.housing
    market = econ.housing_market
    fiscal = getattr(econ, "_fiscal", None)
    cfg = econ.cfg
    year = econ.t // 365
    if getattr(econ, "_permit_year", None) != year:
        econ._permit_year = year
        econ._permits_used = 0
    stock0 = max(1, getattr(econ, "_genesis_dwellings", housing.count()))
    for firm in builders:
        # WIP (work in progress, fractional units) is NOT saleable inventory: it must
        # neither feed the B1 inventory-gap rule nor list. f.inventory carries only
        # whole MINTED-and-unsold dwellings (incremented at mint, decremented at sale),
        # so the native grammar regulates the finished stock while WIP accumulates
        # freely toward the next whole unit.
        # the labor phase's generic fold (inventory += produced) already banked today's
        # output: MOVE it into WIP so f.inventory keeps only whole minted-unsold units
        firm.wip = getattr(firm, "wip", 0.0) + firm.produced
        firm.inventory = max(0.0, firm.inventory - firm.produced)
        # Indivisibility also breaks the native cold start: own sales stay 0 until the
        # FIRST dwelling exists, so B2 decays demand_expected to zero before WIP ever
        # reaches 1.0. While building is PROFITABLE (reference price above unit cost
        # incl. the land fee), floor the demand prior at the seed; unprofitable prices
        # lift the floor and the native decay shuts the builder down.
        land_fee = (
            econ.policy.land_fee_share * econ._house_price
            * (housing.count() / stock0) ** econ.policy.land_fee_stock_elasticity
        )
        unit_cost = firm.wage / max(firm.a, EPS) + land_fee
        if econ._house_price > unit_cost:
            floor = cfg.builder_demand_seed
            gain = cfg.builder_demand_price_gain
            if gain > 0.0:
                # CAMPAIGN FIX: supply finally SEES the price signal -- the floor
                # scales with the profit margin, so a shortage (price >> cost)
                # raises construction instead of being invisible to builders.
                floor *= 1.0 + gain * (econ._house_price / unit_cost - 1.0)
            firm.demand_expected = max(firm.demand_expected, floor)
        while firm.wip >= 1.0:
            permits = int(getattr(econ.policy, "housing_permits", cfg.housing_permits))
            if econ._permits_used >= permits:
                break                            # the zoning quota binds this year (live Policy lever)
            if fiscal is None:
                break
            if econ.ledger.balance(firm.id) < land_fee:
                # CAMPAIGN FIX leg 3: completion needs the land fee IN CASH at the
                # moment of minting, but wage credit is already spent on wages by
                # the time the market phase runs (a credit-phase provision gets
                # intercepted by the wage bill -- verified: revival collapsed
                # 245->7 under relocation). The development loan is drawn AT the
                # completion moment via the standard grant_loan (bank-capacity
                # constrained, conserving). The identity failure once attributed
                # to this call was the peg-break probe gate, fixed separately.
                if cfg.builder_land_fee_credit:
                    from macro_sim.systems.credit import grant_loan
                    grant_loan(econ, firm.id, land_fee - econ.ledger.balance(firm.id))
                if econ.ledger.balance(firm.id) < land_fee:
                    break                        # cannot pay for land: unit stays as WIP
            if land_fee > EPS:
                econ.ledger.transfer(firm.id, fiscal, land_fee)
                econ._land_fee_paid = getattr(econ, "_land_fee_paid", 0.0) + land_fee
                econ._land_fee_paid_tick = (
                    getattr(econ, "_land_fee_paid_tick", 0.0) + land_fee
                )
            firm.wip -= 1.0
            dwelling = housing.mint(firm.id)
            firm.inventory += 1.0
            econ._permits_used += 1
            econ._dwellings_built = getattr(econ, "_dwellings_built", 0) + 1
            if market is not None:
                market.list_dwelling(econ, dwelling.id, firm.id, forced=False)
            land_fee = (
                econ.policy.land_fee_share * econ._house_price
                * (housing.count() / stock0) ** econ.policy.land_fee_stock_elasticity
            )
