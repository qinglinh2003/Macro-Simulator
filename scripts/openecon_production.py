"""Production open-economy portrait: 6 real-world archetype economies, fully coupled, long horizon.

Six archetypes mapped to representative real economies across many knobs (size, productivity,
growth, demographics/age-pyramid, savings, fiscal/tax regime, financial depth, energy, capital
account). Population is a rank-preserving ^0.4 compression of real populations (real linear ratios
+ a >=300 floor are infeasible: China/Gulf ~=47x). On the v23 fixed foundation (real capital clock,
FINDING 5 accelerator damping, FINDING 4 bond-book bound) with housing/energy/labor/strata all live
(they are in FULL_FRONTIER_FLAGS).

Modes:
  --validate   run each archetype as a CLOSED economy (short) and report health -- catch collapses
               BEFORE the coupled run (extreme knob combos can break an economy).
  --smoke      tiny coupled run to size timing.
  (default)    the coupled production run; writes economy_<i>.csv + world_series.csv + summary.json.
"""
from __future__ import annotations

import argparse
import os
import statistics as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# knobs shared by every economy (layered on FULL_FRONTIER_FLAGS, which already has housing, energy,
# labor, consumption strata, deprivation, capital clock, etc.).
COMMON = dict(
    bond_maturity_bucket=30,                # FINDING 4: bound the bond book over the long horizon
    fertility_income_elasticity=0.06,       # demographic transition: richer -> fewer children
    mortality_income_elasticity=0.04,       # richer -> longer life (endogenous aging)
    claims_reconcile_interval=1,            # FINDING 6: dissolve cash-claim strands from cross-household moves under heavy churn
    ledger_rel_tol=1e-8,                    # A5 headroom for 30y x 14k-agent float accumulation (~1.5e-7/tick systematic rounding)
)

# name, real_pop_millions, then per-country knobs. a_K is set to 2.4*a downstream.
#   a=productivity, g=tfp_drift, tfr, mort=mortality_scale, sav=alpha1(MPC; low=high savings),
#   e_int=energy_intensity, cc=capital_control, gov=gov_consumption_share, vat=tax_consumption_rate,
#   inc=tax_income_rate, prof=tax_profit_rate, defc=gov_deficit_target, blev=bank_leverage_mean,
#   ginv=gov_investment_share
#   imm=immigration_cap (host door), gwr=guest_worker_return (host, temporary), rem=remittance_share (origin diaspora)
ARCHETYPES = [
    dict(name="China",   real_pop=1410, a=0.95, g=0.030, tfr=1.2, mort=1.00, sav=0.72,
         e_int=0.060, cc=0.7, gov=0.15, vat=0.13, inc=0.10, prof=0.22, defc=0.02, blev=11.0, ginv=0.05,
         imm=0.05, gwr=0.0,  rem=0.20),
    dict(name="India",   real_pop=1430, a=0.70, g=0.035, tfr=2.4, mort=1.25, sav=0.85,
         e_int=0.045, cc=0.2, gov=0.11, vat=0.14, inc=0.06, prof=0.22, defc=0.04, blev=9.0,  ginv=0.03,
         imm=5.0,  gwr=0.0,  rem=0.40),
    dict(name="USA",     real_pop=335,  a=1.25, g=0.012, tfr=1.7, mort=1.00, sav=0.90,
         e_int=0.050, cc=0.0, gov=0.15, vat=0.06, inc=0.18, prof=0.20, defc=0.045, blev=14.0, ginv=0.02,
         imm=3.0,  gwr=0.0,  rem=0.15),
    dict(name="Germany", real_pop=84,   a=1.30, g=0.008, tfr=1.5, mort=0.85, sav=0.74,
         e_int=0.065, cc=0.0, gov=0.20, vat=0.17, inc=0.24, prof=0.25, defc=0.0,  blev=10.0, ginv=0.03,
         imm=1.0,  gwr=0.0,  rem=0.15),
    dict(name="Gulf",    real_pop=30,   a=1.30, g=0.005, tfr=2.2, mort=0.90, sav=0.58,
         e_int=0.030, cc=0.0, gov=0.20, vat=0.05, inc=0.00, prof=0.05, defc=0.0,  blev=10.0, ginv=0.04,
         imm=8.0,  gwr=0.35, rem=0.10),
    dict(name="Hub",     real_pop=10,   a=1.45, g=0.012, tfr=1.1, mort=0.80, sav=0.72,
         e_int=0.060, cc=0.0, gov=0.10, vat=0.09, inc=0.10, prof=0.15, defc=0.0,  blev=15.0, ginv=0.02,
         imm=2.0,  gwr=0.20, rem=0.10),
]

