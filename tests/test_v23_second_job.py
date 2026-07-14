"""v23 P0: the second contract -- making the intensive margin coherent.

Under `labor_fractional_hours` each firm allocates its labour target GREEDILY down its roster,
so exactly one MARGINAL worker per firm ends up part-time. With one Job per person those
residual hours were UNSELLABLE: measured 13-24 FTE idle while firms posted 180-235 vacancies,
the residue draining into the job guarantee. The production shortfall that followed ratcheted
the B3 markup (inventories chronically below target) into runaway inflation.

A person may now hold ONE additional contract at a DIFFERENT firm, capped so their total hours
never exceed 1.0 FTE.

The accounting semantics are the sharp edge, and the hard gates enforce them:
  * a second contract is an INTENSIVE-margin event -- FTE moves, HEADS do not. Booking it as a
    hire breaks the labour head-flow identity.
  * a relationship wage belongs to a CONTRACT, not a person. The old person-scoped `wage_of`
    returned the PRIMARY job's locked wage to whichever firm asked, so a second employer
    budgeted its posted wage but paid the other firm's -- overrunning its live cash.
"""
from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy


def _frontier(seed: int, ticks: int, **over) -> Config:
    from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
    params = dict(FULL_FRONTIER_FLAGS)
    params.update(seed=seed, n_households=50, demographics_population=400, n_firms_c=40,
                  n_firms_k=20, n_banks=4, n_ticks=ticks)
    params.update(over)
    return Config.v13(**params)


def test_second_job_is_off_by_default():
    cfg = Config.v13(seed=1, n_ticks=5)
    assert cfg.labor_second_job is False


def test_nobody_ever_sells_more_than_one_fte():
    """The cap that makes the extra contract economically coherent."""
    econ = Economy(_frontier(2, 500))
    lm = econ.labor_market
    for _ in range(500):
        econ.step()
        for pid in lm.second_jobs:
            assert lm.total_hours(pid) <= 1.0 + 1e-9, (
                f"person {pid} sold {lm.total_hours(pid)} FTE across contracts"
            )


def test_second_contract_is_at_a_different_firm():
    econ = Economy(_frontier(3, 500))
    lm = econ.labor_market
    for _ in range(500):
        econ.step()
        for pid, extra in lm.second_jobs.items():
            primary = lm.jobs.get(pid)
            assert primary is not None, "an extra contract requires a primary job"
            assert extra.firm_id != primary.firm_id, "two contracts at one firm is a resize"


def test_wage_is_priced_per_contract_not_per_person():
    """Each employer pays ITS OWN relationship wage; the primary employer's locked wage must not
    leak into the second employer's bill (that overran live cash and tripped the cash guard)."""
    econ = Economy(_frontier(4, 600))
    lm = econ.labor_market
    firms = {f.id: f for f in econ.firms}
    for _ in range(600):
        econ.step()
        for pid, extra in lm.second_jobs.items():
            firm = firms.get(extra.firm_id)
            if firm is None:
                continue
            expected = extra.wage * lm.e_of(pid)
            assert lm.wage_of(pid, firm) == pytest.approx(expected), (
                "the second employer must be quoted its own contract's wage"
            )


def test_second_contract_recovers_stranded_hours():
    """The economic result the finding is about: a same-seed twin must cut the idle residual
    hours and raise the labour fill rate."""
    off = Economy(_frontier(5, 900, labor_second_job=False))
    on = Economy(_frontier(5, 900, labor_second_job=True))
    recs_off = [off.step() for _ in range(900)]
    recs_on = [on.step() for _ in range(900)]

    def tail(recs, key):
        vals = [float(r.get(key, 0.0)) for r in recs[-200:]]
        return sum(vals) / len(vals)

    idle_off = tail(recs_off, "labor_underemployment_hours")
    idle_on = tail(recs_on, "labor_underemployment_hours")
    assert idle_on < idle_off, f"extra contracts must absorb residual hours: {idle_on} !< {idle_off}"
    assert tail(recs_on, "labor_fill_rate") > tail(recs_off, "labor_fill_rate")
