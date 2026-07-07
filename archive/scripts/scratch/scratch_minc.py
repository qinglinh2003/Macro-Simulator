"""Does enabling BIRTHS (lower bank_min_capital) + thick capital stabilize banks at full scale?"""
import numpy as np
from config import Config
from economy import Economy
NC,NK,NH,T = 200,100,2000,4000
HEALTHY = dict(bank_target_capital_ratio=0.18, bank_exposure_limit=0.15,
               omo_reserve_target=1.0, omo_drain_frac=0.03, bank_bond_appetite=0.03,
               bank_bond_duration_limit=0.5, bond_maturity=4)
def run(mc):
    cfg=Config.v124(n_firms_c=NC,n_firms_k=NK,n_households=NH,n_ticks=T,seed=0,bank_min_capital=mc,**HEALTHY)
    econ=Economy(cfg); rec=econ.run()
    econ.ledger.assert_conserved()
    alive=np.array([r.get('banks_alive',np.nan) for r in rec])
    u=np.array([r.get('unemployment_rate',np.nan) for r in rec])
    print(f"min_cap={mc:5.0f}: alive_end={alive[-1]:.0f} min[T/2:]={np.nanmin(alive[T//2:]):.0f} mean[T/2:]={np.nanmean(alive[T//2:]):.1f} births={econ._bank_births} deaths={econ._bank_deaths} u={np.nanmean(u[T//2:]):.4f}")
for mc in (400.0, 150.0):
    run(mc)
