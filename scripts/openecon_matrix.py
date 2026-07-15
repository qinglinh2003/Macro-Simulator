"""Open-economy causal-matrix driver (diag/open-economy-portraits).

Runs the portrait causal matrix -- a symmetric baseline (2 seeds) plus one-lever intervention
arms -- as INDEPENDENT Worlds across a process pool. This is the tractable multi-economy speed
lever (per-tick FX coupling rules out intra-run economy parallelism; see the plan doc): 10 arms,
one core each, wall-clock ~= the slowest arm. BLAS is pinned to 1 thread/process (set BELOW before
numpy is imported anywhere) so the workers never oversubscribe the cores.

Each arm writes its own artifact dir (series + diagnose_world identity report), and the driver
collects a matrix summary: per-arm health (CPI, K/Y), the external sector (NFA, current account,
factor income) and whether all 24 world identities held. Same-seed baselines make each arm's
deviation attributable.

Usage:
  python scripts/openecon_matrix.py --stage audit                 # n=3 pop=500 10y
  python scripts/openecon_matrix.py --stage smoke --workers 8     # n=3 pop=200 2y (fast debug)
  python scripts/openecon_matrix.py --stage production            # n=3 pop=2000 30y (hours)
  python scripts/openecon_matrix.py --stage audit --only baseline_a,tariff
"""
from __future__ import annotations

import os

# Pin BLAS BEFORE any numpy import (transitively via the harness) so N workers do not each
# spawn a full BLAS thread pool and thrash the cores.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.openecon_portrait import run_portrait   # noqa: E402


STAGES = {
    "smoke":      dict(n=3, pop=200, years=2),
    "audit":      dict(n=3, pop=500, years=10),
    "production": dict(n=3, pop=2000, years=30),
}


def arms(n: int, years: float):
    """The causal matrix: (name, world_over, overrides_per_country). Every arm shares the
    baseline scale; exactly one lever moves per arm so its effect is attributable against the
    same-seed baseline. overrides_per_country is a length-n list (None = untouched)."""
    shock_at = int(round(years * 365 * 0.4))          # a shock 40% into the horizon
    shock_dur = int(round(years * 365 * 0.2))
    hi = [None] * n
    return [
        # two seeds of the symmetric baseline -> steady state + identity baseline + replication
        ("baseline_a", dict(base_seed=100), None),
        ("baseline_b", dict(base_seed=200), None),
        # one economy grows faster (allocation puzzle / convergence)
        ("productivity_divergence", dict(base_seed=100),
         [{"tfp_drift_rate": 0.04}] + [None] * (n - 1)),
        # an energy shock in ONE economy -> trade + FX transmission. Magnitude 0.6: a 35% cut
        # is fully absorbed by spare capacity (steady-state energy utilisation ~49%, so capacity
        # at 65% never binds); cutting to 40% forces the capacity constraint to bite.
        ("energy_shock", dict(base_seed=100),
         [{"energy_shock_at": shock_at, "energy_shock_magnitude": 0.6,
           "energy_shock_duration": shock_dur}] + [None] * (n - 1)),
        # one economy runs a higher POLICY rate -> trilemma: capital inflow + FX pressure
        ("rate_divergence", dict(base_seed=100),
         [{"r_interest": 0.03}] + [None] * (n - 1)),
        # can a closed capital account sever the rate-divergence channel
        ("capital_control", dict(base_seed=100, capital_control=1.0),
         [{"r_interest": 0.03}] + [None] * (n - 1)),
        # trade-policy cross-border cost
        ("tariff", dict(base_seed=100, tariff=0.15), None),
        # labour mobility + remittances OFF vs baseline
        ("migration_off", dict(base_seed=100, migration=False), None),
        # exchange-rate regime: peg vs float
        ("peg", dict(base_seed=100, peg=True), None),
        # centre-periphery: one large economy + small ones
        ("size_asymmetry", dict(base_seed=100),
         [{"demographics_population": None}]),  # filled per-stage in run_arm
    ]


