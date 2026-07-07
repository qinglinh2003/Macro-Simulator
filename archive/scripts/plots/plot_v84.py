"""v8.4 full-economy diagnostic: one long run, as many indicators as fit on a 6x4 grid.
Groups: core macro / real activity / money+drain / credit / equity market / distribution.
Pure observation -- never touches the model. Run: ``PYTHONPATH=.:scripts uv run python scripts/plots/plot_v84.py``."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
from config import Config                 # noqa: E402
from economy import Economy               # noqa: E402

NC, NK, NH, TICKS, SEED = 200, 100, 2000, 4000, 0
rec = Economy(Config.v84(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS, seed=SEED)).run()
t = [r["t"] for r in rec]
G = dict(alpha=0.25, lw=0.6)


def col(k):
    return [r.get(k, float("nan")) for r in rec]


def line(ax, keys, title, labels=None, zero=False, hline=None, colors=None):
    labels = labels or keys
    for i, k in enumerate(keys):
        ax.plot(t, col(k), lw=1.1, label=labels[i], color=(colors[i] if colors else None))
    if zero:
        ax.axhline(0, color="k", lw=0.7, ls="--", alpha=0.5)
    if hline is not None:
        ax.axhline(hline, color="k", lw=0.7, ls=":", alpha=0.6)
    ax.set_title(title, fontsize=8.5)
    ax.grid(**G)
    if len(keys) > 1:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)


def twin(ax, kl, kr, title, ll, rl):
    ax.plot(t, col(kl), lw=1.1, color="C0", label=ll)
    ax.set_title(title, fontsize=8.5); ax.grid(**G)
    a2 = ax.twinx(); a2.plot(t, col(kr), lw=1.1, color="C3", label=rl)
    ax.legend(fontsize=6, loc="upper left", framealpha=0.6)
    a2.legend(fontsize=6, loc="upper right", framealpha=0.6)


fig, ax = plt.subplots(6, 4, figsize=(22, 24), sharex=True)

# Row 0 -- core macro
twin(ax[0, 0], "real_output", "unemployment_rate", "Output & unemployment", "output", "u")
line(ax[0, 1], ["unemployment_rate", "labor_fill_rate"], "Unemployment & labor fill-rate", ["u", "fill"])
line(ax[0, 2], ["inflation", "wage_inflation"], "Price & wage inflation (per tick)", ["price", "wage"], zero=True)
line(ax[0, 3], ["price_index", "avg_wage"], "Price index & average wage", ["price idx", "avg wage"])

# Row 1 -- real activity
line(ax[1, 0], ["consumption_spending", "investment_spending"], "Consumption & investment", ["C", "I"])
line(ax[1, 1], ["labor_supply", "labor_demand", "employment"], "Labor: supply / demand / hired",
     ["supply", "demand", "hired"])
line(ax[1, 2], ["n_firms_producing", "n_firms_selling"], "Active C-firms", ["producing", "selling"])
line(ax[1, 3], ["avg_markup", "markup_std"], "Markup: mean & dispersion", ["mean", "std"])

# Row 2 -- money, conservation, the drain
drift = max(r.get("conservation_drift", 0.0) for r in rec)
ax[2, 0].plot(t, col("broad_money"), lw=1.1, color="C0", label="broad money ΣD")
ax[2, 0].plot(t, col("net_worth"), lw=1.0, color="C2", ls="--", label="net worth (=M, A5)")
ax[2, 0].set_title(f"Broad money vs net worth  (A5 drift {drift:.1e})", fontsize=8.5)
ax[2, 0].grid(**G); ax[2, 0].legend(fontsize=6, framealpha=0.6)
line(ax[2, 1], ["hh_money_share"], "Household money share (the §9 drain)")
line(ax[2, 2], ["money_velocity"], "Money velocity")
line(ax[2, 3], ["net_drain"], "Net drain (household → firm flow)", zero=True)

# Row 3 -- credit
line(ax[3, 0], ["total_credit", "credit_to_gdp"], "Total credit ΣL & credit/GDP", ["ΣL", "credit/GDP"])
line(ax[3, 1], ["household_debt_total", "household_margin_debt"], "Household debt: consumption & margin",
     ["consumption", "margin"])
line(ax[3, 2], ["aggregate_leverage", "household_leverage"], "Leverage: firms & households",
     ["firm agg", "household"])
line(ax[3, 3], ["new_loans", "writeoffs"], "Loan flow: new & write-offs", ["new", "write-off"], zero=True)

# Row 4 -- equity market
line(ax[4, 0], ["tobin_q_mean", "tobin_q_dispersion"], "Tobin's q: mean & dispersion", ["mean", "disp"], hline=1.0)
line(ax[4, 1], ["equity_market_cap", "book_value"], "Equity market cap vs book", ["market cap", "book"])
line(ax[4, 2], ["equity_turnover"], "Equity turnover (traded / float)")
line(ax[4, 3], ["dividends_paid", "equity_raised"], "Dividends paid & equity raised", ["dividends", "issuance"])

# Row 5 -- distribution / inequality
line(ax[5, 0], ["hh_wealth_gini_incl_equity", "hh_full_networth_gini"], "Wealth Gini (incl. equity / full NW)",
     ["incl equity", "full NW"])
line(ax[5, 1], ["income_gini", "consumption_gini"], "Income & consumption Gini", ["income", "consumption"])
line(ax[5, 2], ["equity_ownership_gini", "firm_size_gini_output"], "Ownership & firm-size Gini",
     ["ownership", "firm size"])
line(ax[5, 3], ["firm_size_pareto_slope", "firm_attractiveness_gini"], "Firm-size Pareto slope & attractiveness Gini",
     ["Pareto slope", "attract Gini"], hline=-1.0)

for a in ax[-1, :]:
    a.set_xlabel("tick", fontsize=8)
uu = np.mean([r["unemployment_rate"] for r in rec[1000:]])
fig.suptitle(f"macro-simulator v8.4 diagnostic  —  {NC}C/{NK}K/{NH}H, {TICKS} ticks, seed {SEED}  "
             f"(pro-rata dividends; mean u[1000:]={uu:.2f}, A5 drift {drift:.1e})", fontsize=13, y=0.999)
fig.tight_layout(rect=(0, 0, 1, 0.996))
fig.savefig("diagnostic_v84.png", dpi=110)
print("wrote diagnostic_v84.png")
print(f"mean u[1000:]={uu:.3f}  final wealth_gini_incl_equity={rec[-1].get('hh_wealth_gini_incl_equity'):.3f}  "
      f"A5 drift={drift:.1e}")
