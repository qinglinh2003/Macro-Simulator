"""Private labor-market phase orchestration."""

from __future__ import annotations

from typing import Any

from macro_sim.behavior import planning as B
from macro_sim.markets.matching import EPS


def run_labor_phase(econ: Any) -> None:
    # Each household supplies 1.0 unit of labor inelastically. Firms are processed
    # in random order (M3(a)); workers are shuffled ONCE per tick and consumed via a
    # shared pointer (a firm processed later faces the depleted tail -> rationing).
    # This is O(N_H+N_F) instead of O(N_F*N_H): no per-firm reshuffle. The specific
    # worker->firm assignment is idiosyncratic noise, integrated out over seeds (M3(a));
    # a fresh shuffle each tick keeps any single household from being persistently
    # favored. A firm hires up to what its LIVE deposits can pay (A4).
    workers = list(econ.households)
    econ.rng.shuffle(workers)
    remaining = [1.0] * len(workers)     # parallel array: worker i's residual supply
    n = len(workers)
    p = 0                                # global pointer into the shuffled worker list

    firms_order = list(econ.firms)
    econ.rng.shuffle(firms_order)
    for f in firms_order:
        need = f.labor_demand_eff
        wage = f.wage
        while need > EPS and p < n:
            affordable = econ.ledger.balance(f.id) / wage
            if affordable <= EPS:
                break                    # firm out of cash -> stop hiring
            avail = remaining[p]
            if avail <= EPS:
                p += 1
                continue
            hire = min(need, avail, affordable)
            if hire <= EPS:
                break
            pay = hire * wage
            econ.ledger.transfer(f.id, workers[p].id, pay)   # wages firm -> household
            f.hired += hire
            f.wagebill += pay
            workers[p].income_realized += pay
            workers[p].labor_sold += hire                    # v9: track employment for the benefit
            remaining[p] -= hire
            need -= hire
            if remaining[p] <= EPS:
                p += 1

        # Production: hired labor yields output added to inventory (§6.3).
        # Sector-aware (B.produce): linear a*N, or Cobb-Douglas A K^alpha N^(1-alpha).
        f.produced = B.produce(f, f.hired, econ._pubcap_factor)
        f.inventory += f.produced
