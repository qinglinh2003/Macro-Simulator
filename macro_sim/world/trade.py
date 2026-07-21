"""The cross-border trade layer (PLAN_v20 §4): dealer-routed imports/exports.

The coupling barrier sets each economy's IMPORT offer from last tick's foreign prices +
the current rate vector (fixed-cadence stale coupling, §5); the goods phase runs it
through the real matching engine (import competition emerges), so money conserves per
economy's ledger by construction. After the domestic step the mirror EXPORTS are shipped
directly — the dealer buys each economy's goods to cover what foreigners imported from it
THIS tick — so ``dealer_i = import_i − mirror_export_i ≈ 0`` when trade is symmetric. The
source inventories are reserved before either domestic market opens and only realized
import sales are invoiced back to those source firms.  Unsold reservations return to
their owners.  The residual dealer inventory (the trade imbalance) drives the rate
groping; grope IS the mean-reversion (§3).
"""

from __future__ import annotations

import math

from macro_sim.markets.matching import EPS, SellOffer
from macro_sim.shocks.engine import read_shock_factor
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


def _tariff_rate(world, i: int) -> tuple[float, float]:
    """Return importer ``i``'s rate and strictly positive acquisition multiplier."""
    value = world.tariff
    if isinstance(value, (list, tuple)) and len(value) != world.n:
        raise ValueError(
            f"tariff must be a scalar or have one value per economy ({world.n})"
        )
    rate = lever(value, i)
    multiplier = 1.0 + rate
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError(
            f"tariff for economy {i} must be finite and satisfy 1 + rate > 0"
        )
    return rate, multiplier


def _has_fiscal_account(econ) -> bool:
    fiscal = getattr(econ, "_fiscal", None)
    return fiscal is not None and econ.ledger.has_account(fiscal)


def _effective_tariff_rate(world, econ, i: int) -> tuple[float, float]:
    """A tax/subsidy without a fiscal cash counterleg is economically inert."""
    rate, multiplier = _tariff_rate(world, i)
    return (rate, multiplier) if _has_fiscal_account(econ) else (0.0, 1.0)


def _stored_tariff_rate(world, econ, i: int) -> tuple[float, float]:
    """Use the barrier-time tariff throughout settlement if policy mutates mid-tick."""
    if not hasattr(econ, "_fx_tariff_rate"):
        return _effective_tariff_rate(world, econ, i)
    rate = float(econ._fx_tariff_rate)
    multiplier = 1.0 + rate
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError(
            f"tariff for economy {i} must be finite and satisfy 1 + rate > 0"
        )
    return rate, multiplier


def _export_policy_rate(world, i: int) -> tuple[float, float]:
    """Return exporter ``i``'s subsidy and positive foreign-price multiplier."""
    value = world.export_subsidy
    if isinstance(value, (list, tuple)) and len(value) != world.n:
        raise ValueError(
            f"export_subsidy must be a scalar or have one value per economy ({world.n})"
        )
    subsidy = lever(value, i)
    multiplier = 1.0 - subsidy
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError(
            f"export_subsidy for economy {i} must be finite and satisfy 1 - rate > 0"
        )
    return subsidy, multiplier


