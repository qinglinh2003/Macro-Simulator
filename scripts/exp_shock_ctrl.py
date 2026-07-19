"""Shock x Controller experiments on the 6-economy archetype world (dev engine).

E1 policy-value: GFC tape x {null, countercyclical-treasury} -- does policy matter?
E2 measurement:  oil-embargo tape x {headline, core} Taylor CB -- the 1970s question.

Real-side readouts only (GDP, unemployment, inflation, recovery) -- housing and
NFA channels are known-polluted until the campaign bugs are fixed.
"""
import argparse, csv, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openecon_production import ARCHETYPES, cfg_kwargs, mapped_pops
from macro_sim.config import Config
from macro_sim.world import World
from macro_sim.shocks import ShockTape
from macro_sim.shocks.scenarios import global_financial_crisis_scenario, oil_embargo_scenario

YEARS, SHOCK_YEAR = 8.0, 2.0
TICKS = int(YEARS * 365)
SHOCK_T = int(SHOCK_YEAR * 365)

KEYS = ["real_gdp", "unemployment_rate", "cpi", "policy_rate", "gov_deficit",
        "gov_debt", "benefit_paid", "total_credit", "price_index", "infl_ema",
        "energy_bought", "e_capacity_utilization", "energy_unfilled"]

def build_world(seed_base, extra_common=None):
    pops = [max(150, int(round(p * 1.0))) for p in mapped_pops()]
    overrides = []
    for i, a in enumerate(ARCHETYPES):
        p = cfg_kwargs(a, pops[i])
        p.update(extra_common or {})
        p["seed"] = seed_base + i
        p["n_ticks"] = TICKS + 10
        overrides.append(p)
    wo = dict(trade=True, capital=True, migration=True, capital_mobility=1.0,
              capital_adjust=0.2, migration_rate=0.02, fx_friction=0.03,
              capital_control=[a["cc"] for a in ARCHETYPES],
              immigration_cap=[a["imm"] for a in ARCHETYPES],
              guest_worker_return=[a["gwr"] for a in ARCHETYPES],
              remittance_share=[a["rem"] for a in ARCHETYPES])
    return [Config.v13(**p) for p in overrides], wo

def countercyclical_rule(context):
    from macro_sim.controllers.protocol import PolicyAction
    obs = context.observation
    if hasattr(obs, "values") and not isinstance(obs, dict):
        values = obs.values()
    else:
        o = obs.to_dict() if hasattr(obs, "to_dict") else obs
        values = o.get("values", o) if isinstance(o, dict) else {}
    u = values.get("unemployment_rate")
    permitted = {item.lever: item for item in context.permitted_actions}
    tgt = permitted.get("gov_deficit_target")
    if u is None or tgt is None or not tgt.allowed or tgt.current_value is None:
        return ()
    cur = float(tgt.current_value)
    notch = 0.005
    if float(u) > 0.10:
        new = cur + notch
    elif float(u) < 0.05:
        new = cur - notch
    else:
        return ()
    if tgt.minimum is not None: new = max(float(tgt.minimum), new)
    if tgt.maximum is not None: new = min(float(tgt.maximum), new)
    if abs(new - cur) < 1e-12: return ()
    return (PolicyAction("gov_deficit_target", new),)

def run(exp, arm, seed, out):
    outp = Path(out); outp.mkdir(parents=True, exist_ok=True)
    if exp == "E2":
        extra = dict(cb_core_inflation=(arm == "core"))
        cfgs, wo = build_world(seed, extra)
        tape = oil_embargo_scenario(start_tick=SHOCK_T, duration_ticks=365)
        world = World(cfgs, base_seed=seed, shocks=tape, **wo)
        for _ in range(TICKS):
            world.step()
    elif exp == "E1":
        cfgs, wo = build_world(seed)
        tape = global_financial_crisis_scenario(start_tick=SHOCK_T, duration_ticks=365)
        world = World(cfgs, base_seed=seed, shocks=tape, **wo)
        if arm == "heuristic":
            from macro_sim.controllers import ControlledSimulationSession
            from macro_sim.controllers.occupants import HeuristicOccupant
            session = ControlledSimulationSession(world)
            for i in range(len(cfgs)):
                session.assign_seat(
                    i, "treasury",
                    HeuristicOccupant(rule_name="countercyclical_fiscal"),
                    actor="experiment")
            session.run(TICKS)
        else:
            for _ in range(TICKS):
                world.step()
    else:
        raise SystemExit(f"unknown exp {exp}")

    for i, econ in enumerate(world.economies):
        with open(outp / f"economy_{i}.csv", "w", newline="") as f:
            wcsv = csv.writer(f)
            cols = [k for k in KEYS if k in econ.records[0]] if econ.records else KEYS
            wcsv.writerow(["t"] + cols)
            for t, r in enumerate(econ.records):
                wcsv.writerow([t] + [r.get(k, "") for k in cols])
    json.dump({"exp": exp, "arm": arm, "seed": seed, "ticks": TICKS,
               "shock_tick": SHOCK_T}, open(outp / "summary.json", "w"))
    print(f"DONE {exp}:{arm}:{seed}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--out", required=True)
    ap.add_argument("--daemon", default=None)
    a = ap.parse_args()
    if a.daemon:
        if os.fork() > 0: os._exit(0)
        os.setsid()
        if os.fork() > 0: os._exit(0)
        sys.stdout.flush(); sys.stderr.flush()
        Path(a.daemon).parent.mkdir(parents=True, exist_ok=True)
        f = open(a.daemon, "a", buffering=1)
        devnull = open(os.devnull, "r")
        os.dup2(devnull.fileno(), 0)
        os.dup2(f.fileno(), 1)
        os.dup2(f.fileno(), 2)
    try:
        run(a.exp, a.arm, a.seed, a.out)
    except BaseException:
        import traceback; traceback.print_exc(); raise

if __name__ == "__main__":
    main()
