"""Stage-2 gate: OMO drains reserves -> the LATENT interbank market ACTIVATES; conservation holds; off=latent."""
import numpy as np
from config import Config
from economy import Economy
NH, T = 800, 1500
def run(omo, target=0.3):
    cfg = Config.v123(n_firms_c=80, n_firms_k=40, n_households=NH, n_ticks=T, seed=0,
                      omo=omo, omo_reserve_target=target)
    econ = Economy(cfg); rec = econ.run()
    econ.ledger.assert_conserved(); econ.ledger.assert_reserves_conserved(); econ._assert_securities_identities()
    peak = max(r.get("peak_intraday_overdraft", 0.0) for r in rec)
    ibvol = max(r.get("interbank_volume", 0.0) for r in rec)
    br = sum(econ.ledger.reserves(b.id) for b in econ.banks if b.alive)
    u = np.array([r.get('unemployment_rate',np.nan) for r in rec])
    alive = sum(1 for b in econ.banks if b.alive)
    return peak, ibvol, br, np.nanmean(u[T//2:]), alive, econ._cb_absorbed, econ.ledger._reserve_M
p0,v0,r0,u0,a0,cb0,M0 = run(False)
p1,v1,r1,u1,a1,cb1,M1 = run(True)
print(f"OMO off: peak_overdraft={p0:.1f} ib_volume={v0:.1f} bank_reserves={r0:.0f} u={u0:.4f} alive={a0} reserve_M={M0:.0f}")
print(f"OMO on : peak_overdraft={p1:.1f} ib_volume={v1:.1f} bank_reserves={r1:.0f} u={u1:.4f} alive={a1} cb_absorbed={cb1:.0f} reserve_M={M1:.0f}")
print(f"GATE: interbank ACTIVATED (overdraft>0 & vol>0) -> {p1>1 and v1>1}; reserves drained -> {r1<0.6*r0}; conserved -> True")
