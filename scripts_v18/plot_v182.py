"""v18.2 diagnostic: indices & incidence -- whose inflation is whose, and the
consumption asymmetry of a supply shock.

Self-contained. Runs a paired experiment on the frontier (v18 stack: necessity/luxury
split + household energy), with vs without a v17.2 energy capacity shock at year 5, and
renders artifacts/diagnostics/diagnostic_v182.png:
  * group-specific inflation: the bottom vs top per-need-unit-expenditure quintile
    (democratic vs plutocratic) -- the shock hits the poor's basket harder (they spend
    a larger share on energy + necessities, the goods that spike);
  * the consumption asymmetry: LUXURY output collapses while NECESSITY output holds
    (necessity is price-inelastic priority demand);
  * necessity share rises through the shock (forced budget reallocation);
  * the deprivation gauge (destitute share) response.

  PYTHONPATH=. uv run python scripts_v18/plot_v182.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.config import Config       # noqa: E402
from macro_sim.economy import Economy     # noqa: E402

OUT = "artifacts/diagnostics/diagnostic_v182.png"
SHOCK_AT = 1825


def run(shock: bool):
    kw = dict(seed=0, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
              demographics_population=500, n_ticks=3650,
              housing_enabled=True, housing_market_enabled=True,
              energy_enabled=True, energy_household=True,
              consumption_strata=True, deprivation_gauges=True, deprivation_burnin_years=3)
    if shock:
        kw.update(energy_shock_at=SHOCK_AT, energy_shock_magnitude=0.4, energy_shock_duration=180)
    return Economy(Config.v13(**kw)).run()


def col(recs, k):
    return np.array([float(r.get(k) or 0.0) for r in recs], float)


def smooth(y, w=31):
    y = np.asarray(y, float)
    if len(y) < w:
        return y
    half = w // 2
    ypad = np.concatenate([np.full(half, y[0]), y, np.full(half, y[-1])])
    return np.convolve(ypad, np.ones(2 * half + 1) / (2 * half + 1), mode="valid")[:len(y)]


def cumindex(infl):
    """Compound a per-tick inflation series into an index (base 1.0)."""
    idx = np.cumprod(1.0 + np.asarray(infl, float))
    return idx / idx[0] if len(idx) and idx[0] != 0 else idx


def main():
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    base = run(shock=False)
    shk = run(shock=True)
    yrs = col(shk, "t") / 365.0

    fig, ax = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle("v18.2 — indices & incidence: the endogenous energy shock is DEFLATIONARY; "
                 "regressive bite is on QUANTITY (luxury sacrifice), not price", fontsize=11)

    # 1: group price LEVEL index (shock) -- democratic (bottom) vs plutocratic (top).
    # base-1 at genesis; a level index (weighted sector price relatives), not compounded.
    ax[0, 0].plot(yrs, smooth(col(shk, "cpi_bottomq_index")), label="bottom quintile", color="C3")
    ax[0, 0].plot(yrs, smooth(col(shk, "cpi_topq_index")), label="top quintile", color="C0")
    ax[0, 0].axvline(SHOCK_AT / 365, color="k", lw=0.6, ls=":")
    ax[0, 0].set_title("group price level (shock) — bottom/top track (price incidence flat)"); ax[0, 0].legend(fontsize=8)

    # 2: sector output, shock vs base -- luxury collapses, necessity holds
    ax[0, 1].plot(yrs, smooth(col(shk, "necessity_output")), label="necessity (shock)", color="C3")
    ax[0, 1].plot(yrs, smooth(col(shk, "luxury_output")), label="luxury (shock)", color="C0")
    ax[0, 1].plot(yrs, smooth(col(base, "luxury_output")), label="luxury (no shock)", color="C0", ls=":", alpha=0.6)
    ax[0, 1].axvline(SHOCK_AT / 365, color="k", lw=0.6, ls=":")
    ax[0, 1].set_title("sector output — luxury collapses, necessity holds"); ax[0, 1].legend(fontsize=8)

    # 3: necessity share, shock vs base
    ax[0, 2].plot(yrs, smooth(col(shk, "necessity_share")), label="shock", color="C3")
    ax[0, 2].plot(yrs, smooth(col(base, "necessity_share")), label="no shock", color="C0")
    ax[0, 2].axvline(SHOCK_AT / 365, color="k", lw=0.6, ls=":")
    ax[0, 2].set_title("necessity share (rises through the shock)"); ax[0, 2].legend(fontsize=8)

    # 4: energy price (the shock driver)
    ax[1, 0].plot(yrs, smooth(col(shk, "energy_price")), label="shock", color="C3")
    ax[1, 0].plot(yrs, smooth(col(base, "energy_price")), label="no shock", color="C0")
    ax[1, 0].axvline(SHOCK_AT / 365, color="k", lw=0.6, ls=":")
    ax[1, 0].set_title("energy price (shock driver)"); ax[1, 0].legend(fontsize=8)

    # 5: real output, shock vs base
    ax[1, 1].plot(yrs, smooth(col(shk, "real_output")), label="shock", color="C3")
    ax[1, 1].plot(yrs, smooth(col(base, "real_output")), label="no shock", color="C0")
    ax[1, 1].axvline(SHOCK_AT / 365, color="k", lw=0.6, ls=":")
    ax[1, 1].set_title("real output"); ax[1, 1].legend(fontsize=8)

    # 6: destitute share, shock vs base
    ax[1, 2].plot(yrs, smooth(col(shk, "deprivation_destitute_share")), label="shock", color="C3")
    ax[1, 2].plot(yrs, smooth(col(base, "deprivation_destitute_share")), label="no shock", color="C0")
    ax[1, 2].axvline(SHOCK_AT / 365, color="k", lw=0.6, ls=":")
    ax[1, 2].set_title("destitute share (gated)"); ax[1, 2].legend(fontsize=8)

    for a in ax.flat:
        a.set_xlabel("year"); a.grid(alpha=0.25)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT, dpi=110)
    print(f"wrote {OUT}")

    # incidence summary: group price-level rise over the shock year (level ratio, robust)
    def window(recs):
        return [r for r in recs if SHOCK_AT <= r["t"] < SHOCK_AT + 365]
    ws = window(shk)
    bi = col(ws, "cpi_bottomq_index"); ti = col(ws, "cpi_topq_index")
    bot = bi[-1] / bi[0] - 1.0 if len(bi) and bi[0] else 0.0
    top = ti[-1] / ti[0] - 1.0 if len(ti) and ti[0] else 0.0
    print(f"shock-year group inflation (level ratio): bottom {bot:+.3f} vs top {top:+.3f} "
          f"(gap {bot - top:+.3f})")
    n0 = np.mean([r["necessity_output"] for r in window(base)])
    n1 = np.mean([r["necessity_output"] for r in ws])
    l0 = np.mean([r["luxury_output"] for r in window(base)])
    l1 = np.mean([r["luxury_output"] for r in ws])
    print(f"shock-year output vs no-shock: necessity {100*(n1/n0-1):+.1f}%  luxury {100*(l1/l0-1):+.1f}%")


if __name__ == "__main__":
    main()
