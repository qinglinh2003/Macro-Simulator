"""Calibrate bank_bond_appetite: banks survive + meaningful bond book + reserves drain + u low."""
import numpy as np
from config import Config
from economy import Economy
NH, T = 1000, 2500
def run(ap):
    cfg = Config.v123(n_firms_c=100, n_firms_k=50, n_households=NH, n_ticks=T, seed=0, bank_bond_appetite=ap)
    econ = Economy(cfg); rec = econ.run()
    econ.ledger.assert_conserved(); econ._assert_securities_identities()
    bids = econ._bank_ids
    bb = sum(l['face'] for l in econ._bonds if l['holder'] in bids)
    br = sum(econ.ledger.reserves(b.id) for b in econ.banks if b.alive)
    u = np.array([r.get('unemployment_rate',np.nan) for r in rec])
    # min alive over the run
    minalive = min(r.get('banks_alive', np.nan) for r in rec[T//4:])
    return ap, bb, br, np.nanmean(u[T//2:]), sum(1 for b in econ.banks if b.alive), minalive
for ap in (0.0, 0.02, 0.05, 0.1, 0.2):
    ap,bb,br,u,alive,minalive = run(ap)
    print(f"appetite={ap:.2f}: bank_bonds={bb:8.0f} bank_reserves={br:9.0f} u={u:.4f} alive_end={alive} min_alive={minalive:.0f}")
