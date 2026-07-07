"""Rich visualization of kernel runs (spec §8.3 deliverable 3, extended).

Two families of plots:

  * plot_dashboard(records, ...) -- an 18-panel single-run dashboard covering every
    metric group: money & conservation, circular flows, the DRAIN IDENTITY (§9),
    labor, prices/inflation, real activity, and distributions over time.
  * plot_cross_run(rows, ...) -- compare a parameter sweep from the run registry
    (runs/index.jsonl): one small multiple per metric, x = swept parameter.

Plus the seed-invariance check (M3(a), §8.3 deliverable 4).

Everything is pure observation; plots never touch the model. Headless Agg backend
so it writes files without a display.
"""

from __future__ import annotations

import statistics
from typing import List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config import Config  # noqa: E402
from economy import Economy  # noqa: E402
from metrics import classify_series  # noqa: E402  (shared with runlog)

_GRID = dict(alpha=0.25, lw=0.6)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _col(records: List[dict], key: str) -> List[float]:
    return [r.get(key, float("nan")) for r in records]


def _line(ax, t, records, keys, *, title, labels=None, zero=False, tag=True, colors=None):
    labels = labels or keys
    for i, k in enumerate(keys):
        y = _col(records, k)
        c = colors[i] if colors else None
        ax.plot(t, y, lw=1.2, label=labels[i], color=c)
    if zero:
        ax.axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ttl = title
    if tag and len(keys) == 1:
        ttl = f"{title}  [{classify_series(_col(records, keys[0]))}]"
    ax.set_title(ttl, fontsize=9)
    ax.grid(**_GRID)
    if len(keys) > 1:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)


def _twin(ax, t, records, key_left, key_right, *, title, ll, rl):
    yl = _col(records, key_left)
    ax.plot(t, yl, lw=1.2, color="C0", label=ll)
    ax.set_ylabel(ll, fontsize=7, color="C0")
    ax.tick_params(axis="y", labelcolor="C0", labelsize=6)
    ax2 = ax.twinx()
    ax2.plot(t, _col(records, key_right), lw=1.0, color="C3", label=rl, alpha=0.8)
    ax2.set_ylabel(rl, fontsize=7, color="C3")
    ax2.tick_params(axis="y", labelcolor="C3", labelsize=6)
    ax.set_title(title, fontsize=9)
    ax.grid(**_GRID)


