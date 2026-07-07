"""Stage-B gate (pre-registered #2): coupon+theta grows the bond stock WITHOUT re-freezing (u stays low)."""
import numpy as np, dataclasses
from config import Config
from economy import Economy

NH, T = 1000, 2500
def run(factory, **kw):
    cfg = factory(n_firms_c=100, n_firms_k=50, n_households=NH, n_ticks=T, seed=0, **kw)
    econ = Economy(cfg); rec = econ.run()
    econ.ledger.assert_conserved(); econ.ledger.assert_reserves_conserved(); econ._assert_securities_identities()
    u = np.array([r.get('unemployment_rate',np.nan) for r in rec])
    peak = 0.0
    return econ, np.nanmean(u[T//2:]), econ._bonds_outstanding

e0,u0,b0 = run(Config.v12, bond_finance_frac=0.0)
e1,u1,b1 = run(Config.v12)                       # v12.1-fix, frac 0.9, thin residual
e2,u2,b2 = run(Config.v123)                      # coupon+theta+maturity
print(f"frac=0.0        : u_late={u0:.4f}  bonds_end={b0:.0f}")
print(f"v12.1-fix f=0.9 : u_late={u1:.4f}  bonds_end={b1:.0f}")
print(f"v123 (coupon+θ)  : u_late={u2:.4f}  bonds_end={b2:.0f}")
ok_u = u2 <= u0 + 0.03
ok_stock = b2 > 5*max(1.0,b1)
print(f"PRE-REG #2: no-refreeze u2({u2:.4f})<=u0+0.03({u0+0.03:.4f}) -> {ok_u}; stock grows b2({b2:.0f})>>b1({b1:.0f}) -> {ok_stock}")
print("PASS" if (ok_u and ok_stock) else "CHECK")
