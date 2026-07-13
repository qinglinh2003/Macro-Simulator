"""v17.2 POST-COMPOSITION stagflation matrix (protocol §5: disclaimer-free, the v16
labor layer live -- u is real, the JG is the L2-recast buffer stock).

World: frontier (v13 daily + housing + FULL v16 stack + energy + household energy).
Shock: year-7 pulse (-40% kappa, 180d) into the mature economy. Cells vary the POLICY
STACK; every cell same seed. The JG hard test = base vs jg_off (supply shock at
capacity with/without the buffer). Usage: python run_v172_matrix.py <cell>
"""

from __future__ import annotations

import sys
import time
import traceback

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.visualization.artifacts import write_run_artifact

V16 = dict(labor_matching="persistent", labor_matching_friction=True,
           labor_relationship_wages=True, labor_job_ladder=True,
           labor_person_efficiency=True, capital_rationed_signal=True,
           firm_subscale_exit=True, capital_firm_entry=True)
BASE = dict(seed=0, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
            demographics_population=500, n_ticks=3650,
            housing_enabled=True, housing_market_enabled=True,
            energy_enabled=True, energy_household=True, **V16)
SHOCK = dict(energy_shock_at=2555, energy_shock_magnitude=0.4, energy_shock_duration=180)
OUT = "outputs/visualizations/v172_matrix"

CELLS = {
    # WITHIN-PAIR DESIGN: every policy arm gets its OWN no-shock twin (same flags,
    # same seed) -- policy flags differ from t0, so cross-arm windows mix ten years
    # of divergent dynamics with the shock response (finding 15's cousin, caught by
    # the first scorecard: the no-shock ref had a HIGHER u-peak than the shock arms).
    "ref": dict(),                                       # no shock (default-stack twin)
    "taylor_off_ref": dict(central_bank=False),
    "core_cb_ref": dict(cb_core_inflation=True),
    "fiscal_flat_ref": dict(deficit_u_cap=1.0),
    "jg_off_ref": dict(job_guarantee=False),
    "base": dict(**SHOCK),                               # default stack: Taylor gentle + deficit + JG
    "taylor_off": dict(**SHOCK, central_bank=False),     # frozen rate through the shock
    "core_cb": dict(**SHOCK, cb_core_inflation=True),    # the CB looks through energy
    "fiscal_flat": dict(**SHOCK, deficit_u_cap=1.0),     # no slack-scaled fiscal counterweight
    "jg_off": dict(**SHOCK, job_guarantee=False),        # THE JG HARD TEST contrast arm
}


def run(cell: str) -> None:
    cfg = Config.v13(**{**BASE, **CELLS[cell]})
    econ = Economy(cfg)
    t0 = time.time()
    try:
        for t in range(cfg.n_ticks):
            econ.step()
            if t % 730 == 0:
                print(f"[{cell}] t={t} ({time.time()-t0:.0f}s)", flush=True)
    except Exception:
        traceback.print_exc()
        print(f"[{cell}] CRASHED at t={econ.t} -- dumping partial series", flush=True)
    write_run_artifact(output_dir=OUT, label=cell, version="v17.2-matrix", cfg=cfg,
                       records=econ.records)
    print(f"[{cell}] done: {len(econ.records)} ticks in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    for cell in sys.argv[1:]:
        run(cell)