# ---------------------------------------------------------------------------
# single-run dashboard
# ---------------------------------------------------------------------------
def plot_dashboard(records: List[dict], path: str = "dashboard.png", *,
                   title: str = "Kernel run", rho: Optional[float] = None) -> str:
    """18-panel dashboard over one run's per-tick metrics."""
    t = _col(records, "t")
    hh = _col(records, "hh_money")
    dH = [float("nan")] + [hh[i] - hh[i - 1] for i in range(1, len(hh))]  # measured ΔH_t

    fig, ax = plt.subplots(6, 3, figsize=(16, 20), sharex=True)

    # -- row 1: money & conservation ---------------------------------------
    tot = _col(records, "total_money")
    ax[0, 0].plot(t, tot, lw=1.2, color="C2")
    drift = (max(tot) - min(tot))
    ax[0, 0].set_title(f"Total money  [{'conserved' if drift < 1e-6 * max(tot) else 'LEAKING!'}]", fontsize=9)
    ax[0, 0].set_ylim(min(tot) * 0.999 - 1, max(tot) * 1.001 + 1)
    ax[0, 0].grid(**_GRID)
    _line(ax[0, 1], t, records, ["hh_money", "firm_money"], title="Money by sector",
          labels=["households", "firms"])
    _line(ax[0, 2], t, records, ["hh_money_share"], title="Household money share")

    # -- row 2: circular flows ---------------------------------------------
    _line(ax[1, 0], t, records, ["wages_paid", "consumption_spending", "dividends_paid"],
          title="Circular flows (per tick)", labels=["wages", "consumption", "dividends"])
    _line(ax[1, 1], t, records, ["hh_saving"], title="Household saving/tick", zero=True)
    # -- drain identity panel (the §9 theorem, drawn) -----------------------
    ax[1, 2].plot(t, dH, lw=1.4, color="C0", label=r"measured $\Delta H_t$")
    if rho is not None:
        pred = [-(1 - rho) * p for p in _col(records, "profit_total")]
        ax[1, 2].plot(t, pred, lw=1.0, color="C3", ls="--", label=r"$-(1-\rho)\Pi_t$ (boom form)")
    ax[1, 2].axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ax[1, 2].set_title("Drain identity  (overlap in boom, split in bust)", fontsize=9)
    ax[1, 2].grid(**_GRID)
    ax[1, 2].legend(fontsize=6, loc="best", framealpha=0.6)

    # -- row 3: profit / firm pool / retained ------------------------------
    _line(ax[2, 0], t, records, ["profit_total"], title="Total profit $\\Pi_t$", zero=True)
    _line(ax[2, 1], t, records, ["retained_total", "dividends_paid"],
          title="Retained vs distributed", labels=["retained", "dividends"])
    _line(ax[2, 2], t, records, ["firm_deposits_max"], title="Largest firm deposits")

    # -- row 4: labor ------------------------------------------------------
    _line(ax[3, 0], t, records, ["employment", "labor_demand", "labor_supply"],
          title="Labor: employ / demand / supply", labels=["employed", "demand", "supply"])
    _line(ax[3, 1], t, records, ["unemployment_rate"], title="Unemployment rate")
    _twin(ax[3, 2], t, records, "labor_fill_rate", "vacancies_unfilled",
          title="Labor fill rate & unfilled", ll="fill rate", rl="unfilled")

    # -- row 5: prices -----------------------------------------------------
    _twin(ax[4, 0], t, records, "price_index", "inflation",
          title="Price index & inflation", ll="price idx", rl="inflation")
    _twin(ax[4, 1], t, records, "avg_markup", "price_cv",
          title="Markup & price dispersion", ll="avg markup", rl="price cv")
    _line(ax[4, 2], t, records, ["avg_wage"], title="Average wage")

    # -- row 6: real activity & distributions ------------------------------
    _line(ax[5, 0], t, records, ["real_output", "real_consumption"],
          title="Real output vs consumption", labels=["output", "consumption"])
    _twin(ax[5, 1], t, records, "inventory", "inventory_investment",
          title="Inventory & investment", ll="inventory", rl="inv. invest")
    _line(ax[5, 2], t, records, ["hh_wealth_gini", "hh_wealth_top10_share", "firm_size_gini_output"],
          title="Inequality over time", labels=["hh wealth Gini", "hh top-10%", "firm-size Gini"])

    for a in ax[-1, :]:
        a.set_xlabel("tick", fontsize=8)
    fig.suptitle(title, fontsize=14, y=0.997)
    fig.tight_layout(rect=(0, 0, 1, 0.995))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# Backward-compatible alias (run.py / older callers).
def plot_run(records: List[dict], path: str = "diagnostic.png", *, rho: Optional[float] = None) -> str:
    return plot_dashboard(records, path, title="Kernel diagnostics", rho=rho)


