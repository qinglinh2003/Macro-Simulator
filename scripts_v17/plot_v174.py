"""v17.4 diagnostic — THE 2022 POLICY MENU, four arms through the same year-5 pulse:
no intervention / SPR release / cap+compensation+household-first (lifted after 1y) /
SOE at-cost. The arc's headline artifact (PLAN 17.4). Run AFTER the four frontier runs:
  PYTHONPATH=. uv run python scripts_v17/plot_v174.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.visualization.artifacts import load_series_csv   # noqa: E402

BASE = "outputs/visualizations/v170_frontier"
ARMS = [
    ("no intervention", "energy_shock", "C3"),
    ("SPR release", "energy_spr", "C2"),
    ("cap+comp+hh-first", "energy_captriple", "C0"),
    ("SOE at-cost", "energy_soe", "C4"),
]
DATA = [(label, load_series_csv(f"{BASE}/{run}/series.csv"), c) for label, run, c in ARMS]
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


def panel(ax, key, title, transform=None, hline=None):
    for label, rec, c in DATA:
        y = col(rec, key)
        if transform is not None:
            y = transform(y, rec)
        ax.plot(col(rec, "t"), y, lw=0.35, color=c, alpha=0.12)
        ax.plot(col(rec, "t"), smooth(y), lw=1.4, color=c, label=label)
    if hline is not None:
        ax.axhline(hline, color="k", lw=0.7, ls=":", alpha=0.6)
    ax.set_title(title, fontsize=8.5)


fig, axes = plt.subplots(3, 3, figsize=(16, 10))
fig.suptitle("v17.4 -- the 2022 policy menu: four arms, one year-5 pulse (-40% kappa, 180d); "
             "frontier world, seed 0", fontsize=11)

panel(axes[0, 0], "real_output", "real output")
panel(axes[0, 1], "energy_price", "energy relative price",
      transform=lambda y, rec: y / np.where(col(rec, "price_index") > 1e-12,
                                            col(rec, "price_index"), np.nan))
panel(axes[0, 2], "inflation_yoy", "annual inflation", hline=0.0)
panel(axes[1, 0], "energy_unfilled", "unmet energy demand")
panel(axes[1, 1], "energy_hh_units", "household energy fill (who is protected)")
panel(axes[1, 2], "energy_share_q1", "poorest-quintile energy burden", hline=0.10)
panel(axes[2, 0], "energy_used", "industry energy use (who is curtailed)")
panel(axes[2, 1], "energy_cap_compensation", "fiscal compensation paid (cap arm)")
panel(axes[2, 2], "spr_flow", "SPR flow / soe dividends",
      transform=lambda y, rec: y + col(rec, "soe_dividends"))

for ax in axes.flat:
    ax.axvspan(T0, T1, color="red", alpha=0.07)
    ax.grid(**G)
    ax.tick_params(labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)

fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig("artifacts/diagnostics/diagnostic_v174.png", dpi=105)
print("wrote artifacts/diagnostics/diagnostic_v174.png")

# scorecard for the results note
w = range(T0, T1 + 180)
print("\n== scorecard (shock window + aftermath, t1825-2185) ==")
for label, rec, _ in DATA:
    ry = np.nansum(col(rec, "real_output")[list(w)])
    unf = np.nansum(col(rec, "energy_unfilled")[list(w)])
    hh = np.nansum(col(rec, "energy_hh_units")[list(w)])
    comp = np.nansum(col(rec, "energy_cap_compensation")[list(w)])
    print(f"{label:20s} output={ry/1e3:8.0f}k unfilled={unf:8.0f} hh_fill={hh:8.0f} fiscal_comp={comp:7.0f}")
