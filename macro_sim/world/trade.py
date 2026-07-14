"""The cross-border trade layer (PLAN_v20 §4): dealer-routed imports/exports.

The coupling barrier sets each economy's IMPORT offer from last tick's foreign prices +
the current rate vector (fixed-cadence stale coupling, §5); the goods phase runs it
through the real matching engine (import competition emerges), so money conserves per
economy's ledger by construction. After the domestic step the mirror EXPORTS are shipped
directly — the dealer buys each economy's goods to cover what foreigners imported from it
THIS tick — so ``dealer_i = import_i − mirror_export_i ≈ 0`` when trade is symmetric. The
residual net inventory (the trade imbalance) drives the rate groping; grope IS the
mean-reversion (§3).
"""

from __future__ import annotations

from macro_sim.markets.matching import EPS, SellOffer
from macro_sim.world.capital import capital_financing, capital_grope_signal, peg_defense
from macro_sim.world.fx import DEALER_ID


def lever(v, i: int) -> float:
    """A policy lever may be a scalar (uniform across economies) or a per-economy list.
    ``None`` ⇒ 0 (inert). Lets one economy set a tariff/subsidy the others do not."""
    if v is None:
        return 0.0
    if isinstance(v, (list, tuple)):
        return float(v[i])
    return float(v)


def _capacity_real(econ) -> float:
    """A soft cap on real import units: a share of the economy's per-tick consumption
    capacity (households × per-capita units). Actual imports are bounded below this by
    household budgets and price competition inside the goods session."""
    return len(econ.households) * float(econ.cfg.a)


def prepare_trade(world) -> None:
    """Coupling barrier: install each economy's cross-border IMPORT offer (§4).

    The import offer facing economy i is the cheapest foreign source priced into currency
    i (foreign domestic price × bilateral rate × iceberg friction). Its stock is CAPPED by
    the economy's last-tick export earnings: at the pure-trade layer there is no capital
    account, so imports must be financed by exports — trade balances per economy over the
    coupling horizon (persistent imbalances await v21). A small bootstrap seed lets trade
    start from cold. Import competition + source choice then emerge from the matching."""
    econs = world.economies
    n = world.n
    rates = world.rates
    fric = world.fx_friction
    prev_export = world._last_export_value          # curr_i, last tick
    # POLICY: a tariff (import tax) marks up the import price — protective (fewer imports) —
    # and its revenue is skimmed to the importer's fiscus in settle_trade. off ⇒ no markup.
    tariff = 1.0 + world.tariff
    for i, econ in enumerate(econs):
        best_price = None
        best_j = -1
        for j in range(n):
            if j == i or world.sanctioned(i, j):  # POLICY: sanctioned partners do not trade
                continue
            pj = econs[j]._price_level            # curr_j, last tick (stale coupling)
            # POLICY: the EXPORTER's subsidy makes its goods cheaper abroad (negative = an
            # export tax, making them dearer). Its fiscus funds the gap in _ship_exports.
            sub = lever(world.export_subsidy, j)
            price_i = pj * (1.0 - sub) * rates.bilateral(i, j) * (1.0 + fric) * tariff
            if pj > EPS and (best_price is None or price_i < best_price):
                best_price, best_j = price_i, j   # economy i imports from its CHEAPEST source
        world._import_source[i] = best_j
        if best_price is None:
            econ._fx_import_offer = econ._fx_export_order = None
            continue
        # import budget (curr_i) = last-tick export earnings; cold-start bootstrap when zero
        budget_i = prev_export[i]
        if budget_i <= EPS:
            budget_i = world.fx_trade_cap * _capacity_real(econ) * best_price   # bootstrap
        budget_i = max(0.0, budget_i + capital_financing(world, i, best_price))  # v21: capital finances a deficit
        cap_real = min(world.fx_trade_cap * _capacity_real(econ), budget_i / best_price)
        # POLICY: an import QUOTA caps the physical volume admitted (a quantity control,
        # unlike the tariff's price control). None ⇒ no ceiling.
        if world.import_quota is not None:
            cap_real = min(cap_real, lever(world.import_quota, i) * _capacity_real(econ))
        econ._fx_import_offer = (
            SellOffer(account=DEALER_ID, stock=cap_real, price=best_price, ref=None)
            if cap_real > EPS
            else None
        )
        econ._fx_export_order = None              # exports settled directly (see settle_trade)


