"""Stage-A smoke at a DEFICIT scale so bonds actually issue; all identities + A5 must hold."""
import numpy as np, dataclasses
from config import Config
from economy import Economy

def run(**kw):
    cfg = Config.v123(n_firms_c=60, n_firms_k=30, n_households=400, n_ticks=1500, seed=0, **kw)
    econ = Economy(cfg); rec = econ.run(); return econ, rec

econ, rec = run()
led = econ.ledger
led.assert_conserved(); led.assert_reserves_conserved(); econ._assert_securities_identities()
face_sum = sum(l['face'] for l in econ._bonds)
gov_debt = econ._bonds_outstanding - led.balance(econ._fiscal)
mats = sorted(set(l['matures_at']-econ.t for l in econ._bonds))
print(f"OK v123 (maturity 8, coupon 0.01) ran {len(rec)} ticks; gov_debt={gov_debt:.0f}")
print(f"  bonds_outstanding={econ._bonds_outstanding:.1f}  Σface_lots={face_sum:.1f}  n_lots={len(econ._bonds)}  ident_ok(|Δ|={abs(face_sum-econ._bonds_outstanding):.2e})")
print(f"  u(last)={rec[-1].get('unemployment_rate',float('nan')):.4f}  interest_bill(last)={econ._gov_interest_bill:.2f}")
h0 = econ.households[0].id
print(f"  hh0 face={econ._bond_holdings.get(h0,0):.2f} market={econ._hh_bond_value(h0):.2f}  (market<face ⇒ duration discount)")
print(f"  distinct remaining maturities held: {mats[:12]}")
