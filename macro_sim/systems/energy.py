"""v17.0 energy: the E-sector and the firm-to-firm energy market (PLAN_v17).

Energy is the model's first INTERMEDIATE input. E-firms are ordinary firms on the
native grammar (B2 expectations, B3 markup, B4 wages, same labor market / credit /
settlement) with ONE structural change: production is CAPACITY-CONSTRAINED,
y_E = min(a_E·L, κ·K), with κ·K the binding edge near baseline — short-run supply
elasticity ≈ 0, and the long-run response emerges from capital accumulation through
the EXISTING capital-goods market (invests=True with v = 1/κ, so the B5 accelerator
targets exactly the capacity that expected demand needs).

Downstream (c/k) firms hold an ENERGY INPUT STOCK — an outside item like inventory,
average-cost valued — replenished toward a coverage target (the phi grammar mirrored
onto an input). Energy bought by firms is INTERMEDIATE consumption: it never enters
GDP; the ledger flows are ordinary transfers, so A4/A5 hold by construction.

Sector demographics are FROZEN through the 17.x arc (entry needs a construction lag,
a later flag): firm_demographics only scans c_firms, so freezing is free.

The buyer-ordering point is the RESERVED RATIONING INTERFACE (protocol §17.0 → §17.4):
`econ.energy_buyer_ordering`, when set, reorders/filters the buy orders before the
market session (priority rationing plugs in there); None = the native protocol.
"""

from __future__ import annotations

from typing import Any, Dict, List

from macro_sim.behavior import planning as B
from macro_sim.domain.agents import Firm
from macro_sim.markets.matching import EPS, BuyOrder, SellOffer, execute_market


def energy_using_firms(econ: Any) -> List[Firm]:
    """The downstream side: producing firms with a Leontief energy requirement.
    Builders are excluded in v17.0 (construction energy is a later coupling)."""
    return [f for f in econ.c_firms + econ.k_firms if f.energy_intensity > 0.0]


def household_energy_need(cfg: Any) -> float:
    """v17.1: real energy need per household per tick, FIXED at the genesis anchor
    (necessity): spend target = energy_hh_share x steady consumption (~w_firm0),
    so need = share * w / p_E0. Uniform per household in v1 (size scaling is the
    17.5 housing coupling's job)."""
    return cfg.energy_hh_share * cfg.w_firm0 / cfg.p_efirm0


def create_e_firms(econ: Any, cfg: Any, balances: Dict[str, float]) -> None:
    """Genesis, FITTED AT t0 (the v15 lesson): supply meets fitted demand at the
    anchored utilization, every input stock starts at its coverage target — no
    artificial opening shortage or restocking wave. Called BEFORE the Ledger is
    built (E-firms are a genesis sector, funded like c/k firms, not by fiscal).
    """
    econ.e_firms = []
    # Aggregate per-tick energy demand implied by the downstream demand seeds
    # (+ household necessity demand when 17.1 is on -- capacity must cover both).
    downstream = econ.c_firms + econ.k_firms
    demand_e0 = cfg.energy_intensity * sum(f.demand_expected for f in downstream)
    if cfg.energy_household:
        demand_e0 += household_energy_need(cfg) * len(econ.households)
    n_e = max(1, cfg.n_firms_e)
    d_seed = demand_e0 / n_e                       # per-E-firm expected demand (neutral B2 start)
    # Capacity fitted so the sector runs at energy_util0 at genesis (headroom).
    k_e0 = demand_e0 / (n_e * cfg.energy_util0 * cfg.kappa_E)
    for idx in range(n_e):
        firm = Firm(
            id=f"E{idx}",
            lambda_d=cfg.lambda_d, phi=cfg.phi, eta=cfg.eta,
            mu_min=cfg.mu_min, mu_max=cfg.mu_max, omega=cfg.omega,
            a=cfg.a_E, rho=cfg.rho, dis_slope=cfg.dis_slope,
            inventory=cfg.phi * d_seed,            # own-output stock at target (quiet genesis)
            price=cfg.p_efirm0, wage=cfg.w_firm0,
            markup=cfg.mu_firm0, demand_expected=d_seed,
            target_inventory_prev=cfg.phi * d_seed,
            sales_prev=d_seed,                     # neutral first B2 update
            # COBB-DOUGLAS + capacity clamp, NOT linear: a linear E-firm is excluded
            # from capital deepening, so as the c-sector's unit labor cost falls with
            # K-growth the energy RELATIVE price drifts up with c-productivity — a
            # Baumol artifact (the 10y diagnostic measured 7x/decade with wages flat
            # across sectors). CD with the same alpha lets uc_E fall in step; A_E =
            # (kappa*util0)^alpha normalizes genesis unit labor cost to exactly w, so
            # the p_efirm0 = (1+mu0)*w price anchor is preserved.
            sells="energy", tech="cobb_douglas",
            # Long-run supply response rides the EXISTING K market (B5 accelerator with
            # v = 1/κ: K* = d^e/κ, capacity tracks demand). Without a K market (v1
            # kernel) there is no way to replace depreciation, so the honest kernel
            # behavior is a FROZEN capital stock: invests=False keeps E-firms out of
            # the settlement capital commit entirely.
            invests=bool(cfg.capital_enabled),
            A=cfg.A, alpha=cfg.alpha,
            # RESERVE-MARGIN accelerator: k* = d^e/(kappa*util0), i.e. capacity targets
            # demand at the anchored utilization, not exact match. Without the margin a
            # purely adaptive accelerator chases a GROWING economy from behind forever:
            # the 10y frontier diagnostic showed util pinned at 1.0 from t~400, recurring
            # rationing waves, markup permanently at cap from t~2800, and an 8x relative
            # price ratchet. Capacity industries plan reserve margins in reality; util0
            # is already the genesis anchor, so this adds NO new dial.
            v=(1.0 / (cfg.kappa_E * cfg.energy_util0) if cfg.capital_enabled else 0.0),
            lambda_I=(cfg.lambda_I if cfg.capital_enabled else 0.0),
            delta_K=(cfg.delta_K if cfg.capital_enabled else 0.0),
            capital=k_e0, capital_prev=k_e0,
            capacity_kappa=cfg.kappa_E,
        )
        firm.A = (cfg.kappa_E * cfg.energy_util0) ** cfg.alpha   # genesis uc_E == w exactly
        balances[firm.id] = cfg.d_efirm0
        econ.firms.append(firm)
        econ.e_firms.append(firm)
    if cfg.soe_efirm and econ.e_firms:
        econ.e_firms[0].state_owned = True   # v17.3: E0 is the SOE (dividends -> fiscal)
    # Downstream Leontief coefficient + input stocks at the coverage target,
    # valued at the genesis energy price anchor.
    for f in downstream:
        f.energy_intensity = cfg.energy_intensity
        f.energy_stock = cfg.energy_coverage_ticks * cfg.energy_intensity * f.demand_expected
        f.energy_stock_cost = f.energy_stock * cfg.p_efirm0
        f.energy_avg_cost = cfg.p_efirm0


