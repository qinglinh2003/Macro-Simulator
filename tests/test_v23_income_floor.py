"""v23: the in-work income floor (a minimum income guarantee).

The unemployment benefit pays for UNSOLD labour (supply - labor_sold - jg_labor): a QUANTITY
rule that insures the jobless and is blind to a worker who sells ALL their labour and still earns
too little. Since v16-L4 made pay = wage * e_i (sigma 0.35) the model manufactures working poor,
and the household behind the last CRITICAL (welfare.deprivation_domain_boundary) is a fully
employed 40-year-old earning 56% of median income with near-zero deposits and zero support.

The floor tops income up to `benefit_income_floor * wage_ref * labour_supply`, tested on INCOME
rather than unsold hours, regardless of employment status.
"""
from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy


def test_income_floor_is_off_by_default():
    cfg = Config.v13(seed=1, n_ticks=5)
    assert cfg.benefit_income_floor == 0.0


def _gov(**over):
    base = dict(seed=1, n_households=40, demographics_population=200, n_firms_c=20, n_firms_k=10,
                n_banks=2, n_ticks=400, government=True, benefit_replacement=0.4,
                job_guarantee=True, jg_wage_ratio=0.5,
                labor_matching="persistent", labor_person_efficiency=True,
                labor_participation=True, efficiency_sigma=0.35)
    base.update(over)
    return Config.v13(**base)


def test_floor_off_is_bit_identical():
    import hashlib, json

    def digest(cfg):
        econ = Economy(cfg)
        h = hashlib.sha256()
        for _ in range(400):
            r = econ.step()
            h.update(json.dumps({k: (round(v, 9) if isinstance(v, float) else v)
                                 for k, v in sorted(r.items())}, default=str).encode())
        return h.hexdigest()[:16]

    assert digest(_gov()) == digest(_gov(benefit_income_floor=0.0))


def test_floor_lifts_the_fully_employed_working_poor_above_the_line():
    """A worker who sells all their labour but earns below the floor must be topped up -- the
    exact case the unemployment benefit misses."""
    econ = Economy(_gov(benefit_income_floor=0.6))
    bridge = econ.demographic_bridge
    for _ in range(400):
        econ.step()

    wage_ref = sum(f.wage for f in econ.firms) / max(1, len(econ.firms))
    floor_rate = econ.policy.benefit_income_floor
    checked = 0
    for h in econ.households:
        if bridge is not None and not bridge.household_has_living_members(h.id):
            continue
        supply = bridge.household_labor_supply(h.id) if bridge is not None else 0.0
        if supply <= 0.0:
            continue
        # after the floor, no household with labour supply ends the tick below its guarantee
        assert h.income_realized >= floor_rate * wage_ref * supply - 1e-6
        checked += 1
    assert checked > 0


def test_floor_conserves_money():
    econ = Economy(_gov(benefit_income_floor=0.6))
    for _ in range(400):
        r = econ.step()
    broad = max(rr for rr in [r.get("broad_money", r.get("total_money", 1.0))])
    assert abs(r.get("conservation_drift", 0.0)) < 1e-6 * broad
