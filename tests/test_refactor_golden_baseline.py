"""Small deterministic baselines for behavior-preserving refactors.

These signatures are intentionally tiny. They are not economic acceptance
tests; they are tripwires for import/package/system extraction work. If a
refactor changes one of these values, the change needs an explicit explanation
before continuing.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config  # noqa: E402
from macro_sim.economy import Economy  # noqa: E402


SIGNATURE_KEYS = (
    "total_money",
    "conservation_drift",
    "real_output",
    "price_index",
    "unemployment_rate",
)


def _signature(cfg: Config) -> dict[str, float]:
    rec = Economy(cfg).run()[-1]
    return {k: round(float(rec.get(k, 0.0)), 8) for k in SIGNATURE_KEYS}


def test_refactor_baseline_v1():
    assert _signature(Config(n_ticks=80, seed=0)) == {
        "total_money": 12000.0,
        "conservation_drift": 0.0,
        "real_output": 100.0,
        "price_index": 2.69173668,
        "unemployment_rate": 0.0,
    }


def test_refactor_baseline_v2():
    assert _signature(Config.v2(n_firms_c=8, n_firms_k=4, n_households=80, n_ticks=80, seed=0)) == {
        "total_money": 10400.0,
        "conservation_drift": 0.0,
        "real_output": 28.4996377,
        "price_index": 9.24029208,
        "unemployment_rate": 0.0,
    }


def test_refactor_baseline_v93():
    assert _signature(Config.v93(n_firms_c=8, n_firms_k=4, n_households=80, n_ticks=80, seed=0)) == {
        "total_money": 11155.53371165,
        "conservation_drift": 0.0,
        "real_output": 60.22844715,
        "price_index": 2.08514388,
        "unemployment_rate": 0.0,
    }


def test_refactor_baseline_v124():
    assert _signature(Config.v124(n_firms_c=8, n_firms_k=4, n_households=80, n_ticks=80, seed=0)) == {
        "total_money": 10982.19194968,
        "conservation_drift": 0.0,
        "real_output": 45.16179256,
        "price_index": 3.33314695,
        "unemployment_rate": 0.0,
    }


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"  FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
