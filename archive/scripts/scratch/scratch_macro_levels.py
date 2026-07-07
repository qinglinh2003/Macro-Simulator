"""Core macro sanity: v8.4 (pro-rata) vs v8.3 (equal-split). Parallel over all seeds/configs."""
import numpy as np
from prun import run_jobs

SEEDS = [0, 1, 2, 3]
TICKS, BURN = 4000, 1000
NC, NK, NH = 200, 100, 2000


def reduce(rec):
    rec = rec[BURN:]
    u = np.array([r["unemployment_rate"] for r in rec])
    y = np.array([r["real_output"] for r in rec])
    pi = np.array([r["inflation"] for r in rec])
    return dict(u=u.mean(), u_cv=u.std() / max(1e-9, u.mean()),
                infl=pi.mean(), y=y.mean(), y_cv=y.std() / max(1e-9, y.mean()))


if __name__ == "__main__":
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS)
    jobs, tags = [], []
    for fac in ("v83", "v84"):
        for sd in SEEDS:
            jobs.append((fac, {**base, "seed": sd})); tags.append(fac)
    recs = run_jobs(jobs)
    res = {"v83": [], "v84": []}
    for tag, rec in zip(tags, recs):
        res[tag].append(reduce(rec))
    for fac, name in [("v83", "v8.3 equal-split"), ("v84", "v8.4 pro-rata")]:
        R = res[fac]
        agg = {k: (np.mean([r[k] for r in R]), np.std([r[k] for r in R])) for k in R[0]}
        print(f"\n=== {name} ===")
        print(f"  unemployment   mean={agg['u'][0]:.3f} ± {agg['u'][1]:.3f}   (cyclical CV={agg['u_cv'][0]:.2f})")
        print(f"  inflation/tick mean={agg['infl'][0]:+.4f} ± {agg['infl'][1]:.4f}")
        print(f"  real output    mean={agg['y'][0]:.0f} ± {agg['y'][1]:.0f}   (cyclical CV={agg['y_cv'][0]:.2f})")
