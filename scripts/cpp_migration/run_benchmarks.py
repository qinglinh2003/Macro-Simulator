#!/usr/bin/env python3
"""Run a named M0 benchmark suite into a transient artifact directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.common import M0Error, REPO_ROOT  # noqa: E402


SUITES = {
    "m0-reference": (
        "full_playable_10k",
        "m4_v0_cash_loop",
        "m4_v1_capital_fiscal",
    ),
    "pr": ("tiny_refactor_v124", "small_closed_daily"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(SUITES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise M0Error(f"refusing to reuse benchmark output directory: {args.output}")
        args.output.mkdir(parents=True)
        for scenario in SUITES[args.suite]:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "benchmarks/python_baseline.py"),
                    "--scenario",
                    scenario,
                    "--repeat",
                    str(args.repeat),
                    "--output",
                    str(args.output / f"{scenario}.json"),
                ],
                cwd=REPO_ROOT,
            )
            if completed.returncode:
                raise M0Error(f"benchmark scenario failed: {scenario}")
        return 0
    except (M0Error, OSError) as exc:
        print(f"benchmark suite error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
