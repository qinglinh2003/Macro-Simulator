"""Which credit component decoupled from output under pro-rata dividends?
Decompose total_credit = firm_credit + household_debt + margin_debt and compare each component's
cyclical comovement with output, v8.3 (equal-split) vs v8.4 (pro-rata)."""
import numpy as np
from config import Config
from economy import Economy

SEEDS = [0, 1, 2, 3]
TICKS, BURN = 4000, 1000
NC, NK, NH = 200, 100, 2000


def cyclical(x, w=201):
    x = np.asarray(x, float)
    trend = np.convolve(x, np.ones(w) / w, mode="same")
    return (x - trend)[w // 2: -(w // 2)]


def comov(cfg_factory):
    comps = {"firm_credit": [], "household_debt": [], "margin_debt": [], "total_credit": []}
    for sd in SEEDS:
        rec = Economy(cfg_factory(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                                  n_ticks=TICKS, seed=sd)).run()
        y = cyclical([r["real_output"] for r in rec][BURN:])
        tot = np.array([r["total_credit"] for r in rec])
        hh = np.array([r.get("household_debt_total", 0.0) for r in rec])
        mg = np.array([r.get("household_margin_debt", 0.0) for r in rec])
        series = {"firm_credit": tot - hh - mg, "household_debt": hh,
                  "margin_debt": mg, "total_credit": tot}
        for k, s in series.items():
            sc = cyclical(s[BURN:])
            comps[k].append(float(np.corrcoef(y, sc)[0, 1]) if sc.std() > 1e-9 else 0.0)
    return {k: (np.mean(v), np.std(v)) for k, v in comps.items()}


for name, fac in [("v8.3 equal-split", Config.v83), ("v8.4 pro-rata", Config.v84)]:
    print(f"\n=== {name} ===  (cyclical comovement with output)")
    for k, (m, s) in comov(fac).items():
        print(f"  {k:16s} corr={m:+.2f} ± {s:.2f}")
