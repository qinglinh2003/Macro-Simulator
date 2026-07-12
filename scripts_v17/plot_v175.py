"""v17.5 diagnostic: the social-protection couplings — fuel poverty feeds a mortality
multiplier (Phase-2 grammar) and a TARGETED energy subsidy arms at the shock (§34
reprise). Twin = the bare shock run (no channel, no subsidy).
Run AFTER `run_v170_frontier.py social`:
  PYTHONPATH=. uv run python scripts_v17/plot_v175.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.visualization.artifacts import load_series_csv   # noqa: E402

SO = load_series_csv("outputs/visualizations/v170_frontier/energy_social/series.csv")
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


t = col(SO, "t")
tw = col(TW, "t")

fig, axes = plt.subplots(2, 3, figsize=(16, 7.5))
fig.suptitle("v17.5 social-protection diagnostic -- fuel poverty -> mortality (gamma=2) + "
             "TARGETED subsidy at the shock (lifted after 1y); frontier world, seed 0", fontsize=11)

ax = axes[0, 0]
draw(ax, t, col(SO, "fuel_poverty_share"), "C0", "protected world")
draw(ax, tw, col(TW, "fuel_poverty_share"), "C3", "bare shock twin")
ax.set_title("fuel poverty (share of households > 10%)", fontsize=8.5)

ax = axes[0, 1]
draw(ax, t, col(SO, "energy_mortality_mult"), "C3", "mortality multiplier")
ax.axhline(1.0, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("the cold-home mortality channel (annual, burn-in discarded)", fontsize=8.5)

ax = axes[0, 2]
draw(ax, t, col(SO, "energy_subsidy_paid"), "C2", "targeted subsidy paid")
ax.set_title("fiscal outlay (armed at the shock, lifted after 1y)", fontsize=8.5)

ax = axes[1, 0]
draw(ax, t, col(SO, "energy_share_q1"), "C0", "protected")
draw(ax, tw, col(TW, "energy_share_q1"), "C3", "bare twin")
ax.axhline(0.10, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("poorest-quintile energy burden", fontsize=8.5)

ax = axes[1, 1]
draw(ax, t, col(SO, "energy_hh_units"), "C0", "protected")
draw(ax, tw, col(TW, "energy_hh_units"), "C3", "bare twin")
ax.set_title("household energy fill", fontsize=8.5)

ax = axes[1, 2]
draw(ax, t, col(SO, "real_output"), "C0", "protected")
draw(ax, tw, col(TW, "real_output"), "C3", "bare twin")
ax.set_title("real output (protection is not free lunch nor drag?)", fontsize=8.5)

for ax in axes.flat:
    ax.axvspan(T0, T1, color="red", alpha=0.08)
    ax.grid(**G)
    ax.tick_params(labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)

fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig("artifacts/diagnostics/diagnostic_v175.png", dpi=105)
print("wrote artifacts/diagnostics/diagnostic_v175.png")
