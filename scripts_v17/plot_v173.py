"""v17.3 diagnostic: the strategic reserve through the same year-5 pulse — SPR built
over years 1-5 (target 3000, flow 20/tick), RELEASED at the shock (Policy target -> 0);
twin = the 17.2 shock run (no SPR). Run AFTER `run_v170_frontier.py spr`:
  PYTHONPATH=. uv run python scripts_v17/plot_v173.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.visualization.artifacts import load_series_csv   # noqa: E402

SP = load_series_csv("outputs/visualizations/v170_frontier/energy_spr/series.csv")
TW = load_series_csv("outputs/visualizations/v170_frontier/energy_shock/series.csv")
T0, T1 = 1825, 1825 + 180
G = dict(alpha=0.25, lw=0.6)
SMOOTH_W = 61


def col(rec, k):
    return np.array([float(r.get(k) or 0.0) if r.get(k) not in (None, "") else np.nan
                     for r in rec], float)


def smooth(y, w=SMOOTH_W):
    y = np.asarray(y, float)
    if np.isnan(y).any():
        idx = np.where(~np.isnan(y))[0]
        if len(idx) == 0:
            return y
        y = np.interp(np.arange(len(y)), idx, y[idx])
    if len(y) < w or w < 3:
        return y
    half = (w if w % 2 else w + 1) // 2
    ypad = np.concatenate([np.full(half, y[0]), y, np.full(half, y[-1])])
    return np.convolve(ypad, np.ones(2 * half + 1) / (2 * half + 1), mode="valid")


def draw(ax, x, y, color, label, lw=1.5):
    ax.plot(x, y, lw=0.4, color=color, alpha=0.15)
    ax.plot(x, smooth(y), lw=lw, color=color, label=label)


t = col(SP, "t")
tw = col(TW, "t")

fig, axes = plt.subplots(2, 3, figsize=(16, 7.5))
fig.suptitle("v17.3 SPR diagnostic -- build years 1-5, RELEASE at the year-5 pulse "
             "(twin: same shock, no SPR); frontier world, seed 0", fontsize=11)

ax = axes[0, 0]
draw(ax, t, col(SP, "spr_stock"), "C2", "SPR stock")
ax.set_title("the reserve: build -> hold -> release", fontsize=8.5)

ax = axes[0, 1]
draw(ax, t, col(SP, "energy_unfilled"), "C2", "with SPR release")
draw(ax, tw, col(TW, "energy_unfilled"), "C3", "no SPR (twin)")
ax.set_title("unmet energy demand through the crunch", fontsize=8.5)

ax = axes[0, 2]
pi = col(SP, "price_index")
draw(ax, t, col(SP, "energy_price") / np.where(pi > 1e-12, pi, np.nan), "C2", "with SPR")
pit = col(TW, "price_index")
draw(ax, tw, col(TW, "energy_price") / np.where(pit > 1e-12, pit, np.nan), "C3", "no SPR")
ax.set_title("energy relative price", fontsize=8.5)

ax = axes[1, 0]
draw(ax, t, col(SP, "real_output"), "C2", "with SPR")
draw(ax, tw, col(TW, "real_output"), "C3", "no SPR")
ax.set_title("real output through the pulse", fontsize=8.5)

ax = axes[1, 1]
draw(ax, t, col(SP, "energy_hh_units"), "C2", "with SPR")
draw(ax, tw, col(TW, "energy_hh_units"), "C3", "no SPR")
ax.set_title("household energy fill", fontsize=8.5)

ax = axes[1, 2]
draw(ax, t, col(SP, "spr_flow"), "C2", "SPR flow (+build/-release)")
ax.axhline(0, color="k", lw=0.7, ls="--", alpha=0.5)
ax.set_title("SPR market flow", fontsize=8.5)

for ax in axes.flat:
    ax.axvspan(T0, T1, color="red", alpha=0.08)
    ax.grid(**G)
    ax.tick_params(labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)

fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig("artifacts/diagnostics/diagnostic_v173.png", dpi=105)
print("wrote artifacts/diagnostics/diagnostic_v173.png")
