"""Does founder-owned genesis (v8.5) PERSIST or erode via rebalancing? Track equity ownership
concentration over time vs the diffuse v8.4 baseline. Also the T8 wealth-tail measures."""
import numpy as np
from prun import run_jobs

SEEDS = [0, 1]
TICKS, NC, NK, NH = 4000, 200, 100, 2000


def windows(rec, key):
    v = np.array([r.get(key, np.nan) for r in rec])
    return v[50:150].mean(), v[1900:2100].mean(), v[-200:].mean()   # early / mid / late


if __name__ == "__main__":
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS)
    jobs, tags = [], []
    for fac in ("v84", "v85"):
        for sd in SEEDS:
            jobs.append((fac, {**base, "seed": sd})); tags.append(fac)
    recs = run_jobs(jobs)
    agg = {"v84": {"own": [], "wtail": []}, "v85": {"own": [], "wtail": []}}
    for tag, rec in zip(tags, recs):
        agg[tag]["own"].append(windows(rec, "equity_ownership_gini"))
        agg[tag]["wtail"].append(windows(rec, "hh_wealth_gini_incl_equity"))
    for fac, name in [("v84", "v8.4 diffuse genesis"), ("v85", "v8.5 founder genesis")]:
        own = np.array(agg[fac]["own"]).mean(axis=0)
        wt = np.array(agg[fac]["wtail"]).mean(axis=0)
        print(f"\n=== {name} ===  (mean over {len(SEEDS)} seeds)")
        print(f"  equity ownership Gini   early={own[0]:.3f}  mid={own[1]:.3f}  late={own[2]:.3f}")
        print(f"  wealth Gini incl equity early={wt[0]:.3f}  mid={wt[1]:.3f}  late={wt[2]:.3f}")
