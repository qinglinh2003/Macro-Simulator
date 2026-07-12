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


def create_e_firms(econ: Any, cfg: Any, balances: Dict[str, float]) -> None:
    """Genesis, FITTED AT t0 (the v15 lesson): supply meets fitted demand at the
    anchored utilization, every input stock starts at its coverage target — no
    artificial opening shortage or restocking wave. Called BEFORE the Ledger is
    built (E-firms are a genesis sector, funded like c/k firms, not by fiscal).
    """
    econ.e_firms = []
    # Aggregate per-tick energy demand implied by the downstream demand seeds.
    downstream = econ.c_firms + econ.k_firms
    demand_e0 = cfg.energy_intensity * sum(f.demand_expected for f in downstream)
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
            sells="energy", tech="linear",
            # Long-run supply response rides the EXISTING K market (B5 accelerator with
            # v = 1/κ: K* = d^e/κ, capacity tracks demand). Without a K market (v1
            # kernel) there is no way to replace depreciation, so the honest kernel
            # behavior is a FROZEN capital stock: invests=False keeps E-firms out of
            # the settlement capital commit entirely.
            invests=bool(cfg.capital_enabled),
            A=cfg.A, alpha=cfg.alpha,
            v=(1.0 / cfg.kappa_E if cfg.capital_enabled else 0.0),
            lambda_I=(cfg.lambda_I if cfg.capital_enabled else 0.0),
            delta_K=(cfg.delta_K if cfg.capital_enabled else 0.0),
            capital=k_e0, capital_prev=k_e0,
            capacity_kappa=cfg.kappa_E,
        )
        balances[firm.id] = cfg.d_efirm0
        econ.firms.append(firm)
        econ.e_firms.append(firm)
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


def run_energy_phase(econ: Any) -> None:
    """The energy phase (every tick, [ANCHOR: post-labor]): E-firms produce, then
    downstream firms buy today's planned use plus a throttled restock toward the
    coverage target; E-firms sell (stock + today's output) at the posted price.
    """
    cfg = econ.cfg
    if not cfg.energy_enabled:
        return
    _produce_e_firms(econ)
    econ._tax_energy = 0.0
    gov = cfg.government
    tc = econ.policy.tax_energy_rate if gov else 0.0

    orders: List[BuyOrder] = []
    for f in energy_using_firms(econ):
        use_need = f.energy_intensity * f.production_target
        target_stock = cfg.energy_coverage_ticks * f.energy_intensity * f.demand_expected
        demand = use_need + cfg.energy_gap_close * (target_stock - f.energy_stock)
        f.energy_bought = 0.0
        if demand <= EPS:
            continue
        budget = econ.ledger.balance(f.id)
        if budget <= EPS:
            continue
        # excise (VAT grammar): the outlay buys energy worth budget/(1+t); rest reserved for tax
        orders.append(BuyOrder(account=f.id, demand=demand, budget=budget / (1.0 + tc), ref=f))

    # RESERVED RATIONING INTERFACE (17.4 plugs in here): a hook may reorder/filter
    # the buy orders before the session; None (default) = the native protocol.
    ordering = getattr(econ, "energy_buyer_ordering", None)
    if ordering is not None:
        orders = ordering(econ, orders)

    offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f)
              for f in econ.e_firms]
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
    for off in offers:
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

    # Transaction-weighted price index, hold-last (burn-in discard is downstream's duty).
    if total_q > EPS:
        econ._energy_price = total_v / total_q
    econ._energy_sold = total_q