def settle_trade(world) -> None:
    """After the domestic steps: read realized imports, ship the mirror exports directly,
    and grope the rate on the dealer's residual net inventory."""
    econs = world.economies
    n = world.n
    rates = world.rates

    import_value = [0.0] * n
    tariff_rev = [0.0] * n
    for i, econ in enumerate(econs):
        off = getattr(econ, "_fx_import_offer", None)
        gross = (off.sold * off.price) if off is not None else 0.0
        econ._fx_import_offer = None
        econ._fx_export_order = None
        # POLICY tariff: split the gross into the goods base (funds the export mirror) and
        # the tariff, which the dealer remits to the importer's fiscus (conserving).
        base = gross / (1.0 + world.tariff)
        rev = gross - base
        fiscal = getattr(econ, "_fiscal", None)
        if rev > EPS and fiscal is not None and econ.ledger.has_account(fiscal):
            econ.ledger.transfer(DEALER_ID, fiscal, rev)
            tariff_rev[i] = rev
            import_value[i] = base
        else:
            import_value[i] = gross           # no fiscus to collect it ⇒ tariff is inert
    world._prev_import_value = import_value
    world._tariff_rev = tariff_rev

    # Ship exports: economy k supplies exactly the imports that were SOURCED FROM it this
    # tick (Σ_i import_value[i] where source[i]==k), valued in curr_k. Correct sourcing (not
    # "everyone imports from everyone") keeps the dealer balanced for N ≥ 3, not just N = 2.
    export_value = [0.0] * n
    subsidy_cost = [0.0] * n
    for k, econ in enumerate(econs):
        target = 0.0
        for i in range(n):
            if i != k and world._import_source[i] == k:
                target += import_value[i] * rates.bilateral(k, i)   # curr_i import → curr_k
        export_value[k] = _ship_exports(econ, target)
        subsidy_cost[k] = _export_subsidy_settle(world, k, econ, export_value[k])
    world._last_export_value = export_value
    world._export_subsidy_cost = subsidy_cost

    # Dealer residual net inventory (curr_i); >0 ⇒ deficit ⇒ curr_i depreciates (e_i ↑).
    # Normalize by money stock so λ is scale-free; fixed economy-id order (§9).

def grope_rates(world) -> None:
    """Move the exchange rates on the dealer's end-of-tick net inventory. Called AFTER every
    cross-border flow has settled, so all flows in a tick occur at ONE rate vector — which is
    what makes the flow/revaluation decomposition (and the passthrough gate) exact."""
    econs = world.economies
    n = world.n
    signal = world.dealer.inventory()
    scaled = [signal[i] / max(1.0, econs[i].ledger.total_money) for i in range(n)]
    scaled = capital_grope_signal(world, scaled)   # v21.1: grope toward the capital-sustained position
    scaled = peg_defense(world, scaled)            # v21.2: peg freezes the rate, reserves absorb
    world.rates.grope(scaled, world.fx_lambda)


def _export_subsidy_settle(world, k: int, econ, shipped: float) -> float:
    """POLICY: the exporter's government funds the export SUBSIDY (foreign buyers paid the
    discounted price; the fiscus tops the exporters up to their full price) — or collects
    the export TAX (a negative subsidy). Conserving; returns the fiscal cost (+) / revenue (−).
    """
    s = lever(world.export_subsidy, k)
    if s == 0.0 or shipped <= EPS:
        return 0.0
    fiscal = getattr(econ, "_fiscal", None)
    if fiscal is None or not econ.ledger.has_account(fiscal):
        return 0.0
    led = econ.ledger
    firms = [f for f in econ.c_firms if f.inventory >= 0.0 and f.price > EPS]
    if not firms:
        return 0.0
    if s > 0.0:
        cost = shipped * s / (1.0 - s)          # top exporters up to their full price
        per = cost / len(firms)
        for f in firms:
            led.transfer(fiscal, f.id, per)     # fiscus → exporters (subsidy)
            f.revenue += per
        return cost
    tax = shipped * (-s)                        # export tax: exporters → fiscus
    per = tax / len(firms)
    for f in firms:
        take = min(per, led.balance(f.id))
        if take > EPS:
            led.transfer(f.id, fiscal, take)
            f.revenue -= take
    return -tax


def _ship_exports(econ, target_value: float) -> float:
    """The dealer buys ``target_value`` (curr) of goods from the economy's firms, paying
    them in their currency. Exports are PRODUCED TO ORDER: a firm ships from inventory and
    produces the rest fresh (export-led production creates the good, like domestic
    production — the good is a real outside item, not money). Exports therefore match the
    target exactly, so the dealer nets to zero for symmetric trade BY CONSTRUCTION; the
    residual (from asymmetric prices/rates) is what the groping clears. Returns the value
    shipped (= target while any firm can post a price)."""
    if target_value <= EPS:
        return 0.0
    led = econ.ledger
    ranked = sorted((f for f in econ.c_firms if f.price > EPS), key=lambda f: f.price)
    if not ranked:
        return 0.0
    shipped = 0.0
    remaining = target_value
    for f in ranked:
        if remaining <= EPS:
            break
        val = remaining if f is ranked[-1] else min(remaining, f.inventory * f.price)
        if val <= EPS:
            continue
        q = val / f.price
        led.transfer(DEALER_ID, f.id, val)        # dealer pays exporter in its currency
        f.inventory = max(0.0, f.inventory - q)   # ship from stock; the rest is produced to order
        f.sales += q
        f.revenue += val
        shipped += val
        remaining -= val
    return shipped
