"""Open-economy portrait harness (diag/open-economy-portraits).

Builds N economies on the v23 FIXED foundation (FULL_FRONTIER_FLAGS -> real capital), couples
them into a World, runs a long horizon, and writes per-economy series + the diagnose_world
identity report. Optional --profile runs the whole thing under cProfile to find the
single-economy hot spots (the only tractable runtime lever, since the per-tick FX coupling
rules out intra-run economy parallelism).

Also prints the R1 clock check: cross-border factor-income magnitude vs domestic interest, so a
mis-annualised cross-border rate would show up immediately.

Usage:
  python scripts/openecon_portrait.py --n 2 --pop 200 --years 2 --profile
  python scripts/openecon_portrait.py --n 3 --pop 500 --years 10 --out artifacts/openecon/audit
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.diagnostics.world_probes import WorldProbeCollector
from macro_sim.world.world import World


def build_configs(n: int, pop: int, ticks: int, productivity_spread: float,
                  overrides_per_country=None):
    """N frontier economies with heterogeneous productivity so trade/capital/migration flows
    are identifiable. Each economy carries the full v23 fixed foundation."""
    configs = []
    for i in range(n):
        # productivity ladder centred on 1.0; a_K scales with it so the K sector stays calibrated
        # (the v23 rule: a_K tracks C-sector labour productivity)
        prod = 1.0 + productivity_spread * (i / max(1, n - 1) - 0.5)
        params = dict(FULL_FRONTIER_FLAGS)
        params.update(
            seed=i,
            n_households=max(50, pop // 10),
            demographics_population=pop,
            n_firms_c=max(20, pop // 10),
            n_firms_k=max(10, pop // 20),
            n_banks=4,
            n_ticks=ticks,
            a=prod,
            a_K=params["a_K"] * prod,
        )
        if overrides_per_country and i < len(overrides_per_country) and overrides_per_country[i]:
            params.update(overrides_per_country[i])
        configs.append(Config.v13(**params))
    return configs


def build_world(configs, **world_over):
    kw = dict(
        base_seed=12345,
        trade=True, capital=True, migration=True,
        capital_mobility=1.0, capital_adjust=0.2,
        migration_rate=0.02, remittance_share=0.2,
        fx_friction=0.03,
    )
    kw.update(world_over)
    return World(configs, **kw)


def run_portrait(n, pop, years, out_dir, world_over=None, overrides_per_country=None,
                 measure_identities=True):
    ticks = int(round(years * 365))
    configs = build_configs(n, pop, ticks, productivity_spread=0.5,
                            overrides_per_country=overrides_per_country)
    world = build_world(configs, **(world_over or {}))

    # R2: the identity gates. WorldProbeCollector wraps World.step, snapshots the pre/post
    # external state each tick, and feeds diagnose_world -- the canonical identity path (the
    # earlier _world_probe_rows guess did not exist, so R2 silently went unmeasured). The
    # collector adds per-tick snapshot overhead, so the runtime profile (--profile) drives the
    # raw world.run instead; the identity report is a correctness gate, not a speed measurement.
    identity = None
    t0 = time.perf_counter()
    if measure_identities:
        collector = WorldProbeCollector(world)
        identity = collector.run(ticks)          # domestic records still accrue on economies
    else:
        world.run(ticks)
    elapsed = time.perf_counter() - t0
    per_econ = [econ.records for econ in world.economies]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # per-economy series
    import csv
    for i, recs in enumerate(per_econ):
        if not recs:
            continue
        cols = sorted({k for r in recs for k in r})
        with (out / f"economy_{i}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in recs:
                w.writerow(r)

    # R2 verdict: every identity check must pass; surface any critical/high finding.
    identity_report = None
    if identity is not None:
        checks = identity.checks
        failed = sorted(name for name, c in checks.items() if not c.get("passed", False))
        sev = {}
        for f in identity.findings:
            sev[f.severity] = sev.get(f.severity, 0) + 1
        identity_report = {
            "all_checks_passed": not failed,
            "n_checks": len(checks),
            "failed_checks": failed,
            "findings_by_severity": sev,
            "findings": [f.issue_id for f in identity.findings],
        }

    # R1: cross-border factor income (world-level, per-economy vector) vs domestic interest.
    # A mis-annualised cross-border rate would make factor income dwarf/vanish vs domestic.
    def tail_mean(recs, key):
        v = [float(r.get(key, float("nan"))) for r in recs[-min(365, len(recs)):]]
        v = [x for x in v if x == x]
        return st.mean(v) if v else float("nan")

    world_recs = getattr(world, "world_records", [])
    tail_wr = world_recs[-min(365, len(world_recs)):]

    def tail_mean_vec(key, i):
        v = [float(r[key][i]) for r in tail_wr if key in r and i < len(r[key])]
        return st.mean(v) if v else float("nan")

    summary = {
        "n": n, "pop": pop, "years": years, "ticks": ticks,
        "wall_seconds": round(elapsed, 1),
        "ticks_per_second": round(ticks / elapsed, 1) if elapsed > 0 else None,
        "identity": identity_report,
        "per_economy": [],
    }
    for i, recs in enumerate(per_econ):
        if not recs:
            continue
        summary["per_economy"].append({
            "economy": i,
            "real_gdp": tail_mean(recs, "real_gdp"),
            "cpi": tail_mean(recs, "cpi_fixed_basket"),
            "K_over_annual_gdp": (tail_mean(recs, "aggregate_capital")
                                  / (tail_mean(recs, "real_gdp") * 365)
                                  if tail_mean(recs, "real_gdp") > 0 else None),
            # R1: external factor income (GNP-GDP wedge) vs domestic interest, same units
            "ext_factor_income": tail_mean_vec("factor_income", i),
            "nfa": tail_mean_vec("nfa", i),
            "current_account": tail_mean_vec("current_account", i),
            "domestic_interest": tail_mean(recs, "interest_paid"),
        })
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    if identity_report is not None:
        verdict = "PASS" if identity_report["all_checks_passed"] else "FAIL"
        print(f"IDENTITY: {verdict}  ({identity_report['n_checks']} checks, "
              f"failed={identity_report['failed_checks']}, "
              f"findings={identity_report['findings_by_severity']})")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--pop", type=int, default=200)
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--out", default="artifacts/openecon/smoke")
    ap.add_argument("--profile", action="store_true")
    args = ap.parse_args()

    if args.profile:
        pr = cProfile.Profile()
        pr.enable()
        # raw world.run (no probe overhead) so the profile reflects the DOMESTIC step cost
        run_portrait(args.n, args.pop, args.years, args.out, measure_identities=False)
        pr.disable()
        s = io.StringIO()
        pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(30)
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "profile.txt").write_text(s.getvalue())
        print("\n=== TOP HOT SPOTS (cumulative) ===")
        print("\n".join(s.getvalue().splitlines()[:40]))
    else:
        run_portrait(args.n, args.pop, args.years, args.out)


if __name__ == "__main__":
    main()