POP_FLOOR = 300
POP_EXPONENT = 0.4   # rank-preserving compression of real populations


def mapped_pops():
    raw = [a["real_pop"] ** POP_EXPONENT for a in ARCHETYPES]
    factor = POP_FLOOR / min(raw)
    return [int(round(x * factor)) for x in raw]


def cfg_kwargs(arch, pop, extra=None):
    from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
    p = dict(FULL_FRONTIER_FLAGS)
    p.update(COMMON)
    p.update(
        n_households=max(50, pop // 10), demographics_population=pop,
        n_firms_c=max(20, pop // 10), n_firms_k=max(10, pop // 20), n_banks=6,
        a=arch["a"], a_K=2.4 * arch["a"], tfp_drift_rate=arch["g"],
        demographics_tfr=arch["tfr"], demographics_mortality_scale=arch["mort"],
        alpha1=arch["sav"], energy_intensity=arch["e_int"],
        gov_consumption_share=arch["gov"], tax_consumption_rate=arch["vat"],
        tax_income_rate=arch["inc"], tax_profit_rate=arch["prof"],
        gov_deficit_target=arch["defc"], bank_leverage_mean=arch["blev"],
        bank_capital_constraint=True, gov_investment_share=arch["ginv"],
    )
    if extra:
        p.update(extra)
    return p


def _validate_worker(spec):
    i, ticks, pop_div = spec
    from macro_sim.config import Config
    from macro_sim.economy import Economy
    arch = ARCHETYPES[i]
    pop = max(150, mapped_pops()[i] // pop_div)
    p = cfg_kwargs(arch, pop, extra=dict(seed=1, n_ticks=ticks))
    recs = Economy(Config.v13(**p)).run()
    burn = min(len(recs) // 3, 2 * 365)
    tail = recs[burn:]

    def col(k):
        return [r.get(k) for r in tail if r.get(k) is not None]
    u = col("unemployment_rate")
    cpi = col("cpi_fixed_basket")
    gdp = col("real_gdp")
    return arch["name"], dict(
        pop=pop, max_u=round(max(u), 3), mean_u=round(st.mean(u), 3),
        cpi_end=round(cpi[-1], 2), gdp_end=round(gdp[-1], 1),
        gdp_cov=round(st.pstdev(gdp) / st.mean(gdp), 3),
    )


def validate(years, pop_div):
    """Run each archetype as a CLOSED economy and report health. capital_control is a WORLD knob,
    so it is dropped here (closed); everything else applies."""
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(v, "1")
    from concurrent.futures import ProcessPoolExecutor
    ticks = int(round(years * 365))
    with ProcessPoolExecutor(max_workers=6) as ex:
        res = dict(ex.map(_validate_worker, [(i, ticks, pop_div) for i in range(len(ARCHETYPES))]))
    print(f"CLOSED-ECONOMY HEALTH CHECK  ({years}y, pop/{pop_div})")
    print(f"{'archetype':10}{'pop':>6}{'max_u':>8}{'mean_u':>8}{'cpi_end':>9}{'gdp_cov':>9}{'gdp_end':>9}")
    for a in ARCHETYPES:
        r = res[a["name"]]
        flag = "  <-- COLLAPSE?" if (r["mean_u"] > 0.35 or r["cpi_end"] > 5 or r["cpi_end"] < 0.2) else ""
        print(f"{a['name']:10}{r['pop']:>6}{r['max_u']:>8}{r['mean_u']:>8}{r['cpi_end']:>9}"
              f"{r['gdp_cov']:>9}{r['gdp_end']:>9}{flag}")


def run_production(years, out, pop_div=1, pop_mult=1.0, base_seed=4242,
                   checkpoint_every=0, resume=None):
    from scripts.openecon_portrait import run_portrait
    pops = [max(150, int(round(p * pop_mult)) // pop_div) for p in mapped_pops()]
    n = len(ARCHETYPES)
    overrides = [cfg_kwargs(a, pops[i]) for i, a in enumerate(ARCHETYPES)]
    # capital_control is a World vector; the rest are per-Config (already in overrides).
    names = [a["name"] for a in ARCHETYPES]
    world_over = dict(
        base_seed=base_seed, trade=True, capital=True, migration=True,
        capital_mobility=1.0, capital_adjust=0.2, migration_rate=0.02,
        fx_friction=0.03,
        capital_control=[a["cc"] for a in ARCHETYPES],
        immigration_cap=[a["imm"] for a in ARCHETYPES],       # per-host: China restrictive, Gulf open door
        guest_worker_return=[a["gwr"] for a in ARCHETYPES],   # per-host: Gulf/Hub temporary labour
        remittance_share=[a["rem"] for a in ARCHETYPES],      # per-origin: India remits most
        # China manages its FX: pegs to the USD (managed float + capital controls = the trilemma corner)
        peg=True, peg_economy=names.index("China"), peg_anchor=names.index("USA"),
        peg_reserves0=8000.0, peg_reserve_scale=5.0e4,
    )
    print("PRODUCTION PORTRAIT (6 real-world archetypes)")
    for a, pop in zip(ARCHETYPES, pops):
        print(f"    {a['name']:9} pop={pop:>5} a={a['a']:.2f} tfr={a['tfr']} sav={a['sav']} "
              f"gov={a['gov']} vat={a['vat']} cc={a['cc']} blev={a['blev']}")
    print(f"  horizon {years}y ({int(round(years*365))} ticks)  out={out}", flush=True)
    return run_portrait(n=n, pop=1000, years=years, out_dir=out, world_over=world_over,
                        overrides_per_country=overrides, measure_identities=True,
                        bond_maturity_bucket=30,
                        checkpoint_every=checkpoint_every, resume=resume,
                        ledger_rel_tol=COMMON.get("ledger_rel_tol"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=30.0)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--pop-div", type=int, default=1, help="divide mapped pops (for fast tests)")
    ap.add_argument("--pop-mult", type=float, default=1.0, help="multiply mapped pops (2.0 = double scale)")
    ap.add_argument("--base-seed", type=int, default=4242, help="world base seed (vary for seed replicates)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--checkpoint", type=int, default=0, metavar="N",
                    help="save a rolling checkpoint.msim into --out every N ticks (0 = off); "
                         "a claims/identity crash also dumps crash_state.msim for forensics")
    ap.add_argument("--resume", default=None, metavar="PATH",
                    help="resume from a checkpoint container written by --checkpoint")
    ap.add_argument("--daemon", default=None,
                    help="fully detach (double-fork + setsid) and log to this path -- survives a "
                         "parent/harness teardown for multi-hour runs")
    args = ap.parse_args()

    if args.daemon:
        # daemonize so a teardown of the launching shell's process group cannot reap the run.
        if os.fork() > 0:
            os._exit(0)
        os.setsid()
        if os.fork() > 0:
            os._exit(0)
        sys.stdout.flush(); sys.stderr.flush()
        Path(args.daemon).parent.mkdir(parents=True, exist_ok=True)
        f = open(args.daemon, "a", buffering=1)
        os.dup2(f.fileno(), 1)
        os.dup2(f.fileno(), 2)
        devnull = open(os.devnull, "r")
        os.dup2(devnull.fileno(), 0)

    if args.validate:
        validate(years=8.0, pop_div=max(args.pop_div, 3))
        return
    if args.smoke:
        s = run_production(years=1.0, out=args.out or "artifacts/openecon/prod6_smoke", pop_div=4)
        ident = s.get("identity") or {}
        print(f"\nsmoke DONE wall={s['wall_seconds']}s ident={ident.get('all_checks_passed')}")
        return
    out = args.out or f"artifacts/openecon/prod6_{int(args.years)}y"
    s = run_production(years=args.years, out=out, pop_div=args.pop_div,
                       pop_mult=args.pop_mult, base_seed=args.base_seed,
                       checkpoint_every=args.checkpoint, resume=args.resume)
    ident = s.get("identity") or {}
    print(f"\nDONE wall={s['wall_seconds']}s ticks/s={s['ticks_per_second']} "
          f"identities_all_pass={ident.get('all_checks_passed')} failed={ident.get('failed_checks')}")


if __name__ == "__main__":
    main()
