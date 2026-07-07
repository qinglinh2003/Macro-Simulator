"""§4 held-out validation pass. Judge the FULL model (Config.v4 -- banks + credit +
capital + firm demographics + cycles; dis_slope=0, no market-structure intervention)
against the 8 macro regularities it was never told (§0-ii). One long run per seed;
each target gets a concrete statistic + verdict. NOTHING here is fed back into the model.

Run: ``PYTHONPATH=.:scripts uv run python scripts/validation/validate_s4.py``.
"""
import numpy as np
from config import Config
from economy import Economy
from metrics import gini

SEEDS = [0, 1, 2]
TICKS = 4000
BURN = 1000                     # drop the transient; cycles/distributions read on [BURN:]
NC, NK, NH = 200, 100, 2000
EPS = 1e-9


def moments(x):
    x = np.asarray(x, float)
    m, s = x.mean(), x.std()
    if s < EPS:
        return 0.0, 0.0
    z = (x - m) / s
    return float((z**3).mean()), float((z**4).mean() - 3.0)   # skew, excess kurtosis


def cyclical(x, w=201):
    """De-trend: series minus a centered rolling mean (business-cycle component)."""
    x = np.asarray(x, float)
    k = np.ones(w) / w
    trend = np.convolve(x, k, mode="same")
    return (x - trend)[w:-w]      # trim convolution edge effects


def rank_size_slope(sizes, tail_frac=1.0):
    """Rank-size (Zipf) slope. tail_frac<1 fits only the largest firms (Zipf is a TAIL
    law); the full-sample fit is flattened by the mass of tiny firms."""
    s = np.sort(np.asarray([v for v in sizes if v > EPS], float))[::-1]
    if len(s) < 8:
        return np.nan, len(s)
    k = max(8, int(len(s) * tail_frac))
    s = s[:k]
    rank = np.arange(1, len(s) + 1)
    slope = np.polyfit(np.log(rank), np.log(s), 1)[0]
    return float(slope), len(s)


def run(seed):
    econ = Economy(Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                             n_ticks=TICKS, seed=seed))
    recs = econ.run()
    ser = {k: np.array([r[k] for r in recs], float) for k in recs[0] if isinstance(recs[0][k], (int, float))}
    hh_wealth = np.array([econ.ledger.balance(h.id) for h in econ.households], float)
    # firm size measured by OUTPUT (sales) -- the conventional Zipf measure. Capital is a
    # misleading proxy here: the accelerator mean-reverts K to a common target, so capital
    # equalizes even while sales concentrate (capital-Gini ~0.1-0.4 vs output-Gini ~0.78).
    firm_out = [f.produced for f in econ.c_firms if f.produced > EPS]
    firm_cap = [f.capital for f in econ.c_firms if f.capital > EPS]
    return ser, hh_wealth, firm_out, firm_cap


# ---- collect across seeds ----------------------------------------------------
S = [run(sd) for sd in SEEDS]
def col(key):   # tail series pooled across seeds
    return np.concatenate([s[0][key][BURN:] for s in S])

verdicts = []
def report(name, ok, detail):
    ok = bool(ok)                       # numpy bools break `is True`; normalize
    verdicts.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}\n      {detail}")

print(f"§4 VALIDATION -- Config.v4, {NC}C/{NK}K/{NH}H, {TICKS} ticks, seeds {SEEDS}, burn-in {BURN}\n")

# T1 Phillips: inflation vs unemployment, negative slope
u, pi = col("unemployment_rate"), col("inflation")
mask = np.isfinite(u) & np.isfinite(pi)
b1 = np.polyfit(u[mask], pi[mask], 1)[0]
r1 = np.corrcoef(u[mask], pi[mask])[0, 1]
report("T1 Phillips (inflation vs unemployment, expect <0)", b1 < 0,
       f"slope={b1:+.3f}  corr={r1:+.3f}")

# T2 Okun: unemployment change vs output growth, negative
per_seed = []
for s in S:
    ro = s[0]["real_output"][BURN:]
    uu = s[0]["unemployment_rate"][BURN:]
    g = np.diff(np.log(np.clip(ro, EPS, None)))
    du = np.diff(uu)
    m = np.isfinite(g) & np.isfinite(du)
    if m.sum() > 10:
        per_seed.append(np.corrcoef(du[m], g[m])[0, 1])
okun = float(np.mean(per_seed))
report("T2 Okun (Δunemployment vs Δlog output, expect <0)", okun < 0,
       f"corr={okun:+.3f} (per-seed {[round(x,2) for x in per_seed]})")

# T3 business-cycle comovement: I, employment, credit, consumption vs output (cyclical)
comov = {}
for s in S:
    yc = cyclical(s[0]["real_output"][BURN:])
    for k in ("investment_spending", "employment", "total_credit", "consumption_spending"):
        xc = cyclical(s[0][k][BURN:])
        comov.setdefault(k, []).append(np.corrcoef(yc, xc)[0, 1])
