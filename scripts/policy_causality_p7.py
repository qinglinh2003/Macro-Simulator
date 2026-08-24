#!/usr/bin/env python3
"""Freeze P7 empirical anchors and player-facing policy evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from macro_sim.diagnostics.policy_empirical_freeze import (
    render_p7_markdown,
    run_p7,
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
        default=ROOT / "artifacts" / "policy-audit" / "p7",
    )
    for stage in range(2, 7):
        parser.add_argument(
            f"--p{stage}-report",
            type=Path,
            default=(
                ROOT / "artifacts" / "policy-audit" / f"p{stage}"
                / f"p{stage}_report.json"
            ),
        )
    parser.add_argument(
        "--policy-explanations",
        type=Path,
        default=(
            ROOT / "macro_sim" / "data" / "locales" / "zh_CN"
            / "policy_explanations.json"
        ),
    )
    parser.add_argument("--fail-on-incomplete", action="store_true")
    args = parser.parse_args()

    payload = run_p7(
        artifact_dir=args.artifact_dir,
        source_revision=_revision(),
        p2_source=args.p2_report,
        p3_source=args.p3_report,
        p4_source=args.p4_report,
        p5_source=args.p5_report,
        p6_source=args.p6_report,
        explanation_source=args.policy_explanations,
    )
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    (args.artifact_dir / "p7_report.md").write_text(
        render_p7_markdown(payload), encoding="utf-8"
    )
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "p7_acceptance_hash": payload["hashes"]["p7_acceptance"],
    }, indent=2, sort_keys=True))
    if (
        args.fail_on_incomplete
        and payload["status"] != "accepted_with_explicit_defects"
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
