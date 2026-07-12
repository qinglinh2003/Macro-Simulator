"""v17.0 diagnostic: the frontier world (v13 daily + demographics + housing) with the
E-sector, energy-on vs energy-off paired 10y runs. Pure observation. Panels follow the
three standing watches (FLOW / BULLWHIP / MARKUP DISCIPLINE) + the strangle test.
Run AFTER scripts_v17/run_v170_frontier.py:
  PYTHONPATH=. uv run python scripts_v17/plot_v170.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.visualization.artifacts import load_series_csv   # noqa: E402

ON = load_series_csv("outputs/visualizations/v170_frontier/energy_on/series.csv")
OFF = load_series_csv("outputs/visualizations/v170_frontier/energy_off/series.csv")
COVER_TARGET = 30.0
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


t_on = col(ON, "t")
t_off = col(OFF, "t")

fig, axes = plt.subplots(4, 3, figsize=(16, 13))
fig.suptitle("v17.0 energy diagnostic -- frontier world (v13 daily + housing), 10y, seed 0",
             fontsize=11)

ax = axes[0, 0]
draw(ax, t_on, col(ON, "real_output"), "C0", "energy ON")
draw(ax, t_off, col(OFF, "real_output"), "C1", "energy OFF")
ax.set_title("real output: the strangle test", fontsize=8.5)

ax = axes[0, 1]
draw(ax, t_on, col(ON, "price_index"), "C0", "CPI on")
draw(ax, t_off, col(OFF, "price_index"), "C1", "CPI off")
draw(ax, t_on, col(ON, "energy_price"), "C2", "energy price")
ax.set_title("price levels", fontsize=8.5)

ax = axes[0, 2]
pi = col(ON, "price_index")
draw(ax, t_on, col(ON, "energy_price") / np.where(pi > 1e-12, pi, np.nan), "C3", "p_E / CPI")
ax.set_title("energy RELATIVE price", fontsize=8.5)

ax = axes[1, 0]
draw(ax, t_on, col(ON, "energy_coverage_mean"), "C0", "aggregate")
draw(ax, t_on, col(ON, "energy_coverage_min"), "C4", "worst active firm")
ax.axhline(COVER_TARGET, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("input-stock coverage (ticks; target 30) -- BULLWHIP watch", fontsize=8.5)

ax = axes[1, 1]
draw(ax, t_on, col(ON, "e_capacity_utilization"), "C0", "utilization")
draw(ax, t_on, col(ON, "e_markup_at_cap_share"), "C3", "markup-at-cap share")
ax.axhline(1.0, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("capacity utilization + MARKUP DISCIPLINE watch", fontsize=8.5)

ax = axes[1, 2]
draw(ax, t_on, col(ON, "energy_cost_share"), "C0", "energy cost share")
ax.axhline(0.05, color="k", lw=0.7, ls=":", alpha=0.5)
ax.axhline(0.08, color="k", lw=0.7, ls=":", alpha=0.5)
ax.set_title("energy cost share of variable cost (anchor 5-8%)", fontsize=8.5)

ax = axes[2, 0]
draw(ax, t_on, col(ON, "energy_sold"), "C0", "sold")
draw(ax, t_on, col(ON, "energy_used"), "C1", "used")
draw(ax, t_on, col(ON, "energy_unfilled"), "C3", "unfilled")
ax.set_title("energy market: sold / used / unfilled", fontsize=8.5)

ax = axes[2, 1]
draw(ax, t_on, col(ON, "energy_restock_share"), "C0", "restock share of purchases")
ax.set_title("restock share -- BULLWHIP watch", fontsize=8.5)

ax = axes[2, 2]
ax.plot(t_on, col(ON, "energy_flow_gap"), lw=0.5, color="C0")
ax.set_title("flow soft gauge (produced - used - dStocks; ~0)", fontsize=8.5)

ax = axes[3, 0]
draw(ax, t_on, col(ON, "e_hhi"), "C0", "E-sector HHI")
ax.axhline(0.25, color="k", lw=0.7, ls=":", alpha=0.6)
ax.set_title("E-sector concentration (floor 1/4 = 0.25)", fontsize=8.5)

ax = axes[3, 1]
draw(ax, t_on, col(ON, "unemployment_rate"), "C0", "u on")
draw(ax, t_off, col(OFF, "unemployment_rate"), "C1", "u off")
draw(ax, t_on, col(ON, "jg_employment_rate"), "C2", "JG share on")
ax.set_title("unemployment", fontsize=8.5)

ax = axes[3, 2]
draw(ax, t_on, col(ON, "inflation_yoy"), "C0", "infl yoy on")
draw(ax, t_off, col(OFF, "inflation_yoy"), "C1", "infl yoy off")
ax.axhline(0.0, color="k", lw=0.7, ls="--", alpha=0.5)
ax.set_title("annual inflation", fontsize=8.5)

for ax in axes.flat:
    ax.grid(**G)
    ax.tick_params(labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)

fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig("artifacts/diagnostics/diagnostic_v170.png", dpi=105)
print("wrote artifacts/diagnostics/diagnostic_v170.png")
