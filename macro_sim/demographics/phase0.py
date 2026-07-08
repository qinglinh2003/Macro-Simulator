"""CLI for generating the Phase 0 demographic genesis pyramid."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from macro_sim.demographics.kernel import create_genesis_population
from macro_sim.demographics.leslie import build_leslie_matrix, spectral_diagnostics, stable_age_distribution
from macro_sim.demographics.rates import Phase0VitalRates, expected_life_at_birth
from macro_sim.demographics.visualization import plot_stable_pyramid


def generate_phase0_artifacts(
    *,
    output_dir: str | Path,
    n: int = 40_000,
    seed: int = 0,
    start_date: date = date(2000, 1, 1),
    build_relationships: bool = True,
) -> dict:
    output_dir = Path(output_dir)
    rates = Phase0VitalRates()
    matrix = build_leslie_matrix(rates)
    stable = stable_age_distribution(matrix)
    diag = spectral_diagnostics(matrix, dt=rates.dt)
    state = create_genesis_population(
        rates,
        n=n,
        seed=seed,
        start_date=start_date,
        build_relationships=build_relationships,
    )
    figure = plot_stable_pyramid(stable, rates, output_dir / "stable_pyramid.png")
    metrics = {
        "n": n,
        "seed": seed,
        "current_date": state.current_date.isoformat(),
        "omega": rates.omega,
        "dt": rates.dt,
        "e0": expected_life_at_birth(rates),
        "lambda1": diag.lambda1,
        "growth_rate": diag.growth_rate,
        "damping_ratio": diag.damping_ratio,
        "cycle_period": diag.cycle_period,
        "alive_count": state.alive_count,
        "relationship_stats": state.relationship_stats.to_dict() if state.relationship_stats is not None else None,
        "figure": str(figure),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True))
    return metrics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 0 demographic kernel artifacts.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/demographics/phase0_kernel"))
    parser.add_argument("--n", type=int, default=40_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2000, 1, 1))
    parser.add_argument("--no-relationships", action="store_true")
    args = parser.parse_args(argv)
    metrics = generate_phase0_artifacts(
        output_dir=args.output_dir,
        n=args.n,
        seed=args.seed,
        start_date=args.start_date,
        build_relationships=not args.no_relationships,
    )
    print(f"output_dir: {args.output_dir}")
    print(
        f"e0={metrics['e0']:.2f} lambda={metrics['lambda1']:.6f} "
        f"r={metrics['growth_rate']:.5f} damping={metrics['damping_ratio']:.5f}"
    )
    if metrics["relationship_stats"] is not None:
        rel = metrics["relationship_stats"]
        print(
            f"households={rel['households']} avg_size={rel['avg_household_size']:.2f} "
            f"minor_placement={rel['minor_placement_rate']:.3f} "
            f"parent_coverage={rel['minor_parent_coverage_rate']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
