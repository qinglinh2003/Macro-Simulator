#!/usr/bin/env python3
"""Run a curated, resumable Config screening batch."""

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

from macro_sim.diagnostics.config_batch import run_contract_batch
from macro_sim.diagnostics.config_contracts import (
    activation_contracts,
    screening_contracts,
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
    digest = hashlib.sha256()
    digest.update(status.encode("utf-8"))
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
    parser.add_argument("--module", required=True)
    parser.add_argument(
        "--activation",
        action="store_true",
        help="run reviewed contracts that require a shared activation scenario",
    )
    parser.add_argument("--field", action="append", dest="fields")
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument("--population", type=int, default=100_000)
    parser.add_argument("--days", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--burn-in-days", type=int)
    parser.add_argument("--stage", default="screening")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    contracts = (
        activation_contracts(module=args.module)
        if args.activation
        else screening_contracts(module=args.module)
    )
    if args.fields:
        requested = set(args.fields)
        contracts = tuple(
            contract
            for contract in contracts
            if contract.field_name in requested
        )
        missing = requested - {contract.field_name for contract in contracts}
        if missing:
            parser.error(
                "fields are not executable in the selected contract set: "
                + ", ".join(sorted(missing))
            )
    payload = run_contract_batch(
        contracts,
        seeds=args.seeds or [101, 211, 307, 401],
        artifact_dir=args.output_dir,
        source_revision=_source_revision(),
        stage=args.stage,
        population=args.population,
        days_override=args.days,
        workers=args.workers,
        burn_in_days=args.burn_in_days,
        resume=not args.no_resume,
    )
    print(
        json.dumps(
            {
                "contract_count": payload["contract_count"],
                "executed_runs": payload["executed_runs"],
                "cache_hits": payload["cache_hits"],
                "output": str(args.output_dir / "batch_report.json"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
