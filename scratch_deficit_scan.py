"""If the government MAINTAINS a moderate deficit (deficit-targeting rule), what is unemployment?
Scan gov_deficit_target across seeds; report mean u, realised deficit/GDP, debt/GDP trend, A5."""
import numpy as np
from prun import run_jobs

SEEDS = [0, 1, 2]
NC, NK, NH, TICKS, BURN = 100, 50, 1000, 800, 300
TARGETS = [0.0, 0.02, 0.05, 0.10]


def reduce(rec):
    u = np.array([r["unemployment_rate"] for r in rec][BURN:])
    dgdp = np.array([r.get("gov_deficit_to_gdp", 0.0) for r in rec][BURN:])
    drev = np.array([r.get("gov_deficit_to_revenue", 0.0) for r in rec][BURN:])
    debt_mid = rec[TICKS // 2].get("gov_debt_to_gdp", 0.0)
    debt_end = rec[-1].get("gov_debt_to_gdp", 0.0)
    return dict(u=u.mean(), u_peak=u.max(), u_hi=float((u > 0.5).mean()),
                dgdp=dgdp.mean(), drev=drev.mean(), debt_mid=debt_mid, debt_end=debt_end,
                a5=max(r["conservation_drift"] for r in rec))


if __name__ == "__main__":
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS, gov_consumption_share=0.0)
    jobs, tags = [], []
    for tgt in TARGETS:
        for sd in SEEDS:
            jobs.append(("v9", {**base, "gov_deficit_target": tgt, "seed": sd})); tags.append(tgt)
    recs = run_jobs(jobs)
    by = {t: [] for t in TARGETS}
    for tag, rec in zip(tags, recs):
        by[tag].append(reduce(rec))
    print("deficit_target | mean u | u_peak | %ticks u>0.5 | realised def/GDP | def/rev | debt/GDP mid->end | A5")
    for t in TARGETS:
        R = by[t]
        m = lambda k: np.mean([r[k] for r in R])
        print(f"    {t:.2f}       | {m('u'):.3f}  | {m('u_peak'):.2f}   |    {m('u_hi'):.2f}      | "
              f"{m('dgdp'):+.3f}          | {m('drev'):+.2f}   | {m('debt_mid'):.1f} -> {m('debt_end'):.1f}     | {m('a5'):.0e}")
