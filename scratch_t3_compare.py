"""Is v8.4's T3 fail (credit comovement +0.14) a pro-rata effect or T3 seed-noise?
Run v8.3 (equal split) vs v8.4 (pro-rata) on the SAME 6 seeds; report per-seed credit-output
cyclical comovement + the full four-way T3 tally. If both straddle the 0.2 cutoff with overlapping
spread, it's noise (the known-fragile T3), not a mechanism effect."""
import numpy as np
from config import Config
from economy import Economy

SEEDS = [0, 1, 2, 3, 4, 5]
TICKS, BURN = 4000, 1000
NC, NK, NH = 200, 100, 2000
KEYS = ("investment_spending", "employment", "total_credit", "consumption_spending")


def cyclical(x, w=201):
    x = np.asarray(x, float)
    k = np.ones(w) / w
    trend = np.convolve(x, k, mode="same")
    return (x - trend)[w // 2: -(w // 2)]


def t3(cfg_factory):
    per = {k: [] for k in KEYS}
    for sd in SEEDS:
        rec = Economy(cfg_factory(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                                  n_ticks=TICKS, seed=sd)).run()
        series = {k: [r[k] for r in rec] for k in KEYS + ("real_output",)}
        yc = cyclical(series["real_output"][BURN:])
        for k in KEYS:
            per[k].append(float(np.corrcoef(yc, cyclical(series[k][BURN:]))[0, 1]))
    return per


for name, fac in [("v8.3 equal-split", Config.v83), ("v8.4 pro-rata", Config.v84)]:
    per = t3(fac)
    print(f"\n=== {name} ===")
    for k in KEYS:
        v = np.array(per[k])
        print(f"  {k.split('_')[0]:14s} mean={v.mean():+.2f}  sd={v.std():.2f}  per-seed={[round(x,2) for x in v]}")
    means = {k: np.mean(per[k]) for k in KEYS}
    npass = sum(1 for sd in range(len(SEEDS)) if all(per[k][sd] > 0.2 for k in KEYS))
    print(f"  T3 all>0.2 on the 6-seed MEAN: {all(m > 0.2 for m in means.values())}  |  per-seed pass count: {npass}/{len(SEEDS)}")
