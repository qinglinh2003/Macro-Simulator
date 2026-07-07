"""Trace WHY late-sample u rises in v12. frac=0 vs frac=0.9, one seed, 4000t."""
import numpy as np, dataclasses
from config import Config
from economy import Economy

NC,NK,NH,TICKS,SEED = 200,100,2000,4000,0

def run(frac):
    cfg = Config.v12(n_firms_c=NC,n_firms_k=NK,n_households=NH,n_ticks=TICKS,seed=SEED)
    cfg = dataclasses.replace(cfg, bond_finance_frac=frac)
    return Economy(cfg).run()

def col(rec,k): return np.array([r.get(k,float('nan')) for r in rec],float)

for frac in (0.0,0.9):
    rec = run(frac)
    print(f"=== frac={frac} ===")
    keys = ['unemployment_rate','effective_unemployment','consumption_c','hh_bond_wealth','bonds_outstanding','banks_alive','gov_debt']
    have = [k for k in keys if not np.isnan(col(rec,k)).all()]
    print("   have:", have)
    for lo,hi in [(0,1000),(1000,2000),(2000,3000),(3000,4000)]:
        parts=[]
        for k in have:
            parts.append(f"{k}={np.nanmean(col(rec,k)[lo:hi]):.4g}")
        print(f"  t[{lo}:{hi}] " + "  ".join(parts))
