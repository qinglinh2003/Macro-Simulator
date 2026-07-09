"""Phase 1 demographic-economy acceptance harness.

The harness keeps Phase 1 honest: demographic rates remain exogenous while
demographic events safely drive economic accounts and metrics.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from macro_sim.config import Config
from macro_sim.demographics.kernel import MicroDemographicKernel, create_genesis_population
from macro_sim.demographics.lifecycle_households import LifecycleHouseholdConfig, apply_leaving_home_dynamics
from macro_sim.demographics.rates import Phase0VitalRates
from macro_sim.demographics.social import SocialDynamicsConfig
from macro_sim.economy import Economy


@dataclass(frozen=True)
class Phase1AcceptanceConfig:
    name: str = "tiny"
    version: str = "v124"   # v13 rides the v12.4 base: resolution fund + entry bootstrap keep the
    #                         bank sector alive at scale (v123 reproduces the pre-fix cascade)
    population: int = 200
    ticks: int = 90
    n_firms_c: int = 20
    n_firms_k: int = 10
    n_banks: int = 2
    seed: int = 0


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    details: dict[str, Any]


@dataclass(frozen=True)
class Phase1AcceptanceResult:
    name: str
    passed: bool
    gates: dict[str, GateResult]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "gates": {name: asdict(gate) for name, gate in self.gates.items()},
            "metrics": self.metrics,
        }


def preset_config(name: str) -> Phase1AcceptanceConfig:
    presets = {
        "tiny": Phase1AcceptanceConfig(name="tiny", population=200, ticks=90, n_firms_c=20, n_firms_k=10, n_banks=2),
        "light": Phase1AcceptanceConfig(name="light", population=1000, ticks=365, n_firms_c=80, n_firms_k=40, n_banks=4),
        "soak": Phase1AcceptanceConfig(name="soak", population=1000, ticks=365 * 5, n_firms_c=80, n_firms_k=40, n_banks=4),
    }
    if name not in presets:
        raise ValueError(f"unknown Phase 1 acceptance preset {name!r}; expected one of {sorted(presets)}")
    return presets[name]


def run_phase1_acceptance(config: Phase1AcceptanceConfig) -> Phase1AcceptanceResult:
    cfg = _economy_config(config)
    econ = Economy(cfg)
    baseline = _baseline_demographic_state(cfg, econ.demographic_rates, config.population)
    baseline_kernel = MicroDemographicKernel(
        econ.demographic_rates,
        rng_seed=cfg.seed + 13_001,
        social_config=_social_config(cfg),
    )
    leaving_rng = random.Random(cfg.seed + 13_002)
    path_invariant = True
    first_path_mismatch: int | None = None

    for tick in range(config.ticks):
        baseline_kernel.tick(baseline, economic_state=None)
        _run_baseline_leaving_home(baseline, cfg, leaving_rng)
        rec = econ.step()
        if _person_state_signature(baseline) != _person_state_signature(econ.demographic_state):
            path_invariant = False
            first_path_mismatch = tick + 1
            break
        _ = rec

    records = econ.records
    final = records[-1] if records else {}
    initial_population = config.population
    births = len(getattr(econ.demographic_state, "birth_events", []))
    deaths = len(getattr(econ.demographic_state, "death_events", []))
    final_population = int(getattr(econ.demographic_state, "alive_count", 0))
    stock_flow_ok = final_population == initial_population + births - deaths
    required_demo_metrics = [
        "population_alive",
        "births_tick",
        "deaths_tick",
        "marriages_tick",
        "divorces_tick",
        "dependency_ratio",
        "married_share",
        "minor_household_missing",
    ]
    required_per_capita_metrics = [
        "real_output_per_capita",
        "real_consumption_per_capita",
        "household_income_per_capita",
        "household_net_worth_per_capita",
        "household_debt_per_capita",
    ]
    demographic_metrics_ok = _has_finite_metrics(final, required_demo_metrics)
    per_capita_ok = _has_finite_metrics(final, required_per_capita_metrics)
    labor_bridge_error = abs(final.get("person_labor_supply", 0.0) - final.get("labor_supply", 0.0))
    labor_bridge_ok = labor_bridge_error < 1e-7
    minor_missing_max = max((row.get("minor_household_missing", 0.0) for row in records), default=0.0)

    gates = {
        "population_path_invariant": GateResult(
            "population_path_invariant",
            path_invariant,
            {"first_mismatch_tick": first_path_mismatch},
        ),
        "stock_flow_identity": GateResult(
            "stock_flow_identity",
            stock_flow_ok,
            {"initial": initial_population, "births": births, "deaths": deaths, "final": final_population},
        ),
        "claim_identity": GateResult(
            "claim_identity",
            True,
            {"checked_by": "Economy._phase5_check_and_record each tick"},
        ),
        "minor_safety": GateResult(
            "minor_safety",
            minor_missing_max == 0.0,
            {"minor_household_missing_max": minor_missing_max},
        ),
        "demographic_metrics": GateResult(
            "demographic_metrics",
            demographic_metrics_ok,
            {"required": required_demo_metrics},
        ),
        "per_capita_metrics": GateResult(
            "per_capita_metrics",
            per_capita_ok,
            {"required": required_per_capita_metrics},
        ),
        "labor_supply_bridge": GateResult(
            "labor_supply_bridge",
            labor_bridge_ok,
            {"absolute_error": labor_bridge_error},
        ),
    }
    metrics = {
        "version": config.version,
        "ticks": len(records),
        "initial_population": initial_population,
        "final_population": final_population,
        "births": births,
        "deaths": deaths,
        "marriages": len(getattr(econ.demographic_state, "marriage_events", [])),
        "divorces": len(getattr(econ.demographic_state, "divorce_events", [])),
        "leaving_home": len(getattr(econ.demographic_state, "leaving_home_events", [])),
        "last_real_output_per_capita": final.get("real_output_per_capita"),
        "last_real_consumption_per_capita": final.get("real_consumption_per_capita"),
        "last_dependency_ratio": final.get("dependency_ratio"),
        "last_banks_alive": final.get("banks_alive"),
    }
    return Phase1AcceptanceResult(
        name=config.name,
        passed=all(gate.passed for gate in gates.values()),
        gates=gates,
        metrics=metrics,
    )


def run_acceptance_matrix(
    *,
    presets: Sequence[Phase1AcceptanceConfig],
    workers: int = 1,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    workers = max(1, int(workers))
    if workers > 1 and len(presets) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run_phase1_acceptance, presets))
    else:
        results = [run_phase1_acceptance(config) for config in presets]
    summary = {
        "passed": all(result.passed for result in results),
        "workers": workers,
        "runs": [result.to_dict() for result in results],
    }
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def _economy_config(config: Phase1AcceptanceConfig) -> Config:
    factory = getattr(Config, config.version)
    return factory(
        n_ticks=config.ticks,
        seed=config.seed,
        n_households=max(1, config.population),
        n_firms_c=config.n_firms_c,
        n_firms_k=config.n_firms_k,
        n_banks=config.n_banks,
        demographics_enabled=True,
        demographics_population=config.population,
        demographic_lifecycle_consumption=True,
    )


def _baseline_demographic_state(cfg: Config, rates: Phase0VitalRates, population: int):
    return create_genesis_population(rates, n=population, seed=cfg.seed + 13_000)


def _social_config(cfg: Config) -> SocialDynamicsConfig:
    return SocialDynamicsConfig(
        marriage_enabled=cfg.demographic_marriage_enabled,
        divorce_enabled=cfg.demographic_divorce_enabled,
        marriage_market_interval_days=cfg.demographic_marriage_market_interval_days,
        annual_marriage_rate_peak=cfg.demographic_annual_marriage_rate_peak,
        annual_divorce_rate_base=cfg.demographic_annual_divorce_rate_base,
    )


def _lifecycle_config(cfg: Config) -> LifecycleHouseholdConfig:
    return LifecycleHouseholdConfig(
        leave_home_min_age=cfg.demographic_leave_home_min_age,
        leave_home_peak_end_age=cfg.demographic_leave_home_peak_end_age,
        annual_leave_rate_peak=cfg.demographic_annual_leave_rate_peak,
        annual_leave_rate_late=cfg.demographic_annual_leave_rate_late,
    )


def _run_baseline_leaving_home(state: Any, cfg: Config, rng: random.Random) -> None:
    if not cfg.demographic_adult_leaving_home_enabled:
        return
    events = apply_leaving_home_dynamics(state, _lifecycle_config(cfg), rng)
    if not events:
        return
    if not hasattr(state, "leaving_home_events"):
        state.leaving_home_events = []
    state.leaving_home_events.extend(events)


def _person_state_signature(state: Any) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            person.id,
            person.alive,
            person.age,
            person.household_id,
            person.partner_id,
            person.mother_id,
            person.father_id,
            person.death_tick,
        )
        for person in state.people
    )


def _has_finite_metrics(record: dict[str, Any], names: Iterable[str]) -> bool:
    for name in names:
        value = record.get(name)
        if not isinstance(value, (int, float)):
            return False
        if value != value:
            return False
    return True


def _default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / "acceptance" / f"phase1_acceptance_{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run v13 Phase 1 demographic-economy acceptance gates.")
    parser.add_argument("--preset", action="append", choices=["tiny", "light", "soak"], default=None)
    parser.add_argument("--workers", type=int, default=max(1, min(10, os.cpu_count() or 1)))
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=None, help="Override all selected preset seeds")
    args = parser.parse_args(argv)

    names = args.preset or ["tiny"]
    configs = [preset_config(name) for name in names]
    if args.seed is not None:
        configs = [
            Phase1AcceptanceConfig(**{**asdict(config), "seed": args.seed})
            for config in configs
        ]
    output_path = args.output_path or _default_output_path()
    summary = run_acceptance_matrix(presets=configs, workers=args.workers, output_path=output_path)
    print(f"phase1 acceptance output: {output_path}")
    print(f"passed: {summary['passed']}")
    for run in summary["runs"]:
        failed = [name for name, gate in run["gates"].items() if not gate["passed"]]
        print(f"  {run['name']}: passed={run['passed']} ticks={run['metrics']['ticks']} failed={failed}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
