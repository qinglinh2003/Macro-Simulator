"""v18.0 diagnostic: the subsistence basket & deprivation gauges on the frontier.

Runs two worlds itself (self-contained) and renders diagnostic_v180.png:
  * healthy  -- JG + benefits on (the quiet baseline: acute gauge must stay empty);
  * no_net   -- safety net removed (the discriminating counterfactual: the gauge lights
                up, the wealth gradient opens, the domain boundary is breached).

The point of the panel is the CONTRAST: the same instrument reads ~0 acute deprivation
under the healthy baseline and a large, wealth-graded acute stock once the floor is
pulled -- evidence the line is meaningful, not trivially empty.

  PYTHONPATH=. uv run python scripts_v18/plot_v180.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.config import Config       # noqa: E402
from macro_sim.economy import Economy     # noqa: E402

OUT = "outputs/visualizations/v180/diagnostic_v180.png"
N_TICKS = 3650


def run(**extra):
    base = dict(seed=0, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
                demographics_population=500, n_ticks=N_TICKS,
                housing_enabled=True, housing_market_enabled=True,
                energy_enabled=True, energy_household=True,
                deprivation_gauges=True, deprivation_burnin_years=3)
    base.update(extra)
    return Economy(Config.v13(**base)).run()


def col(recs, k):
    return np.array([float(r.get(k) or 0.0) for r in recs], float)


def smooth(y, w=61):
    y = np.asarray(y, float)
    if len(y) < w:
        return y
    half = w // 2
    ypad = np.concatenate([np.full(half, y[0]), y, np.full(half, y[-1])])
    return np.convolve(ypad, np.ones(2 * half + 1) / (2 * half + 1), mode="valid")[:len(y)]


def main():
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    healthy = run()
    no_net = run(benefit_replacement=0.0, jg_wage_ratio=0.0, gov_deficit_target=0.0)
    yrs = col(healthy, "t") / 365.0
    yrs2 = col(no_net, "t") / 365.0

    fig, ax = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle("v18.0 — subsistence basket & deprivation gauges (healthy vs safety-net-off)", fontsize=13)

    # 1: adult coverage
    ax[0, 0].plot(yrs, smooth(col(healthy, "deprivation_coverage_adult")), label="healthy", color="C0")
    ax[0, 0].plot(yrs2, smooth(col(no_net, "deprivation_coverage_adult")), label="no safety net", color="C3")
    ax[0, 0].axhline(1.0, color="k", lw=0.8, ls="--", label="subsistence line")
    ax[0, 0].set_title("adult household coverage"); ax[0, 0].set_ylabel("coverage (×basket)"); ax[0, 0].legend(fontsize=8)

    # 2: below-line shares (no_net)
    ax[0, 1].plot(yrs2, smooth(col(no_net, "deprivation_below100_share")), label="<100%", color="C1")
    ax[0, 1].plot(yrs2, smooth(col(no_net, "deprivation_below60_share")), label="<60%", color="C3")
    ax[0, 1].plot(yrs2, smooth(col(no_net, "deprivation_below30_share")), label="<30%", color="k")
    ax[0, 1].set_title("deprivation share of persons (no safety net)"); ax[0, 1].legend(fontsize=8)

    # 3: acute stock -- the domain boundary
    ax[0, 2].plot(yrs, col(healthy, "deprivation_acute_stock"), label="healthy", color="C0")
    ax[0, 2].plot(yrs2, col(no_net, "deprivation_acute_stock"), label="no safety net", color="C3")
    ax[0, 2].set_title("acute stock (sub-30% > acute_days) — DOMAIN BOUNDARY"); ax[0, 2].legend(fontsize=8)

    # 4: age gradient (no_net)
    ax[1, 0].plot(yrs2, smooth(col(no_net, "deprivation_coverage_child")), label="child", color="C2")
    ax[1, 0].plot(yrs2, smooth(col(no_net, "deprivation_coverage_adult")), label="adult", color="C0")
    ax[1, 0].plot(yrs2, smooth(col(no_net, "deprivation_coverage_elder")), label="elder", color="C4")
    ax[1, 0].axhline(1.0, color="k", lw=0.8, ls="--")
    ax[1, 0].set_title("coverage by age band (no safety net)"); ax[1, 0].legend(fontsize=8)

    # 5: wealth gradient (no_net)
    ax[1, 1].plot(yrs2, smooth(col(no_net, "deprivation_below100_share_bottomq")), label="bottom wealth Q", color="C3")
    ax[1, 1].plot(yrs2, smooth(col(no_net, "deprivation_below100_share_topq")), label="top wealth Q", color="C0")
    ax[1, 1].set_title("below-line share by wealth quintile (no safety net)"); ax[1, 1].legend(fontsize=8)

    # 6: healthy baseline -- raw flow share vs resource-GATED destitute share. The gate
    # separates the year-8.5 bank-shakeout liquidity artifact (raw flow spike, wealthy
    # frozen households) from the genuine recession destitution core (gated) that
    # coincides with the u spike.
    ax[1, 2].plot(yrs, smooth(col(healthy, "deprivation_below30_share")), label="<30% (raw flow)", color="C1")
    ax[1, 2].plot(yrs, smooth(col(healthy, "deprivation_destitute_share")), label="destitute (gated)", color="k")
    axu = ax[1, 2].twinx()
    uh = col(healthy, "person_unemployment_rate")
    axu.plot(yrs, smooth(uh), label="u (rhs)", color="C7", lw=0.8, ls=":")
    axu.set_ylabel("unemployment", fontsize=8)
    ax[1, 2].set_title("HEALTHY baseline: raw flow vs gated destitute (+u)"); ax[1, 2].legend(fontsize=8, loc="upper left")

    for a in ax.flat:
        a.set_xlabel("year"); a.grid(alpha=0.25)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT, dpi=110)
    print(f"wrote {OUT}")
    # console summary
    hn = [r for r in healthy if r.get("deprivation_active", 0) >= 1]
    nn = [r for r in no_net if r.get("deprivation_active", 0) >= 1]
    print(f"healthy: max acute stock={max(r['deprivation_acute_stock'] for r in hn):.0f}, "
          f"boundary breached={any(r['deprivation_boundary']>=1 for r in hn)}")
    print(f"no_net:  max acute stock={max(r['deprivation_acute_stock'] for r in nn):.0f}, "
          f"boundary breached={any(r['deprivation_boundary']>=1 for r in nn)}")


if __name__ == "__main__":
    main()