def seed_entrant_energy(econ: Any, firm: Firm) -> None:
    """New c-firm entrants (firm demographics) join the energy economy houseless:
    zero stock (real_entry_signal spirit: nothing ex nihilo), the Leontief
    coefficient, and the hold-last market price as their initial cost expectation.
    They restock through the market like everyone else."""
    if not getattr(econ.cfg, "energy_enabled", False):
        return
    firm.energy_intensity = econ.cfg.energy_intensity
    firm.energy_avg_cost = getattr(econ, "_energy_price", econ.cfg.p_efirm0)


def _produce_e_firms(econ: Any) -> None:
    """E-firms produce BEFORE the energy market (they need labor+capital, not energy),
    so the market sells stock + TODAY'S output — the exact goods-market grammar.

    Selling only yesterday's stock is a DEATH SPIRAL under stock-out: with phi<1 an
    E-firm's sales are inventory-capped at ~(2phi/(1+phi))·d^e < d^e, so B2 reads
    'demand below expectations' and contracts at ~lambda_d·(1-phi)/(1+phi) per tick —
    supply implodes exactly when demand explodes (found in the 17.0 kernel probe;
    the phase order is the load-bearing difference from the goods market)."""
    for f in econ.e_firms:
        f.produced = B.produce(f, f.hired, econ._pubcap_factor)
        if f.capacity_kappa > 0.0:
            f.produced = min(f.produced, f.capacity_kappa * f.capital)
        f.inventory += f.produced


def apply_energy_shock(econ: Any) -> None:
    """v17.2: the capacity-shock SCENARIO (the model's first deliberate exogenous
    shock). kappa multiplier at shock_at; a pulse restores it EXACTLY at the end
    (float-exact: store the pre-shock value instead of dividing back). The
    accelerator's v keeps its genesis technology: after a permanent cut, capacity
    re-expands through the unfilled-demand channel with a lag — the lag IS the
    experiment. energy_shock_at=0 => never fires => bit-identical."""
    cfg = econ.cfg
    if cfg.energy_shock_at <= 0:
        return
    if econ.t == cfg.energy_shock_at:
        econ._energy_kappa0 = [ef.capacity_kappa for ef in econ.e_firms]
        for ef in econ.e_firms:
            ef.capacity_kappa *= (1.0 - cfg.energy_shock_magnitude)
        econ._energy_shock_active = 1.0
    elif (cfg.energy_shock_duration > 0
          and econ.t == cfg.energy_shock_at + cfg.energy_shock_duration):
        for ef, k0 in zip(econ.e_firms, getattr(econ, "_energy_kappa0", [])):
            ef.capacity_kappa = k0
        econ._energy_shock_active = 0.0


