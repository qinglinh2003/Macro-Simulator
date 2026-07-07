"""Verify the user's capital-ratio prescription at FULL NH2000/4000t scale."""
import numpy as np
from config import Config
from economy import Economy
NC,NK,NH,T = 200,100,2000,4000
def run(label, **kw):
    cfg = Config.v124(n_firms_c=NC,n_firms_k=NK,n_households=NH,n_ticks=T,seed=0,**kw)
    econ=Economy(cfg); rec=econ.run()
    econ.ledger.assert_conserved(); econ._assert_securities_identities()
    alive=np.array([r.get('banks_alive',np.nan) for r in rec]); u=np.array([r.get('unemployment_rate',np.nan) for r in rec])
    peak=max(r.get('peak_intraday_overdraft',0.0) for r in rec)
    bb=sum(l['face'] for l in econ._bonds if l['holder'] in econ._bank_ids)
    print(f"{label:34s} alive_end={alive[-1]:.0f} min[T/2:]={np.nanmin(alive[T//2:]):.0f} mean[T/2:]={np.nanmean(alive[T//2:]):.1f} deaths={econ._bank_deaths} u={np.nanmean(u[T//2:]):.4f} peak_od={peak:.0f} bank_bonds={bb:.0f}")

run("v124 base (aggressive)")
run("v124 HEALTHY (user rx)", bank_target_capital_ratio=0.18, bank_exposure_limit=0.15,
    omo_reserve_target=1.0, omo_drain_frac=0.03, bank_bond_appetite=0.03, bank_bond_duration_limit=0.5, bond_maturity=4)
