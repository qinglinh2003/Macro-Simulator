#!/usr/bin/env python3
"""Run a resumable native Config combination package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.config_combinations import (
    COMBINATION_PACKAGES,
    run_combination_package,
)


def _source_revision() -> str:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPOSITORY_ROOT,
        text=True,
    )
    digest = hashlib.sha256(status.encode("utf-8"))
    for line in status.splitlines():
        relative = line[3:]
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        path = REPOSITORY_ROOT / relative
        if path.is_file():
            digest.update(relative.encode("utf-8"))
            digest.update(path.read_bytes())
    return f"{commit}+worktree.{digest.hexdigest()[:16]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, choices=COMBINATION_PACKAGES)
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument("--population", type=int, default=100_000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--burn-in-days", type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-resume", action="store_true")
    arguments = parser.parse_args()
    report = run_combination_package(
        COMBINATION_PACKAGES[arguments.package],
        seeds=arguments.seeds or [101, 211, 307, 401],
        artifact_dir=arguments.output_dir,
        source_revision=_source_revision(),
        population=arguments.population,
        workers=arguments.workers,
        burn_in_days=arguments.burn_in_days,
        resume=not arguments.no_resume,
    )
    print(json.dumps({
        "package": arguments.package,
        "design_resolution": report["design_resolution"],
        "executed_runs": report["executed_runs"],
        "cache_hits": report["cache_hits"],
        "output": str(arguments.output_dir / "combination_report.json"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

