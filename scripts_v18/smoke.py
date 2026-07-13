"""v18 bit-identity smoke: run the two reference worlds at a fixed seed and digest
the full per-tick record series. Usage:

    PYTHONPATH=$(pwd) uv run python scripts_v18/smoke.py baseline   # capture hashes
    PYTHONPATH=$(pwd) uv run python scripts_v18/smoke.py check      # compare vs stored
    PYTHONPATH=$(pwd) uv run python scripts_v18/smoke.py check --flags  # v18 flags ON, shared columns only

Two worlds:
  A "macro":    Config.v124 stack, no demographics -- fast, covers the money/bank/goods core.
  B "frontier": Config.v13 daily-tick world with demographics + housing + energy(+hh) --
                the full v16/v17 composition stack the v18 gauges live in.

The digest walks every record in order; for `--flags` runs, only columns present in the
BASELINE run are compared (new observation columns are allowed, moved values are not)
-- the v16 shared-column digest discipline.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config              # noqa: E402
from macro_sim.economy import Economy            # noqa: E402

HASH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_hashes.json")

WORLDS = {
    "macro": lambda **extra: Config.v124(
        n_firms_c=60, n_firms_k=30, n_households=400, n_ticks=400, seed=0, **extra),
    "frontier": lambda **extra: Config.v13(
        seed=0, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
        demographics_population=500, n_ticks=730,
        housing_enabled=True, housing_market_enabled=True,
        energy_enabled=True, energy_household=True, **extra),
}

# v18 flag surface: every stage adds its fields here; `check --flags` turns them all on
# so the guarded-no-op discipline is exercised cumulatively (fields at non-default values
# with the master flag off must also not move a value -- mirror of test_energy_off).
V18_FLAGS_OFF_NONDEFAULTS: dict = {
    # stage 18.0: master flag (deprivation_gauges) stays off, knobs at non-default --
    # must be inert (the guarded-no-op discipline).
    "subsistence_share": 0.6,
    "deprivation_burnin_years": 4,
    "deprivation_acute_days": 5,
}


def digest(records, columns=None) -> str:
    h = hashlib.sha256()
    for rec in records:
        keys = sorted(rec.keys()) if columns is None else [k for k in sorted(columns) if k in rec]
        for k in keys:
            h.update(k.encode())
            h.update(repr(rec[k]).encode())
    return h.hexdigest()


def run_world(name: str, **extra):
    econ = Economy(WORLDS[name](**extra))
    econ.run()
    return econ.records


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    use_flags = "--flags" in sys.argv
    if mode == "baseline":
        hashes = {}
        for name in WORLDS:
            recs = run_world(name)
            hashes[name] = {"digest": digest(recs), "columns": sorted(recs[0].keys()),
                            "n_ticks": len(recs)}
            print(f"[{name}] {hashes[name]['digest']}  ({len(recs)} ticks)")
        with open(HASH_FILE, "w") as f:
            json.dump(hashes, f, indent=1)
        print(f"wrote {HASH_FILE}")
        return 0
    with open(HASH_FILE) as f:
        stored = json.load(f)
    ok = True
    for name in WORLDS:
        extra = dict(V18_FLAGS_OFF_NONDEFAULTS) if use_flags else {}
        recs = run_world(name, **extra)
        cols = stored[name]["columns"] if use_flags else None
        d = digest(recs, columns=cols)
        match = d == stored[name]["digest"] if not use_flags else None
        if use_flags:
            # shared-column comparison against a fresh flag-off run is exact only if
            # baseline was captured on this tree; compare against stored digest of the
            # SAME column set (stored digest covers exactly its stored columns).
            match = d == stored[name]["digest"]
        status = "OK " if match else "FAIL"
        if not match:
            ok = False
        print(f"[{status}] {name}: {d}  (expected {stored[name]['digest']})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
