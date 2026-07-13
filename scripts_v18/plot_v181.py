"""v18.1 diagnostic: the necessity/luxury sector split on the frontier.

Self-contained. Renders artifacts/diagnostics/diagnostic_v181.png:
  * necessity share over the run (100% in the genesis slump -> ~25-30% mature: Engel
    over development);
  * the Engel gradient (necessity share of the bottom vs top per-need-unit expenditure
    quintile) -- the cross-sectional Engel curve, emergent;
  * sector price indices P_N / P_L;
  * sector markups + time-at-ceiling (the markup watch: must stay off mu_max);
  * sector firm counts (entry routing + the oscillation watch);
  * a quiet-baseline check: aggregate real output / consumption stays smooth.

  PYTHONPATH=. uv run python scripts_v18/plot_v181.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.config import Config       # noqa: E402
from macro_sim.economy import Economy     # noqa: E402

OUT = "artifacts/diagnostics/diagnostic_v181.png"


def run():
    cfg = Config.v13(seed=0, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
                     demographics_population=500, n_ticks=3650,
                     housing_enabled=True, housing_market_enabled=True,
                     energy_enabled=True, energy_household=True,
                     consumption_strata=True)
    return Economy(cfg).run()


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
    recs = run()
    yrs = col(recs, "t") / 365.0

    fig, ax = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle("v18.1 — necessity / luxury split (Engel's law, sector prices & markups)", fontsize=13)

    ax[0, 0].plot(yrs, smooth(col(recs, "necessity_share")), color="C0")
    ax[0, 0].set_title("aggregate necessity share (Engel over development)")
    ax[0, 0].set_ylabel("necessity / goods consumption"); ax[0, 0].set_ylim(0, 1.05)

    ax[0, 1].plot(yrs, smooth(col(recs, "necessity_share_bottomq")), label="bottom expend./need-unit Q", color="C3")
    ax[0, 1].plot(yrs, smooth(col(recs, "necessity_share_topq")), label="top expend./need-unit Q", color="C0")
    ax[0, 1].set_title("Engel gradient (cross-section) — bottom > top"); ax[0, 1].legend(fontsize=8)

    ax[0, 2].plot(yrs, smooth(col(recs, "necessity_price_index")), label="P_N", color="C3")
    ax[0, 2].plot(yrs, smooth(col(recs, "luxury_price_index")), label="P_L", color="C0")
    ax[0, 2].set_title("sector price indices"); ax[0, 2].legend(fontsize=8)

    ax[1, 0].plot(yrs, smooth(col(recs, "necessity_markup")), label="necessity", color="C3")
    ax[1, 0].plot(yrs, smooth(col(recs, "luxury_markup")), label="luxury", color="C0")
    ax[1, 0].set_title("sector mean markup (watch: off the ceiling)"); ax[1, 0].legend(fontsize=8)

    ax[1, 1].plot(yrs, smooth(col(recs, "necessity_markup_at_cap")), label="necessity", color="C3")
    ax[1, 1].plot(yrs, smooth(col(recs, "luxury_markup_at_cap")), label="luxury", color="C0")
    ax[1, 1].set_title("share of firms at mu_max (must stay low)"); ax[1, 1].set_ylim(-0.02, 1.02); ax[1, 1].legend(fontsize=8)

    ax[1, 2].plot(yrs, col(recs, "n_firms_necessity"), label="necessity", color="C3")
    ax[1, 2].plot(yrs, col(recs, "n_firms_luxury"), label="luxury", color="C0")
    ax[1, 2].set_title("sector firm counts (entry routing / oscillation watch)"); ax[1, 2].legend(fontsize=8)

    for a in ax.flat:
        a.set_xlabel("year"); a.grid(alpha=0.25)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT, dpi=110)
    print(f"wrote {OUT}")
    mature = [r for r in recs[-730:] if r.get("necessity_share") is not None]
    ns = np.mean([r["necessity_share"] for r in mature])
    bq = np.mean([r["necessity_share_bottomq"] for r in mature])
    tq = np.mean([r["necessity_share_topq"] for r in mature])
    print(f"mature necessity share {ns:.3f}; Engel gradient {bq:.3f}/{tq:.3f} = {bq/max(1e-9,tq):.2f}x")
    print(f"necessity firms {mature[-1]['n_firms_necessity']:.0f} / luxury {mature[-1]['n_firms_luxury']:.0f}")


if __name__ == "__main__":
    main()
