"""diagnostic_v212.png — the impossible trinity (PLAN_v21 §3).

A pegged economy with an open capital account. Left: an INDEPENDENT (low) policy rate ⇒
reserves drain ⇒ the peg breaks ⇒ the currency devalues (a currency crisis). Right: MATCHING
the anchor rate ⇒ reserves stable ⇒ the peg holds — at the cost of zero monetary autonomy.

    PYTHONPATH=$(pwd) uv run python scripts_v20/plot_v212.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from macro_sim.config import Config  # noqa: E402
from macro_sim.world import World  # noqa: E402


def _run(r_peg):
    peg0 = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=r_peg)
    anc = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=0.05)
    w = World([peg0, anc], base_seed=9, trade=True, capital=True, capital_mobility=3.0,
              capital_adjust=0.2, peg=True, peg_reserves0=5000.0, peg_reserve_scale=0.02)
    w.run()
    return w.world_records


def main() -> None:
    indep = _run(0.02)   # independent low rate ⇒ crisis
    match = _run(0.05)   # matched ⇒ sustainable

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for col, (recs, title) in enumerate([(indep, "independent rate (0.02 vs 0.05)"),
                                         (match, "matched rate (0.05 = anchor)")]):
        t = [r["t"] for r in recs]
        broke = next((r["t"] for r in recs if not r["peg_intact"]), None)
        axes[0][col].plot(t, [r["reserves"] for r in recs], color="C3", lw=1.3)
        axes[0][col].set_title(f"FX reserves — {title}")
        axes[1][col].plot(t, [r["e"][0] for r in recs], color="C0", lw=1.3, label="pegged e0")
        axes[1][col].set_title("exchange rate (pegged economy)")
        if broke is not None:
            for ax in (axes[0][col], axes[1][col]):
                ax.axvline(broke, color="k", ls="--", lw=0.8)
            axes[1][col].annotate("peg breaks →\ndevaluation", xy=(broke, 1.0),
                                  xytext=(broke * 0.5, 1.1), fontsize=8,
                                  arrowprops=dict(arrowstyle="->", lw=0.6))
        for ax in (axes[0][col], axes[1][col]):
            ax.grid(alpha=0.3)
    fig.suptitle("v21.2 — the impossible trinity: peg + open capital ⇒ independent policy is unsustainable", fontsize=12)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v212.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
