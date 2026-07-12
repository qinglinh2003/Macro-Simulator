"""v17.2 diagnostic: the capacity-shock scenario on the frontier — a year-5 pulse
(-40% kappa, 180 days, windfall surtax live) vs the no-shock 17.1 twin. The stagflation
EXPERIMENT MATRIX runs post-composition (protocol §5); this is the machinery portrait.
Run AFTER `run_v170_frontier.py shock`:
  PYTHONPATH=. uv run python scripts_v17/plot_v172.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.visualization.artifacts import load_series_csv   # noqa: E402

SH = load_series_csv("outputs/visualizations/v170_frontier/energy_shock/series.csv")
TW = load_series_csv("outputs/visualizations/v170_frontier/energy_hh/series.csv")
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


def shade(ax):
    ax.axvspan(T0, T1, color="red", alpha=0.08)


t = col(SH, "t")
tw = col(TW, "t")

fig, axes = plt.subplots(3, 3, figsize=(16, 10))
fig.suptitle("v17.2 capacity-shock diagnostic -- year-5 pulse (-40% kappa, 180d, windfall 0.3) "
             "vs the no-shock twin; frontier world, seed 0", fontsize=11)

ax = axes[0, 0]
draw(ax, t, col(SH, "real_output"), "C3", "shock")
draw(ax, tw, col(TW, "real_output"), "C0", "no-shock twin")
ax.set_title("real output through the pulse", fontsize=8.5)

ax = axes[0, 1]
pi = col(SH, "price_index")
draw(ax, t, col(SH, "energy_price") / np.where(pi > 1e-12, pi, np.nan), "C3", "shock")
pit = col(TW, "price_index")
draw(ax, tw, col(TW, "energy_price") / np.where(pit > 1e-12, pit, np.nan), "C0", "twin")
ax.set_title("energy RELATIVE price", fontsize=8.5)

ax = axes[0, 2]
draw(ax, t, col(SH, "inflation_yoy"), "C3", "shock (headline-fed CB)")
draw(ax, tw, col(TW, "inflation_yoy"), "C0", "twin")
ax.axhline(0, color="k", lw=0.7, ls="--", alpha=0.5)
ax.set_title("annual inflation: the cost-push signature", fontsize=8.5)

ax = axes[1, 0]
draw(ax, t, col(SH, "e_capacity_utilization"), "C3", "utilization")
draw(ax, t, col(SH, "energy_shock_active"), "C1", "shock window")
ax.set_title("capacity utilization + the shock window", fontsize=8.5)

ax = axes[1, 1]
draw(ax, t, col(SH, "energy_coverage_mean"), "C3", "shock")
draw(ax, tw, col(TW, "energy_coverage_mean"), "C0", "twin")
ax.axhline(30, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("input-stock coverage: the BUFFER absorbing the pulse", fontsize=8.5)

ax = axes[1, 2]
draw(ax, t, col(SH, "energy_unfilled"), "C3", "unfilled")
draw(ax, t, col(SH, "energy_sold"), "C0", "sold")
ax.set_title("rationing during the pulse", fontsize=8.5)

ax = axes[2, 0]
draw(ax, t, col(SH, "energy_hh_units"), "C3", "household fill (shock)")
draw(ax, tw, col(TW, "energy_hh_units"), "C0", "twin")
ax.set_title("household energy fill: who eats the shortage", fontsize=8.5)

ax = axes[2, 1]
draw(ax, t, col(SH, "energy_share_q1"), "C3", "poorest quintile share")
draw(ax, t, col(SH, "energy_share_q5"), "C2", "richest quintile share")
ax.axhline(0.10, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("distributional bite through the pulse", fontsize=8.5)

ax = axes[2, 2]
draw(ax, t, col(SH, "tax_energy_windfall"), "C2", "windfall remitted")
ax.set_title("windfall surtax (shock-response fiscal instrument)", fontsize=8.5)

for ax in axes.flat:
    shade(ax)
    ax.grid(**G)
    ax.tick_params(labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)

fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig("artifacts/diagnostics/diagnostic_v172.png", dpi=105)
print("wrote artifacts/diagnostics/diagnostic_v172.png")
