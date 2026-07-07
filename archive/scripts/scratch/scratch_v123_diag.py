"""Why didn't banks buy? Instrument interbank flag, gov_debt, gap, remaining, bank headroom."""
from config import Config
from economy import Economy

cfg = Config.v123(n_firms_c=100, n_firms_k=50, n_households=1000, n_ticks=600, seed=0, bank_bond_appetite=0.5)
print("interbank flag:", cfg.interbank, "| bank_bond_appetite:", cfg.bank_bond_appetite, "| bank_min_capital:", cfg.bank_min_capital, "| frac:", cfg.bond_finance_frac)
econ = Economy(cfg)
# run to near end, then inspect one issuance manually
econ.run(590)
led = econ.ledger
gov_debt = econ._bonds_outstanding - led.balance(econ._fiscal)
gap = cfg.bond_finance_frac*gov_debt - econ._bonds_outstanding
print(f"gov_debt={gov_debt:.0f}  bonds_out={econ._bonds_outstanding:.0f}  gap(target-held)={gap:.0f}")
for b in econ.banks[:6]:
    print(f"  bank {b.id}: balance={led.balance(b.id):.0f} reserves={led.reserves(b.id):.0f} alive={b.alive} headroom(bal-mincap)={max(0,led.balance(b.id)-cfg.bank_min_capital):.0f}")