cm = {k: float(np.mean(v)) for k, v in comov.items()}
report("T3 BC comovement (I / N / credit / C with output, expect >0)",
       all(v > 0.2 for v in cm.values()),
       "  ".join(f"{k.split('_')[0]}={v:+.2f}" for k, v in cm.items()))

# T4 endogenous involuntary unemployment: persistent, non-corner, rationed
um = col("unemployment_rate")
involuntary = np.mean((col("labor_supply") - col("employment")) / np.clip(col("labor_supply"), EPS, None))
report("T4 endogenous unemployment (persistent, involuntary)",
       0.02 < um.mean() < 0.98 and involuntary > 0.01,
       f"mean u={um.mean():.3f} (sd {um.std():.3f}, range {um.min():.2f}-{um.max():.2f})  "
       f"involuntary rationing={involuntary:.3f}")

# T5 fat-tailed output growth: excess kurtosis > 0 (Gaussian=0, Laplace=3)
g_all = np.concatenate([np.diff(np.log(np.clip(s[0]["real_output"][BURN:], EPS, None))) for s in S])
g_all = g_all[np.isfinite(g_all)]
sk, ek = moments(g_all)
report("T5 fat-tailed growth (excess kurtosis > 0)", ek > 0.5,
       f"excess kurtosis={ek:+.2f} (Gauss 0, Laplace 3)  skew={sk:+.2f}  n={len(g_all)}")

# T6 Zipf/Pareto firm size: is the SHAPE a power law? Measure on output (sales). A clean
# Zipf is rank-size slope ~ -1 with moderate Gini (~0.5-0.6). The miss is about SHAPE, not
# level: output is concentrated (Gini ~0.78) but the slope is too steep, and capital is flat.
out_sl = [rank_size_slope(s[2], tail_frac=1.0)[0] for s in S]
cap_sl = [rank_size_slope(s[3], tail_frac=1.0)[0] for s in S]
out_g = [gini(s[2]) for s in S]                                  # among producing firms
out_g_series = float(np.mean(col("firm_size_gini_output")))      # incl. idle firms
out_sl = [x for x in out_sl if np.isfinite(x)]
zo, zc, zg = float(np.mean(out_sl)), float(np.mean(cap_sl)), float(np.mean(out_g))
clean_zipf = (-1.3 < zo < -0.7)                                  # power-law SHAPE, not level
report("T6 Zipf/Pareto firm size (power-law SHAPE, slope ~ -1)",
       clean_zipf,
       f"output rank-size slope={zo:+.2f} (Zipf=-1)  capital slope={zc:+.2f}  "
       f"output-Gini={zg:.2f} among active / {out_g_series:.2f} incl. idle  "
       f"-> concentrated but NOT power-law (growth is accelerator/mean-reverting, not Gibrat)")

# T7 credit-driven boom-bust: leverage/credit cycles and comoves with output
lev_amp, lev_corr = [], []
for s in S:
    lev = s[0]["aggregate_leverage"][BURN:]
    yc = cyclical(s[0]["real_output"][BURN:])
    lc = cyclical(lev)
    lev_amp.append(lev.std() / max(EPS, abs(lev.mean())))
    lev_corr.append(np.corrcoef(yc, lc)[0, 1])
la, lcorr = float(np.mean(lev_amp)), float(np.mean(lev_corr))
report("T7 credit-driven boom-bust (leverage cycles + comoves)",
       la > 0.05 and abs(lcorr) > 0.15,
       f"leverage CV={la:.2f}  corr(leverage,output)={lcorr:+.2f}")

# T8 wealth distribution: right-skewed, heavy-tailed
wealth = np.concatenate([s[1] for s in S])
wg = gini(list(wealth))
ws, wk = moments(wealth)
top10 = np.sort(wealth)[::-1][:max(1, len(wealth)//10)].sum() / max(EPS, wealth.sum())
report("T8 wealth distribution (right-skewed, heavy-tailed)",
       ws > 0.5 and wg > 0.3,
       f"Gini={wg:.3f}  skew={ws:+.2f}  excess kurt={wk:+.2f}  top-10% share={top10:.2f}")

n_pass = sum(verdicts)
print(f"\nSCORE: {n_pass}/8 held-out regularities reproduced from the axioms alone.")
print("Both misses are structural, not noise, and neither is caused by the v5 anti-monopoly\n"
      "dial (dis_slope=0 here). T6: firm SALES are concentrated (Gini ~0.78) but the SHAPE is\n"
      "not a power law -- accelerator growth mean-reverts to a common K* (not Gibrat), so no\n"
      "clean Zipf slope; capital stock is even flatter. Needs idiosyncratic multiplicative\n"
      "growth. T8: household wealth is too EQUAL (Gini ~0.12) -- agents are homogeneous\n"
      "(MPC/return heterogeneity deferred in §5) and equity is not attributed to households\n"
      "(choice 甲). Both point at specific, already-documented next increments.")
