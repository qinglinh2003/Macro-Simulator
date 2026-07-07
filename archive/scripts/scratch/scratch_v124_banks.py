"""Which lever kills the banks? Ablate from v12 (healthy) -> v124, track banks_alive."""
import numpy as np
from config import Config
from economy import Economy
NH, T = 1000, 2500
def probe(label, factory, **kw):
    cfg = factory(n_firms_c=100, n_firms_k=50, n_households=NH, n_ticks=T, seed=0, **kw)
    econ = Economy(cfg); rec = econ.run()
    alive = np.array([r.get('banks_alive', np.nan) for r in rec])
    u = np.array([r.get('unemployment_rate', np.nan) for r in rec])
    print(f"{label:38s} alive_end={alive[-1]:.0f} min_alive[T/2:]={np.nanmin(alive[T//2:]):.0f} mean_alive[T/2:]={np.nanmean(alive[T//2:]):.1f} u={np.nanmean(u[T//2:]):.4f}")

probe("v12 (rollover, coupon0 theta0)", Config.v12)
probe("v12 + coupon 0.01", Config.v12, bond_coupon=0.01)
probe("v12 + theta 0.15 (deposit drain)", Config.v12, bond_theta=0.15, bond_maturity=8)
probe("v123 (coupon+theta+maturity)", Config.v123)
probe("v124 (+OMO+lolr+appetite)", Config.v124)
