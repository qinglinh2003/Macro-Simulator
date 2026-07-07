"""Pin the v8.4-vs-v8.5 crisis mechanism. Per config/seed measure:
  - collapse frequency: fraction of steady-state ticks with u>0.9 and u>0.5, and max u;
  - margin fire-sales: margin_deleveraged mean/max, and corr(fire-sale_t, u_{t+1});
  - end-state wipeouts: # households insolvent (net worth <= 0) and max leverage among solvent.
Hypothesis: v8.4 has more frequent/severe u-collapses, driven by margin fire-sales, leaving a fat
tail of insolvent/over-levered households -- v8.5 does not."""
import numpy as np
from multiprocessing import Pool
from config import Config
from economy import Economy

SEEDS = [0, 1, 2, 3, 4]
TICKS, BURN, NC, NK, NH, EPS = 4000, 1000, 200, 100, 2000, 1e-9


def run_seed(args):
    factory, seed = args
    econ = Economy(getattr(Config, factory)(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                                             n_ticks=TICKS, seed=seed))
    rec = econ.run()
    u = np.array([r["unemployment_rate"] for r in rec])[BURN:]
    dl = np.array([r.get("margin_deleveraged", 0.0) for r in rec])[BURN:]
    u_next = u[1:]
    dl_lag = dl[:-1]
    corr = float(np.corrcoef(dl_lag, u_next)[0, 1]) if dl_lag.std() > EPS else float("nan")
    # end-state per-household leverage / solvency
    po = {f.id: f.share_price for f in econ.c_firms}
    nds, levs, insolvent = [], [], 0
    for h in econ.households:
        eq = sum(sh * po.get(fid, 0.0) for fid, sh in h.holdings.items())
        nw = econ.ledger.balance(h.id) + eq - econ.ledger.debt(h.id)
        md = getattr(h, "margin_debt", 0.0)
        if nw <= EPS:
            insolvent += 1
        elif md > EPS:
            levs.append(md / nw)
    return dict(u_frac90=float((u > 0.9).mean()), u_frac50=float((u > 0.5).mean()), u_max=float(u.max()),
                dl_mean=float(dl.mean()), dl_max=float(dl.max()), dl_active=float((dl > EPS).mean()),
                corr_dl_u=corr, insolvent=insolvent, lev_max=(max(levs) if levs else 0.0),
                lev_p99=(float(np.percentile(levs, 99)) if levs else 0.0))


if __name__ == "__main__":
    jobs, tags = [], []
    for fac in ("v84", "v85"):
        for sd in SEEDS:
            jobs.append((fac, sd)); tags.append(fac)
    with Pool(min(len(jobs), 10)) as p:
        out = p.map(run_seed, jobs)
    agg = {"v84": [], "v85": []}
    for tag, r in zip(tags, out):
        agg[tag].append(r)
    for fac, name in [("v84", "v8.4 diffuse"), ("v85", "v8.5 founder")]:
        R = agg[fac]
        m = lambda k: np.mean([r[k] for r in R])
        print(f"\n=== {name} ===  (mean over {len(SEEDS)} seeds)")
        print(f"  collapse freq   u>0.9={m('u_frac90'):.3f}  u>0.5={m('u_frac50'):.3f}  max u={m('u_max'):.3f}")
        print(f"  margin fire-sale mean={m('dl_mean'):.1f}  max={m('dl_max'):.0f}  active-ticks={m('dl_active'):.3f}  corr(fire_t,u_t+1)={m('corr_dl_u'):+.2f}")
        print(f"  end-state       insolvent hh={m('insolvent'):.0f}/{NH}  max lev(solvent)={m('lev_max'):.1f}  p99 lev={m('lev_p99'):.2f}")
