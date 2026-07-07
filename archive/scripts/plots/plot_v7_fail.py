"""Illustrate v7's failure mode: household credit did NOT concentrate wealth in a few hands.
Instead of 'a few rich + many poor', the drain + debt trap crush EVERYONE toward negative net
worth together. 4 panels: net-worth distribution (OFF vs ON), debt-trap over time, the drain."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from config import Config
from economy import Economy

NC, NK, NH, T = 200, 100, 2000, 3000
K = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=T, seed=0)


def run(credit):
    cfg = Config.v7(household_credit=credit, hh_subsistence=(1.3 if credit else 0.0), **K)
    econ = Economy(cfg); recs = econ.run()
    nw = np.array([econ.ledger.balance(h.id) - econ.ledger.debt(h.id) for h in econ.households])
    return econ, recs, nw


eoff, roff, nw_off = run(False)     # thrift-paradox baseline (credit off)
eon, ron, nw_on = run(True)         # + household credit (the collapse)

fig, ax = plt.subplots(2, 2, figsize=(15, 10))

# (A) sorted net worth per household -- does a rich tail emerge?
a = ax[0, 0]
a.plot(np.sort(nw_off), color="C0", lw=1.6, label="credit OFF (thrift paradox)")
a.plot(np.sort(nw_on), color="C3", lw=1.6, label="credit ON (c_min=1.3)")
a.axhline(0, color="black", lw=0.8, ls="--", alpha=0.6)
a.set_xlabel("households, ranked by net worth"); a.set_ylabel("net worth (deposits − debt)")
a.set_title("(A) No rich tail emerges — credit pushes EVERYONE underwater together")
a.legend(loc="upper left", fontsize=9)

# (B) net-worth distribution
b = ax[0, 1]
lo = min(nw_off.min(), nw_on.min()); hi = max(nw_off.max(), nw_on.max())
bins = np.linspace(lo, hi, 50)
b.hist(nw_off, bins=bins, color="C0", alpha=0.6, label="credit OFF")
b.hist(nw_on, bins=bins, color="C3", alpha=0.6, label="credit ON")
b.axvline(0, color="black", lw=0.8, ls="--", alpha=0.6)
b.set_xlabel("net worth"); b.set_ylabel("# households")
b.set_title("(B) Distribution: credit ON collapses the spread into a negative pile (not a tail)")
b.legend(fontsize=9)

# (C) the debt-deflation trap over time
c = ax[1, 0]
t = [r["t"] for r in ron]
c.plot(t, [r["real_output"] for r in ron], color="C2", lw=1.4, label="output")
c.set_xlabel("tick"); c.set_ylabel("real output", color="C2")
c.tick_params(axis="y", labelcolor="C2")
c2 = c.twinx()
c2.plot(t, [r["household_debt_total"] for r in ron], color="C3", lw=1.4, label="household debt")
c2.set_ylabel("household debt", color="C3"); c2.tick_params(axis="y", labelcolor="C3")
c.set_title("(C) The debt-deflation trap: debt piles up as output collapses to 0")

# (D) the drain: borrowed money leaks to firms (household money share stays low)
d = ax[1, 1]
d.plot([r["t"] for r in roff], [r["hh_money_share"] for r in roff], color="C0", lw=1.4, label="credit OFF")
d.plot([r["t"] for r in ron], [r["hh_money_share"] for r in ron], color="C3", lw=1.4, label="credit ON")
d.set_xlabel("tick"); d.set_ylabel("household share of all money")
d.set_title("(D) The §9 drain: borrowed money leaks to firms — households never hold it")
d.legend(fontsize=9)

fig.suptitle("v7 failure mode — household credit did NOT concentrate wealth; it socialised DEBT "
             "(everyone underwater) via the drain-fed trap", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig("v7_failure.png", dpi=120)
print(f"credit OFF: nw range [{nw_off.min():.1f}, {nw_off.max():.1f}], underwater {np.mean(nw_off<0)*100:.0f}%")
print(f"credit ON : nw range [{nw_on.min():.1f}, {nw_on.max():.1f}], underwater {np.mean(nw_on<0)*100:.0f}%")
print("saved v7_failure.png")
