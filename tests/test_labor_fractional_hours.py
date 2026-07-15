"""Persistent private Jobs with a fractional-hours intensive margin."""

from __future__ import annotations

import hashlib
import json
import pickle

import pytest

from macro_sim.config import Config
from macro_sim.diagnostics.models import RunSpec
from macro_sim.diagnostics.scenarios import build_frontier_config, root_cause_matrix
from macro_sim.economy import Economy


def _active_jobs(econ):
    lm = econ.labor_market
    return {
        pid: job for pid, job in lm.jobs.items()
        if pid not in lm.suspended
    }


def test_flag_is_explicit_default_off_and_frontier_only_enables_persistent():
    base = Config.v13(
        n_households=20, demographics_population=80,
        n_firms_c=8, n_firms_k=2, n_banks=1,
    )
    assert base.labor_fractional_hours is False
    with pytest.raises(AssertionError, match="fractional hours need persistent"):
        Config.v13(
            n_households=20, demographics_population=80,
            n_firms_c=8, n_firms_k=2, n_banks=1,
            labor_matching="spot", labor_fractional_hours=True,
        )

    spec = RunSpec(
        name="fractional", seed=0, ticks=5, population=80,
        n_firms_c=8, n_firms_k=2, n_banks=1,
    )
    assert build_frontier_config(spec).labor_fractional_hours is True
    spot = next(item for item in root_cause_matrix(
        ticks=5, population=80, n_firms_c=8, n_firms_k=2, n_banks=1,
    ) if item.scenario == "ablation:spot_labor")
    spot_cfg = build_frontier_config(spot)
    assert spot_cfg.labor_matching == "spot"
    assert spot_cfg.labor_fractional_hours is False


