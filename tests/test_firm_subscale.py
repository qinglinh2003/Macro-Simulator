"""v16-L6: sub-person firm scale -- footfall, subscale exit, demand-driven K entry.

The whole-person employment grammar imposes a MINIMUM VIABLE FIRM SCALE. The K
sector at this calibration (~0.1 worker/firm) starved through an information
deadlock: empty shelf -> zero sales -> zero expected demand (§4 holdout catch).
Three mechanisms: (1) footfall -- unmet buy orders enter seller expectations;
(2) subscale exit hazard -- firms below the viability line liquidate, staggered,
demand share concentrating in survivors; (3) K entry from sector retained
earnings when every incumbent is capacity-short. Firm count becomes an emergent
equilibrium. Builders are exempt from (2) by construction.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy

L6 = dict(capital_rationed_signal=True, firm_subscale_exit=True,
          capital_firm_entry=True)


def make_econ(**overrides):
    params = dict(
        seed=7,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=1500,
        labor_matching="persistent",
        labor_suspension=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def test_flags_off_no_l6_effects():
    econ = make_econ()
    for _ in range(200):
        econ.step()
    assert len(econ.k_firms) == 25                      # nobody exits
    assert all(f.rationed_demand == 0.0 for f in econ.firms)
    assert all(f.subscale_ticks == 0 for f in econ.firms)


def test_footfall_keeps_demand_observable():
    """With zero K inventory and zero sales, expectations must NOT spiral to zero."""
    def k_demand_at(t_end, flag):
        econ = make_econ(capital_rationed_signal=flag)
        for _ in range(t_end):
            econ.step()
        return sum(f.demand_expected for f in econ.k_firms)

    starved = k_demand_at(400, False)                   # the deadlock: decays toward 0
    seen = k_demand_at(400, True)                       # footfall: orders stay visible
    assert seen > 2.0 * max(starved, 1e-9)


def test_subscale_exit_consolidates_but_never_extinguishes():
    econ = make_econ(**{**L6, "capital_firm_entry": False})
    for _ in range(900):
        econ.step()
    assert 1 <= len(econ.k_firms) < 25                  # consolidation happened...
    assert len(econ.k_firms) >= 1                       # ...the floor held
    assert len(econ.c_firms) >= 1


def test_k_sector_revives_whole_person_jobs():
    """The end-to-end cure: with L6 on, the K sector employs WHOLE PERSONS again,
    produces, and the aggregate capital stock stops bleeding."""
    econ = make_econ(**L6)
    k_aggr = []
    for t in range(1500):
        econ.step()
        if t in (400, 1499):
            k_aggr.append(sum(f.capital for f in econ.c_firms))
    lm = econ.labor_market
    k_ids = {f.id for f in econ.k_firms}
    k_workers = [pid for pid, j in lm.jobs.items() if j.firm_id in k_ids]
    assert len(k_workers) >= 1                          # real persons, on K rosters
    assert sum(f.produced for f in econ.k_firms) > 0.0 or \
           sum(f.inventory for f in econ.k_firms) > 0.0
    assert k_aggr[1] > k_aggr[0]                        # capital grows, not decays


def test_entry_reopens_the_sector_after_consolidation():
    econ = make_econ(**L6)
    max_after_min = min_seen = 25
    for _ in range(2000):
        econ.step()
        n = len(econ.k_firms)
        if n < min_seen:
            min_seen = n
            max_after_min = n
        max_after_min = max(max_after_min, n)
    assert min_seen < 25                                # consolidation
    assert max_after_min > min_seen                     # entry re-expanded the sector
