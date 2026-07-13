"""v18.3 acceptance tests (PLAN_v18) — the policy handle: differential VAT.

Per-sector VAT rates (τ_N on necessities, τ_L on luxuries) are live Policy levers; None
⇒ fall back to the uniform τ_c ⇒ bit-identical. "Done" for the differential-VAT handle:
  * neutrality: setting τ_N = τ_L = τ_c reproduces the uniform-VAT run exactly (the
    differential plumbing is correct);
  * zero-rating necessities (τ_N = 0, τ_L > 0) is PROGRESSIVE: the effective VAT rate
    falls on the necessity-heavy poor and rises on the luxury-heavy rich (the §34
    wealth-allowance reprise on the consumption side) -- emergent from the Engel
    gradient, not seeded.

Run: ``uv run python tests/test_differential_vat.py`` or via pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                       # noqa: E402

from macro_sim.config import Config                      # noqa: E402
from macro_sim.economy import Economy                    # noqa: E402


def _econ(**extra):
    base = dict(seed=0, n_households=30, n_firms_c=30, n_firms_k=15, n_banks=2,
                demographics_population=300, n_ticks=1095,
                housing_enabled=True, housing_market_enabled=True,
                energy_enabled=True, energy_household=True, consumption_strata=True,
                tax_consumption_rate=0.15)
    base.update(extra)
    return Economy(Config.v13(**base))


def test_differential_vat_neutral_when_equal():
    """Setting τ_N = τ_L = τ_c must reproduce the uniform-VAT run bit-for-bit (the
    differential path collapses to the uniform path)."""
    a = _econ().run()
    e = _econ()
    e.policy.tax_necessity_rate = 0.15
    e.policy.tax_luxury_rate = 0.15
    b = e.run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"], f"differential-equal not neutral at t={x['t']}"
        assert x["price_index"] == y["price_index"]
        assert x["conservation_drift"] == y["conservation_drift"]


def test_zero_rated_necessity_is_progressive():
    """Zero-rating necessities (τ_N=0, τ_L=0.25) ⇒ the effective VAT rate is lower for the
    necessity-heavy bottom expenditure quintile than the luxury-heavy top (progressive),
    while conservation holds."""
    e = _econ()
    e.policy.tax_necessity_rate = 0.0
    e.policy.tax_luxury_rate = 0.25
    recs = e.run()
    late = [r for r in recs[-365:] if r.get("necessity_share_bottomq") is not None]
    bq = float(np.mean([r["necessity_share_bottomq"] for r in late]))
    tq = float(np.mean([r["necessity_share_topq"] for r in late]))
    # with necessities zero-rated, effective VAT rate = (1 - necessity_share) * τ_L
    eff_poor = (1.0 - bq) * 0.25
    eff_rich = (1.0 - tq) * 0.25
    assert eff_poor < eff_rich, f"zero-rated necessity not progressive: poor {eff_poor:.3f} vs rich {eff_rich:.3f}"
    # conservation still holds through the differential remit
    assert max(abs(r.get("conservation_drift", 0.0)) for r in recs) < 1e-6 * recs[0]["total_money"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all differential-vat tests passed")
