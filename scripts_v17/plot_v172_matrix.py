"""v17.2 post-composition stagflation matrix portrait + scorecard. The u panel is now
MEANINGFUL (v16 friction: a natural rate exists); the JG hard test = base vs jg_off.
Run AFTER run_v172_matrix.py finished all cells:
  PYTHONPATH=. uv run python scripts_v17/plot_v172_matrix.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

from macro_sim.visualization.artifacts import load_series_csv   # noqa: E402

BASE = "outputs/visualizations/v172_matrix"
ARMS = [
    ("no shock (ref)", "ref", "0.5"),
    ("default stack", "base", "C0"),
    ("Taylor off", "taylor_off", "C3"),
    ("CB reads core", "core_cb", "C2"),
    ("fiscal flat", "fiscal_flat", "C1"),
    ("JG off", "jg_off", "C4"),
]
DATA = [(label, load_series_csv(f"{BASE}/{cell}/series.csv"), c) for label, cell, c in ARMS]
T0, T1 = 2555, 2555 + 180
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


def panel(ax, key, title, transform=None, hline=None, xlim=(1800, 3650)):
    for label, rec, c in DATA:
        y = col(rec, key)
        if transform is not None:
            y = transform(y, rec)
        ax.plot(col(rec, "t"), y, lw=0.3, color=c, alpha=0.10)
        ax.plot(col(rec, "t"), smooth(y), lw=1.4, color=c, label=label)
    if hline is not None:
        ax.axhline(hline, color="k", lw=0.7, ls=":", alpha=0.6)
    ax.set_xlim(*xlim)
    ax.set_title(title, fontsize=8.5)


fig, axes = plt.subplots(2, 3, figsize=(16, 8))
fig.suptitle("v17.2 POST-COMPOSITION stagflation matrix -- year-7 pulse (-40% kappa, 180d) x the "
             "policy stack; v16 labor live (u is real); frontier, seed 0", fontsize=10.5)

panel(axes[0, 0], "real_output", "real output")
panel(axes[0, 1], "unemployment_rate", "unemployment (natural rate exists now)")
panel(axes[0, 2], "inflation_yoy", "annual inflation: the stagflation test", hline=0.0)
panel(axes[1, 0], "jg_employment_rate", "JG share (the buffer under a supply shock)")
panel(axes[1, 1], "real_wage", "real wage")
panel(axes[1, 2], "energy_price", "energy relative price",
      transform=lambda y, rec: y / np.where(col(rec, "price_index") > 1e-12,
                                            col(rec, "price_index"), np.nan))

for ax in axes.flat:
    ax.axvspan(T0, T1, color="red", alpha=0.07)
    ax.grid(**G)
    ax.tick_params(labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)

fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig("artifacts/diagnostics/diagnostic_v172_matrix.png", dpi=105)
print("wrote artifacts/diagnostics/diagnostic_v172_matrix.png")

# WITHIN-PAIR scorecard: each policy arm vs its OWN no-shock twin (same flags/seed)
PAIRS = [
    ("default stack", "base", "ref"),
    ("Taylor off", "taylor_off", "taylor_off_ref"),
    ("CB reads core", "core_cb", "core_cb_ref"),
    ("fiscal flat", "fiscal_flat", "fiscal_flat_ref"),
    ("JG off", "jg_off", "jg_off_ref"),
]
w = list(range(T0, min(T1 + 365, 3650)))
print("\n== stagflation scorecard (each arm vs ITS OWN no-shock twin, t2555-2920) ==")
for label, cell, refcell in PAIRS:
    rec = load_series_csv(f"{BASE}/{cell}/series.csv")
    ref = load_series_csv(f"{BASE}/{refcell}/series.csv")
    dy = (np.nansum(col(rec, "real_output")[w]) - np.nansum(col(ref, "real_output")[w])) \
        / max(1.0, np.nansum(col(ref, "real_output")[w]))
    du = np.nanmax(smooth(col(rec, "unemployment_rate"))[w]) - \
        np.nanmax(smooth(col(ref, "unemployment_rate"))[w])
    dinfl = np.nanmax(smooth(col(rec, "inflation_yoy"))[w]) - \
        np.nanmax(smooth(col(ref, "inflation_yoy"))[w])
    djg = np.nanmax(smooth(col(rec, "jg_employment_rate"))[w]) - \
        np.nanmax(smooth(col(ref, "jg_employment_rate"))[w])
    print(f"{label:15s} d_output={dy:+.1%}  d_u_peak={du:+.3f}  d_infl_peak={dinfl:+.2f}  d_jg={djg:+.3f}")
