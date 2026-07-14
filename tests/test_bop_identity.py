"""The open-economy accounting identities (PLAN_v20 §6).

The closed economy's hard gate is A5 (`ΣD − ΣL − bank_securities = M`, asserted every tick).
Opening the economy needs TWO more identities, and they must be GATES, not gauges:

1. **The multilateral BoP / passthrough identity (a HARD GATE).** The dealer is a zero-spread
   intermediary: every cross-border payload credits it in one currency and debits an equal
   numéraire value in another. So its per-tick numéraire FLOW ≡ 0. A nonzero flow means a
   payload created or destroyed value — the open-economy analog of `ConservationError`.

2. **The world identity.** Σ_i NFA_i = −(cumulative revaluation). The world's apparent net
   position with ITSELF is not zero — it is EXACTLY the accumulated valuation effect (the
   valuation channel). With the flow gated at zero, this closes to machine precision.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.world import World
from macro_sim.world.fx import DEALER_ID, BalanceOfPaymentsError


def _world(**kw):
    def cfg(a, r):
        return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=200,
                           seed=0, a=a, r_interest=r)
    return World([cfg(1.5, 0.06), cfg(0.6, 0.02)], base_seed=9, trade=True, capital=True,
                 capital_mobility=3.0, capital_adjust=0.2, **kw)


def test_passthrough_gate_holds_and_per_economy_a5_holds():
    world = _world()
    world.run()                                   # the gate runs every tick; a leak would raise
    for econ in world.economies:
        econ.ledger.assert_conserved()            # closed-economy A5 still holds per economy
        econ.ledger.assert_non_negative()


def test_world_identity_sigma_nfa_equals_minus_cumulative_revaluation():
    """Σ_i NFA_i = −(cumulative revaluation), to machine precision. NOT a tautology: the
    flow is gated at zero INDEPENDENTLY, so the residual is genuinely the valuation channel."""
    world = _world()
    world.run()
    for rec in world.world_records[::40]:
        residual = sum(rec["nfa"]) + rec["dealer_valuation"]
        assert abs(residual) < 1e-6


def test_the_gate_math_fires_on_a_non_passthrough_flow():
    """A gate that cannot fail is worthless. Hand the dealer a position change with no
    offsetting leg and the flow test must reject it."""
    world = _world()
    world.run(30)
    inv, e0 = world.dealer.inventory(), world.rates.e
    honest = list(inv)                                     # flow = 0 ⇒ accepted
    world.dealer.assert_flow_is_passthrough(honest, e0)
    leaky = [inv[0] - 25.0, inv[1]]                        # +25 of curr0 from nowhere
    with pytest.raises(BalanceOfPaymentsError):
        world.dealer.assert_flow_is_passthrough(leaky, e0)


def test_the_gate_catches_a_leak_injected_mid_tick(monkeypatch):
    """Integration: a cross-border payload that moves money to the dealer with NO offsetting
    leg. Per-economy A5 still passes (the transfer is a legal intra-ledger move) — which is
    exactly WHY the closed gate cannot catch it and the multilateral one must."""
    import macro_sim.world.world as W

    world = _world()
    world.run(30)

    def leaky_payload(w):
        econ = w.economies[0]
        econ.ledger.transfer(econ.households[0].id, DEALER_ID, 25.0)   # <- value from nowhere
        econ.ledger.assert_conserved()          # A5 is FINE — it is a legal intra-ledger move
        w._factor_income = [0.0] * w.n

    monkeypatch.setattr(W, "capital_interest", leaky_payload)   # runs inside the tick
    with pytest.raises(BalanceOfPaymentsError):
        world.step()
