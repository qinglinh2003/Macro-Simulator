#!/usr/bin/env python3
"""Run native P8 institutional delivery and occupant evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from macro_sim.diagnostics.policy_institutional_delivery import run_p8


ROOT = Path(__file__).resolve().parents[1]


def _revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=ROOT / "artifacts" / "policy-audit" / "p8",
    )
    for stage in (3, 4, 7):
        parser.add_argument(
            f"--p{stage}-report",
            type=Path,
            default=(
                ROOT / "artifacts" / "policy-audit" / f"p{stage}"
                / f"p{stage}_report.json"
            ),
        )
    parser.add_argument(
        "--p4-artifact-dir",
        type=Path,
        default=ROOT / "artifacts" / "policy-audit" / "p4",
    )
    parser.add_argument(
        "--rl-artifact",
        type=Path,
        default=(
            ROOT / "macro_sim" / "rl" / "artifacts"
            / "fiscal_stabilization_v1.msrl"
        ),
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--fail-on-incomplete", action="store_true")
    args = parser.parse_args()

    completed = 0

    def progress(seed: int) -> None:
        nonlocal completed
        completed += 1
        print(f"[{completed}/8] delivery seed={seed}", flush=True)

    payload = run_p8(
        artifact_dir=args.artifact_dir,
        source_revision=_revision(),
        p3_source=args.p3_report,
        p4_source=args.p4_report,
        p7_source=args.p7_report,
        p4_artifact_dir=args.p4_artifact_dir,
        rl_artifact=args.rl_artifact,
        resume=not args.no_resume,
        progress=progress,
    )
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "p8_acceptance_hash": payload["hashes"]["p8_acceptance"],
    }, indent=2, sort_keys=True))
    if (
        args.fail_on_incomplete
        and payload["status"] != "accepted_with_explicit_limitations"
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