def run_arm(spec):
    name, n, pop, years, out_root, world_over, opc = spec
    # size_asymmetry: economy 0 is 3x population; harness derives agent counts from pop.
    if name == "size_asymmetry":
        opc = [{"demographics_population": pop * 3, "n_households": max(50, (pop * 3) // 10),
                "n_firms_c": max(20, (pop * 3) // 10), "n_firms_k": max(10, (pop * 3) // 20)}] \
              + [None] * (n - 1)
    out_dir = Path(out_root) / name
    t0 = time.perf_counter()
    try:
        summary = run_portrait(n, pop, years, str(out_dir), world_over=world_over,
                               overrides_per_country=opc, measure_identities=True)
        status = "ok"
        err = None
    except Exception as e:  # noqa: BLE001 -- an arm failure must not sink the matrix
        summary, status, err = None, "error", repr(e)
    return {
        "arm": name, "status": status, "error": err,
        "wall_seconds": round(time.perf_counter() - t0, 1),
        "summary": summary,
    }


def digest_arm(result):
    """One compact matrix row per arm."""
    s = result.get("summary")
    row = {"arm": result["arm"], "status": result["status"],
           "wall_s": result["wall_seconds"]}
    if result["status"] != "ok" or not s:
        row["error"] = result.get("error")
        return row
    ident = s.get("identity") or {}
    row["identities_pass"] = ident.get("all_checks_passed")
    row["failed_checks"] = ident.get("failed_checks")
    row["findings"] = ident.get("findings_by_severity")
    row["economies"] = [
        {"i": e["economy"], "gdp": round(e["real_gdp"], 1), "cpi": round(e["cpi"], 3),
         "K_over_Y": round(e["K_over_annual_gdp"], 2) if e["K_over_annual_gdp"] else None,
         "nfa": round(e["nfa"], 2) if e["nfa"] == e["nfa"] else None,
         "ca": round(e["current_account"], 4) if e["current_account"] == e["current_account"] else None}
        for e in s.get("per_economy", [])
    ]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=list(STAGES), default="audit")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None, help="comma-separated arm names")
    args = ap.parse_args()

    cfg = STAGES[args.stage]
    n, pop, years = cfg["n"], cfg["pop"], cfg["years"]
    out_root = args.out or f"artifacts/openecon/matrix_{args.stage}"
    Path(out_root).mkdir(parents=True, exist_ok=True)

    selected = set(args.only.split(",")) if args.only else None
    specs = [
        (name, n, pop, years, out_root, world_over, opc)
        for (name, world_over, opc) in arms(n, years)
        if selected is None or name in selected
    ]

    print(f"matrix stage={args.stage} n={n} pop={pop} years={years} "
          f"arms={len(specs)} workers={args.workers}")
    t0 = time.perf_counter()
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(run_arm, spec): spec[0] for spec in specs}
        for fut in as_completed(futures):
            result = fut.result()
            row = digest_arm(result)
            rows.append(row)
            print(f"  [{result['status']:5}] {result['arm']:24} "
                  f"{result['wall_seconds']:6.1f}s  identities={row.get('identities_pass')}")
    wall = round(time.perf_counter() - t0, 1)

    rows.sort(key=lambda r: r["arm"])
    report = {"stage": args.stage, "n": n, "pop": pop, "years": years,
              "wall_seconds": wall, "workers": args.workers, "arms": rows}
    (Path(out_root) / "matrix_summary.json").write_text(json.dumps(report, indent=1, default=str))
    print(f"\nmatrix wall={wall}s  ->  {out_root}/matrix_summary.json")
    # surface any arm that failed an identity or crashed
    bad = [r["arm"] for r in rows if r["status"] != "ok" or r.get("identities_pass") is False]
    print("ARMS NEEDING ATTENTION:", bad if bad else "none (all identities held)")


if __name__ == "__main__":
    main()
