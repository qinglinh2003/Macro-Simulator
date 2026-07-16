#!/usr/bin/env python3
"""30-year narrative analysis of the prod6 portrait: decade tables + 3 figure panels.

Reads the per-economy CSVs + world_series.csv of one (or more) seed dirs and emits
markdown tables (stdout) + PNG figure panels (figs/ inside the first seed dir's parent).
stdlib csv + numpy + matplotlib only.
"""
import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NAMES = ["China", "India", "USA", "Germany", "Gulf", "Hub"]
COLORS = ["#d62728", "#ff7f0e", "#1f77b4", "#2ca02c", "#8c564b", "#9467bd"]

ECON_COLS = ["real_gdp", "nominal_gdp", "gdp_deflator", "cpi_fixed_basket", "cpi_headline",
             "person_unemployment_rate", "policy_rate", "avg_wage", "adult_population",
             "child_population", "consumption_gini", "aggregate_capital",
             "births_tick", "deaths_tick", "tfp_index_c"]
WORLD_BASES = ["e", "augmented_nfa", "current_account", "remittances", "factor_income",
               "import_value", "migrant_stock"]


def read_cols(path, wanted):
    """Return {col: np.array} for the wanted columns of a wide CSV (row-streamed)."""
    with open(path, newline="") as fh:
        r = csv.reader(fh)
        header = next(r)
        idx = {c: header.index(c) for c in wanted if c in header}
        out = {c: [] for c in idx}
        for row in r:
            for c, i in idx.items():
                v = row[i]
                try:
                    out[c].append(float(v))
                except ValueError:
                    out[c].append(np.nan)
    return {c: np.asarray(v) for c, v in out.items()}


def ma(x, w=365):
    if len(x) < w:
        return x
    k = np.ones(w) / w
    y = np.convolve(x, k, mode="valid")
    return np.concatenate([np.full(w - 1, np.nan), y])


def cagr(series, t0, t1):
    a, b = series[t0], series[t1 - 1]
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0 or b <= 0:
        return np.nan
    years = (t1 - t0) / 365.0
    return (b / a) ** (1.0 / years) - 1.0


