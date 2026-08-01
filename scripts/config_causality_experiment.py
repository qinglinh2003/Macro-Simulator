#!/usr/bin/env python3
"""Run one paired Config counterfactual against the native C++ engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.config_experiment import (
    DEFAULT_POPULATION,
    DEFAULT_WORKERS,
    run_root_config_experiment,
    run_world_config_experiment,
)


def _json_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(
            f"invalid JSON treatment value: {error.msg}"
        ) from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", required=True)
    parser.add_argument("--scope", choices=("root", "world"), default="root")
    parser.add_argument("--treatment", required=True, type=_json_value)
    parser.add_argument("--control", type=_json_value)
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument("--population", type=int, default=DEFAULT_POPULATION)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--countries", type=int)
    parser.add_argument("--burn-in-days", type=int)
    parser.add_argument(
        "--series-metric", action="append", dest="series_metric_ids"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runner = (
        run_world_config_experiment
        if args.scope == "world"
        else run_root_config_experiment
    )
    countries = args.countries
    if countries is None:
        countries = 3 if args.scope == "world" else 1
    payload = runner(
        field=args.field,
        treatment_value=args.treatment,
        control_value=args.control,
        seeds=args.seeds or [101, 211, 307, 401],
        population=args.population,
        days=args.days,
        workers=args.workers,
        countries=countries,
        burn_in_days=args.burn_in_days,
        series_metric_ids=args.series_metric_ids or (),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "field": payload["field"],
                "changed_metric_count": payload["changed_metric_count"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
