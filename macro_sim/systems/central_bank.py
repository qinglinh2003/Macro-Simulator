"""Central-bank policy-rate and quantity-tool orchestration."""

from __future__ import annotations

from typing import Any

from macro_sim.markets.matching import EPS


def assert_omo_balance_sheet(econ: Any, tol: float = 1.0e-8) -> None:
    """Hard gate for the reserve-drain counterasset and CB liability."""
    claims = getattr(econ, "_cb_omo_claims", {})
    if any(value < -tol for value in claims.values()):
        raise AssertionError(f"negative OMO claim: {claims!r}")
    total = sum(max(0.0, float(value)) for value in claims.values())
    absorbed = float(getattr(econ, "_cb_absorbed", 0.0))
    scale = max(1.0, total, abs(absorbed))
    if abs(total - absorbed) > tol * scale:
        raise AssertionError(
            f"OMO balance sheet does not close: bank claims={total}, "
            f"CB liability={absorbed}"
        )


def _resolve_failed_bank_omo_claims(econ: Any, banks: list[Any]) -> None:
    """Move a failed bank's risk-free CB claim with its resolved franchise."""
    claims = econ._cb_omo_claims
    alive_ids = {bank.id for bank in banks}
    stranded = sum(
        max(0.0, amount) for bank_id, amount in claims.items()
        if bank_id not in alive_ids
    )
    if stranded <= EPS or not banks:
        return
    for bank_id in list(claims):
        if bank_id not in alive_ids:
            claims[bank_id] = 0.0
    per = stranded / len(banks)
    for bank in banks:
        claims[bank.id] = claims.get(bank.id, 0.0) + per


def set_policy_rate(econ: Any) -> None:
    cfg = econ.cfg.central_banking
    pol = econ.policy
    # The inflation sensor is an observation state, not part of the Taylor-rule
    # decision.  A temporary manual rate setting must not freeze it, otherwise an
    # experimental rate shock also changes the information state and creates a
    # second, hidden treatment when the override is released.
    if cfg.central_bank:
        # B4c: the sensor smoothing is the CB's OWN measurement choice (policy)
        econ._infl_ema += pol.infl_ema_lambda * (econ._prev_inflation - econ._infl_ema)
    if pol.policy_rate_override is not None:
        # the player hand-sets the rate (a manual hike/cut), bypassing the Taylor rule and the frozen fallback.
        econ._rate = min(pol.r_max, max(0.0, pol.policy_rate_override))
        return
    if not cfg.central_bank:
        econ._rate = cfg.r_interest
        return
    # B4c: r*, u* are the CB's revisable ESTIMATES; r_max is its (policy) ceiling
    u_prev = getattr(econ, "_prev_u", pol.u_natural)
    r_target = (
        pol.r_neutral
        + pol.taylor_phi_pi * (econ._infl_ema - pol.inflation_target)
        - pol.taylor_phi_u * (u_prev - pol.u_natural)
    )
    r_new = pol.rate_inertia * econ._rate + (1.0 - pol.rate_inertia) * r_target
    econ._rate = min(pol.r_max, max(0.0, r_new))


def run_omo_phase(econ: Any) -> None:
    cfg = econ.cfg.central_banking
    pol = econ.policy                    # v12.4: the OMO/QE stance is a LIVE, player-adjustable policy dial;
    #                                      `bonds`/`interbank` (whether the machinery EXISTS) stay structural (Config).
    econ._omo_flow = 0.0
    if not (pol.omo and cfg.bonds and cfg.interbank):
        return
    banks = [b for b in econ.banks if b.alive]
    if not banks:
        return
    claims = getattr(econ, "_cb_omo_claims", None)
    if claims is None:
        # Compatibility for narrow test doubles and old serialized states.
        claims = econ._cb_omo_claims = {bank.id: 0.0 for bank in econ.banks}
    for bank in econ.banks:
        claims.setdefault(bank.id, 0.0)
    _resolve_failed_bank_omo_claims(econ, banks)
    if getattr(cfg, "omo_index_deposits", False):
        # v13: index the reserve target to what the payment system actually needs -- the
        # genesis-anchored nominal target detaches as soon as the price level moves (the sick
        # 10k run drained 135M against a fixed 868k target and ran on LOLR for ten years)
        target = pol.omo_reserve_target * pol.reserve_floor_frac * econ.ledger.total_money   # B4a
    else:
        target = pol.omo_reserve_target * econ._reserve_M0
    econ._omo_target_value = target   # metrics: reserve_gap reads the SAME target the OMO acts on
    current = sum(econ.ledger.reserves(b.id) for b in banks)
    move = pol.omo_drain_frac * (current - target)
    if move > EPS:
        pos = {b.id: econ.ledger.reserves(b.id) for b in banks if econ.ledger.reserves(b.id) > EPS}
        tot = sum(pos.values())
        if tot <= EPS:
            return
        drained = 0.0
        for index, (bid, r) in enumerate(pos.items()):
            x = move - drained if index == len(pos) - 1 else move * r / tot
            x = min(x, max(0.0, econ.ledger.reserves(bid)))
            econ.ledger.retire_reserves(bid, x)
            claims[bid] += x
            drained += x
        econ._cb_absorbed = sum(claims.values())
        econ._omo_flow = drained
    elif move < -EPS and econ._cb_absorbed > EPS:
        holders = [(bank, max(0.0, claims.get(bank.id, 0.0))) for bank in banks]
        outstanding = sum(amount for _bank, amount in holders)
        inject = min(-move, outstanding)
        redeemed = 0.0
        positive = [(bank, amount) for bank, amount in holders if amount > EPS]
        for index, (bank, amount) in enumerate(positive):
            x = inject - redeemed if index == len(positive) - 1 else inject * amount / outstanding
            x = min(x, claims[bank.id])
            econ.ledger.issue_reserves(bank.id, x)
            claims[bank.id] -= x
            redeemed += x
        econ._cb_absorbed = sum(claims.values())
        econ._omo_flow = -redeemed
    assert_omo_balance_sheet(econ)