def _effective_export_policy_rate(world, econ, i: int) -> tuple[float, float]:
    """Do not make exporters absorb a fiscal policy whose cash counterleg cannot exist."""
    subsidy, multiplier = _export_policy_rate(world, i)
    return (subsidy, multiplier) if _has_fiscal_account(econ) else (0.0, 1.0)


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
    # Validate every importer before reserving source inventory, so malformed
    # policy cannot leave a half-prepared coupling barrier behind.
    tariffs = [
        _effective_tariff_rate(world, econ, i) for i, econ in enumerate(econs)
    ]
    export_policies = [
        _effective_export_policy_rate(world, econ, i)
        for i, econ in enumerate(econs)
    ]
    if any(item is not None for item in world._export_reservations):
        raise AssertionError("stale export reservation crossed a coupling barrier")
    # Export-side capacity shocks are shared across all importers at this barrier.
    # A None entry retains the exact historical path and arithmetic when inert.
    shock_export_remaining = []
    for source in econs:
        factor = read_shock_factor(source, "export_capacity")
        shock_export_remaining.append(
            None if factor == 1.0
            else factor * sum(max(0.0, float(f.inventory)) for f in source.c_firms)
        )

    for i, econ in enumerate(econs):
        tariff_rate, tariff_multiplier = tariffs[i]
        # The acquisition-price trade is gross of tariff.  The domestic
        # national-accounts journal is currently at basic/pre-product-tax prices,
        # so retain the wedge for an explicit importer-side deflation there.
        econ._fx_tariff_rate = tariff_rate
        econ._fx_export_subsidy_rate = export_policies[i][0]
        indicative_price = None
        best_j = -1
        for j in range(n):
            if j == i or world.sanctioned(i, j):  # POLICY: sanctioned partners do not trade
                continue
            pj = econs[j]._price_level            # curr_j, last tick (stale coupling)
            # POLICY: the EXPORTER's subsidy makes its goods cheaper abroad (negative = an
            # export tax, making them dearer). Its fiscus funds the gap in _ship_exports.
            _subsidy, export_multiplier = export_policies[j]
            price_i = (
                pj * export_multiplier * rates.bilateral(i, j)
                * (1.0 + fric) * tariff_multiplier
            )
            if pj > EPS and (
                indicative_price is None or price_i < indicative_price
            ):
                # The stale country price selects a source without looking into the
                # current domestic sessions.  The binding contract quote is formed
                # below from the actual source-firm lots reserved at this barrier.
                indicative_price, best_j = price_i, j
        world._import_source[i] = best_j
        if indicative_price is None:
            econ._fx_import_offer = econ._fx_export_order = None
            continue
        cap_real = world.fx_trade_cap * _capacity_real(econ)
        import_factor = read_shock_factor(econ, "import_capacity")
        if import_factor != 1.0:
            cap_real *= import_factor
        # POLICY: an import QUOTA caps the physical volume admitted (a quantity control,
        # unlike the tariff's price control). None ⇒ no ceiling.
        if world.import_quota is not None:
            q = world.import_quota[i] if isinstance(world.import_quota, (list, tuple)) \
                else world.import_quota
            if q is not None:      # B5a: per-economy None = that importer is open
                cap_real = min(cap_real, float(q) * _capacity_real(econ))
        # ``cap_real`` and the market offer are units DELIVERED to the importer.
        # Under an iceberg cost the exporter must ship ``(1 + friction)`` source
        # units for every delivered unit; the difference melts in transit.  Reserve
        # those shipped units before either domestic market opens so the same unit
        # cannot be sold at home and abroad.  Stable economy order and
        # posted-price/firm-id order give deterministic scarcity allocation when
        # several importers choose the same exporter.
        iceberg_multiplier = 1.0 + fric
        candidate_lots = []
        remaining = cap_real * iceberg_multiplier
        source = econs[best_j]
        export_remaining = shock_export_remaining[best_j]
        _source_subsidy, export_multiplier = export_policies[best_j]
        spread = getattr(world, "fx_spread", 0.0)
        acquisition_factor = (
            export_multiplier
            * rates.bilateral(i, best_j)
            * tariff_multiplier
            / max(1e-9, 1.0 - spread)   # DEALER-BLEED FIX A: the importer pays the spread
        )
        for firm in sorted(source.c_firms, key=lambda item: (item.price, item.id)):
            if remaining <= EPS:
                break
            lot_price = float(firm.price)
            if lot_price <= EPS:
                continue
            units = min(max(0.0, float(firm.inventory)), remaining)
            if export_remaining is not None:
                units = min(units, max(0.0, export_remaining))
            if units <= EPS:
                continue
            candidate_lots.append(
                {"firm_id": firm.id, "units": units, "price": lot_price}
            )
            remaining -= units
            if export_remaining is not None:
                export_remaining -= units

        candidate_shipped = sum(float(lot["units"]) for lot in candidate_lots)
        candidate_barrier_value = sum(
            float(lot["units"]) * float(lot["price"])
            for lot in candidate_lots
        )
        candidate_delivered = candidate_shipped / iceberg_multiplier
        candidate_gross = candidate_barrier_value * acquisition_factor
        candidate_contract_price = (
            candidate_gross / candidate_delivered
            if candidate_delivered > EPS else 0.0
        )
        # The stale country aggregate above is a source-choice signal only.  Both
        # bootstrap finance and the binding budget use the current reserved-lot
        # quote, so an obsolete aggregate price cannot leak into the contract.
        budget_i = prev_export[i]
        if budget_i <= EPS:
            budget_i = candidate_gross
        budget_i = max(
            0.0,
            budget_i + capital_financing(world, i, candidate_contract_price),
        )

        lots = []
        remaining_budget = budget_i
        by_id = {firm.id: firm for firm in source.c_firms}
        for candidate in candidate_lots:
            if remaining_budget <= EPS:
                break
            unit_acquisition_cost = float(candidate["price"]) * acquisition_factor
            units = min(
                float(candidate["units"]),
                remaining_budget / unit_acquisition_cost,
            )
            if units <= EPS:
                continue
            firm = by_id[candidate["firm_id"]]
            firm.inventory -= units
            lots.append(
                {
                    "firm_id": candidate["firm_id"],
                    "units": units,
                    "price": float(candidate["price"]),
                }
            )
            remaining_budget -= units * unit_acquisition_cost
        if shock_export_remaining[best_j] is not None:
            actual_units = sum(float(item["units"]) for item in lots)
            shock_export_remaining[best_j] -= actual_units
        reserved_shipped = sum(float(lot["units"]) for lot in lots)
        barrier_lot_basic_value = sum(
            float(lot["units"]) * float(lot["price"]) for lot in lots
        )
        world._export_reservations[i] = (
            {
                "source": best_j,
                "iceberg_multiplier": iceberg_multiplier,
                "barrier_lot_basic_value": barrier_lot_basic_value,
                "lots": lots,
            }
            if reserved_shipped > EPS else None
        )
        delivered_stock = reserved_shipped / iceberg_multiplier
        # A single foreign offer can represent heterogeneous source lots because
        # settlement applies one common fill fraction to every reserved lot.  Its
        # value is therefore linear in the delivered fill at this weighted quote.
        contract_gross_importer = barrier_lot_basic_value * acquisition_factor
        contract_price = (
            contract_gross_importer / delivered_stock
            if delivered_stock > EPS else 0.0
        )
        econ._fx_import_offer = (
            SellOffer(
                account=DEALER_ID,
                stock=delivered_stock,
                price=contract_price,
                ref=None,
            )
            if delivered_stock > EPS else None
        )
        econ._fx_export_order = None              # reserved exports settle in settle_trade


