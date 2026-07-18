#!/usr/bin/env python3
"""Extreme-world portraits: push the economy where no run has gone, hunt silent bugs.

Five scenarios on the 6-archetype base (single seed each -- exploration, not statistics):
  X1 crisis   : engineered peg break mid-run (exploits the static-rate pressure machinery)
  X2 banking  : leverage 24x + loose household credit -> failure cascades at 14k scale
  X3 boom     : tfr ~2x, mortality 0.8x -> housing SHORTAGE regime + youth bulge
  X4 blowout  : deficit 12% GDP + generous welfare -> fiscal-dominance inflation attempt
  X5 century  : 60 years, pop x1 -> slow-accumulation bugs (A5 drift ceiling, index drift)
"""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openecon_production import ARCHETYPES, cfg_kwargs, mapped_pops
from openecon_portrait import run_portrait

BASE_WORLD = dict(trade=True, capital=True, migration=True, capital_mobility=1.0,
                  capital_adjust=0.2, migration_rate=0.02, fx_friction=0.03)

def scenario(name):
    n = len(ARCHETYPES)
    names = [a["name"] for a in ARCHETYPES]
    years, pop_mult, seed = 30.0, 2.0, 4242
    extra_common = {}
    extra_by_econ = {}
    wo = dict(BASE_WORLD)
    wo.update(capital_control=[a["cc"] for a in ARCHETYPES],
              immigration_cap=[a["imm"] for a in ARCHETYPES],
              guest_worker_return=[a["gwr"] for a in ARCHETYPES],
              remittance_share=[a["rem"] for a in ARCHETYPES],
              peg=True, peg_economy=names.index("China"), peg_anchor=names.index("USA"),
              peg_reserves0=8000.0, peg_reserve_scale=5.0e4)
    if name == "X1":  # currency crisis: static-rate mismatch drains thin reserves
        extra_by_econ[names.index("China")] = dict(r_interest=0.008)   # below the 0.01 world
        cc = [a["cc"] for a in ARCHETYPES]; cc[names.index("China")] = 0.5
        wo.update(capital_control=cc, peg_reserves0=20000.0, peg_reserve_scale=0.02)
    elif name == "X2":  # banking stress
        extra_common = dict(bank_leverage_mean=24.0, hh_credit_limit=4.0)
    elif name == "X3":  # population boom
        boom_tfr = {"China": 2.6, "India": 4.5, "USA": 3.4, "Germany": 3.0, "Gulf": 4.4, "Hub": 2.2}
        for i, a in enumerate(ARCHETYPES):
            extra_by_econ[i] = dict(demographics_tfr=boom_tfr[a["name"]],
                                    demographics_mortality_scale=a["mort"] * 0.8)
    elif name == "X4":  # fiscal blowout
        extra_common = dict(gov_deficit_target=0.12, deficit_u_cap=3.0,
                            benefit_replacement=0.5, pension_replacement=0.5)
    elif name == "X5":  # century world
        years, pop_mult = 60.0, 1.0
    else:
        raise SystemExit(f"unknown scenario {name}")
    pops = [max(150, int(round(p * pop_mult))) for p in mapped_pops()]
    overrides = []
    for i, a in enumerate(ARCHETYPES):
        p = cfg_kwargs(a, pops[i])
        p.update(extra_common)
        p.update(extra_by_econ.get(i, {}))
        p["seed"] = seed + i
        overrides.append(p)
    return n, pops, years, overrides, wo

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--daemon", default=None)
    args = ap.parse_args()
    if args.daemon:
        if os.fork() > 0: os._exit(0)
        os.setsid()
        if os.fork() > 0: os._exit(0)
        sys.stdout.flush(); sys.stderr.flush()
        Path(args.daemon).parent.mkdir(parents=True, exist_ok=True)
        f = open(args.daemon, "a", buffering=1)
        os.dup2(f.fileno(), 1); os.dup2(f.fileno(), 2)
        devnull = open(os.devnull, "r")
        os.dup2(devnull.fileno(), 0)
    n, pops, years, overrides, wo = scenario(args.scenario)
    out = args.out or f"artifacts/openecon/extreme_{args.scenario}"
    print(f"EXTREME {args.scenario}: years={years} pops={pops}", flush=True)
    s = run_portrait(n=n, pop=1000, years=years, out_dir=out, world_over=wo,
                     overrides_per_country=overrides, measure_identities=True,
                     bond_maturity_bucket=30, checkpoint_every=1000)
    ident = (s.get("identity") or {})
    print(f"DONE {args.scenario}: ident={ident.get('all_checks_passed')} failed={ident.get('failed_checks')}", flush=True)

if __name__ == "__main__":
    main()
