"""v18.4 acceptance tests (PLAN_v18) — inter-household family transfers.

The first-line private safety net: a household that cannot afford its necessity need from
live deposits is topped up by kin households (parents / adult children) holding a surplus
above their own need x a buffer. "Done" for the family-transfer coupling:
  * flag off (with a non-default buffer) ⇒ bit-identical, no family columns leak;
  * the transfer is ATOMIC and CONSERVING (the A5 / conservation gate stays green when
    the flag is on);
  * the mechanism SURFACES the exposed -- in-need households with no kin donor -- a
    distributional object the arc could not name before.

Honest finding (PLAN_v18 18.4): the deprivation REDUCTION is small. Kin support works
against IDIOSYNCRATIC shocks (one member down, others help); it is overwhelmed by
SYSTEMIC deprivation (a no-safety-net collapse leaves few donors with any surplus), and
dormant in the healthy baseline (the JG + benefits net already clears deprivation). So
the acceptance checks conservation + exposure surfacing, not a large deprivation drop.

Run: ``uv run python tests/test_family_transfers.py`` or via pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config                      # noqa: E402
from macro_sim.economy import Economy                    # noqa: E402


def _world(**extra) -> Config:
    base = dict(seed=0, n_households=30, n_firms_c=30, n_firms_k=15, n_banks=2,
                demographics_population=300, n_ticks=1460,
                housing_enabled=True, housing_market_enabled=True,
                energy_enabled=True, energy_household=True, consumption_strata=True)
    base.update(extra)
    return Config.v13(**base)


def test_family_off_bit_identical():
    """Flag off with a non-default buffer ⇒ nothing moves, no family columns."""
    a = Economy(_world(n_ticks=730)).run()
    b = Economy(_world(n_ticks=730, family_transfer_buffer=2.0)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"]
        assert x["conservation_drift"] == y["conservation_drift"]
        assert "family_transfer_total" not in y, "family columns must not appear with the flag off"


def test_family_conserves_and_surfaces_exposed():
    """No-safety-net (so deprivation exists) + family transfers on: conservation holds,
    and the exposed (in-need, no-kin-donor) gauge is populated -- the mechanism names the
    truly vulnerable even when it cannot help them (systemic collapse ⇒ few donors)."""
    recs = Economy(_world(n_ticks=1460, family_transfers=True,
                          benefit_replacement=0.0, jg_wage_ratio=0.0, gov_deficit_target=0.0)).run()
    # conservation through the atomic transfer
    assert max(abs(r.get("conservation_drift", 0.0)) for r in recs) < 1e-6 * recs[0]["total_money"]
    active = [r for r in recs if r.get("family_transfer_total") is not None]
    assert active, "family gauges never populated"
    # the exposed gauge surfaces the no-kin-donor in-need households at some point
    assert max(r.get("family_exposed", 0.0) for r in active) > 0.0, "exposed gauge never fired"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all family-transfer tests passed")
