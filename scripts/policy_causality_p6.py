#!/usr/bin/env python3
"""Run native P6 finite-size and rare-event policy confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from macro_sim.diagnostics.policy_scale_confirmation import (
    P6_POPULATIONS,
    P6_SEEDS,
    render_p6_markdown,
    run_p6,
)


ROOT = Path(__file__).resolve().parents[1]


def _revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=ROOT / "artifacts" / "policy-audit" / "p6",
    )
    parser.add_argument(
        "--p2-report",
        type=Path,
        default=ROOT / "artifacts" / "policy-audit" / "p2" / "p2_report.json",
    )
    parser.add_argument(
        "--p5-report",
        type=Path,
        default=ROOT / "artifacts" / "policy-audit" / "p5" / "p5_report.json",
    )
    parser.add_argument("--small-jobs", type=int, default=4)
    parser.add_argument("--large-jobs", type=int, default=1)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--fail-on-incomplete", action="store_true")
    args = parser.parse_args()

    completed = 0

    def progress(result: dict[str, object], cached: bool) -> None:
        nonlocal completed
        completed += 1
        print(
            f"[{completed}] population={result['population']} seed={result['seed']} "
            f"lever={result['lever']} {'cache' if cached else 'fresh'}",
            flush=True,
        )

    payload = run_p6(
        artifact_dir=args.artifact_dir,
        source_revision=_revision(),
        p2_source=args.p2_report,
        p5_source=args.p5_report,
        seeds=(P6_SEEDS[0],) if args.preflight else P6_SEEDS,
        populations=(P6_POPULATIONS[0],) if args.preflight else P6_POPULATIONS,
        workers=8,
        small_jobs=args.small_jobs,
        large_jobs=args.large_jobs,
        resume=not args.no_resume,
        formal=not args.preflight,
        progress=progress,
    )
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    (args.artifact_dir / "p6_report.md").write_text(
        render_p6_markdown(payload), encoding="utf-8"
    )
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "p6_acceptance_hash": payload["hashes"]["p6_acceptance"],
    }, indent=2, sort_keys=True))
    if args.fail_on_incomplete and payload["status"] not in {
        "accepted_with_explicit_defects", "preflight_complete"
    }:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
