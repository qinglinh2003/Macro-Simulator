"""Confirm collapse driver: rate trajectory + a bank's equity vs economic_capital + bond P&L."""
import numpy as np
from config import Config
from economy import Economy
cfg = Config.v123(n_firms_c=100, n_firms_k=50, n_households=1000, n_ticks=600, seed=0, bank_bond_appetite=0.02)
print("central_bank:", cfg.central_bank, "| r_interest:", cfg.r_interest, "| bond_coupon:", cfg.bond_coupon)
econ = Economy(cfg)
for i in range(600):
    econ.step()
    if i in (100,250,400,450,500,550):
        alive=[b for b in econ.banks if b.alive]
        bids=econ._bank_ids
        bb=sum(l['face'] for l in econ._bonds if l['holder'] in bids)
        # sample first alive bank
        b0 = alive[0] if alive else None
        if b0:
            bal=econ.ledger.balance(b0.id); ec=econ._bank_economic_capital(b0)
            print(f"t={i}: rate={econ._rate:.4f} n_alive={len(alive)} bonds(bank)={bb:.0f} | bank0 bal={bal:.1f} econ_cap={ec:.1f} (P&L={ec-bal:.1f})")
        else:
            print(f"t={i}: rate={econ._rate:.4f} n_alive=0 bonds(bank)={bb:.0f}")
