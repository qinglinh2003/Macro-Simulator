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
from macro_sim.world.trade import lever


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
    for econ in world.economies:
        econ._outward_remittance_tax_revenue = 0.0
        econ._remittance_tax_revenue_external = 0.0
    # The MIGRANT'S CALCULUS: what I would earn abroad, converted home at the exchange rate,
    # versus what I earn at home. Deliberately NOT wage/own-price-index: remittances raise the
    # ORIGIN's price level, which would depress its measured "real wage" and pull in yet more
    # migrants — a perverse self-reinforcing loop that, once a quota cuts the remittances,
    # flips the flow's direction outright. The nominal wage at the rate is what a migrant who
    # remits home actually faces.
    #
    # And it is SMOOTHED: nobody emigrates on a one-tick wage flicker. On the raw series both
    # economies momentarily out-earn each other and each starts "sending" people — nonsense.
    # Migration responds to a PERSISTENT gap.
    raw = [_wage(e) for e in econs]
    if world._rw_ema is None:
        world._rw_ema = list(raw)
    a = world.wage_smoothing
    world._rw_ema = [a * raw[i] + (1.0 - a) * world._rw_ema[i] for i in range(n)]
    w_ema = world._rw_ema

    # 1. each origin's desired stock, driven by the wage pull toward its best host,
    #    capped by its own emigration ceiling (a structural friction).
    host_of = [-1] * n
    for i in range(n):
        # POLICY: sanctioned partners are not migration destinations (no bilateral flow).
        candidates = [j for j in range(n) if j != i and not world.sanctioned(i, j)]
        if not candidates:
            continue
        home_value = {j: w_ema[j] * world.rates.bilateral(i, j) for j in candidates}
        host = max(candidates, key=lambda j: home_value[j])
        host_of[i] = host
        gap = (home_value[host] - w_ema[i]) / max(1e-9, w_ema[i])
        pop = len(econs[i].households)
        own_cap = world.migration_max_share * pop
        # POLICY: an EMIGRATION cap — the origin restricts its own people from leaving.
        if world.emigration_cap is not None:
            ecap = world.emigration_cap[i] if isinstance(world.emigration_cap, (list, tuple)) \
                else world.emigration_cap
            if ecap is not None:   # B5a: per-economy None = that origin is open
                own_cap = min(own_cap, float(ecap) * pop)
        if gap > 0.0:
            world._migrant_stock[i] = min(own_cap, world._migrant_stock[i] + world.migration_rate * gap * pop)
        else:
            world._migrant_stock[i] = max(0.0, world._migrant_stock[i] * (1.0 - world.migration_rate))
        # POLICY: a GUEST-WORKER regime — migrants are temporary and return home at a rate
        # (permanent settlement ⇒ 0). Applied after the pull, so it damps the steady state.
        gw = lever(world.guest_worker_return, host)   # the HOST's temporary-migration return rate
        if gw > 0.0:
            world._migrant_stock[i] *= (1.0 - gw)

    # 2. POLICY — the immigration cap/quota (a run-time government lever): each host admits
    #    at most `immigration_cap × its population` immigrants in total. When it binds, the
    #    would-be migrants are turned away (stocks scaled down) ⇒ the wage gap PERSISTS
    #    (policy blocks convergence). None ⇒ open borders ⇒ the v22.1 mechanism unchanged.
    world._immigration_binding = [False] * n
    if world.immigration_cap is not None:
        for h in range(n):
            incoming = [i for i in range(n) if host_of[i] == h]
            total = sum(world._migrant_stock[i] for i in incoming)
            hcap = world.immigration_cap[h] if isinstance(world.immigration_cap, (list, tuple)) \
                else world.immigration_cap
            if hcap is None:       # B5a: per-economy None = that host is open
                continue
            ceiling = float(hcap) * len(econs[h].households)   # per-HOST cap
            if total > ceiling + EPS and total > 0.0:
                scale = ceiling / total
                for i in incoming:
                    world._migrant_stock[i] *= scale
                world._immigration_binding[h] = True

    # 3. Remittance receipts and signed current-account transfers.  Household
    # receipts are net of origin tax for the legacy distribution gauge; the CA uses
    # the gross cross-border amount and records the host's equal debit.
    remit = [0.0] * n
    current_transfers = [0.0] * n
    tax_rev = [0.0] * n
    for i in range(n):
        host = host_of[i]
        S = world._migrant_stock[i]
        if host < 0 or S <= EPS:
            continue
        remit_host = lever(world.remittance_share, i) * S * _wage(econs[host])   # origin i's diaspora send-home rate
        net_origin, origin_tax, host_outflow, gross_origin = _remit(
            world, host, i, remit_host,
        )
        remit[i] += net_origin
        tax_rev[i] += origin_tax
        current_transfers[host] -= host_outflow
        current_transfers[i] += gross_origin
    world._remittances = remit
    world._current_transfers = current_transfers
    world._remittance_tax_rev = tax_rev
    for i, econ in enumerate(econs):
        econ._remittance_tax_revenue_external = tax_rev[i]


