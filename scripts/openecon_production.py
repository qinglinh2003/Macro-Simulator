"""Production open-economy portrait: long-horizon, large-scale, differentiated N-economy World.

Five archetype economies spread across TWO axes (size x productivity, deliberately
de-correlated so the dataset separates scale effects from productivity effects), fully coupled
(trade + capital + migration, floating FX), on the v23 FIXED foundation (real capital clock +
FINDING 5 accelerator damping) with the FINDING 4 bond-book bound (bucket=30) so a 30-year daily
horizon stays tractable.

Writes the FULL metric set per economy (economy_<i>.csv) plus the world-level cross-border series
(world_series.csv: FX, NFA, current account, trade, factor income, remittances, reserves) and the
diagnose_world identity report. Designed for a ~2-3 hour run; use --smoke to size it first.

Usage:
  python scripts/openecon_production.py --smoke            # 1y, tiny pops -- validate + time
  python scripts/openecon_production.py --years 30         # the production run
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.openecon_portrait import run_portrait   # noqa: E402

# (name, productivity a, population).  a_K tracks a (the v23 rule a_K = 2.4 * a).
ARCHETYPES = [
    ("big_average",     1.00, 2000),   # large economy, middling productivity -- the centre
    ("rich_entrepot",   1.35,  600),   # small but highly productive -- tech/finance hub
    ("advanced",        1.15, 1000),   # medium, high productivity
    ("developing_large", 0.80, 1400),  # large-ish, low productivity -- catching up
    ("poor_small",      0.65,  700),   # small, low productivity -- periphery
]


def scaled(pop):
    return dict(
        demographics_population=pop,
        n_households=max(50, pop // 10),
        n_firms_c=max(20, pop // 10),
        n_firms_k=max(10, pop // 20),
        n_banks=6,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=30.0)
    ap.add_argument("--smoke", action="store_true", help="1y, tiny pops, to validate + time")
    ap.add_argument("--out", default=None)
    ap.add_argument("--bond-bucket", type=int, default=30)
    args = ap.parse_args()

    if args.smoke:
        years = 1.0
        arche = [(nm, a, max(200, pop // 8)) for nm, a, pop in ARCHETYPES]
        out = args.out or "artifacts/openecon/production_smoke"
    else:
        years = args.years
        arche = ARCHETYPES
        out = args.out or f"artifacts/openecon/production_{int(years)}y"

    n = len(arche)
    overrides = [
        {"a": a, "a_K": 2.4 * a, **scaled(pop)}
        for (_, a, pop) in arche
    ]
    world_over = dict(
        base_seed=4242,
        trade=True, capital=True, migration=True,
        capital_mobility=1.0, capital_adjust=0.2,
        migration_rate=0.02, remittance_share=0.2,
        fx_friction=0.03,
    )

    print("PRODUCTION PORTRAIT")
    print(f"  economies : {n}")
    for (nm, a, pop), o in zip(arche, overrides):
        print(f"    {nm:16} a={a:.2f}  pop={o['demographics_population']:>5}  "
              f"firms_c={o['n_firms_c']} firms_k={o['n_firms_k']} banks={o['n_banks']}")
    print(f"  horizon   : {years} years ({int(round(years*365))} daily ticks)")
    print(f"  coupling  : trade+capital+migration, floating FX, bond_bucket={args.bond_bucket}")
    print(f"  out       : {out}", flush=True)

    summary = run_portrait(
        n=n, pop=1000, years=years, out_dir=out,
        world_over=world_over, overrides_per_country=overrides,
        measure_identities=True, bond_maturity_bucket=args.bond_bucket,
    )
    ident = summary.get("identity") or {}
    print(f"\nDONE. wall={summary['wall_seconds']}s  ticks/s={summary['ticks_per_second']}")
    print(f"identities_all_pass={ident.get('all_checks_passed')}  "
          f"failed={ident.get('failed_checks')}  findings={ident.get('findings_by_severity')}")


if __name__ == "__main__":
    main()