def settle_trade(world) -> None:
    """Invoice realized imports against reserved source lots and return unused goods."""
    econs = world.economies
    n = world.n
    rates = world.rates

    import_value = [0.0] * n
    import_volume = [0.0] * n
    tariff_rev = [0.0] * n
    for i, econ in enumerate(econs):
        off = getattr(econ, "_fx_import_offer", None)
        gross = (off.sold * off.price) if off is not None else 0.0
        import_volume[i] = off.sold if off is not None else 0.0
        econ._fx_import_offer = None
        econ._fx_export_order = None
        # POLICY tariff: split the gross into the goods base (funds the export mirror) and
        # the tariff, which the dealer remits to the importer's fiscus (conserving).
        _rate, tariff_multiplier = _stored_tariff_rate(world, econ, i)
        base = gross / tariff_multiplier
        rev = gross - base
        fiscal = getattr(econ, "_fiscal", None)
        if abs(rev) > EPS and fiscal is not None and econ.ledger.has_account(fiscal):
            if rev > 0.0:
                econ.ledger.transfer(DEALER_ID, fiscal, rev)
            else:
                econ.ledger.transfer(fiscal, DEALER_ID, -rev)
            tariff_rev[i] = rev
            import_value[i] = base
        else:
            import_value[i] = gross           # no fiscus to collect it ⇒ tariff is inert
    world._prev_import_value = import_value
    world._prev_import_volume = import_volume
    world._tariff_rev = tariff_rev
    for i, econ in enumerate(econs):
        # Mirror World policy flows onto the domestic fiscal journal before its
        # same-period metrics are committed.
        econ._tariff_revenue_external = tariff_rev[i]

    # Settle the physical lots reserved at the coupling barrier. Only the fraction
    # actually bought in the importing goods market is invoiced; every unsold unit is
    # returned to its exact source firm. The source-currency invoice is the import
    # base converted at the same opening rate, preserving the dealer passthrough gate.
    export_value = [0.0] * n
    export_delivered_volume = [0.0] * n
    export_shipped_volume = [0.0] * n
    iceberg_loss_volume = [0.0] * n
    export_barrier_lot_basic_value = [0.0] * n
    export_account_lot_basic_value = [0.0] * n
    export_receipts_by_firm = [dict() for _ in range(n)]
    subsidy_cost = [0.0] * n
    unbacked_export_volume = [0.0] * n
    for importer, reservation in enumerate(world._export_reservations):
        if reservation is None:
            continue
        source_index = int(reservation["source"])
        source = econs[source_index]
        by_id = {firm.id: firm for firm in source.c_firms}
        iceberg_multiplier = float(reservation["iceberg_multiplier"])
        delivered = max(0.0, import_volume[importer])
        required_shipped = delivered * iceberg_multiplier
        reserved_shipped = sum(
            float(lot["units"]) for lot in reservation["lots"]
        )
        if required_shipped - reserved_shipped > 1e-9 * max(
            1.0, required_shipped, reserved_shipped,
        ):
            raise AssertionError(
                "import sale exceeded iceberg-backed source goods: "
                f"delivered={delivered} required_shipped={required_shipped} "
                f"reserved_shipped={reserved_shipped}"
            )
        reserved_delivered = reserved_shipped / iceberg_multiplier
        fill_fraction = (
            delivered / reserved_delivered if reserved_delivered > EPS else 0.0
        )
        if fill_fraction > 1.0 + 1e-9:
            raise AssertionError(
                "import fill exceeded the reserved foreign offer: "
                f"delivered={delivered} reserved_delivered={reserved_delivered}"
            )
        fill_fraction = min(1.0, max(0.0, fill_fraction))
        used_lots = []
        for lot in reservation["lots"]:
            firm = by_id.get(lot["firm_id"])
            if firm is None:
                raise AssertionError(
                    f"reserved exporter disappeared before settlement: {lot['firm_id']}"
                )
            reserved_units = float(lot["units"])
            # Every lot receives the same fill fraction.  This preserves the
            # barrier-time weighted contract price for any partial market fill;
            # consuming a cheapest prefix would change the value behind the single
            # importer quote after households had already traded at it.
            used = reserved_units * fill_fraction
            returned = reserved_units - used
            if returned > EPS:
                firm.inventory += returned
            if used > EPS:
                used_lots.append((
                    firm,
                    used,
                    used * float(lot["price"]),
                    used * float(firm.price),
                ))

        shipped = sum(units for _firm, units, _weight, _current in used_lots)
        if abs(shipped - required_shipped) > 1e-9 * max(
            1.0, shipped, required_shipped,
        ):
            raise AssertionError(
                "iceberg shipment did not back realized imports: "
                f"delivered={delivered} shipped={shipped} "
                f"required_shipped={required_shipped}"
            )
        if shipped <= EPS:
            continue

        target = import_value[importer] * rates.bilateral(source_index, importer)
        # DEALER-BLEED FIX A: settlement converts at mid x (1 - spread); the importer
        # already paid the mirrored 1/(1-s) in acquisition, so the exporter's contract
        # identity (sum units x price) recovers EXACTLY and the margin stays in dealer
        # inventory as market-making revenue.
        spread = getattr(world, "fx_spread", 0.0)
        if spread > 0.0:
            world._conversion_volume[importer] += import_value[importer] / max(
                1e-12, rates.e[importer]
            )
            margin = target * spread / max(1e-12, rates.e[source_index])
            world._fx_spread_margin_tick = getattr(
                world, "_fx_spread_margin_tick", 0.0
            ) + margin
            target *= 1.0 - spread
        weight_total = sum(weight for _firm, _units, weight, _current in used_lots)
        account_value_total = sum(
            current for _firm, _units, _weight, current in used_lots
        )
        paid = 0.0
        for index, (firm, units, weight, _current) in enumerate(used_lots):
            amount = (
                target - paid if index == len(used_lots) - 1
                else target * weight / max(EPS, weight_total)
            )
            if amount > EPS:
                source.ledger.transfer(DEALER_ID, firm.id, amount)
            firm.sales += units
            firm.revenue += amount
            export_receipts_by_firm[source_index][firm.id] = (
                export_receipts_by_firm[source_index].get(firm.id, 0.0) + amount
            )
            paid += amount
        export_value[source_index] += paid
        export_delivered_volume[source_index] += delivered
        export_shipped_volume[source_index] += shipped
        iceberg_loss_volume[source_index] += shipped - delivered
        export_barrier_lot_basic_value[source_index] += weight_total
        export_account_lot_basic_value[source_index] += account_value_total

    world._export_reservations = [None] * n
    for k, econ in enumerate(econs):
        subsidy_cost[k] = _export_subsidy_settle(
            world, k, econ, export_value[k], export_receipts_by_firm[k],
        )
    export_contract_basic_value = [
        export_value[i] + subsidy_cost[i] for i in range(n)
    ]
    export_barrier_lot_contract_gap = [
        export_barrier_lot_basic_value[i] - export_contract_basic_value[i]
        for i in range(n)
    ]
    for i, gap in enumerate(export_barrier_lot_contract_gap):
        scale = max(
            1.0,
            abs(export_barrier_lot_basic_value[i]),
            abs(export_contract_basic_value[i]),
        )
        if abs(gap) > 1e-9 * scale:
            raise AssertionError(
                "export contract did not settle at reserved lot basic value: "
                f"economy={i} contract_basic={export_contract_basic_value[i]} "
                f"barrier_lots={export_barrier_lot_basic_value[i]}"
            )
    export_lot_repricing_gap = [
        export_account_lot_basic_value[i] - export_barrier_lot_basic_value[i]
        for i in range(n)
    ]
    export_inventory_withdrawal_price_adjustment = [
        export_account_lot_basic_value[i] - export_contract_basic_value[i]
        for i in range(n)
    ]
    world._last_export_value = export_value
    world._last_export_delivered_volume = export_delivered_volume
    world._last_export_volume = export_shipped_volume
    world._iceberg_loss_volume = iceberg_loss_volume
    world._export_contract_basic_value = export_contract_basic_value
    world._export_barrier_lot_basic_value = export_barrier_lot_basic_value
    world._export_account_lot_basic_value = export_account_lot_basic_value
    world._export_barrier_lot_contract_gap = export_barrier_lot_contract_gap
    world._export_lot_repricing_gap = export_lot_repricing_gap
    world._export_inventory_withdrawal_price_adjustment = (
        export_inventory_withdrawal_price_adjustment
    )
    world._unbacked_export_volume = unbacked_export_volume
    world._export_subsidy_cost = subsidy_cost
    for i, econ in enumerate(econs):
        econ._export_subsidy_cost_external = subsidy_cost[i]
        # Same-tick external-trade journals consumed by domestic accounting after
        # World settlement. Imports are destination-delivered units; exports are
        # source-shipped units. Their difference is the physical iceberg loss.
        # Assign rather than accumulate so a zero-trade tick clears prior flows.
        econ._fx_import_transaction_value_external = import_value[i]
        econ._fx_import_value_external = import_value[i]
        econ._fx_import_delivered_volume_external = import_volume[i]
        econ._fx_import_volume_external = import_volume[i]
        econ._fx_export_transaction_value_external = export_value[i]
        econ._fx_export_value_external = export_value[i]
        econ._fx_export_delivered_volume_external = export_delivered_volume[i]
        econ._fx_export_shipped_volume_external = export_shipped_volume[i]
        econ._fx_export_volume_external = export_shipped_volume[i]
        econ._fx_iceberg_loss_volume_external = iceberg_loss_volume[i]
        econ._fx_export_contract_basic_value_external = (
            export_contract_basic_value[i]
        )
        econ._fx_export_barrier_lot_basic_value_external = (
            export_barrier_lot_basic_value[i]
        )
        econ._fx_export_account_lot_basic_value_external = (
            export_account_lot_basic_value[i]
        )
        econ._fx_export_barrier_lot_contract_gap_external = (
            export_barrier_lot_contract_gap[i]
        )
        econ._fx_export_lot_repricing_gap_external = export_lot_repricing_gap[i]
        econ._fx_export_inventory_withdrawal_price_adjustment_external = (
            export_inventory_withdrawal_price_adjustment[i]
        )

    # Dealer residual net inventory (curr_i); >0 ⇒ deficit ⇒ curr_i depreciates (e_i ↑).
    # Normalize by money stock so λ is scale-free; fixed economy-id order (§9).

