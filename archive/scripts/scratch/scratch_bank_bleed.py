"""Diagnose the NH2000/4000t bank bleed: births/deaths, founder pool, policy rate, ROE-vs-hurdle over time."""
import numpy as np
from config import Config
from economy import Economy
NC,NK,NH,T = 200,100,2000,4000
cfg = Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=T, seed=0)
econ = Economy(cfg)
for i in range(T):
    econ.step()
    if i % 500 == 0 or i in (100,250):
        alive=[b for b in econ.banks if b.alive]
        elig=sum(1 for h in econ.households if econ.ledger.balance(h.id)+econ._hh_bond_value(h.id) >= cfg.bank_min_capital)
        tot_cap=sum(max(0,econ.ledger.balance(b.id)) for b in alive)
        tot_inc=sum(b.interest_income for b in alive)
        roe = tot_inc/tot_cap if tot_cap>0 else 0
        births=econ._bank_births; deaths=econ._bank_deaths
        print(f"t={i:4d} alive={len(alive)} births={births} deaths={deaths} rate={econ._rate:.4f} roe={roe:.4f} roe/r={roe/max(econ._rate,1e-4):.2f} eligible_founders={elig}")