def test_explicit_false_is_bit_identical_to_default_including_rng_streams():
    """The disabled flag is a no-op even as unrelated model patches evolve."""
    def digest(explicit: bool):
        overrides = {"labor_fractional_hours": False} if explicit else {}
        cfg = Config.v13(
            seed=913, n_households=20, n_firms_c=12, n_firms_k=6, n_banks=2,
            demographics_population=120, n_ticks=30,
            labor_matching="persistent", labor_matching_friction=True,
            labor_relationship_wages=True, labor_job_ladder=True,
            labor_person_efficiency=True, labor_suspension=True,
            **overrides,
        )
        econ = Economy(cfg)
        keys = (
            "t", "real_output", "price_index", "employment", "unemployment_rate",
            "wages_paid", "labor_E", "labor_U", "labor_JG", "labor_hires_total",
            "labor_churn_seps_total", "employment_C", "employment_K",
        )
        rows = []
        for _ in range(30):
            record = econ.step()
            rows.append({key: record.get(key) for key in keys})
        state = {
            "rows": rows,
            "jobs": sorted(
                (pid, job.firm_id, str(job.hire_date), job.wage, job.hours)
                for pid, job in econ.labor_market.jobs.items()
            ),
            "rosters": sorted(
                (firm_id, list(person_ids))
                for firm_id, person_ids in econ.labor_market.rosters.items()
            ),
            "suspended": sorted(
                (pid, susp.firm_id, susp.since_tick, susp.wage_at)
                for pid, susp in econ.labor_market.suspended.items()
            ),
            "balances": sorted(econ.ledger._bal.items()),
        }
        return (
            hashlib.sha256(json.dumps(
                state, sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest(),
            hashlib.sha256(pickle.dumps(
                econ._labor_rng.getstate(), protocol=4,
            )).hexdigest(),
            hashlib.sha256(pickle.dumps(
                econ._eff_rng.getstate(), protocol=4,
            )).hexdigest(),
        )

    assert digest(explicit=False) == digest(explicit=True)


def test_frontier_small_k_sector_produces_and_all_units_reconcile():
    spec = RunSpec(
        name="small-k", seed=0, ticks=10, population=200,
        n_firms_c=20, n_firms_k=10, n_banks=2,
    )
    econ = Economy(build_frontier_config(spec))
    for _ in range(9):
        econ.step()
    claims_before = {
        pid: econ.demographic_bridge.claims.balance_sheet(pid).labor_income_tick
        for pid in econ.labor_market.jobs
    }
    record = econ.step()
    lm = econ.labor_market
    accounts = econ.labor_accounts
    active = _active_jobs(econ)

    k_output = sum(firm.produced for firm in econ.k_firms)
    assert k_output > 0.0
    assert active and all(0.0 < job.hours <= 1.0 for job in active.values())
    assert len(active) == len(set(active))       # one private Job per person
    on_rosters = [pid for ids in lm.rosters.values() for pid in ids]
    assert sorted(on_rosters) == sorted(lm.jobs)

    private_fte = sum(job.hours for job in active.values())
    underemployment_hours = sum(1.0 - job.hours for job in active.values())
    assert accounts.employed == pytest.approx(private_fte)
    assert accounts.employed_heads == pytest.approx(len(active))
    assert accounts.underemployment_hours == pytest.approx(underemployment_hours)
    assert accounts.underemployed_heads == pytest.approx(
        sum(job.hours < 1.0 - 1e-6 for job in active.values())
    )
    assert record["labor_underemployment_hours"] == pytest.approx(underemployment_hours)
    assert accounts.employed + accounts.job_guarantee + accounts.unemployed \
        == pytest.approx(accounts.labor_supply)
    assert accounts.private_fte_inflows_total - accounts.private_fte_outflows_total \
        == pytest.approx(accounts.employed)
    assert sum(h.labor_sold for h in econ.households) == pytest.approx(private_fte)
    for household in econ.households:
        supply = econ.demographic_bridge.household_labor_supply(household.id)
        assert household.labor_sold + household.jg_labor == pytest.approx(supply)

    # v23: a person on this roster may hold their PRIMARY job at another firm and only a SECOND
    # contract here, so the contract must be resolved PER FIRM -- reading lm.jobs[pid] would
    # price the other employer's relationship wage and hours into this firm's books.
    partial_k_jobs: list[tuple[int, object]] = []
    for firm in econ.k_firms:
        contracts = {}
        for pid in lm.rosters.get(firm.id, ()):
            if pid in lm.suspended:
                continue
            job = lm.job_at(pid, firm.id)
            if job is not None:
                contracts[pid] = job
        expected_effective = sum(job.hours * lm.e_of(pid) for pid, job in contracts.items())
        expected_wages = sum(job.hours * lm.wage_of(pid, firm) for pid, job in contracts.items())
        assert firm.hired == pytest.approx(expected_effective)
        assert firm.wagebill == pytest.approx(expected_wages)
        partial_k_jobs.extend(
            (pid, job) for pid, job in contracts.items() if job.hours < 1.0
        )

    # A part-time K contract is INCIDENTAL to the scenario: with a calibrated capital-goods
    # productivity the K sector can staff whole workers on a given tick. Only the per-contract
    # claim attribution below needs one; the reconciliation identities above are this test's
    # substance and are checked unconditionally.
    if partial_k_jobs:
        person_id, job = partial_k_jobs[0]
        firm = next(firm for firm in econ.k_firms if firm.id == job.firm_id)
        claim_delta = (
            econ.demographic_bridge.claims.balance_sheet(person_id).labor_income_tick
            - claims_before.get(person_id, 0.0)
        )
        assert claim_delta == pytest.approx(job.hours * lm.wage_of(person_id, firm))
    assert abs(record["conservation_drift"]) < 1e-8


def test_existing_job_hours_shrink_immediately_and_zero_target_removes_link():
    """The enabled intensive margin intentionally does not use layoff hysteresis."""
    econ = Economy(Config.v13(
        seed=4, n_households=20, demographics_population=80,
        n_firms_c=8, n_firms_k=1, n_banks=1, n_ticks=20,
        labor_matching="persistent", labor_fractional_hours=True,
        labor_matching_friction=False, labor_relationship_wages=False,
        labor_person_efficiency=False, labor_suspension=False,
        capital_rationed_signal=False, churn_annual=0.0, lambda_d=1.0,
    ))
    for _ in range(10):
        econ.step()
    lm = econ.labor_market
    firm = econ.k_firms[0]
    active = [pid for pid in lm.rosters.get(firm.id, ()) if pid not in lm.suspended]
    assert active
    person_id = active[0]
    old_hours = lm.jobs[person_id].hours

    # Force a smaller positive next-tick plan. The same relationship is resized;
    # hours changes are FTE flows, not fake head hires/separations.
    firm.inventory = 0.0
    firm.sales_prev = max(1e-5, old_hours * 0.05)
    firm.rationed_prev = 0.0
    heads_before = econ.labor_accounts.hires_total - econ.labor_accounts.layoff_seps_total
    econ.step()
    assert person_id in lm.jobs and lm.jobs[person_id].firm_id == firm.id
    assert 0.0 < lm.jobs[person_id].hours < old_hours
    assert econ.labor_accounts.hires_total - econ.labor_accounts.layoff_seps_total \
        == pytest.approx(heads_before)

    # A true zero target removes the Job instead of retaining a zero-hour pseudo-link.
    firm.inventory = 0.0
    firm.sales_prev = 0.0
    firm.rationed_prev = 0.0
    layoffs_before = econ.labor_accounts.layoff_seps_total
    econ.step()
    assert not any(
        pid not in lm.suspended and lm.jobs[pid].firm_id == firm.id
        for pid in lm.rosters.get(firm.id, ())
    )
    assert econ.labor_accounts.layoff_seps_total > layoffs_before
    assert all(0.0 < job.hours <= 1.0 for job in lm.jobs.values())


@pytest.mark.parametrize(("field", "message"), [
    ("hires_total", "head-flow reconciliation"),
    ("private_fte_inflows_total", "FTE-flow reconciliation"),
])
def test_fractional_head_and_fte_flow_gates_have_teeth_across_ticks(field, message):
    econ = Economy(Config.v13(
        seed=2, n_households=20, demographics_population=80,
        n_firms_c=8, n_firms_k=2, n_banks=1, n_ticks=6,
        labor_matching="persistent", labor_fractional_hours=True,
    ))
    for _ in range(3):
        econ.step()
    setattr(
        econ.labor_accounts, field,
        getattr(econ.labor_accounts, field) + 0.25,
    )
    with pytest.raises(AssertionError, match=message):
        econ.step()