def main():
    seed_dir = Path(sys.argv[1])
    econ = []
    for i in range(6):
        econ.append(read_cols(seed_dir / f"economy_{i}.csv", ECON_COLS))
        print(f"loaded economy_{i}", file=sys.stderr)
    wanted_world = [f"{b}_{i}" for b in WORLD_BASES for i in range(6)] + ["peg_intact"]
    world = read_cols(seed_dir / "world_series.csv", wanted_world)
    print("loaded world", file=sys.stderr)

    T = len(econ[0]["real_gdp"])
    yrs = np.arange(T) / 365.0
    D = [(0, T // 3), (T // 3, 2 * T // 3), (2 * T // 3, T)]  # three decades

    # ---------------- tables ----------------
    def table(title, header, rows):
        print(f"\n#### {title}\n")
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))
        for r in rows:
            print("| " + " | ".join(r) + " |")

    # 1. growth by decade
    rows = []
    for i, nm in enumerate(NAMES):
        g = econ[i]["real_gdp"]
        gm = ma(g)
        cs = [cagr(gm, max(a, 365), b) for a, b in D]
        rows.append([nm] + [f"{100*c:+.1f}%" if np.isfinite(c) else "--" for c in cs]
                    + [f"{np.nanmean(g[-365:]):.0f}"])
    table("实际 GDP 年化增速(按十年)", ["economy", "Y1-10", "Y11-20", "Y21-30", "末期水平"], rows)

    # 2. inflation by decade (fixed basket)
    rows = []
    for i, nm in enumerate(NAMES):
        p = econ[i]["cpi_fixed_basket"]
        cs = [cagr(p, a, b) for a, b in D]
        rows.append([nm] + [f"{100*c:+.1f}%" if np.isfinite(c) else "--" for c in cs]
                    + [f"{p[-1]:.2f}"])
    table("CPI(固定篮)年化通胀(按十年)", ["economy", "Y1-10", "Y11-20", "Y21-30", "末期指数"], rows)

    # 3. unemployment + policy rate by decade
    rows = []
    for i, nm in enumerate(NAMES):
        u = econ[i]["person_unemployment_rate"]
        r_ = econ[i]["policy_rate"]
        us = [f"{100*np.nanmean(u[a:b]):.1f}%" for a, b in D]
        zlb = 100 * np.nanmean(r_ < 1e-9)
        first0 = np.argmax(np.convolve((r_ < 1e-9).astype(float), np.ones(365)/365, 'valid') > 0.99)
        rows.append([nm] + us + [f"{zlb:.0f}%", f"{first0/365:.1f}y" if zlb > 1 else "--"])
    table("失业率(十年均值)与 ZLB", ["economy", "U Y1-10", "U Y11-20", "U Y21-30", "利率贴零时间占比", "首次持续贴零"], rows)

    # 4. demography
    rows = []
    for i, nm in enumerate(NAMES):
        a0 = econ[i]["adult_population"][0] + econ[i]["child_population"][0]
        a1 = econ[i]["adult_population"][-1] + econ[i]["child_population"][-1]
        ch0 = econ[i]["child_population"][0] / a0
        ch1 = econ[i]["child_population"][-1] / a1
        mig = world.get(f"migrant_stock_{i}", np.zeros(T))[-1]
        rows.append([nm, f"{a0:.0f}", f"{a1:.0f}", f"{100*(a1/a0-1):+.0f}%",
                     f"{100*ch0:.0f}%→{100*ch1:.0f}%", f"{mig:.0f}"])
    table("人口三十年", ["economy", "初始", "末期", "增幅", "儿童占比变化", "末期移民存量"], rows)

    # 5. external position
    rows = []
    for i, nm in enumerate(NAMES):
        nfa = world[f"augmented_nfa_{i}"]
        ca = world[f"current_account_{i}"]
        rem = world[f"remittances_{i}"]
        # NFA sign flip
        sign0 = np.sign(nfa[365])
        flip = np.where(np.sign(nfa) != sign0)[0]
        flip_y = f"{flip[0]/365:.1f}y" if len(flip) else "--"
        rows.append([nm, f"{nfa[-1]:.2e}", f"{np.nanmean(ca[-365:]):+.1f}",
                     f"{np.nanmean(rem[-365:]):.1f}", flip_y])
    table("对外头寸(末期)", ["economy", "NFA", "经常账户(末年均)", "侨汇(末年均)", "NFA 变号时点"], rows)

    # 6. FX
    rows = []
    for i, nm in enumerate(NAMES):
        e = world[f"e_{i}"]
        rows.append([nm, f"{e[0]:.3f}", f"{e[T//3]:.3f}", f"{e[2*T//3]:.3f}", f"{e[-1]:.3f}",
                     f"{100*(e[-1]/e[0]-1):+.0f}%"])
    peg_ok = world.get("peg_intact", np.array([np.nan]))
    print(f"\npeg_intact 全程为真比例: {100*np.nanmean(peg_ok):.1f}%")
    table("汇率 e_i(对外币价格;涨=贬值)", ["economy", "t0", "10y", "20y", "30y", "总变动"], rows)

    # ---------------- figures ----------------
    figdir = seed_dir.parent / "report_figs"
    figdir.mkdir(exist_ok=True)

    # Fig 1: domestic macro
    fig, axes = plt.subplots(4, 1, figsize=(11, 14), sharex=True)
    for i, nm in enumerate(NAMES):
        axes[0].plot(yrs, ma(econ[i]["real_gdp"]), color=COLORS[i], label=nm, lw=1.4)
        axes[1].plot(yrs, econ[i]["cpi_fixed_basket"], color=COLORS[i], lw=1.2)
        axes[2].plot(yrs, 100 * ma(econ[i]["person_unemployment_rate"]), color=COLORS[i], lw=1.2)
        axes[3].plot(yrs, 100 * ma(econ[i]["policy_rate"], 90), color=COLORS[i], lw=1.2)
    axes[0].set_yscale("log"); axes[0].set_title("Real GDP (365d MA, log)"); axes[0].legend(ncol=6, fontsize=8)
    axes[1].set_yscale("log"); axes[1].set_title("CPI fixed basket (log)")
    axes[2].set_title("Unemployment % (365d MA)")
    axes[3].set_title("Policy rate % (90d MA)"); axes[3].set_xlabel("years")
    for ax in axes: ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(figdir / "fig1_domestic_macro.png", dpi=110); plt.close(fig)

    # Fig 2: external
    fig, axes = plt.subplots(4, 1, figsize=(11, 14), sharex=True)
    for i, nm in enumerate(NAMES):
        axes[0].plot(yrs, world[f"e_{i}"], color=COLORS[i], label=nm, lw=1.2)
        axes[1].plot(yrs, world[f"augmented_nfa_{i}"], color=COLORS[i], lw=1.4)
        axes[2].plot(yrs, ma(world[f"current_account_{i}"]), color=COLORS[i], lw=1.2)
        axes[3].plot(yrs, ma(world[f"remittances_{i}"]), color=COLORS[i], lw=1.2)
    axes[0].set_yscale("log"); axes[0].set_title("FX e_i (log; up = depreciation vs numeraire)"); axes[0].legend(ncol=6, fontsize=8)
    axes[1].set_title("NFA (augmented)"); axes[1].axhline(0, color="k", lw=0.5)
    axes[2].set_title("Current account (365d MA)"); axes[2].axhline(0, color="k", lw=0.5)
    axes[3].set_title("Remittances received (365d MA)"); axes[3].set_xlabel("years")
    for ax in axes: ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(figdir / "fig2_external.png", dpi=110); plt.close(fig)

    # Fig 3: society
    fig, axes = plt.subplots(4, 1, figsize=(11, 14), sharex=True)
    for i, nm in enumerate(NAMES):
        pop = econ[i]["adult_population"] + econ[i]["child_population"]
        axes[0].plot(yrs, pop / pop[0], color=COLORS[i], label=nm, lw=1.4)
        axes[1].plot(yrs, ma(econ[i]["avg_wage"] / np.where(econ[i]["cpi_fixed_basket"] > 0, econ[i]["cpi_fixed_basket"], np.nan)), color=COLORS[i], lw=1.2)
        axes[2].plot(yrs, ma(econ[i]["consumption_gini"]), color=COLORS[i], lw=1.2)
        axes[3].plot(yrs, world[f"migrant_stock_{i}"], color=COLORS[i], lw=1.2)
    axes[0].set_title("Population (index, t0=1)"); axes[0].legend(ncol=6, fontsize=8)
    axes[1].set_title("Real wage (avg_wage / CPI, 365d MA)")
    axes[2].set_title("Consumption Gini (365d MA)")
    axes[3].set_title("Migrant stock (hosted)"); axes[3].set_xlabel("years")
    for ax in axes: ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(figdir / "fig3_society.png", dpi=110); plt.close(fig)

    print(f"\nfigures -> {figdir}/fig1_domestic_macro.png, fig2_external.png, fig3_society.png",
          file=sys.stderr)


if __name__ == "__main__":
    main()
