#!/usr/bin/env python3
"""Run one validated M0 Python-oracle benchmark scenario."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cpp_migration.benchmarks import (  # noqa: E402
    assemble_result,
    load_benchmark_scenarios,
    run_worker,
    run_worker_process,
)
from scripts.cpp_migration.common import (  # noqa: E402
    M0Error,
    canonical_json_bytes,
    write_new_canonical_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scenarios = load_benchmark_scenarios()
        if args.scenario not in scenarios:
            raise M0Error(f"unknown benchmark scenario: {args.scenario}")
        if args.repeat < 1:
            raise M0Error("--repeat must be positive")
        scenario = scenarios[args.scenario]
        if args.worker:
            if args.output.exists():
                raise M0Error(f"refusing to overwrite worker output: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_json_bytes(run_worker(scenario)))
            return 0

        samples = []
        with tempfile.TemporaryDirectory(prefix="macro-m0-benchmark-") as raw:
            root = Path(raw)
            for repetition in range(args.repeat):
                path = root / f"worker-{repetition:03d}.json"
                run_worker_process(args.scenario, path)
                samples.append(json.loads(path.read_text(encoding="utf-8")))
        result = assemble_result(
            scenario,
            samples,
            command=[
                "python_baseline.py",
                "--scenario",
                args.scenario,
                "--repeat",
                str(args.repeat),
            ],
        )
        write_new_canonical_json(args.output, result)
        print(
            f"{args.scenario}: repetitions={args.repeat} "
            f"semantic_digest={result['semantic_result_digest']}"
        )
        return 0
    except (M0Error, OSError, RuntimeError, ValueError) as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