def rate_grope_signal(world):
    """Build the closing FX signal and execute any real peg-reserve swap.

    Peg defense is itself a cross-border flow.  It must happen before the dealer's
    passthrough hard gate, even though the resulting signal is applied to rates only
    after that gate.
    """
    econs = world.economies
    n = world.n
    # The CB's reserve asset backs equal-and-opposite dealer settlement legs.
    # Only the residual market position should move the exchange rate.
    signal = world.market_external_positions()
    scaled = [signal[i] / max(1.0, econs[i].ledger.total_money) for i in range(n)]
    scaled = capital_grope_signal(world, scaled)   # v21.1: grope toward the capital-sustained position

    # A stock imbalance can exceed the current money stock after a crisis.  Feeding
    # that unbounded ratio straight into a log-price update makes one discrete
    # tâtonnement step arbitrarily large (and eventually overflows exp), rather than
    # describing price discovery.  This smooth relative-gap transform has unit slope
    # at equilibrium and approaches a finite one-step adjustment as the market moves
    # far out of balance; it is a response function, not a post-hoc rate clamp.
    bounded = []
    for value in scaled:
        if not math.isfinite(value):
            raise FloatingPointError(f"non-finite FX imbalance signal: {value!r}")
        bounded.append(value / (1.0 + abs(value)))
    # Bound the ordinary market-feedback signal first.  If reserves are exhausted,
    # ``peg_defense`` deliberately substitutes the accumulated, finite pent-up
    # pressure for a one-off crisis devaluation; compressing that release would
    # erase the regime-break mechanism this layer is meant to represent.
    return peg_defense(world, bounded)             # v21.2: peg freezes the rate, reserves absorb


