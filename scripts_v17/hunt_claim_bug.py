"""Hunt the seed-2 claim-identity violation (hh 143, claims=-1.26 vs ledger=0.20).

The house diagnosis pattern (v13 estate arc): PHASE-LEVEL identity probes -- wrap
every phase, assert the claim identity after each, report tick+phase+household at
FIRST drift. Runs the exact 6-leg replication sequence under a PINNED hash salt.
Usage: PYTHONHASHSEED=<salt> python hunt_claim_bug.py
"""

from __future__ import annotations

import os
import sys
import traceback

import macro_sim.economy as E
from macro_sim.config import Config

PHASES = [
    "run_planning_phase", "run_credit_phase", "run_labor_phase", "run_energy_phase",
    "run_production_phase", "run_goods_phase", "run_capital_goods_phase",
    "run_settlement_phase", "run_debt_service_phase", "run_housing_market_phase",
    "run_firm_demographics_phase", "run_equity_phase", "run_bank_runs_phase",
    "run_bill_issuance_phase",
]


def arm_probes() -> None:
    for name in PHASES:
        orig = getattr(E, name)

        def make(o, n):
            def wrapped(econ):
                o(econ)
                bridge = getattr(econ, "demographic_bridge", None)
                if bridge is not None:
                    try:
                        bridge.assert_all_claim_identities(econ)
                    except AssertionError as exc:
                        print(f"FIRST DRIFT: t={econ.t} phase={n}: {exc}", flush=True)
                        raise
            return wrapped
        setattr(E, name, make(orig, name))


V16 = dict(labor_matching="persistent", labor_matching_friction=True,
           labor_relationship_wages=True, labor_job_ladder=True,
           labor_person_efficiency=True, capital_rationed_signal=True,
           firm_subscale_exit=True, capital_firm_entry=True)
BASE = dict(n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
            demographics_population=500, n_ticks=3285,
            housing_enabled=True, housing_market_enabled=True,
            energy_enabled=True, energy_household=True, **V16)
SHOCK = dict(energy_shock_at=2555, energy_shock_magnitude=0.4, energy_shock_duration=180)


def leg(tag: str, **extra) -> None:
    econ = E.Economy(Config.v13(**BASE, **extra))
    try:
        econ.run()
        print(f"[{tag}] clean", flush=True)
    except AssertionError:
        print(f"[{tag}] CRASH at t={econ.t} (salt={os.environ.get('PYTHONHASHSEED')})", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    arm_probes()
    print(f"salt={os.environ.get('PYTHONHASHSEED')} -- running the 6-leg sequence", flush=True)
    leg("s1-ref", seed=1)
    leg("s1-shk", seed=1, **SHOCK)
    leg("s1-core-ref", seed=1, cb_core_inflation=True)
    leg("s1-core-shk", seed=1, cb_core_inflation=True, **SHOCK)
    leg("s2-ref", seed=2)
    leg("s2-shk", seed=2, **SHOCK)
    print("ALL 6 LEGS CLEAN", flush=True)