def plot_dashboard_v2(records: List[dict], path: str = "dashboard_v2.png", *,
                      title: str = "v2 run (investment + capital)") -> str:
    """12-panel v2 dashboard: the two-sector money circuit, the cure channel B_K,
    investment/capital accumulation, and the drain decomposition (§10)."""
    t = _col(records, "t")
    hh = _col(records, "hh_money")
    dH = [float("nan")] + [hh[i] - hh[i - 1] for i in range(1, len(hh))]

    fig, ax = plt.subplots(4, 3, figsize=(16, 14), sharex=True)

    tot = _col(records, "total_money")
    ax[0, 0].plot(t, tot, lw=1.2, color="C2")
    drift = max(tot) - min(tot)
    ax[0, 0].set_title(f"Total money (3 sectors)  [{'conserved' if drift < 1e-6*max(tot) else 'LEAKING!'}]", fontsize=9)
    ax[0, 0].set_ylim(min(tot) * 0.999 - 1, max(tot) * 1.001 + 1)
    ax[0, 0].grid(**_GRID)
    _line(ax[0, 1], t, records, ["hh_money", "c_firm_money", "k_firm_money"],
          title="Money by sector", labels=["households", "C-firms", "K-firms"])
    _line(ax[0, 2], t, records, ["hh_money_share"], title="Household money share")

    # the cure channel
    _line(ax[1, 0], t, records, ["wages_C", "wages_K"],
          title="Wages by sector (B_K = cure channel)", labels=["B_C (consumption)", "B_K (capital)"])
    _line(ax[1, 1], t, records, ["dividends_C", "dividends_K"],
          title="Dividends by sector", labels=["V_C", "V_K"])
    # drain decomposition: reversal <=> R_K > retained
    _line(ax[1, 2], t, records, ["retained_intended_total", "investment_spending"],
          title="Drain decomposition (reversal: R_K > retained)",
          labels=["(1-ρ)Π retained", "R_K investment"])

    _line(ax[2, 0], t, records, ["net_drain"], title="Net household drain  (>0 drains, <0 refills)", zero=True)
    ax[2, 1].plot(t, dH, lw=1.2, color="C0", label=r"measured $\Delta H_t$")
    ax[2, 1].axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ax[2, 1].set_title("Measured ΔH_t (household money change)", fontsize=9)
    ax[2, 1].grid(**_GRID)
    _twin(ax[2, 2], t, records, "investment_units", "aggregate_capital",
          title="Investment & capital stock", ll="I_t (units)", rl="ΣK_f")

    _twin(ax[3, 0], t, records, "real_output", "aggregate_capital",
          title="Output vs capital ceiling", ll="consumption output", rl="ΣK_f")
    _line(ax[3, 1], t, records, ["unemployment_rate"], title="Unemployment rate")
    _line(ax[3, 2], t, records, ["price_index", "capital_price_index"],
          title="Prices by sector", labels=["consumption", "capital"])

    for a in ax[-1, :]:
        a.set_xlabel("tick", fontsize=8)
    fig.suptitle(title, fontsize=13, y=0.997)
    fig.tight_layout(rect=(0, 0, 1, 0.995))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_dashboard_v3(records: List[dict], path: str = "dashboard_v3.png", *,
                      title: str = "v3 run (banks + endogenous money)") -> str:
    """12-panel v3 dashboard: the credit layer. Headline is broad money ΣD going from
    a flat line (v1/v2) to a LIVE series, while net worth ΣD−ΣL stays pinned at M."""
    t = _col(records, "t")
    fig, ax = plt.subplots(4, 3, figsize=(16, 14), sharex=True)

    # -- the headline: broad money alive, net worth flat at M --------------
    bm = _col(records, "broad_money")
    nw = _col(records, "net_worth")
    ax[0, 0].plot(t, bm, lw=1.3, color="C0", label="broad money ΣD")
    ax[0, 0].plot(t, nw, lw=1.1, color="C2", ls="--", label="net worth ΣD−ΣL (=M)")
    ax[0, 0].set_title("Broad money (alive) vs net worth (=M)", fontsize=9)
    ax[0, 0].grid(**_GRID); ax[0, 0].legend(fontsize=6, framealpha=0.6)
    _line(ax[0, 1], t, records, ["total_credit"], title="Outstanding credit ΣL")
    _line(ax[0, 2], t, records, ["aggregate_leverage"], title="Aggregate leverage ΣL / ΣNW")

    # -- credit flows -------------------------------------------------------
    _line(ax[1, 0], t, records, ["new_loans"], title="New loans / tick")
    _line(ax[1, 1], t, records, ["credit_wage", "credit_investment"],
          title="Credit by purpose", labels=["wage", "investment"])
    _line(ax[1, 2], t, records, ["interest_paid", "principal_repaid"],
          title="Debt service", labels=["interest", "principal"])

    # -- money by sector + bank --------------------------------------------
    _line(ax[2, 0], t, records, ["hh_money", "c_firm_money", "k_firm_money", "bank_money"],
          title="Money by sector (+ bank)", labels=["hh", "C", "K", "bank"])
    _line(ax[2, 1], t, records, ["n_firms_borrowing"], title="# firms borrowing")
    _line(ax[2, 2], t, records, ["hh_money_share"], title="Household money share")

    # -- real economy -------------------------------------------------------
    _twin(ax[3, 0], t, records, "real_output", "aggregate_capital",
          title="Output vs capital", ll="output", rl="ΣK")
    _line(ax[3, 1], t, records, ["unemployment_rate"], title="Unemployment rate")
    _line(ax[3, 2], t, records, ["price_index", "capital_price_index"],
          title="Prices by sector", labels=["consumption", "capital"])

    for a in ax[-1, :]:
        a.set_xlabel("tick", fontsize=8)
    fig.suptitle(title, fontsize=13, y=0.997)
    fig.tight_layout(rect=(0, 0, 1, 0.995))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_dashboard_v4(records: List[dict], path: str = "dashboard_v4.png", *,
                      title: str = "v4 run (firm entry/exit + bankruptcy)") -> str:
    """12-panel v4 dashboard: firm demographics (emergent count, churn, zombies cleared),
    bankruptcy/bank stress, and the persistence of monopoly (the revolving door) -- all
    while A5 holds (net worth flat at M)."""
    import numpy as _np
    t = _col(records, "t")
    fig, ax = plt.subplots(4, 3, figsize=(16, 14), sharex=True)

    # -- demographics ------------------------------------------------------
    _line(ax[0, 0], t, records, ["firm_count_c"], title="C-firm count (emergent, entry↔exit)")
    _line(ax[0, 1], t, records, ["births", "deaths"], title="Births vs deaths / tick (churn)",
          labels=["births", "deaths"])
    _line(ax[0, 2], t, records, ["n_zombies"], title="Zombies (insolvent firms) — cleared → ~0", zero=True)

    # -- bankruptcy & the bank --------------------------------------------
    _line(ax[1, 0], t, records, ["writeoffs"], title="Bad debt written off / tick")
    cum = _np.cumsum(_col(records, "writeoffs"))
    ax[1, 1].plot(t, cum, lw=1.3, color="C3")
    ax[1, 1].set_title("Cumulative writeoffs (bank absorbs)", fontsize=9); ax[1, 1].grid(**_GRID)
    _line(ax[1, 2], t, records, ["bank_equity"], title="Bank equity (→0 = insolvent/crisis)", zero=True)

    # -- monopoly persists (the revolving door) ---------------------------
    _line(ax[2, 0], t, records, ["avg_markup"], title="Avg markup (monopoly profit — NOT competed away)")
    _line(ax[2, 1], t, records, ["firm_size_gini_output"], title="Firm-size Gini (concentration)")
    _line(ax[2, 2], t, records, ["hh_money_share"], title="Household money share")

    # -- macro + A5 --------------------------------------------------------
    bm = _col(records, "broad_money"); nw = _col(records, "net_worth")
    ax[3, 0].plot(t, bm, lw=1.2, color="C0", label="broad money ΣD")
    ax[3, 0].plot(t, nw, lw=1.1, color="C2", ls="--", label="net worth =M (A5)")
    ax[3, 0].set_title("Broad money vs net worth (A5)", fontsize=9)
    ax[3, 0].grid(**_GRID); ax[3, 0].legend(fontsize=6, framealpha=0.6)
    _twin(ax[3, 1], t, records, "real_output", "unemployment_rate",
          title="Output & unemployment", ll="output", rl="u")
    _line(ax[3, 2], t, records, ["total_credit"], title="Outstanding credit ΣL")

    for a in ax[-1, :]:
        a.set_xlabel("tick", fontsize=8)
    fig.suptitle(title, fontsize=13, y=0.997)
    fig.tight_layout(rect=(0, 0, 1, 0.995))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_dashboard_v6(records: List[dict], path: str = "diagnostic_v6.png", *,
                      title: str = "v6 run (capital market: equity index + choice yi)") -> str:
    """12-panel v6 dashboard (aligned with v2-v4). Row 0-1: the NEW equity-market series
    (price vs fundamental, Tobin's q, bubble gap = the valuation phantom, turnover, chartist
    trend, equity share of wealth). Row 2: choice-yi wealth distribution + market cap vs book.
    Row 3: macro + A5 continuity -- money conserves EVEN through a bubble/crash."""
    import numpy as _np
    t = _col(records, "t")
    fig, ax = plt.subplots(4, 3, figsize=(16, 14), sharex=True)

    # -- the equity market headline ---------------------------------------
    ax[0, 0].plot(t, _col(records, "stock_price"), lw=1.3, color="C0", label="index price")
    ax[0, 0].plot(t, _col(records, "fundamental_ps"), lw=1.1, color="C1", ls="--",
                  label="fundamental (book/share)")
    ax[0, 0].set_title("Index price vs fundamental (net asset value)", fontsize=9)
    ax[0, 0].grid(**_GRID); ax[0, 0].legend(fontsize=6, framealpha=0.6)
    _line(ax[0, 1], t, records, ["tobin_q"], title="Tobin's q = market cap / book  (1 = at book)")
    ax[0, 1].axhline(1.0, color="black", lw=0.7, ls=":", alpha=0.6)
    _line(ax[0, 2], t, records, ["bubble_gap"],
          title="Bubble = market cap − book (valuation phantom, NOT money)", zero=True)

    # -- market mechanics --------------------------------------------------
    _line(ax[1, 0], t, records, ["equity_turnover"], title="Turnover (traded units / float)")
    _line(ax[1, 1], t, records, ["equity_trend"], title="Chartist trend signal (momentum)", zero=True)
    _line(ax[1, 2], t, records, ["equity_wealth_share"], title="Equity share of household wealth")

    # -- choice yi: wealth distribution & valuation levels -----------------
    _line(ax[2, 0], t, records, ["hh_wealth_gini", "hh_wealth_gini_incl_equity"],
          title="Wealth Gini: deposits vs incl. equity (yi)", labels=["deposits", "+ equity"])
    _line(ax[2, 1], t, records, ["market_cap", "book_value"],
          title="Market cap vs book value", labels=["market cap", "book (Σ net worth)"])
    _line(ax[2, 2], t, records, ["hh_money_share"], title="Household money share (drain)")

    # -- macro + A5 (money conserves even through a bubble/crash) ----------
    bm = _col(records, "broad_money"); nw = _col(records, "net_worth")
    ax[3, 0].plot(t, bm, lw=1.2, color="C0", label="broad money ΣD")
    ax[3, 0].plot(t, nw, lw=1.1, color="C2", ls="--", label="net worth =M (A5)")
    drift = max(r.get("conservation_drift", 0.0) for r in records)
    ax[3, 0].set_title(f"Broad money vs net worth (A5 drift {drift:.1e})", fontsize=9)
    ax[3, 0].grid(**_GRID); ax[3, 0].legend(fontsize=6, framealpha=0.6)
    _twin(ax[3, 1], t, records, "real_output", "unemployment_rate",
          title="Output & unemployment", ll="output", rl="u")
    _line(ax[3, 2], t, records, ["avg_markup", "firm_size_gini_output"],
          title="Markup & firm-size Gini", labels=["avg markup", "firm-size Gini"])

    for a in ax[-1, :]:
        a.set_xlabel("tick", fontsize=8)
    fig.suptitle(title, fontsize=13, y=0.997)
    fig.tight_layout(rect=(0, 0, 1, 0.995))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# cross-run comparison (parameter sweep from the registry)