def grope_rates(world, signal=None) -> None:
    """Apply a precomputed closing signal after every tick's flow gate has passed."""
    if signal is None:
        signal = rate_grope_signal(world)
    world.rates.grope(signal, world.fx_lambda)


def _export_subsidy_settle(
    world, k: int, econ, shipped: float, receipts_by_firm: dict | None = None,
) -> float:
    """POLICY: the exporter's government funds the export SUBSIDY (foreign buyers paid the
    discounted price; the fiscus tops the exporters up to their full price) — or collects
    the export TAX (a negative subsidy). Conserving; returns the fiscal cost (+) / revenue (−).
    """
    if hasattr(econ, "_fx_export_subsidy_rate"):
        s = float(econ._fx_export_subsidy_rate)
        multiplier = 1.0 - s
        if not math.isfinite(multiplier) or multiplier <= 0.0:
            raise ValueError(
                f"export_subsidy for economy {k} must be finite and satisfy 1 - rate > 0"
            )
    else:
        s, _multiplier = _effective_export_policy_rate(world, econ, k)
    if s == 0.0 or shipped <= EPS:
        return 0.0
    fiscal = getattr(econ, "_fiscal", None)
    if fiscal is None or not econ.ledger.has_account(fiscal):
        return 0.0
    led = econ.ledger
    receipts_by_firm = receipts_by_firm or {}
    by_id = {firm.id: firm for firm in econ.c_firms}
    firms = [by_id[firm_id] for firm_id in receipts_by_firm if firm_id in by_id]
    if not firms:
        return 0.0
    receipt_total = sum(max(0.0, receipts_by_firm.get(firm.id, 0.0)) for firm in firms)
    if receipt_total <= EPS:
        return 0.0
    if s > 0.0:
        cost = shipped * s / (1.0 - s)          # top exporters up to their full price
        for f in firms:
            amount = cost * receipts_by_firm[f.id] / receipt_total
            led.transfer(fiscal, f.id, amount)  # fiscus → actual exporters
            f.revenue += amount
        return cost
    # Buyer invoice = untaxed value * (1 + tax rate), so remove only the tax
    # wedge rather than applying the rate again to the tax-inclusive receipt.
    tax = shipped * (-s) / (1.0 - s)
    collected = 0.0
    for f in firms:
        due = tax * receipts_by_firm[f.id] / receipt_total
        take = min(due, led.balance(f.id))
        if take > EPS:
            led.transfer(f.id, fiscal, take)
            f.revenue -= take
            collected += take
    return -collected


def _ship_exports(econ, target_value: float) -> float:
    """Sell no more than currently available inventory.

    Coupled worlds use barrier reservations above; this bounded helper remains useful
    for direct callers and as a regression seam against unbacked residual filling.
    """
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
        val = min(remaining, max(0.0, f.inventory) * f.price)
        if val <= EPS:
            continue
        q = val / f.price
        led.transfer(DEALER_ID, f.id, val)        # dealer pays exporter in its currency
        f.inventory -= q
        f.sales += q
        f.revenue += val
        shipped += val
        remaining -= val
    return shipped
