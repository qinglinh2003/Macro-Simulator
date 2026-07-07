"""Did issuance fire? Track PEAK bonds_outstanding + issuance events, v12 vs v123, two scales."""
import numpy as np
from config import Config
from economy import Economy

def probe(factory, label, NH, T):
    cfg = factory(n_firms_c=60, n_firms_k=30, n_households=NH, n_ticks=T, seed=0)
    econ = Economy(cfg)
    peak=0.0; peak_lots=0; issued_ticks=0; last_gd=0.0
    for _ in range(T):
        econ.step()
        b=econ._bonds_outstanding
        if b>peak: peak=b
        if len(econ._bonds)>peak_lots: peak_lots=len(econ._bonds)
        last_gd = econ._bonds_outstanding - econ.ledger.balance(econ._fiscal)
    print(f"{label} NH{NH}/{T}t: peak_bonds={peak:.0f} peak_lots={peak_lots} end_bonds={econ._bonds_outstanding:.0f} gov_debt={last_gd:.0f}")

probe(Config.v12,  "v12 (mat1)", 400, 1500)
probe(Config.v123, "v123(mat8)", 400, 1500)
probe(Config.v12,  "v12 (mat1)", 2000, 1500)
probe(Config.v123, "v123(mat8)", 2000, 1500)
