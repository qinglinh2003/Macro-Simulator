"""v9.3 full-economy diagnostic: one long run, as many indicators as fit on a 9x4 grid.
Groups: core macro / real activity / money+drain / credit / equity market / distribution / v9 government /
v9.1 supply side / v9.3 LABOR+WELFARE (the new job-guarantee + welfare indicators).
Pure observation -- never touches the model. Run: ``uv run python plot_v93.py``."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
from config import Config                 # noqa: E402
from economy import Economy               # noqa: E402

NC, NK, NH, TICKS, SEED = 200, 100, 2000, 4000, 0
rec = Economy(Config.v93(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS, seed=SEED)).run()
t = [r["t"] for r in rec]
G = dict(alpha=0.25, lw=0.6)


SMOOTH_W = 61            # centered rolling-mean window (over 4000 ticks) -- readability


def col(k):
    return np.array([r.get(k, float("nan")) for r in rec], float)


def smooth(y, w=SMOOTH_W):
    """Centered rolling mean (edge-padded) for readable trends; NaN-robust."""
    y = np.asarray(y, float)
    if np.isnan(y).any():                       # forward/back-fill gaps so the mean is clean
        idx = np.where(~np.isnan(y))[0]
        if len(idx) == 0:
            return y
        y = np.interp(np.arange(len(y)), idx, y[idx])
    if len(y) < w or w < 3:
        return y
    if w % 2 == 0:
        w += 1
    half = w // 2
    ypad = np.concatenate([np.full(half, y[0]), y, np.full(half, y[-1])])
    return np.convolve(ypad, np.ones(w) / w, mode="valid")


def _draw(ax, y, color, label, lw=1.6):
    ax.plot(t, y, lw=0.5, color=color, alpha=0.16)      # faint raw for context
    ax.plot(t, smooth(y), lw=lw, color=color, label=label)   # bold smoothed


def line(ax, keys, title, labels=None, zero=False, hline=None, colors=None):
    labels = labels or keys
    for i, k in enumerate(keys):
        _draw(ax, col(k), (colors[i] if colors else f"C{i}"), labels[i])
    if zero:
        ax.axhline(0, color="k", lw=0.7, ls="--", alpha=0.5)
    if hline is not None:
        ax.axhline(hline, color="k", lw=0.7, ls=":", alpha=0.6)
    ax.set_title(title, fontsize=8.5)
    ax.grid(**G)
    if len(keys) > 1:
        ax.legend(fontsize=6, loc="best", framealpha=0.6)


def twin(ax, kl, kr, title, ll, rl):
    _draw(ax, col(kl), "C0", ll)
    ax.set_title(title, fontsize=8.5); ax.grid(**G)
    a2 = ax.twinx(); _draw(a2, col(kr), "C3", rl)
    ax.legend(fontsize=6, loc="upper left", framealpha=0.6)
    a2.legend(fontsize=6, loc="upper right", framealpha=0.6)


fig, ax = plt.subplots(9, 4, figsize=(22, 36), sharex=True)

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
_draw(ax[2, 0], col("broad_money"), "C0", "broad money ΣD")
ax[2, 0].plot(t, smooth(col("net_worth")), lw=1.3, color="C2", ls="--", label="net worth (=M, A5)")
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

# Row 6 -- v9 GOVERNMENT (fiscal indicators, normalised)
line(ax[6, 0], ["gov_deficit_to_gdp", "gov_deficit_to_revenue"], "Fiscal deficit (share of GDP / of revenue)",
     ["deficit/GDP", "deficit/revenue"], zero=True)
line(ax[6, 1], ["gov_debt_to_gdp"], "Government debt / GDP  (private net wealth; watch if bounded)", zero=True)
line(ax[6, 2], ["tax_profit", "tax_income", "tax_consumption", "tax_wealth"], "Tax revenue by base",
     ["profit", "income", "VAT", "wealth"])
twin(ax[6, 3], "gov_consumption", "unemployment_rate", "Gov spending vs unemployment", "gov C", "u")

# Row 7 -- v9.1 SUPPLY SIDE (public-capital / productivity channel + real payoff)
line(ax[7, 0], ["public_capital"], "Public capital K_pub  (gov investment + JG public works)")
line(ax[7, 1], ["pubcap_factor"], "Productivity factor (1+K_pub/K_ref)^γ  (>1 = supply-side lift)", hline=1.0)
line(ax[7, 2], ["real_output", "real_consumption"], "REAL output & consumption (welfare, the payoff)",
     ["real output", "real consumption"])
line(ax[7, 3], ["public_investment", "gov_consumption"], "Gov investment vs consumption (spending mix)",
     ["public investment", "gov consumption"])

# Row 8 -- v9.3 LABOR + WELFARE (the NEW indicators: the job-guarantee buffer stock + the welfare metrics)
line(ax[8, 0], ["unemployment_rate", "effective_unemployment", "jg_employment_rate"],
     "Labor: private u / effective (no-income) u / JG buffer stock",
     ["private u", "effective u", "JG buffer"], colors=["C3", "C2", "C0"])
line(ax[8, 1], ["poverty_rate", "income_poverty_rate", "consumption_floor_share"],
     "Poverty: relative (consumption) / income / subsistence-floor share",
     ["cons poverty", "income poverty", "at floor"], colors=["C3", "C1", "C4"])
twin(ax[8, 2], "bottom10_consumption", "welfare_log", "Bottom-decile real C & log social welfare",
     "bottom-10% real C", "log welfare")
ax[8, 2].plot(t, smooth(col("sen_welfare")), lw=1.3, color="C2", ls="--", label="Sen welfare")
ax[8, 2].legend(fontsize=6, loc="lower right", framealpha=0.6)
line(ax[8, 3], ["jg_spending", "benefit_paid"], "Outside-money floors: JG wage bill vs unemployment benefit",
     ["JG wage bill", "benefit"], colors=["C0", "C1"])

for a in ax[-1, :]:
    a.set_xlabel("tick", fontsize=8)
BURN = 1000
uu = np.mean([r["unemployment_rate"] for r in rec[BURN:]])
euu = np.mean([r.get("effective_unemployment", 0.0) for r in rec[BURN:]])
jgb = np.mean([r.get("jg_employment_rate", 0.0) for r in rec[BURN:]])
pov = np.mean([r.get("poverty_rate", 0.0) for r in rec[BURN:]])
fig.suptitle(f"macro-simulator v9.3 diagnostic  —  {NC}C/{NK}K/{NH}H, {TICKS} ticks, seed {SEED}  "
             f"(labor welfare: job guarantee + wired min_wage; mean[{BURN}:] private u={uu:.2f}, "
             f"effective u={euu:.3f}, JG buffer={jgb:.3f}, poverty={pov:.3f}; A5 drift {drift:.1e})",
             fontsize=13, y=0.999)
fig.tight_layout(rect=(0, 0, 1, 0.997))
fig.savefig("diagnostic_v93.png", dpi=110)
print("wrote diagnostic_v93.png")
print(f"mean[{BURN}:]  private u={uu:.3f}  effective u={euu:.4f}  JG buffer={jgb:.4f}  "
      f"poverty={pov:.4f}  bottom10C={np.mean([r.get('bottom10_consumption',0.0) for r in rec[BURN:]]):.3f}  "
      f"A5 drift={drift:.1e}")
