"""Confirm the surprise: diseconomy de-concentrates at m=1, NOT m>=2. More seeds +
mechanism check (under m>=2 is the biggest-output firm still the cheapest-priced?
if so the capital cost-advantage beats the diseconomy penalty -> winner stays)."""
import numpy as np
from config import Config
from economy import Economy

SEEDS = range(6)
TICKS, TAIL = 1000, 150
NC, NK, NH = 80, 40, 800


def run(m, slope, seed):
    cfg = Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS,
                    search_m=m, dis_slope=slope, seed=seed)
    econ = Economy(cfg)
    rec = econ.run()
    t = rec[-TAIL:]
    g = np.mean([r["firm_size_gini_output"] for r in t])
    mk = np.mean([r["avg_markup"] for r in t])
    # mechanism: rank of biggest-output firm by price (0 = cheapest). If ~0, the
    # largest firm is (near) cheapest despite the diseconomy -> capital advantage wins.
    cf = [f for f in econ.firms if f.sells == "consumption" and f.produced > 1e-9]
    rank = np.nan
    if len(cf) >= 3:
        big = max(cf, key=lambda f: f.produced)
        cheaper = sum(1 for f in cf if f.price < big.price)
        rank = cheaper / (len(cf) - 1)   # fraction of producers cheaper than the biggest
    return g, mk, rank


print("cell               Gini(mean±std)   markup         big-firm price-rank")
for m in (1, 5):
    for slope in (0.0, 0.005):
        gs, mks, rs = zip(*(run(m, slope, s) for s in SEEDS))
        rs = [r for r in rs if not np.isnan(r)]
        print(f"m={m} slope={slope:<6}  {np.mean(gs):.3f}±{np.std(gs):.3f}     "
              f"{np.mean(mks):.3f}±{np.std(mks):.3f}   "
              f"rank={np.mean(rs):.2f} (0=biggest is cheapest)")
