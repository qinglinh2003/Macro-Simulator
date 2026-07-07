"""Parallel §4 held-out validation for ANY config factory. Seeds run across all cores.

    PYTHONPATH=.:scripts uv run python scripts/validation/validate_parallel.py v85 0,1,2,3,4

Judges the 8 macro regularities (§4) the model was never told (§0-ii). Nothing is fed back."""
from __future__ import annotations

import sys
from multiprocessing import Pool

import numpy as np
from config import Config
from economy import Economy
from metrics import gini

TICKS, BURN, NC, NK, NH, EPS = 4000, 1000, 200, 100, 2000, 1e-9


def moments(x):
    x = np.asarray(x, float)
    m, s = x.mean(), x.std()
    if s < EPS:
        return 0.0, 0.0
    z = (x - m) / s
    return float((z**3).mean()), float((z**4).mean() - 3.0)


def cyclical(x, w=201):
    x = np.asarray(x, float)
    trend = np.convolve(x, np.ones(w) / w, mode="same")
    return (x - trend)[w:-w]


def rank_size_slope(sizes, tail_frac=1.0):
    s = np.sort(np.asarray([v for v in sizes if v > EPS], float))[::-1]
    if len(s) < 8:
        return np.nan, len(s)
    k = max(8, int(len(s) * tail_frac))
    s = s[:k]
    rank = np.arange(1, len(s) + 1)
    return float(np.polyfit(np.log(rank), np.log(s), 1)[0]), len(s)


def run_seed(args):
    factory, seed = args
    econ = Economy(getattr(Config, factory)(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                                             n_ticks=TICKS, seed=seed))
    recs = econ.run()
    ser = {k: np.array([r[k] for r in recs], float)
           for k in recs[0] if isinstance(recs[0][k], (int, float))}
    po = {f.id: f.share_price for f in econ.c_firms}
    hh_wealth = np.array([econ.ledger.balance(h.id)
                          + sum(sh * po.get(fid, 0.0) for fid, sh in h.holdings.items())
                          - econ.ledger.debt(h.id) for h in econ.households], float)
    firm_out = [f.produced for f in econ.c_firms if f.produced > EPS]
    firm_cap = [f.capital for f in econ.c_firms if f.capital > EPS]
    return ser, hh_wealth, firm_out, firm_cap


def main():
    factory = sys.argv[1] if len(sys.argv) > 1 else "v84"
    seeds = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [0, 1, 2]
    with Pool(min(len(seeds), 10)) as p:
        S = p.map(run_seed, [(factory, sd) for sd in seeds])

    def col(key):
        return np.concatenate([s[0][key][BURN:] for s in S])

    verdicts = []

    def report(name, ok, detail):
        ok = bool(ok); verdicts.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}\n      {detail}")

    print(f"§4 VALIDATION -- Config.{factory}, {NC}C/{NK}K/{NH}H, {TICKS} ticks, seeds {seeds}, burn {BURN}\n")

    u, pi = col("unemployment_rate"), col("inflation")
    m = np.isfinite(u) & np.isfinite(pi)
    b1 = np.polyfit(u[m], pi[m], 1)[0]
    report("T1 Phillips (inflation vs unemployment, expect <0)", b1 < 0,
           f"slope={b1:+.3f}  corr={np.corrcoef(u[m], pi[m])[0,1]:+.3f}")

    per = []
    for s in S:
        g = np.diff(np.log(np.clip(s[0]["real_output"][BURN:], EPS, None)))
        du = np.diff(s[0]["unemployment_rate"][BURN:])
        mm = np.isfinite(g) & np.isfinite(du)
        if mm.sum() > 10:
            per.append(np.corrcoef(du[mm], g[mm])[0, 1])
    report("T2 Okun (Δu vs Δlog output, expect <0)", np.mean(per) < 0,
           f"corr={np.mean(per):+.3f} (per-seed {[round(x,2) for x in per]})")

    comov = {}
    for s in S:
        yc = cyclical(s[0]["real_output"][BURN:])
        for k in ("investment_spending", "employment", "total_credit", "consumption_spending"):
            comov.setdefault(k, []).append(np.corrcoef(yc, cyclical(s[0][k][BURN:]))[0, 1])
    cm = {k: float(np.mean(v)) for k, v in comov.items()}
    report("T3 BC comovement (I / N / credit / C with output, expect >0)",
           all(v > 0.2 for v in cm.values()),
           "  ".join(f"{k.split('_')[0]}={v:+.2f}" for k, v in cm.items()))

    um = col("unemployment_rate")
    inv = np.mean((col("labor_supply") - col("employment")) / np.clip(col("labor_supply"), EPS, None))
    report("T4 endogenous unemployment (persistent, involuntary)",
           0.02 < um.mean() < 0.98 and inv > 0.01,
           f"mean u={um.mean():.3f} (sd {um.std():.3f}, range {um.min():.2f}-{um.max():.2f})  involuntary={inv:.3f}")

    g_all = np.concatenate([np.diff(np.log(np.clip(s[0]["real_output"][BURN:], EPS, None))) for s in S])
    g_all = g_all[np.isfinite(g_all)]
    sk, ek = moments(g_all)
    report("T5 fat-tailed growth (excess kurtosis > 0)", ek > 0.5,
           f"excess kurt={ek:+.2f}  skew={sk:+.2f}  n={len(g_all)}")

    out_sl = [x for x in (rank_size_slope(s[2])[0] for s in S) if np.isfinite(x)]
    cap_sl = [rank_size_slope(s[3])[0] for s in S]
    zo, zc, zg = float(np.mean(out_sl)), float(np.mean(cap_sl)), float(np.mean([gini(s[2]) for s in S]))
    clean = -1.3 < zo < -0.7
    report("T6 Zipf/Pareto firm size (power-law SHAPE, slope ~ -1)", clean,
           f"output slope={zo:+.2f} (Zipf=-1)  capital slope={zc:+.2f}  output-Gini={zg:.2f}  "
           f"-> {'clean power law' if clean else 'concentrated but not power-law'}")

    lev_amp, lev_corr = [], []
    for s in S:
        lev = s[0]["aggregate_leverage"][BURN:]
        lc = cyclical(lev); yc = cyclical(s[0]["real_output"][BURN:])
        lev_amp.append(lev.std() / max(EPS, abs(lev.mean())))
        lev_corr.append(np.corrcoef(yc, lc)[0, 1])
    la, lcorr = float(np.mean(lev_amp)), float(np.mean(lev_corr))
    report("T7 credit-driven boom-bust (leverage cycles + comoves)",
           la > 0.05 and abs(lcorr) > 0.15, f"leverage CV={la:.2f}  corr(leverage,output)={lcorr:+.2f}")

    wealth = np.concatenate([s[1] for s in S])
    ws, wk = moments(wealth)
    top10 = np.sort(wealth)[::-1][:max(1, len(wealth)//10)].sum() / max(EPS, wealth.sum())
    pos = np.sort(wealth[wealth > EPS])[::-1]
    tail = pos[:max(8, len(pos)//10)]
    pslope = (np.polyfit(np.log(np.arange(1, len(tail)+1)), np.log(tail), 1)[0] if len(tail) >= 8 else float("nan"))
    report("T8 wealth distribution (right-skewed, heavy-tailed)", ws > 0.5 and wk > 1.0,
           f"skew={ws:+.2f}  excess kurt={wk:+.2f}  top-10% share={top10:.2f}  upper-tail slope={pslope:+.2f}")

    print(f"\nSCORE: {sum(verdicts)}/8   (Config.{factory}, {len(seeds)} seeds)")


if __name__ == "__main__":
    main()
