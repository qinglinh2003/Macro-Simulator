"""v17.1 diagnostic: household energy demand on the frontier — headline vs core CPI,
the household budget share and its poverty gradient, fill vs need, plus the 17.0
watches for continuity. Twin = the 17.0 energy_on run (household off).
Run AFTER `run_v170_frontier.py household`:
  PYTHONPATH=. uv run python scripts_v17/plot_v171.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.visualization.artifacts import load_series_csv   # noqa: E402

HH = load_series_csv("outputs/visualizations/v170_frontier/energy_hh/series.csv")
E0 = load_series_csv("outputs/visualizations/v170_frontier/energy_on/series.csv")
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


t = col(HH, "t")
t0 = col(E0, "t")

fig, axes = plt.subplots(3, 3, figsize=(16, 10))
fig.suptitle("v17.1 household energy diagnostic -- frontier world, 10y, seed 0 "
             "(twin: 17.0 energy-on / household-off)", fontsize=11)

ax = axes[0, 0]
draw(ax, t, col(HH, "cpi_headline"), "C0", "headline (incl. energy)")
draw(ax, t, col(HH, "price_index"), "C1", "core (c-goods)")
ax.set_title("headline vs core CPI", fontsize=8.5)

ax = axes[0, 1]
draw(ax, t, col(HH, "headline_inflation") * 365, "C0", "headline (ann.)")
draw(ax, t, col(HH, "inflation") * 365, "C1", "core (ann.)")
ax.axhline(0, color="k", lw=0.7, ls="--", alpha=0.5)
ax.set_title("per-tick inflation x365 (CB reads headline by default)", fontsize=8.5)

ax = axes[0, 2]
draw(ax, t, col(HH, "energy_hh_share_mean"), "C0", "mean")
draw(ax, t, col(HH, "energy_share_q1"), "C3", "poorest quintile")
draw(ax, t, col(HH, "energy_share_q5"), "C2", "richest quintile")
ax.axhline(0.10, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("household energy budget share (fuel-poverty line 10%)", fontsize=8.5)

ax = axes[1, 0]
draw(ax, t, col(HH, "fuel_poverty_share"), "C3", "share of households > 10%")
ax.set_title("fuel poverty", fontsize=8.5)

ax = axes[1, 1]
need = col(HH, "energy_hh_units") * 0 + np.nanmax(col(HH, "energy_hh_units"))  # visual ref only
draw(ax, t, col(HH, "energy_hh_units"), "C0", "household units bought")
ax.set_title("household energy fill (fixed real need; gaps = rationing)", fontsize=8.5)

ax = axes[1, 2]
draw(ax, t, col(HH, "energy_hh_spend"), "C0", "household energy spend")
draw(ax, t, col(HH, "tax_energy"), "C2", "excise remitted")
ax.set_title("household energy outlay (consumption GDP component)", fontsize=8.5)

ax = axes[2, 0]
draw(ax, t, col(HH, "real_output"), "C0", "hh-energy world")
draw(ax, t0, col(E0, "real_output"), "C1", "17.0 twin")
ax.set_title("real output vs the 17.0 twin (composition shift only)", fontsize=8.5)

ax = axes[2, 1]
draw(ax, t, col(HH, "e_capacity_utilization"), "C0", "utilization")
draw(ax, t, col(HH, "e_markup_at_cap_share"), "C3", "markup-at-cap share")
ax.set_title("17.0 watches carried: capacity + markup discipline", fontsize=8.5)

ax = axes[2, 2]
draw(ax, t, col(HH, "energy_coverage_mean"), "C0", "aggregate coverage")
ax.axhline(30, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("17.0 watches carried: input-stock coverage", fontsize=8.5)

for ax in axes.flat:
    ax.grid(**G)
    ax.tick_params(labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)

fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig("artifacts/diagnostics/diagnostic_v171.png", dpi=105)
print("wrote artifacts/diagnostics/diagnostic_v171.png")
