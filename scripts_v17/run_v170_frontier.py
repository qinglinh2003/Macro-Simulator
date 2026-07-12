"""v17.0 diagnostic run: the v15-frontier world (v13 daily tick + demographics +
housing) with energy ON vs OFF, 10 years, crash-tolerant (partial series dumped)."""

from __future__ import annotations

import sys
import time
import traceback

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.visualization.artifacts import write_run_artifact

PARAMS = dict(seed=0, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
              demographics_population=500, n_ticks=3650,
              housing_enabled=True, housing_market_enabled=True)
OUT = "outputs/visualizations/v170_frontier"


def run(label: str, **extra) -> None:
    cfg = Config.v13(**{**PARAMS, **extra})
    econ = Economy(cfg)
    t0 = time.time()
    try:
        for t in range(cfg.n_ticks):
            econ.step()
            if t % 365 == 0:
                print(f"[{label}] t={t} ({time.time()-t0:.0f}s)", flush=True)
    except Exception:
        traceback.print_exc()
        print(f"[{label}] CRASHED at t={econ.t} -- dumping partial series", flush=True)
    write_run_artifact(output_dir=OUT, label=label, version="v17.0", cfg=cfg, records=econ.records)
    print(f"[{label}] done: {len(econ.records)} ticks in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "energy"):
        run("energy_on", energy_enabled=True)
    if which in ("both", "baseline"):
        run("energy_off")
    if which == "household":                      # v17.1 diagnostic twin (17.0 run is the reference)
        run("energy_hh", energy_enabled=True, energy_household=True)
    if which == "shock":                          # v17.2 diagnostic: a year-5 pulse, -40% capacity, 180 days
        run("energy_shock", energy_enabled=True, energy_household=True,
            energy_shock_at=1825, energy_shock_magnitude=0.4, energy_shock_duration=180,
            tax_energy_windfall=0.3)
    if which == "spr":                            # v17.3: same shock, but an SPR built in advance
        cfg = Config.v13(**{**PARAMS, **dict(
            energy_enabled=True, energy_household=True,
            energy_shock_at=1825, energy_shock_magnitude=0.4, energy_shock_duration=180,
            tax_energy_windfall=0.3, spr_target_units=3000.0, spr_flow_cap=20.0)})
        econ = Economy(cfg)
        t0 = time.time()
        try:
            for t in range(cfg.n_ticks):
                if t == 1825:
                    econ.policy.spr_target_units = 0.0   # RELEASE at the shock (live lever)
                econ.step()
                if t % 365 == 0:
                    print(f"[energy_spr] t={t} ({time.time()-t0:.0f}s)", flush=True)
        except Exception:
            traceback.print_exc()
            print(f"[energy_spr] CRASHED at t={econ.t} -- dumping partial series", flush=True)
        write_run_artifact(output_dir=OUT, label="energy_spr", version="v17.3", cfg=cfg,
                           records=econ.records)
        print(f"[energy_spr] done: {len(econ.records)} ticks in {time.time()-t0:.0f}s", flush=True)
    if which == "captriple":                      # v17.4: cap+compensation+household_first AT the
        # shock (live levers), lifted one year later -- the 2022 pattern
        cfg = Config.v13(**{**PARAMS, **dict(
            energy_enabled=True, energy_household=True,
            energy_shock_at=1825, energy_shock_magnitude=0.4, energy_shock_duration=180)})
        econ = Economy(cfg)
        t0 = time.time()
        try:
            for t in range(cfg.n_ticks):
                if t == 1825:
                    econ.policy.energy_price_cap = 1.1 * econ._energy_price
                    econ.policy.energy_rationing = "household_first"
                    econ.policy.energy_cap_compensation = True
                if t == 1825 + 365:
                    econ.policy.energy_price_cap = 0.0
                    econ.policy.energy_rationing = "market"
                    econ.policy.energy_cap_compensation = False
                econ.step()
                if t % 365 == 0:
                    print(f"[energy_captriple] t={t} ({time.time()-t0:.0f}s)", flush=True)
        except Exception:
            traceback.print_exc()
            print(f"[energy_captriple] CRASHED at t={econ.t}", flush=True)
        write_run_artifact(output_dir=OUT, label="energy_captriple", version="v17.4", cfg=cfg,
                           records=econ.records)
        print(f"[energy_captriple] done in {time.time()-t0:.0f}s", flush=True)
    if which == "soe":                            # v17.4 comparison arm: SOE at-cost through the shock
        run("energy_soe", energy_enabled=True, energy_household=True,
            energy_shock_at=1825, energy_shock_magnitude=0.4, energy_shock_duration=180,
            soe_efirm=True, soe_price_at_cost=True)
    if which == "social":                         # v17.5: mortality channel armed + targeted subsidy AT the shock
        cfg = Config.v13(**{**PARAMS, **dict(
            energy_enabled=True, energy_household=True,
            energy_shock_at=1825, energy_shock_magnitude=0.4, energy_shock_duration=180,
            energy_mortality_gamma=2.0, energy_signal_burnin_years=2)})
        econ = Economy(cfg)
        t0 = time.time()
        try:
            for t in range(cfg.n_ticks):
                if t == 1825:
                    econ.policy.energy_subsidy_rate = 0.5
                    econ.policy.energy_subsidy_threshold = 0.5   # targeted (the §34 lesson)
                if t == 1825 + 365:
                    econ.policy.energy_subsidy_rate = 0.0
                econ.step()
                if t % 365 == 0:
                    print(f"[energy_social] t={t} ({time.time()-t0:.0f}s)", flush=True)
        except Exception:
            traceback.print_exc()
            print(f"[energy_social] CRASHED at t={econ.t}", flush=True)
        write_run_artifact(output_dir=OUT, label="energy_social", version="v17.5", cfg=cfg,
                           records=econ.records)
        print(f"[energy_social] done in {time.time()-t0:.0f}s", flush=True)
