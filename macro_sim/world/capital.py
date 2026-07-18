"""The international capital layer (PLAN_v21): persistent cross-border positions.

v20 mean-reverts the dealer's inventory (trade balances). v21 relaxes that: the interest
differential offsets the trade-balance pressure on the rate, so a persistent position — a
net foreign asset position — accumulates, financed by yield-seeking capital. The held
position earns the domestic interest rate: a cross-border interest flow = the current
account's factor-income line = the GNP≠GDP wedge (Layer B emerging from Layer A). All flows
route through the ledger, so each economy conserves; the capital flag off ⇒ v20 exactly.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from macro_sim.markets.matching import EPS
from macro_sim.world.fx import DEALER_ID

# The pegging CB's FX reserves: an account holding the ANCHOR's currency, inside the anchor
# economy's ledger (a real foreign asset, not a scalar). Reserves cannot go negative — that
# is the crisis.
CBRES_ID = "CBRES"
EXTERNAL_ISSUER_ID = "EXTISSUER"


def settlement_fractions(value, n: int) -> list[float]:
    """Validate and expand the external-interest cash-settlement policy.

    The policy is deliberately owned by :class:`World`, rather than by a domestic
    ``Config``: it governs cross-border contract settlement and may be common to the
    world or debtor-specific.  Re-validating at use time also makes run-time policy
    experiments fail loudly if they install a malformed value.
    """
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = list(value)
        if len(values) != n:
            raise ValueError(
                "external_interest_settlement_fraction must be a scalar or "
                f"have one value per economy ({n})"
            )
    else:
        values = [value] * n

    result: list[float] = []
    for item in values:
        try:
            fraction = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "external_interest_settlement_fraction values must be numeric"
            ) from exc
        if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
            raise ValueError(
                "external_interest_settlement_fraction values must be finite and in [0, 1]"
            )
        result.append(fraction)
    return result


def seed_reserves(world, amount_foreign: float) -> None:
    """Genesis: the pegging CB ACQUIRES its FX reserves through a conserving swap — its
    fiscus pays domestic currency to the dealer, which delivers foreign currency into the
    reserve account (the government borrowed at home to buy foreign assets, as CBs do).
    Numéraire-equal on both legs ⇒ a passthrough ⇒ the BoP gate holds from tick 0."""
    anchor = world.peg_anchor
    home, host = world.economies[world.peg_economy], world.economies[anchor]
    host.ledger.add_account(CBRES_ID)
    fiscal = getattr(home, "_fiscal", None)
    if fiscal is None or not home.ledger.has_account(fiscal) or amount_foreign <= EPS:
        return
    amount_dom = amount_foreign * world.rates.bilateral(world.peg_economy, anchor)
    home.ledger.transfer(fiscal, DEALER_ID, amount_dom)     # fiscus pays domestic (goes into debt)
    host.ledger.transfer(DEALER_ID, CBRES_ID, amount_foreign)   # dealer delivers the foreign asset


def _funder(econ):
    """Return the explicit aggregate-NFA issuer used by this coarse capital layer.

    The model does not yet allocate the external position across household, firm,
    bank and sovereign contracts.  Charging an arbitrary first live bank made
    aggregate factor income depend on bank list order and mixed an economy-wide
    liability into one bank's P&L.  Until typed external contracts exist, the
    Treasury/central-bank account is the explicit aggregate counterparty.
    """
    if econ.cfg.government:
        return econ._fiscal
    if econ.ledger.has_account(EXTERNAL_ISSUER_ID):
        return EXTERNAL_ISSUER_ID
    return None


def peg_defense(world, scaled):
    """The trilemma (PLAN_v21 §3). Under a PEG the exchange rate is FIXED and the central
    bank absorbs the imbalance onto FX reserves (the CB becomes the dealer of last resort).
    Open capital + an INDEPENDENT interest rate ⇒ persistent pressure ⇒ reserves drift
    monotonically ⇒ the peg is unsustainable: the CB has lost monetary autonomy (fixed rate
    + open capital + independent policy — pick two). Reserves hitting zero BREAKS the peg
    (the rate floats and devalues — a currency crisis, the reserve-drain analog of a bank
    run). Returns the (frozen while the peg holds) grope signal. peg off ⇒ unchanged."""
    if not world.peg:
        return scaled
    if world._peg_intact:
        # The trilemma proper: the pegged economy (0) runs an interest rate that differs
        # from the anchor. With open capital that mismatch is a CONTINUOUS one-way flow the
        # CB must keep offsetting from reserves. A LOWER rate ⇒ capital flees ⇒ the CB sells
        # FX reserves to defend. The POLICY rate (cfg.r_interest) — the deliberate choice,
        # not the endogenous Taylor path — is what defines "independent policy".
        p = world.peg_economy
        rates = [float(e.cfg.r_interest) for e in world.economies]
        r_mean = sum(rates) / world.n
        mismatch = r_mean - rates[p]                  # >0 ⇒ pegger's rate too LOW ⇒ outflow ⇒ drain
        M0 = world.economies[p].ledger.total_money
        # POLICY: capital controls throttle the flow that drains reserves — closing the
        # account lets the peg + an independent rate BOTH survive (the trilemma's 3rd corner).
        pressure = world.capital_mobility * mismatch * M0 * (1.0 - world.capital_control[p])
        drain_for = pressure * world.peg_reserve_scale        # foreign currency to sell
        _defend_peg(world, drain_for)                          # a REAL, conserving FX swap
        world._pent_up += pressure                             # suppressed depreciation accumulates
        a = world.peg_anchor
        if world.reserves() <= EPS:
            world._peg_intact = False                 # reserves exhausted ⇒ peg breaks
            # Release pent-up pressure = DEVALUATION of the pegger, ON TOP of the anchor's
            # own motion; the rest of the world keeps floating through the crisis tick.
            release = list(scaled)
            release[p] = scaled[a] + max(0.0, world._pent_up / max(1.0, M0))
            return release
        # v24 FIX (portrait finding A4): a bilateral peg fixes the CROSS rate e_p/e_a,
        # not the world. The old `[0.0]*n` froze EVERY currency for as long as the peg
        # held -- one intact peg silently turned the whole simulation into a fixed-
        # exchange-rate regime (the 30y portrait ran that way). The pegger now INHERITS
        # the anchor's grope signal: log_e[p] and log_e[a] receive identical increments,
        # so e_p/e_a is invariant by construction (the gauge renormalization shifts all
        # log-rates equally and cannot move a cross rate) while every other currency
        # floats on its own dealer-inventory signal.
        out = list(scaled)
        out[p] = scaled[a]
        return out
    return scaled                                     # peg already broken ⇒ free float


def _defend_peg(world, drain_for: float) -> None:
    """The CB defends the peg with a REAL foreign-exchange swap, routed through the dealer.

    Selling reserves (``drain_for`` > 0): the CB hands FOREIGN currency to the dealer (from
    its reserve account in the anchor economy's ledger) and takes back DOMESTIC currency —
    it is buying up its own currency to hold the peg. Buying reserves (< 0) is the reverse.
    Numéraire-equal on both legs ⇒ a passthrough ⇒ the multilateral BoP gate holds.
    """
    anchor = world.peg_anchor
    home, host = world.economies[world.peg_economy], world.economies[anchor]
    fiscal = getattr(home, "_fiscal", None)
    if fiscal is None or not home.ledger.has_account(fiscal):
        return
    e = world.rates.e
    if drain_for > EPS:                                # SELL reserves (defend a weak currency)
        drain_for = min(drain_for, host.ledger.balance(CBRES_ID))   # cannot sell what it lacks
        if drain_for <= EPS:
            return
        drain_dom = drain_for * world.rates.bilateral(world.peg_economy, anchor)  # curr_anchor → curr_pegger
        host.ledger.transfer(CBRES_ID, DEALER_ID, drain_for)        # CB → dealer (foreign)
        home.ledger.transfer(DEALER_ID, fiscal, drain_dom)          # dealer → CB (domestic)
    elif drain_for < -EPS:                             # BUY reserves (resist appreciation)
        buy_for = -drain_for
        buy_dom = buy_for * world.rates.bilateral(world.peg_economy, anchor)
        home.ledger.transfer(fiscal, DEALER_ID, buy_dom)            # CB pays domestic
        host.ledger.transfer(DEALER_ID, CBRES_ID, buy_for)          # dealer → CB (foreign)


def _pay_households(econ, amount: float) -> None:
    """Pay repatriated factor income and post it to domestic income/claim books."""
    if amount <= EPS:
        return
    bridge = getattr(econ, "demographic_bridge", None)
    recipients = [
        household
        for household in econ.households
        if bridge is None or bridge.household_has_living_members(household.id)
    ]
    if not recipients:
        # All demographic shells may be empty during an estate transition.  Keep
        # the cross-border passthrough conserving without inventing a dead person's
        # income claim; the fiscal estate receiver can redistribute next tick.
        fiscal = getattr(econ, "_fiscal", None)
        if fiscal is None or not econ.ledger.has_account(fiscal):
            raise AssertionError("factor-income economy has no live or fiscal recipient")
        econ.ledger.transfer(DEALER_ID, fiscal, amount)
        return
    per = amount / len(recipients)
    for h in recipients:
        econ.ledger.transfer(DEALER_ID, h.id, per)
        if bridge is not None:
            bridge.post_capital_income(h.id, per)
        h.income_realized += per


def _matrix(n: int) -> list[list[float]]:
    return [[0.0 for _ in range(n)] for _ in range(n)]


def _validated_non_negative_vector(value, n: int, name: str) -> list[float]:
    try:
        raw = list(value)
    except TypeError as exc:
        raise ValueError(f"{name} must have one value per economy") from exc
    if len(raw) != n:
        raise ValueError(f"{name} must have one value per economy ({n})")
    result = []
    for item in raw:
        number = float(item)
        if not math.isfinite(number) or number < 0.0:
            raise ValueError(f"{name} values must be finite and non-negative")
        result.append(number)
    return result


def _validated_arrears_matrix(value, n: int) -> list[list[float]]:
    try:
        raw = list(value)
    except TypeError as exc:
        raise ValueError(
            "_factor_income_arrears_bilateral must be a debtor-by-creditor matrix"
        ) from exc
    if len(raw) != n:
        raise ValueError(
            f"_factor_income_arrears_bilateral must have {n} debtor rows"
        )
    result = _matrix(n)
    for i, row in enumerate(raw):
        result[i] = _validated_non_negative_vector(
            row, n, f"_factor_income_arrears_bilateral[{i}]",
        )
        if result[i][i] > EPS:
            raise ValueError("external interest arrears cannot be owed to the debtor itself")
        result[i][i] = 0.0
    return result


def _creditor_weights(positions: list[float], e: list[float]) -> list[float]:
    """Current creditor claims in the common numeraire."""
    return [max(0.0, -positions[j]) / e[j] for j in range(len(positions))]


def _allocate_to_creditors(
    amount: float, weights: list[float], *, debtor: int,
) -> list[float] | None:
    """Lock a debtor-currency obligation to the current creditor owners.

    Returning ``None`` distinguishes "owner not observable" from a genuinely zero
    obligation.  The caller retains such amounts in a lossless compatibility bucket
    until a creditor distribution becomes observable.
    """
    eligible = [
        creditor for creditor, weight in enumerate(weights)
        if creditor != debtor and weight > EPS
    ]
    total_weight = sum(weights[creditor] for creditor in eligible)
    if amount <= EPS:
        return [0.0] * len(weights)
    if total_weight <= EPS:
        return None
    allocation = [0.0] * len(weights)
    allocated = 0.0
    for creditor in eligible[:-1]:
        value = amount * weights[creditor] / total_weight
        allocation[creditor] = value
        allocated += value
    allocation[eligible[-1]] = amount - allocated
    return allocation


def _pay_pro_rata(obligations: list[float], budget: float) -> list[float]:
    """Pay one priority class pro rata, assigning its final float residual exactly."""
    total = sum(obligations)
    if total <= EPS or budget <= EPS:
        return [0.0] * len(obligations)
    if budget >= total - EPS:
        return list(obligations)
    budget = min(budget, total)
    eligible = [index for index, value in enumerate(obligations) if value > EPS]
    payments = [0.0] * len(obligations)
    paid = 0.0
    for index in eligible[:-1]:
        value = budget * obligations[index] / total
        payments[index] = value
        paid += value
    payments[eligible[-1]] = budget - paid
    return payments


def _net_factor_income_local(
    bilateral: list[list[float]], e: list[float],
) -> list[float]:
    """Signed local-currency factor income (positive outflow, negative receipt)."""
    n = len(bilateral)
    net = [sum(bilateral[i]) for i in range(n)]
    for debtor in range(n):
        for creditor in range(n):
            amount = bilateral[debtor][creditor]
            if amount > 0.0:
                net[creditor] -= amount / e[debtor] * e[creditor]
    return net


def _opening_arrears(
    world, creditor_weights: list[float],
) -> tuple[list[list[float]], list[float]]:
    """Load the bilateral stock, lazily migrating the pre-v23 debtor-only vector.

    Old checkpoints had only ``_factor_income_arrears[i]`` and therefore did not
    identify the creditor.  When current ownership is observable we lock that stock
    once using current creditor weights.  Otherwise it remains in an explicit
    unallocated vector; malformed state raises instead of silently erasing debt.
    """
    n = world.n
    legacy_raw = getattr(world, "_factor_income_arrears", [0.0] * n)
    legacy = _validated_non_negative_vector(
        legacy_raw, n, "_factor_income_arrears",
    )
    matrix_raw = getattr(world, "_factor_income_arrears_bilateral", None)
    unallocated_raw = getattr(world, "_factor_income_arrears_unallocated", None)

    if matrix_raw is None:
        matrix = _matrix(n)
        unallocated = [0.0] * n
        for debtor, amount in enumerate(legacy):
            allocation = _allocate_to_creditors(
                amount, creditor_weights, debtor=debtor,
            )
            if allocation is None:
                unallocated[debtor] = amount
            else:
                matrix[debtor] = allocation
    else:
        matrix = _validated_arrears_matrix(matrix_raw, n)
        unallocated = (
            [0.0] * n if unallocated_raw is None
            else _validated_non_negative_vector(
                unallocated_raw, n, "_factor_income_arrears_unallocated",
            )
        )
        # Also support callers that populated only the legacy row vector on a new
        # World.  A non-empty bilateral row is authoritative because it contains
        # strictly more ownership information than the scalar compatibility field.
        for debtor in range(n):
            canonical = sum(matrix[debtor]) + unallocated[debtor]
            if canonical <= EPS and legacy[debtor] > EPS:
                allocation = _allocate_to_creditors(
                    legacy[debtor], creditor_weights, debtor=debtor,
                )
                if allocation is None:
                    unallocated[debtor] = legacy[debtor]
                else:
                    matrix[debtor] = allocation

    # Resolve ownerless legacy amounts as soon as a creditor distribution exists.
    # They are opening arrears (and thus retain payment priority over current accrual).
    for debtor, amount in enumerate(unallocated):
        if amount <= EPS:
            continue
        allocation = _allocate_to_creditors(
            amount, creditor_weights, debtor=debtor,
        )
        if allocation is not None:
            matrix[debtor] = [
                matrix[debtor][creditor] + allocation[creditor]
                for creditor in range(n)
            ]
            unallocated[debtor] = 0.0
    return matrix, unallocated


def capital_interest(world, positions=None) -> None:
    """Factor income — a REAL conserving cross-border flow (the GNP≠GDP wedge).

    A positive dealer position in currency i means foreigners hold claims on economy i: i is
    a net DEBTOR and PAYS interest abroad (GNP < GDP). A negative position means the economy
    is a net CREDITOR. The interest is not parked in the dealer (that would compound the
    principal); it is REPATRIATED — the dealer routes it, in numéraire-equal value, to the
    creditor economies' households as investment income (GNP > GDP for them).

    Collected numéraire ≡ distributed numéraire, so the flow is a PASSTHROUGH and the
    multilateral BoP gate holds. It is a true current-account item: the debtor's NFA
    deteriorates by what it pays, the creditor's improves by what it receives.  ``_rate``
    is already a per-tick contract rate throughout the domestic credit system, so factor
    income applies it once, with no second calendar-frequency conversion.
    """
    n = world.n
    rates = world.rates
    e = rates.e
    # World.step supplies the opening position snapshot.  Direct unit callers may
    # omit it and intentionally service the current stock.  Interest on trade or
    # capital acquired later in this tick begins next tick, preserving causality.
    if positions is None:
        positions = getattr(world, "_factor_interest_positions", None)
    positions = (
        [float(value) for value in positions]
        if positions is not None
        else [econ.ledger.balance(DEALER_ID) for econ in world.economies]
    )
    if len(positions) != n or any(not math.isfinite(value) for value in positions):
        raise ValueError("factor-interest positions must be finite and match World.n")
    fractions = settlement_fractions(
        getattr(world, "external_interest_settlement_fraction", 1.0), n,
    )
    for econ in world.economies:
        econ._external_interest_fiscal = 0.0

    # D[i][j], A[i][j], and P[i][j] are all denominated in debtor i's
    # currency.  Once D is allocated, later portfolio changes cannot move the
    # creditor: ownership lives in the matrix rather than in today's weights.
    weights = _creditor_weights(positions, e)
    opening_arrears, opening_unallocated = _opening_arrears(world, weights)
    accrued = _matrix(n)
    accrued_unallocated = [0.0] * n
    for i, econ in enumerate(world.economies):
        rate = float(getattr(econ, "_rate", econ.cfg.r_interest))
        due = max(0.0, max(0.0, positions[i]) * rate)
        if due <= EPS:
            continue
        allocation = _allocate_to_creditors(due, weights, debtor=i)
        if allocation is None:
            accrued_unallocated[i] = due
        else:
            accrued[i] = allocation

    cash = _matrix(n)
    arrears_paid = _matrix(n)
    current_paid = _matrix(n)
    closing_arrears = _matrix(n)
    closing_unallocated = [
        opening_unallocated[i] + accrued_unallocated[i] for i in range(n)
    ]
    for debtor, econ in enumerate(world.economies):
        opening_total = sum(opening_arrears[debtor])
        current_total = sum(accrued[debtor])
        serviceable = opening_total + current_total
        funder = _funder(econ)
        budget = (
            fractions[debtor] * serviceable
            if funder is not None and serviceable > EPS else 0.0
        )

        # Contractual priority is old arrears first.  Within a priority class every
        # creditor receives the same pro-rata recovery; the final creditor receives
        # the deterministic floating-point residual so row identities close exactly.
        arrears_paid[debtor] = _pay_pro_rata(opening_arrears[debtor], budget)
        budget -= sum(arrears_paid[debtor])
        current_paid[debtor] = _pay_pro_rata(accrued[debtor], budget)
        for creditor in range(n):
            cash[debtor][creditor] = (
                arrears_paid[debtor][creditor]
                + current_paid[debtor][creditor]
            )
            closing_arrears[debtor][creditor] = max(
                0.0,
                opening_arrears[debtor][creditor]
                + accrued[debtor][creditor]
                - cash[debtor][creditor],
            )

        cash_out = sum(cash[debtor])
        if cash_out > EPS:
            econ.ledger.transfer(funder, DEALER_ID, cash_out)
            econ._external_interest_fiscal += cash_out

    # Repatriate the exact bilateral cash matrix.  The cash passthrough remains
    # numeraire-zero even when the creditor set has changed since an arrear arose.
    for creditor, econ in enumerate(world.economies):
        receipt_numeraire = sum(
            cash[debtor][creditor] / e[debtor] for debtor in range(n)
        )
        _pay_households(econ, receipt_numeraire * e[creditor])

    cash_factor = _net_factor_income_local(cash, e)
    accrued_factor = _net_factor_income_local(accrued, e)
    for debtor in range(n):
        # Preserve even a structurally inconsistent ownerless accrual as the
        # debtor's liability instead of making it disappear from accrual accounts.
        accrued_factor[debtor] += accrued_unallocated[debtor]
    world._factor_income_cash_bilateral = cash
    world._factor_income_accrued_bilateral = accrued
    world._factor_income_accrued_unallocated = accrued_unallocated
    world._factor_income_arrears_bilateral = closing_arrears
    world._factor_income_arrears_unallocated = closing_unallocated
    world._factor_income_cash = cash_factor
    world._factor_income_accrued = accrued_factor
    world._factor_income_accrual = list(accrued_factor)  # noun-form compatibility alias
    world._factor_income = list(cash_factor)  # legacy: factor income means settled cash
    world._factor_income_arrears = [
        sum(closing_arrears[i]) + closing_unallocated[i] for i in range(n)
    ]
    world._factor_income_unpaid_tick = [
        sum(accrued[i][j] - current_paid[i][j] for j in range(n))
        + accrued_unallocated[i]
        for i in range(n)
    ]
    world._factor_income_arrears_cured_tick = [
        sum(arrears_paid[i]) for i in range(n)
    ]


def target_positions(world):
    """Portfolio-balance target: foreigners want to hold ``mobility·(rate_i − r_mean)·M_i``
    of currency i. A high rate ⇒ positive ⇒ foreigners accumulate i-claims ⇒ economy i is a
    net DEBTOR (the dealer's target i-position is positive). Fixed economy-id order (§9)."""
    rates = [float(getattr(e, "_rate", e.cfg.r_interest)) for e in world.economies]
    r_mean = sum(rates) / world.n
    return [world.capital_mobility * (rates[i] - r_mean) * world.economies[i].ledger.total_money
            for i in range(world.n)]


def capital_financing(world, i, best_price) -> float:
    """Capital RELAXES the balanced-trade constraint: net NFA = cumulative current-account
    imbalance, so a persistent position needs a persistent trade deficit financed by
    yield-seeking capital toward the portfolio target (§1). The per-tick inflow closes the
    gap to target; it finances EXTRA imports (a deficit) that accumulate the dealer's
    i-position toward target. At target the inflow stops and the NFA is stable. Returns the
    extra import budget (curr_i); negative for a low-rate economy (outflow). off ⇒ 0."""
    if not world.capital or world.capital_mobility == 0.0 or best_price <= 0.0:
        return 0.0
    target = target_positions(world)[i]
    # Official FX-reserve acquisition has equal dealer settlement legs and a
    # matching reserve asset.  Portfolio flows react to the market position net
    # of that backing, not to the gross plumbing balance.
    current = world.market_external_positions()[i]
    # POLICY: capital controls throttle the flow (0 = free mobility, 1 = closed account).
    # Closing the account lets a peg keep monetary autonomy — the trilemma's third corner.
    return world.capital_adjust * (target - current) * (1.0 - world.capital_control[i])


def capital_grope_signal(world, scaled):
    """When capital is on, the rate gropes toward the capital-SUSTAINED position, not zero:
    signal_i = (inventory_i − throttle·target_i)/M_i. At the target the rate is stable and the
    NFA persists (else a nonzero equilibrium position would depreciate the rate forever).
    off ⇒ signal unchanged ⇒ v20 mean-to-zero groping ⇒ bit-identical.

    POLICY: capital controls throttle the grope target by (1 − capital_control), exactly as they
    throttle the capital FLOW in ``capital_financing``. Without this the rate chased the FULL
    open-account target while the account was closed, so under a closed account (capital_control
    → 1) the rate over-shot toward a position capital could not finance and TRADE flows filled the
    gap — inflating external positions instead of shrinking them (the opposite of the trilemma's
    third corner). At capital_control = 0 the throttle is 1.0 ⇒ bit-identical to the open account;
    at 1.0 the target is 0 ⇒ the rate reverts to v20 trade-balance groping, so a closed account +
    an independent rate no longer manufacture a spurious NFA."""
    if not world.capital or world.capital_mobility == 0.0:
        return scaled
    target = target_positions(world)
    return [scaled[i] - (1.0 - world.capital_control[i]) * target[i]
            / max(1.0, world.economies[i].ledger.total_money)
            for i in range(world.n)]