def run_energy_phase(econ: Any) -> None:
    """The energy phase (every tick, [ANCHOR: post-labor]): E-firms produce, then
    downstream firms buy today's planned use plus a throttled restock toward the
    coverage target; E-firms sell (stock + today's output) at the posted price.
    """
    cfg = econ.cfg
    if not cfg.energy_enabled:
        return
    apply_energy_shock(econ)
    _produce_e_firms(econ)
    econ._tax_energy = 0.0
    econ._spr_flow = 0.0
    gov = cfg.government
    tc = econ.policy.tax_energy_rate if gov else 0.0

    # v17.3 SOE pricing rule: the state-owned E-firm posts unit cost (markup 0),
    # bypassing Calvo -- a state pricing rule, not a market one. Live Policy lever.
    if gov and econ.policy.soe_price_at_cost:
        for ef in econ.e_firms:
            if ef.state_owned:
                ef.markup = 0.0
                ef.price = B.unit_cost(ef)

    # v17.3 hoarding (default OFF): firms scale the coverage target with the energy
    # price TREND (slow EMA reference) -- the 1970s anticipatory-stockpiling amplifier.
    # beta=0 => multiplier exactly 1.0 => bit-identical.
    slow = getattr(econ, "_energy_price_slow", cfg.p_efirm0)
    econ._energy_price_slow = slow + (getattr(econ, "_energy_price", cfg.p_efirm0) - slow) / 30.0
    hoard_mult = 1.0
    if cfg.energy_hoarding_beta > 0.0 and slow > EPS:
        trend = getattr(econ, "_energy_price", cfg.p_efirm0) / slow - 1.0
        hoard_mult = 1.0 + cfg.energy_hoarding_beta * max(0.0, trend)

    orders: List[BuyOrder] = []
    for f in energy_using_firms(econ):
        use_need = f.energy_intensity * f.production_target
        target_stock = hoard_mult * cfg.energy_coverage_ticks * f.energy_intensity * f.demand_expected
        demand = use_need + cfg.energy_gap_close * (target_stock - f.energy_stock)
        f.energy_bought = 0.0
        if demand <= EPS:
            continue
        budget = econ.ledger.balance(f.id)
        if budget <= EPS:
            continue
        # excise (VAT grammar): the outlay buys energy worth budget/(1+t); rest reserved for tax
        orders.append(BuyOrder(account=f.id, demand=demand, budget=budget / (1.0 + tc), ref=f))
    if cfg.energy_household:
        # v17.1: households buy their necessity need in the SAME session (deposits-capped,
        # A4). Documented behavioral primitive: need is met first, price-inelastically, up
        # to the budget -- inelasticity is emergent from the fixed real need.
        need = household_energy_need(cfg)
        for h in econ.households:
            budget = econ.ledger.balance(h.id)
            if budget <= EPS:
                continue
            orders.append(BuyOrder(account=h.id, demand=need, budget=budget / (1.0 + tc), ref=h))

    # v17.3 SPR: below target the fiscal node BUYS (deficit-financed: the fiscal
    # account may run negative, transfers conserve); above target it SELLS at just
    # under the cheapest ask (a release undercuts to move), proceeds -> fiscal.
    # All flows are ordinary session trades: A5-safe by construction.
    spr_buy = spr_sell = 0.0
    pol = econ.policy
    if gov and pol.spr_flow_cap > 0.0:
        stock = getattr(econ, "_spr_stock", 0.0)
        if pol.spr_target_units > stock + EPS:
            spr_buy = min(pol.spr_target_units - stock, pol.spr_flow_cap)
            orders.append(BuyOrder(account=econ._fiscal, demand=spr_buy,
                                   budget=float("inf"), ref=None))
        elif stock > pol.spr_target_units + EPS:
            spr_sell = min(stock - pol.spr_target_units, pol.spr_flow_cap)

    # RESERVED RATIONING INTERFACE (17.4 plugs in here): a hook may reorder/filter
    # the buy orders before the session; None (default) = the native protocol.
    ordering = getattr(econ, "energy_buyer_ordering", None)
    if ordering is not None:
        orders = ordering(econ, orders)

    offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f)
              for f in econ.e_firms]
    spr_offer = None
    if spr_sell > EPS:
        release_price = 0.999 * min(f.price for f in econ.e_firms)
        spr_offer = SellOffer(account=econ._fiscal, stock=spr_sell, price=release_price, ref=None)
        offers.append(spr_offer)
    trades = execute_market(orders, offers, protocol=econ.protocol,
                            rng=econ._energy_rng, ledger=econ.ledger)

    bought_q: Dict[str, float] = {}
    bought_v: Dict[str, float] = {}
    for tr in trades:
        bought_q[tr.buyer] = bought_q.get(tr.buyer, 0.0) + tr.qty
        bought_v[tr.buyer] = bought_v.get(tr.buyer, 0.0) + tr.value
    total_q = total_v = 0.0
    for f in energy_using_firms(econ):
        q = bought_q.get(f.id, 0.0)
        if q <= 0.0:
            continue
        v = bought_v.get(f.id, 0.0)
        f.energy_bought = q
        f.energy_stock += q
        f.energy_stock_cost += v
        f.energy_avg_cost = f.energy_stock_cost / f.energy_stock if f.energy_stock > EPS \
            else f.energy_avg_cost
        total_q += q
        total_v += v
        if tc > 0.0:
            excise = min(v * tc, econ.ledger.balance(f.id))
            if excise > EPS:
                econ.ledger.transfer(f.id, econ._fiscal, excise)
                econ._tax_energy += excise
    hh_spend = hh_units = 0.0
    if cfg.energy_household:
        bridge = getattr(econ, "demographic_bridge", None)
        for h in econ.households:
            q = bought_q.get(h.id, 0.0)
            h.energy_units = q
            h.energy_spent = bought_v.get(h.id, 0.0)
            if q <= 0.0:
                continue
            hh_spend += h.energy_spent
            hh_units += q
            # household ledger outflows MUST post through the person-claim bridge
            # (the v13 fault line: unposted household flows drift the claim identity)
            if bridge is not None and h.energy_spent > EPS:
                bridge.post_household_consumption(h.id, h.energy_spent)
            if tc > 0.0:
                excise = min(h.energy_spent * tc, econ.ledger.balance(h.id))
                if excise > EPS:
                    econ.ledger.transfer(h.id, econ._fiscal, excise)
                    if bridge is not None:
                        bridge.post_household_tax_payment(h.id, excise)
                    econ._tax_energy += excise
    econ._energy_hh_spend = hh_spend
    econ._energy_hh_units = hh_units

    # v17.3 SPR settlement: buys enter the reserve stock; a release drains it.
    if gov and (spr_buy > 0.0 or spr_offer is not None):
        q_in = bought_q.get(econ._fiscal, 0.0)
        econ._spr_stock = getattr(econ, "_spr_stock", 0.0) + q_in
        econ._spr_cost = getattr(econ, "_spr_cost", 0.0) + bought_v.get(econ._fiscal, 0.0)
        if spr_offer is not None and spr_offer.sold > 0.0:
            avg = econ._spr_cost / max(EPS, econ._spr_stock)
            econ._spr_stock = max(0.0, econ._spr_stock - spr_offer.sold)
            econ._spr_cost = max(0.0, econ._spr_cost - avg * spr_offer.sold)
        econ._spr_flow = q_in - (spr_offer.sold if spr_offer is not None else 0.0)

    for off in offers:
        if off.ref is None:
            continue                         # the SPR release offer (settled above)
        ef: Firm = off.ref
        ef.inventory = off.stock             # decremented live during trading
        ef.sales = off.sold
        ef.revenue = off.sold * off.price

    # UNFILLED demand feeds expectations (the capacity-blindness fix). Under a hard
    # capacity cap, sales can never exceed kappa*K, so B2-on-sales ratchets d^e down to
    # capacity and the accelerator (k* = d^e/kappa) can NEVER see the true demand -- a
    # rationed sector locks at its slump-trough capacity forever (v124+energy probe:
    # output pinned at 40% of baseline). The market OBSERVED the addressed demand, so
    # E-firm expectations get the B2 correction for the unfilled component, pro-rata to
    # sales (equal split if nothing sold). Zero when the market clears => no-op in slack.
    unfilled = max(0.0, sum(o.demand for o in orders) - total_q)
    if unfilled > EPS and econ.e_firms and cfg.capital_enabled:
        # Gated on the K market existing: the correction FEEDS THE ACCELERATOR; without
        # a way to expand capacity it would only inflate expectations the firm cannot
        # act on (the kernel world keeps plain B2-on-sales).
        for ef in econ.e_firms:
            share = (ef.sales / total_q) if total_q > EPS else (1.0 / len(econ.e_firms))
            ef.demand_expected += ef.lambda_d * unfilled * share
    econ._energy_unfilled = unfilled

    # Transaction-weighted price index over ALL session trades (firms + households +
    # SPR), hold-last (burn-in discard is downstream's duty).
    idx_q = sum(tr.qty for tr in trades)
    idx_v = sum(tr.value for tr in trades)
    if idx_q > EPS:
        econ._energy_price = idx_v / idx_q
    econ._energy_sold = idx_q
