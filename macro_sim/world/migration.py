"""The migration & remittance layer (PLAN_v22): people cross the border, money flows home.

Workers migrate toward higher REAL wages (residency change, tracked as a stock); they earn
in the host and remit a share home. Remittances are a cross-border TRANSFER — money one way,
no goods/asset counterpart — routed through the dealer (collected from host households, whom
the migrants are among; converted; distributed to origin households), so each economy's
ledger conserves. This completes the current account: trade + factor income (v21) +
transfers (v22). It is also the deprivation escape valve v18 flagged as absent in a closed
economy — labor can leave a poor economy for a rich one.
"""

from __future__ import annotations

from macro_sim.markets.matching import EPS
from macro_sim.world.fx import DEALER_ID


def _real_wage(econ) -> float:
    if not econ.records:
        return econ.cfg.w_firm0
    r = econ.records[-1]
    return r.get("avg_wage", econ.cfg.w_firm0) / max(1e-9, r.get("price_index", 1.0))


def _wage(econ) -> float:
    return econ.records[-1].get("avg_wage", econ.cfg.w_firm0) if econ.records else econ.cfg.w_firm0


def run_migration(world) -> None:
    econs = world.economies
    n = world.n
    rw = [_real_wage(e) for e in econs]

    # 1. each origin's desired stock, driven by the real-wage pull toward its best host,
    #    capped by its own emigration ceiling (a structural friction).
    host_of = [-1] * n
    for i in range(n):
        # POLICY: sanctioned partners are not migration destinations (no bilateral flow).
        candidates = [j for j in range(n) if j != i and not world.sanctioned(i, j)]
        host = max(candidates, key=lambda j: rw[j], default=None)
        if host is None:
            continue
        host_of[i] = host
        gap = (rw[host] - rw[i]) / max(1e-9, rw[i])
        pop = len(econs[i].households)
        own_cap = world.migration_max_share * pop
        if gap > 0.0:
            world._migrant_stock[i] = min(own_cap, world._migrant_stock[i] + world.migration_rate * gap * pop)
        else:
            world._migrant_stock[i] = max(0.0, world._migrant_stock[i] * (1.0 - world.migration_rate))

    # 2. POLICY — the immigration cap/quota (a run-time government lever): each host admits
    #    at most `immigration_cap × its population` immigrants in total. When it binds, the
    #    would-be migrants are turned away (stocks scaled down) ⇒ the wage gap PERSISTS
    #    (policy blocks convergence). None ⇒ open borders ⇒ the v22.1 mechanism unchanged.
    world._immigration_binding = [False] * n
    if world.immigration_cap is not None:
        for h in range(n):
            incoming = [i for i in range(n) if host_of[i] == h]
            total = sum(world._migrant_stock[i] for i in incoming)
            ceiling = world.immigration_cap * len(econs[h].households)
            if total > ceiling + EPS and total > 0.0:
                scale = ceiling / total
                for i in incoming:
                    world._migrant_stock[i] *= scale
                world._immigration_binding[h] = True

    # 3. remittances (net of the remittance tax, a fiscal policy lever).
    remit = [0.0] * n
    tax_rev = [0.0] * n
    for i in range(n):
        host = host_of[i]
        S = world._migrant_stock[i]
        if host < 0 or S <= EPS:
            continue
        remit_host = world.remittance_share * S * _wage(econs[host])   # migrant earnings sent home (curr_host)
        remit[i], tax_rev[i] = _remit(world, host, i, remit_host)
    world._remittances = remit
    world._remittance_tax_rev = tax_rev


def _remit(world, host: int, origin: int, amount_host: float):
    """Conserving cross-border transfer host → origin. Collect ``amount_host`` (curr_host)
    from host households, convert at the rate, then — POLICY — the origin government levies a
    REMITTANCE TAX on the inflow (revenue to its fiscal account); the net reaches origin
    households. Routed through the dealer (net-zero passthrough). Returns (net_remittance,
    tax_revenue) in curr_origin."""
    if amount_host <= EPS:
        return 0.0, 0.0
    collected = _collect(world.economies[host], amount_host)
    if collected <= EPS:
        return 0.0, 0.0
    amount_origin = collected * world.rates.bilateral(origin, host)   # curr_host → curr_origin
    oe = world.economies[origin]
    tax = 0.0
    fiscal = getattr(oe, "_fiscal", None)
    if world.remittance_tax > 0.0 and fiscal is not None and oe.ledger.has_account(fiscal):
        tax = world.remittance_tax * amount_origin
        oe.ledger.transfer(DEALER_ID, fiscal, tax)                   # remittance tax → origin fiscal
    _distribute(oe, amount_origin - tax)                             # net to origin households
    return amount_origin - tax, tax


def _collect(econ, amount: float) -> float:
    """Take ``amount`` from households pro-rata by deposit (capped by cash) into the dealer."""
    led = econ.ledger
    hh = econ.households
    total = sum(led.balance(h.id) for h in hh)
    if total <= EPS:
        return 0.0
    amount = min(amount, total)
    collected = 0.0
    for h in hh:
        bal = led.balance(h.id)
        take = min(bal, amount * bal / total)
        if take > EPS:
            led.transfer(h.id, DEALER_ID, take)
            collected += take
    return collected


def _distribute(econ, amount: float) -> None:
    """Pay ``amount`` from the dealer to households, split equally (remittance receipts)."""
    if amount <= EPS:
        return
    led = econ.ledger
    hh = econ.households
    per = amount / len(hh)
    for h in hh:
        led.transfer(DEALER_ID, h.id, per)
