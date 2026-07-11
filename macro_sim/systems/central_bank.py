"""Central-bank policy-rate and quantity-tool orchestration."""

from __future__ import annotations

from typing import Any

from macro_sim.markets.matching import EPS


def set_policy_rate(econ: Any) -> None:
    cfg = econ.cfg.central_banking
    pol = econ.policy
    if pol.policy_rate_override is not None:
        # the player hand-sets the rate (a manual hike/cut), bypassing the Taylor rule and the frozen fallback.
        econ._rate = min(cfg.r_max, max(0.0, pol.policy_rate_override))
        return
    if not cfg.central_bank:
        econ._rate = cfg.r_interest
        return
    econ._infl_ema += cfg.infl_ema_lambda * (econ._prev_inflation - econ._infl_ema)
    u_prev = getattr(econ, "_prev_u", cfg.u_natural)
    r_target = (
        cfg.r_neutral
        + pol.taylor_phi_pi * (econ._infl_ema - pol.inflation_target)
        - pol.taylor_phi_u * (u_prev - cfg.u_natural)
    )
    r_new = pol.rate_inertia * econ._rate + (1.0 - pol.rate_inertia) * r_target
    econ._rate = min(cfg.r_max, max(0.0, r_new))


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
    if getattr(cfg, "omo_index_deposits", False):
        # v13: index the reserve target to what the payment system actually needs -- the
        # genesis-anchored nominal target detaches as soon as the price level moves (the sick
        # 10k run drained 135M against a fixed 868k target and ran on LOLR for ten years)
        target = pol.omo_reserve_target * cfg.reserve_floor_frac * econ.ledger.total_money
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
        for bid, r in pos.items():
            x = move * r / tot
            econ.ledger.retire_reserves(bid, x)
            econ._cb_absorbed += x
        econ._omo_flow = move
    elif move < -EPS and econ._cb_absorbed > EPS:
        inject = min(-move, econ._cb_absorbed)
        per = inject / len(banks)
        for b in banks:
            econ.ledger.issue_reserves(b.id, per)
        econ._cb_absorbed -= inject
        econ._omo_flow = -inject
