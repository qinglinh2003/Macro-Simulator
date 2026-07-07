"""v10.1 full-economy diagnostic: one long run, as many indicators as fit on a 10x4 grid.
Groups: core macro / real activity / money+drain / credit / equity / distribution / v9 government /
v9.1 supply side / v9.3 labor+welfare / v10 MONETARY (policy rate, Taylor response, transmission).
Pure observation -- never touches the model. Run: ``uv run python plot_v101.py``."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
from config import Config                 # noqa: E402
from economy import Economy               # noqa: E402

NC, NK, NH, TICKS, SEED = 200, 100, 2000, 4000, 0
rec = Economy(Config.v11(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS, seed=SEED)).run()
t = [r["t"] for r in rec]
G = dict(alpha=0.25, lw=0.6)

SMOOTH_W = 61            # centered rolling-mean window (over 4000 ticks) -- readability


def col(k):
    return np.array([r.get(k, float("nan")) for r in rec], float)


def smooth(y, w=SMOOTH_W):
    """Centered rolling mean (edge-padded) for readable trends; NaN-robust."""
    y = np.asarray(y, float)
    if np.isnan(y).any():
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
    ax.plot(t, y, lw=0.5, color=color, alpha=0.16)
    ax.plot(t, smooth(y), lw=lw, color=color, label=label)


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


fig, ax = plt.subplots(11, 4, figsize=(22, 44), sharex=True)

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

# Row 6 -- v9 GOVERNMENT
line(ax[6, 0], ["gov_deficit_to_gdp", "gov_deficit_to_revenue"], "Fiscal deficit (share of GDP / of revenue)",
     ["deficit/GDP", "deficit/revenue"], zero=True)
line(ax[6, 1], ["gov_debt_to_gdp"], "Government debt / GDP  (private net wealth; watch if bounded)", zero=True)
line(ax[6, 2], ["tax_profit", "tax_income", "tax_consumption", "tax_wealth"], "Tax revenue by base",
     ["profit", "income", "VAT", "wealth"])
twin(ax[6, 3], "gov_consumption", "unemployment_rate", "Gov spending vs unemployment", "gov C", "u")

# Row 7 -- v9.1 SUPPLY SIDE
line(ax[7, 0], ["public_capital"], "Public capital K_pub  (gov investment + JG public works)")
line(ax[7, 1], ["pubcap_factor"], "Productivity factor (1+K_pub/K_ref)^γ  (>1 = supply-side lift)", hline=1.0)
line(ax[7, 2], ["real_output", "real_consumption"], "REAL output & consumption (welfare, the payoff)",
     ["real output", "real consumption"])
line(ax[7, 3], ["public_investment", "gov_consumption"], "Gov investment vs consumption (spending mix)",
     ["public investment", "gov consumption"])

# Row 8 -- v9.3 LABOR + WELFARE
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

# Row 9 -- v10 MONETARY (the NEW indicators: the policy rate, the Taylor response, transmission)
infl_target = float(getattr(Config.v11(), "inflation_target", 0.0))
line(ax[9, 0], ["policy_rate", "real_rate"], "Policy rate & real rate (r − π̄)", ["policy rate", "real rate"],
     zero=True, colors=["C0", "C2"])
line(ax[9, 1], ["inflation", "inflation_ema"], "Inflation & the CB's smoothed signal π̄  (dotted = target)",
     ["inflation", "π̄ (EMA)"], hline=infl_target, colors=["C7", "C3"])
twin(ax[9, 2], "policy_rate", "unemployment_rate", "Policy rate vs unemployment (transmission)", "rate", "u")
twin(ax[9, 3], "policy_rate", "inflation_ema", "Policy rate vs smoothed inflation (Taylor response)", "rate", "π̄")

# Row 10 -- v11 BANKING SECTOR (the NEW indicators: n_banks loan-book banks; crisis dormant on the stable frontier)
line(ax[10, 0], ["bank_capital"], "Aggregate bank capital  (Σ bank deposit balances = the loss buffer)")
line(ax[10, 1], ["bank_leverage"], "Bank leverage (Σ loans / Σ capital)  (higher = thinner, more fragile)")
twin(ax[10, 2], "banks_alive", "n_bank_failures", "Banks alive & cumulative failures", "alive", "failures (cum)")
line(ax[10, 3], ["bank_size_gini"], "Bank-size concentration (loan-book Gini)  (too-big-to-fail if it climbs)")

for a in ax[-1, :]:
    a.set_xlabel("tick", fontsize=8)
BURN = 1000
uu = np.mean([r["unemployment_rate"] for r in rec[BURN:]])
rr = np.mean([r.get("policy_rate", 0.0) for r in rec[BURN:]])
ii = np.mean([r.get("inflation", 0.0) for r in rec[BURN:]])
n_banks = len(rec) and int(getattr(Config.v11(), "n_banks", 1))
fails = rec[-1].get("n_bank_failures", 0.0)
lev = np.mean([r.get("bank_leverage", 0.0) for r in rec[BURN:]])
fig.suptitle(f"macro-simulator v11 diagnostic  —  {NC}C/{NK}K/{NH}H, {TICKS} ticks, seed {SEED}  "
             f"(full stack: govt + supply + JG + central bank + deposit-prop + progressive wealth tax + "
             f"{n_banks} BANKS; mean[{BURN}:] u={uu:.3f}, policy rate={rr:.3f}, inflation={ii:.4f}; "
             f"bank leverage={lev:.2f}, failures={fails:.0f}; A5 drift {drift:.1e})",
             fontsize=12, y=0.999)
fig.tight_layout(rect=(0, 0, 1, 0.997))
fig.savefig("diagnostic_v11.png", dpi=105)
print("wrote diagnostic_v11.png")
print(f"mean[{BURN}:]  policy rate={rr:.4f}  inflation={ii:.4f}  (target {infl_target})  u={uu:.4f}  "
      f"A5 drift={drift:.1e}")
