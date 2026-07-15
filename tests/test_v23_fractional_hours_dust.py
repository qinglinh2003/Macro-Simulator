"""v23: fractional hour allocations must not manufacture float-dust jobs.

Every allocation site tested hours against EPS (~1e-9), a FLOAT-DUST threshold rather than an
economic one, while the downstream pay guard also tested `rate * hours` against EPS. The two
were mathematically inconsistent: a job whose hours sat just above EPS produced pay BELOW EPS
for any wage rate under 1.0, and the "non-positive pay" assertion then killed the whole run.

Observed in the 2191-tick causal matrix: baseline_s1 died with
    AssertionError: fractional Job generated non-positive pay: 9.201665378716538e-10
"""
from __future__ import annotations

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.labor.persistent import MIN_JOB_HOURS


def test_min_job_hours_sits_far_above_float_dust():
    from macro_sim.markets.matching import EPS
    assert MIN_JOB_HOURS > EPS * 100, "the job floor must not be a float-dust threshold"
    # a job at the floor still pays a real cash flow for any plausible wage rate
    assert MIN_JOB_HOURS * 0.01 > EPS, "pay at the floor must stay above the pay guard"


def test_no_dust_jobs_survive_a_fractional_run():
    """Every live fractional Job must clear the economic floor -- no nanosecond employment."""
    from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
    params = dict(FULL_FRONTIER_FLAGS)
    params.update(seed=1, n_households=50, demographics_population=300, n_firms_c=30,
                  n_firms_k=15, n_banks=4, n_ticks=400)
    econ = Economy(Config.v13(**params))
    for _ in range(400):
        econ.step()
        for job in econ.labor_market.jobs.values():
            assert job.hours > MIN_JOB_HOURS or job.hours == 0.0, (
                f"dust job survived: person {job.person_id} at {job.hours} FTE"
            )


def test_frontier_seed_1_survives_the_horizon_that_crashed():
    """baseline_s1 is the seed that died at 2191 ticks. A shorter but representative horizon
    must now run clean through the fractional labour phase."""
    from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
    params = dict(FULL_FRONTIER_FLAGS)
    params.update(seed=1, n_households=50, demographics_population=500, n_firms_c=50,
                  n_firms_k=25, n_banks=4, n_ticks=900)
    econ = Economy(Config.v13(**params))
    for _ in range(900):
        econ.step()   # must not raise "fractional Job generated non-positive pay"
