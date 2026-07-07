"""Formal seed-invariance sign-off for v1 (spec M3(a), §8.3 deliverable 4).

Micro queuing order is idiosyncratic noise with no 'true' value, so it is
randomized (seeded) and integrated out: a macro result that depends on the seed
ordering is an artifact, not a finding. This test re-runs the kernel across
several seeds — with the LARGER invariance-variant N (50 firms / 500 households)
so small-sample noise does not masquerade as seed-dependence — and asserts the
stationary (post-burn-in) means of the key series agree across seeds within a
tolerance on the coefficient of variation.

Run directly: ``uv run python tests/test_seed_invariance.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config              # noqa: E402
from macro_sim.reporting.diagnostics import seed_invariance  # noqa: E402

# Series that should be seed-invariant, and the CV ceiling across seeds. These are
# aggregate stationary means; with the larger N a few-percent spread is expected
# sampling noise, so 0.15 is a comfortable ceiling that still catches real
# seed-dependence (which would show up as tens of percent).
# The v1 kernel collapses to a depression (§9), so real_output is a near-zero *residual*
# whose relative noise is high (and does NOT shrink with N) even though the macro STATE
# — the depression — is seed-invariant. So we test seed-invariance on the robust state
# indicators (unemployment, price, markup); output-invariance is checked in the healthy
# v2/v3 economies (test_v3 seed check), where it holds (cv~0.015).
KEYS = ["price_index", "unemployment_rate", "avg_markup"]
CV_CEILING = 0.15


def test_macro_series_are_seed_invariant():
    inv = seed_invariance(Config(), seeds=[0, 1, 2, 3], keys=KEYS)
    offenders = {k: s["cv"] for k, s in inv["summary"].items() if s["cv"] >= CV_CEILING}
    assert not offenders, (
        f"seed-dependent macro series (cv >= {CV_CEILING}): {offenders} — "
        "result may be an artifact of queuing order, not a finding (M3(a))"
    )


def _run_all():
    print("Seed-invariance across seeds [0,1,2,3], larger N (50 firms / 500 hh):")
    inv = seed_invariance(Config(), seeds=[0, 1, 2, 3], keys=KEYS)
    failures = 0
    for k, s in inv["summary"].items():
        ok = s["cv"] < CV_CEILING
        failures += 0 if ok else 1
        print(f"  {k:22s} mean={s['mean']:.4f}  cv={s['cv']:.3f}  "
              f"per_seed={[round(v,3) for v in s['per_seed']]}  [{'OK' if ok else 'CHECK'}]")
    print(f"\n{'PASS' if not failures else 'FAIL'}: "
          f"{len(inv['summary']) - failures}/{len(inv['summary'])} series seed-invariant")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
