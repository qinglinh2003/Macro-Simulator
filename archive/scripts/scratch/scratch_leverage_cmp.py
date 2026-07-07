"""Puzzle: ownership Gini converges (v8.4≈v8.5) yet v8.5 is far more stable. Hypothesis: diffuse
genesis forces the system to lever UP (buy equity on margin from scratch); founder genesis endows
equity UNLEVERED, so v8.5 carries persistently less margin debt. Test it directly."""
import numpy as np
from prun import run_jobs

SEEDS = [0, 1, 2, 3, 4]
TICKS, NC, NK, NH = 4000, 200, 100, 2000


def wins(rec, key):
    v = np.array([r.get(key, np.nan) for r in rec])
    return v[50:200].mean(), v[1000:].mean()   # early / steady-state[BURN:]


if __name__ == "__main__":
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS)
    jobs, tags = [], []
    for fac in ("v84", "v85"):
        for sd in SEEDS:
            jobs.append((fac, {**base, "seed": sd})); tags.append(fac)
    recs = run_jobs(jobs)
    keys = ["household_margin_debt", "aggregate_leverage", "avg_household_leverage",
            "total_credit", "share_margin_underwater"]
    agg = {"v84": {k: [] for k in keys}, "v85": {k: [] for k in keys}}
    for tag, rec in zip(tags, recs):
        for k in keys:
            agg[tag][k].append(wins(rec, k))
    for fac, name in [("v84", "v8.4 diffuse"), ("v85", "v8.5 founder")]:
        print(f"\n=== {name} ===  (mean over {len(SEEDS)} seeds; early t50-200 / steady t1000+)")
        for k in keys:
            e, s = np.array(agg[fac][k]).mean(axis=0)
            print(f"  {k:26s} early={e:12.2f}   steady={s:12.2f}")
