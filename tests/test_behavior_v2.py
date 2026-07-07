"""Unit tests for the v2 sector-aware behavior dispatch (PLAN_v2 step 2).

Pins the Cobb-Douglas math and the production<->labor-demand inversion round-trip,
and checks the linear path is unchanged from v1 (bit-identical dispatch).

Run: ``uv run python tests/test_behavior_v2.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from behavior import labor_demand_notional, plan_investment, produce, unit_cost  # noqa: E402
from config import Config  # noqa: E402
from agents import Firm  # noqa: E402

TOL = 1e-9


def test_linear_produce_is_a_times_N():
    f = Firm.create(0, Config())
    assert abs(produce(f, 7.0) - f.a * 7.0) < TOL
    assert abs(labor_demand_notional(f, produce(f, 7.0)) - 7.0) < TOL
    assert abs(unit_cost(f) - f.wage / f.a) < TOL  # v1 constant


def test_cobb_douglas_produce_and_inversion_roundtrip():
    f = Firm.create_c_firm(0, Config())  # K=20, A=1, alpha=0.3
    for N in (0.5, 3.0, 12.7, 50.0):
        y = produce(f, N)
        # y = A K^alpha N^(1-alpha)
        expected = f.A * f.capital ** f.alpha * N ** (1 - f.alpha)
        assert abs(y - expected) < 1e-7, f"produce mismatch at N={N}"
        # invert: labor_demand_notional(y) must recover N
        N_back = labor_demand_notional(f, y)
        assert abs(N_back - N) < 1e-6, f"inversion mismatch at N={N}: got {N_back}"


def test_cobb_douglas_diminishing_returns_uc_rises():
    """uc = w N^d / y* should RISE with planned output (diminishing returns)."""
    f = Firm.create_c_firm(0, Config())
    ucs = []
    for y_star in (5.0, 20.0, 60.0):
        f.production_target = y_star
        f.labor_demand_notional = labor_demand_notional(f, y_star)
        ucs.append(unit_cost(f))
    assert ucs[0] < ucs[1] < ucs[2], f"unit cost should rise with output, got {ucs}"


def test_zero_output_guards():
    f = Firm.create_c_firm(0, Config())
    assert labor_demand_notional(f, 0.0) == 0.0
    f.production_target = 0.0
    f.labor_demand_notional = 0.0
    assert unit_cost(f) > 0.0  # fallback (unit cost at N=1), not a crash


def test_plan_investment_accelerator():
    cfg = Config()
    f = Firm.create_c_firm(0, cfg)     # K=20, v=2.5, lambda_I=0.25, delta_K=0.05
    f.demand_expected = 30.0
    plan_investment(f)
    k_star = cfg.v * 30.0              # 75
    expected = max(0.0, cfg.lambda_I * (k_star - f.capital) + cfg.delta_K * f.capital)
    assert abs(f.investment_target - expected) < TOL, f"I* mismatch: {f.investment_target} vs {expected}"
    assert f.investment_target > 0.0   # desired K above current => positive investment


def test_kfirm_and_v1firm_do_not_invest():
    cfg = Config()
    for f in (Firm.create_k_firm(0, cfg), Firm.create(0, cfg)):
        f.demand_expected = 100.0
        plan_investment(f)
        assert f.investment_target == 0.0


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