# ---------------------------------------------------------------------------
def plot_cross_run(rows: List[dict], x_param: str, y_metrics: Sequence[str],
                   path: str = "sweep.png", *, title: str = "Parameter sweep") -> str:
    """Small multiples: for each metric, plot its tail-mean against a swept param.

    rows: entries from runlog.load_index() (each has cfg_* params and m_* means).
    x_param: e.g. 'cfg_rho'.  y_metrics: e.g. ['m_unemployment_rate', 'm_real_output'].
    """
    pts = sorted([r for r in rows if x_param in r], key=lambda r: r[x_param])
    xs = [r[x_param] for r in pts]

    n = len(y_metrics)
    ncol = min(3, n)
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(5 * ncol, 3.4 * nrow), squeeze=False)
    for i, m in enumerate(y_metrics):
        a = axes[i // ncol][i % ncol]
        ys = [r.get(m, float("nan")) for r in pts]
        a.plot(xs, ys, "o-", lw=1.4, ms=5, color="C0")
        a.set_title(m.replace("m_", ""), fontsize=10)
        a.set_xlabel(x_param.replace("cfg_", ""), fontsize=8)
        a.grid(**_GRID)
    for j in range(n, nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")
    fig.suptitle(title, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# seed-invariance (M3(a), §8.3 deliverable 4)
# ---------------------------------------------------------------------------
def seed_invariance(cfg: Config, seeds: List[int], *, keys=None, burn_in_frac: float = 0.5) -> dict:
    keys = keys or ["price_index", "real_output", "unemployment_rate", "avg_markup"]
    per_seed = {}
    for s in seeds:
        econ = Economy(cfg.invariance_variant(s))
        recs = econ.run()
        tail = recs[int(len(recs) * burn_in_frac):]
        per_seed[s] = {k: statistics.fmean(r[k] for r in tail) for k in keys}

    summary = {}
    for k in keys:
        vals = [per_seed[s][k] for s in seeds]
        mean = statistics.fmean(vals)
        sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        summary[k] = {"mean": mean, "sd": sd,
                      "cv": sd / abs(mean) if abs(mean) > 1e-9 else 0.0,
                      "per_seed": vals}
    return {"per_seed": per_seed, "summary": summary}
