"""Command-line entry point for the production economic diagnostic suite."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Sequence

from macro_sim.diagnostics.runner import run_diagnostic_suite
from macro_sim.diagnostics.scenarios import diagnostic_matrix, profile_defaults, root_cause_matrix


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run multi-seed economic diagnostics and causal probes.")
    parser.add_argument("--profile", choices=("smoke", "audit", "production", "soak"), default="audit")
    parser.add_argument(
        "--matrix", choices=("causal", "root-causes"), default="causal",
        help="Temporary paired interventions or ten permanent mechanism ablations.",
    )
    parser.add_argument("--workers", type=int, default=10, help="Independent worker processes; capped at 10.")
    parser.add_argument("--seeds", type=int, default=5, help="Baseline seeds; five gives the default ten-job matrix.")
    parser.add_argument(
        "--intervention-replicates", type=int, default=1,
        help="Causal arms per intervention across the first N baseline seeds (1..seeds).",
    )
    parser.add_argument("--seed", type=int, default=0, help="Common seed for the root-cause ablation matrix.")
    parser.add_argument("--ticks", type=int, default=None)
    parser.add_argument("--population", type=int, default=None)
    parser.add_argument("--n-firms-c", type=int, default=None)
    parser.add_argument("--n-firms-k", type=int, default=None)
    parser.add_argument("--n-banks", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-world", action="store_true", help="Skip the fast open-economy identity probes.")
    args = parser.parse_args(argv)

    params = profile_defaults(args.profile)
    for name, value in (
        ("ticks", args.ticks), ("population", args.population),
        ("n_firms_c", args.n_firms_c), ("n_firms_k", args.n_firms_k),
        ("n_banks", args.n_banks),
    ):
        if value is not None:
            params[name] = value
    specs = (
        diagnostic_matrix(
            **params,
            seeds=args.seeds,
            intervention_replicates=args.intervention_replicates,
        )
        if args.matrix == "causal"
        else root_cause_matrix(**params, seed=args.seed)
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir or Path("artifacts") / "diagnostics" / (
        f"v23_{args.profile}_{args.matrix}_{stamp}"
    )
    payload = run_diagnostic_suite(
        specs, output_dir=output_dir, workers=args.workers, include_world=not args.skip_world,
    )
    critical = sum(issue["severity"] == "critical" for issue in payload["issues"])
    high = sum(issue["severity"] == "high" for issue in payload["issues"])
    print(f"report: {output_dir / 'REPORT.md'}")
    print(f"issues: {critical} critical, {high} high, {len(payload['issues'])} total")
    valid_execution = (
        payload["manifest"]["successful"] == payload["manifest"]["jobs"]
        and payload["manifest"]["reproducibility_valid"]
    )
    return 0 if valid_execution else 1


if __name__ == "__main__":
    raise SystemExit(main())
