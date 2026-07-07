"""Isolate the collapse: is it the run cascade (needs LoLR) or insolvency/bug? Toggle bank_runs."""
import numpy as np
from config import Config
from economy import Economy
NH, T = 1000, 1200
def run(ap, runs):
    cfg = Config.v123(n_firms_c=100, n_firms_k=50, n_households=NH, n_ticks=T, seed=0,
                      bank_bond_appetite=ap, bank_runs=runs)
    econ = Economy(cfg)
    traj=[]
    for i in range(T):
        econ.step()
        if i % 150 == 0 or (i<20):
            traj.append((i, econ.metrics_alive() if hasattr(econ,'metrics_alive') else sum(1 for b in econ.banks if b.alive)))
    econ.ledger.assert_conserved(); econ._assert_securities_identities()
    bids=econ._bank_ids
    bb=sum(l['face'] for l in econ._bonds if l['holder'] in bids)
    return sum(1 for b in econ.banks if b.alive), bb, traj
for runs in (True, False):
    alive,bb,traj = run(0.02, runs)
    print(f"appetite=0.02 bank_runs={runs}: alive_end={alive} bank_bonds={bb:.0f}")
    print("   alive traj:", [(t,a) for t,a in traj])
