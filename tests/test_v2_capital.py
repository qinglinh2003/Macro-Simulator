"""v2 acceptance tests (DESIGNDOC §10.8, PLAN_v2 §6).

Covers the four things that make v2 trustworthy:
  * three-sector money conservation, with capital correctly EXCLUDED (real, not money);
  * the capital law of motion K_t = (1-δ_K)K_{t-1} + I_t per firm per tick;
  * the v2 drain identity to machine precision (unconditional and boom form), which
    is the quantitative acceptance instrument (PLAN_v2 §1.4);
  * drain *mitigation* attributable to B_K -- households materially less drained than
    v1 (full reversal is calibration, not a v1/plumbing pass-fail).

Run: ``uv run python tests/test_v2_capital.py``.
"""

from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config          # noqa: E402
from economy import Economy        # noqa: E402

TOL = 1e-6


def _run_v2(**kw):
    econ = Economy(Config.v2(n_firms_c=20, n_firms_k=10, n_households=200, n_ticks=300, seed=0, **kw))
    recs = econ.run()
    return econ, recs


def test_three_sector_conservation():
    econ, recs = _run_v2()
    M = econ.ledger.genesis_money
    worst = max(r["conservation_drift"] for r in recs)
    assert worst < TOL, f"3-sector money not conserved; worst drift {worst:.3e}"
    # explicit: hh + C + K deposits == M
    last = recs[-1]
    assert abs((last["hh_money"] + last["c_firm_money"] + last["k_firm_money"]) - M) < TOL


def test_capital_excluded_from_money():
    """Capital is a real stock: it changes over the run while total money stays == M."""
    econ, recs = _run_v2()
    caps = [r["aggregate_capital"] for r in recs]
    monies = [r["total_money"] for r in recs]
    assert max(caps) - min(caps) > 1.0, "capital should vary over the run"
    assert max(monies) - min(monies) < TOL, "total money must be invariant despite K moving"


def test_capital_law_of_motion():
    """K_t = (1-δ_K)K_{t-1} + I_t per C-firm per tick, to machine precision."""
    econ = Economy(Config.v2(n_firms_c=20, n_firms_k=10, n_households=200, n_ticks=120, seed=1))
    worst = 0.0
    for _ in range(econ.cfg.n_ticks):
        econ.step()
        for f in econ.c_firms:
            expected = (1.0 - f.delta_K) * f.capital_prev + f.investment
            worst = max(worst, abs(f.capital - expected))
    assert worst < 1e-9, f"capital law of motion violated; worst residual {worst:.3e}"


def test_v2_drain_identity_unconditional():
    """ΔH_t = B_t + V_t − R_C,t every tick, machine precision (PLAN_v2 §4)."""
    econ, recs = _run_v2()
    hh = [r["hh_money"] for r in recs]
    worst = 0.0
    for i in range(1, len(recs)):
        dH = hh[i] - hh[i - 1]
        rhs = recs[i]["wages_paid"] + recs[i]["dividends_paid"] - recs[i]["consumption_spending"]
        worst = max(worst, abs(dH - rhs))
    assert worst < TOL, f"unconditional v2 drain identity violated; worst {worst:.3e}"


def test_v2_drain_identity_boom_form():
    """On boom ticks (all profits ≥ 0, no dividend cash-cap): ΔH = R_K − (1−ρ)Π_total."""
    econ = Economy(Config.v2(n_firms_c=20, n_firms_k=10, n_households=200, n_ticks=300, seed=0))
    rho = econ.cfg.rho
    rows = []
    prev_H = None
    for _ in range(econ.cfg.n_ticks):
        rec = econ.step()
        profits = [f.profit for f in econ.firms]
        H = rec["hh_money"]
        if prev_H is not None:
            rows.append((H - prev_H, rec["investment_spending"], sum(profits),
                         all(p >= 0 for p in profits), rec["dividend_shortfall"]))
        prev_H = H
    boom = [(dH, RK, Pi) for (dH, RK, Pi, allpos, sf) in rows if allpos and sf < 1e-9]
    assert boom, "no clean boom ticks to exercise the boom-form identity"
    worst = max(abs(dH - (RK - (1 - rho) * Pi)) for (dH, RK, Pi) in boom)
    assert worst < TOL, f"boom-form v2 drain identity violated; worst {worst:.3e}  (n_boom={len(boom)})"


def test_drain_mitigated_vs_v1():
    """v2 households are materially less drained than v1, attributable to B_K.

    Conservative (§10.8): asserts mitigation + a live cure channel, NOT full reversal
    (net_drain can stay > 0 -- that is calibration, not a pass/fail). Uses a long
    horizon and the last-quarter tail so v1's collapse transient is not counted, then
    a generous margin (empirically ~12x mitigation, robust across seeds; assert >3x).
    """
    v1_recs = Economy(Config(n_ticks=600, seed=0)).run()
    v2_recs = Economy(Config.v2(n_firms_c=20, n_firms_k=10, n_households=200, n_ticks=600, seed=0)).run()

    def tail_mean(recs, key, frac=0.75):
        tail = recs[int(len(recs) * frac):]
        return statistics.fmean(r[key] for r in tail)

    v1_share = tail_mean(v1_recs, "hh_money_share")
    v2_share = tail_mean(v2_recs, "hh_money_share")
    assert tail_mean(v2_recs, "wages_K") > 0.0, "cure channel B_K is dead (cold-start not wired?)"
    assert tail_mean(v2_recs, "investment_spending") > 0.0, "no investment happening"
    assert v2_share > 3.0 * v1_share, (
        f"v2 should retain materially more household money than v1: "
        f"v2_share={v2_share:.4f} vs v1_share={v1_share:.4f}"
    )


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
