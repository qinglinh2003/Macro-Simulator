"""Empirical verification of the 'depression is inevitable' proof.

The design note derives, from the three inter-sector transfers alone (wages &
dividends firm->hh, purchases hh->firm), an exact per-tick identity for the change
in household-sector money H_t = sum_h D_h:

  (1)  ΔH_t = W_t + V_t - E_t                          [sector flow identity]
  (12) ΔH_t = -Σ_{π_f≥0}(1-ρ)π_f  -  Σ_{π_f<0}π_f      [exact, all regimes]
  (8)  ΔH_t = -(1-ρ)Π_t   when every firm's profit ≥ 0 [boom-phase clean form]

Because these follow purely from the transfer rules + accounting, (1) and (12)
must hold EVERY tick to machine precision. If they do, the proof's algebra is
backed by the running system (and it doubles as another ledger-leak check). (8)
is checked on the subset of ticks where all firms are profitable.

Run directly: ``uv run python tests/test_household_drain.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config          # noqa: E402
from economy import Economy        # noqa: E402

TOL = 1e-6  # absolute float tolerance for identities over ~1e4 money


def _run_and_collect(cfg):
    """Step the economy tick by tick, capturing per-firm profit right after each
    settlement (before the next tick's Phase-1 reset)."""
    econ = Economy(cfg)
    rows = []
    prev_H = econ.ledger.total_money - sum(econ.ledger.balance(f.id) for f in econ.firms)  # H at t=-1 (genesis hh)
    for _ in range(cfg.n_ticks):
        rec = econ.step()
        profits = [f.profit for f in econ.firms]   # tick-t profits, not yet reset
        H = rec["hh_money"]
        rows.append({
            "t": rec["t"],
            "H": H,
            "dH": H - prev_H,
            "W": rec["wages_paid"],
            "V": rec["dividends_paid"],
            "E": rec["consumption_spending"],
            "profits": profits,
            "Pi": sum(profits),
            "rho": cfg.rho,
        })
        prev_H = H
    return rows


def test_flow_identity_1_holds_every_tick():
    """(1) ΔH_t = W_t + V_t - E_t, to machine precision, every tick."""
    rows = _run_and_collect(Config())
    worst = max(abs(r["dH"] - (r["W"] + r["V"] - r["E"])) for r in rows)
    assert worst < TOL, f"flow identity (1) violated; worst residual = {worst:.3e}"


def test_exact_identity_12_holds_every_tick():
    """(12) ΔH_t = -Σ(1-ρ)π⁺ - Σπ⁻, to machine precision, every tick and every regime."""
    rows = _run_and_collect(Config())
    worst = 0.0
    for r in rows:
        rho = r["rho"]
        rhs = -sum((1 - rho) * p for p in r["profits"] if p >= 0.0) \
              - sum(p for p in r["profits"] if p < 0.0)
        worst = max(worst, abs(r["dH"] - rhs))
    assert worst < TOL, f"exact identity (12) violated; worst residual = {worst:.3e}"


def test_boom_phase_identity_8():
    """(8) ΔH_t = -(1-ρ)Π_t on ticks where ALL firms are profitable (boom phase).

    Also asserts the qualitative claim: on those ticks the drain is non-positive
    (households lose money) whenever ρ<1 and there is positive profit.
    """
    cfg = Config()
    rows = _run_and_collect(cfg)
    boom = [r for r in rows if all(p >= 0.0 for p in r["profits"])]
    assert boom, "no all-profitable ticks found; cannot exercise (8)"
    worst = max(abs(r["dH"] - (-(1 - r["rho"]) * r["Pi"])) for r in boom)
    assert worst < TOL, f"boom identity (8) violated; worst residual = {worst:.3e}"
    # drain direction: with rho<1 and Pi>0, ΔH must be strictly negative.
    if cfg.rho < 1.0:
        drains = [r for r in boom if r["Pi"] > TOL]
        assert drains and all(r["dH"] < TOL for r in drains), "boom phase should drain households"


def test_rho_one_stops_the_drain():
    """Corollary: ρ=1 (full payout) => ΔH_t ≈ 0 on all-profitable ticks (no drain)."""
    from dataclasses import replace
    rows = _run_and_collect(replace(Config(), rho=1.0))
    boom = [r for r in rows if all(p >= 0.0 for p in r["profits"])]
    worst = max(abs(r["dH"]) for r in boom)
    assert worst < TOL, f"ρ=1 should freeze household money in boom; worst |ΔH| = {worst:.3e}"


def _run_all():
    import statistics
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {t.__name__}: {exc}")

    # Also print the headline numbers so the identities are visible, not just asserted.
    rows = _run_and_collect(Config())
    boom = [r for r in rows if all(p >= 0.0 for p in r["profits"])]
    print(f"\n  ticks total={len(rows)}  all-profitable(boom)={len(boom)}")
    if boom:
        res8 = max(abs(r["dH"] - (-(1 - r["rho"]) * r["Pi"])) for r in boom)
        print(f"  (8) max residual over boom ticks: {res8:.2e}")
    res12 = max(
        abs(r["dH"] - (-sum((1 - r["rho"]) * p for p in r["profits"] if p >= 0)
                       - sum(p for p in r["profits"] if p < 0)))
        for r in rows)
    print(f"  (12) max residual over ALL ticks:  {res12:.2e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
