"""Stage-C gate (ledger refactor): banks buy bonds w/ reserves -> reserves DRAIN, bank bonds appear, ALL identities hold."""
import numpy as np
from config import Config
from economy import Economy

NH, T = 1000, 2500
def run(appetite):
    cfg = Config.v123(n_firms_c=100, n_firms_k=50, n_households=NH, n_ticks=T, seed=0, bank_bond_appetite=appetite)
    econ = Economy(cfg); rec = econ.run()
    econ.ledger.assert_conserved(); econ.ledger.assert_reserves_conserved(); econ._assert_securities_identities()
    bids = econ._bank_ids
    bank_bonds = sum(l['face'] for l in econ._bonds if l['holder'] in bids)
    bank_res = sum(econ.ledger.reserves(b.id) for b in econ.banks if b.alive)
    u = np.array([r.get('unemployment_rate',np.nan) for r in rec])
    face = sum(l['face'] for l in econ._bonds)
    gd = econ._bonds_outstanding - econ.ledger.balance(econ._fiscal)
    return dict(bonds=econ._bonds_outstanding, bank_bonds=bank_bonds, bank_res=bank_res,
                u=np.nanmean(u[T//2:]), identD=abs(face-econ._bonds_outstanding), govdebt=gd,
                alive=sum(1 for b in econ.banks if b.alive), banksec=econ.ledger.bank_securities)
a0=run(0.0); a5=run(0.5)
print(f"appetite=0.0: bonds={a0['bonds']:.0f} bank_bonds={a0['bank_bonds']:.0f} bank_res={a0['bank_res']:.0f} gov_debt={a0['govdebt']:.0f} u={a0['u']:.4f} alive={a0['alive']}")
print(f"appetite=0.5: bonds={a5['bonds']:.0f} bank_bonds={a5['bank_bonds']:.0f} bank_res={a5['bank_res']:.0f} gov_debt={a5['govdebt']:.0f} u={a5['u']:.4f} alive={a5['alive']} banksec={a5['banksec']:.0f}")
print(f"GATE: bank_bonds>0 -> {a5['bank_bonds']>1}; reserves DRAINED -> {a5['bank_res']<0.8*a0['bank_res']}; A5+identities conserved -> {a5['identD']<1e-6} (identΔ={a5['identD']:.1e})")