def _remit(world, host: int, origin: int, amount_host: float):
    """Conserving cross-border transfer host → origin. Collect ``amount_host`` (curr_host)
    from host households, convert at the rate, then — POLICY — the origin government levies a
    REMITTANCE TAX on the inflow (revenue to its fiscal account); the net reaches origin
    households. Routed through the dealer (net-zero passthrough). Returns (net_remittance,
    tax_revenue, host outflow, gross origin inflow).  The latter pair is the signed
    current-transfer bridge and is equal in numeraire at the transaction FX vector.
    """
    if amount_host <= EPS:
        return 0.0, 0.0, 0.0, 0.0
    collected = _collect(world.economies[host], amount_host)
    if collected <= EPS:
        return 0.0, 0.0, 0.0, 0.0
    # POLICY: the HOST may tax OUTWARD remittances (e.g. the Gulf states) — levied before the
    # money leaves, revenue to the host's fiscus.
    he = world.economies[host]
    h_fiscal = getattr(he, "_fiscal", None)
    out_rate = lever(world.outward_remittance_tax, host)   # B5a: the HOST's own rate
    if out_rate > 0.0 and h_fiscal is not None and he.ledger.has_account(h_fiscal):
        out_tax = out_rate * collected
        if out_tax > EPS:
            he.ledger.transfer(DEALER_ID, h_fiscal, out_tax)   # host taxes the outflow
            he._outward_remittance_tax_revenue += out_tax
            collected -= out_tax
    amount_origin = collected * world.rates.bilateral(origin, host)   # curr_host → curr_origin
    # DEALER-BLEED FIX A: remittance conversion pays out at mid x (1 - spread)
    spread = getattr(world, "fx_spread", 0.0)
    if spread > 0.0:
        world._conversion_volume[host] += collected / max(1e-12, world.rates.e[host])
        world._fx_spread_margin_tick = getattr(
            world, "_fx_spread_margin_tick", 0.0
        ) + amount_origin * spread / max(1e-12, world.rates.e[origin])
        amount_origin *= 1.0 - spread
    oe = world.economies[origin]
    tax = 0.0
    fiscal = getattr(oe, "_fiscal", None)
    in_rate = lever(world.remittance_tax, origin)          # B5a: the ORIGIN's own rate
    if in_rate > 0.0 and fiscal is not None and oe.ledger.has_account(fiscal):
        tax = in_rate * amount_origin
        oe.ledger.transfer(DEALER_ID, fiscal, tax)                   # remittance tax → origin fiscal
    _distribute(oe, amount_origin - tax)                             # net to origin households
    return amount_origin - tax, tax, collected, amount_origin


def _collect(econ, amount: float) -> float:
    """Take ``amount`` from households pro-rata by deposit (capped by cash) into the dealer."""
    led = econ.ledger
    bridge = getattr(econ, "demographic_bridge", None)
    hh = [
        household
        for household in econ.households
        if bridge is None or bridge.household_has_living_members(household.id)
    ]
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
            if bridge is not None:
                bridge.post_household_cash_delta(
                    h.id, -take, reason="outward_remittance",
                )
            collected += take
    return collected


def _distribute(econ, amount: float) -> None:
    """Pay remittance receipts and post them to domestic income/claim books."""
    if amount <= EPS:
        return
    led = econ.ledger
    bridge = getattr(econ, "demographic_bridge", None)
    hh = [
        household
        for household in econ.households
        if bridge is None or bridge.household_has_living_members(household.id)
    ]
    if not hh:
        fiscal = getattr(econ, "_fiscal", None)
        if fiscal is None or not led.has_account(fiscal):
            raise AssertionError("remittance economy has no live or fiscal recipient")
        led.transfer(DEALER_ID, fiscal, amount)
        return
    per = amount / len(hh)
    for h in hh:
        led.transfer(DEALER_ID, h.id, per)
        if bridge is not None:
            bridge.post_transfer_income(h.id, per, reason="remittance")
        h.income_realized += per
