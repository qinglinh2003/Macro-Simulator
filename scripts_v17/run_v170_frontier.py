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
