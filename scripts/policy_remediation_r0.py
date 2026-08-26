#!/usr/bin/env python3
"""Build the deterministic Policy remediation R0 ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_remediation import (
    build_remediation_ledger,
    validate_remediation_ledger,
    write_remediation_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


def _revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit-root",
        type=Path,
        default=ROOT / "artifacts" / "policy-audit",
        help="directory containing the frozen P1-P8 reports",
    )
    parser.add_argument(
        "--baseline-revision",
        default=_revision(),
        help="revision from which the remediation branch was created",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "docs" / "policy_remediation_ledger_v39.json",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=ROOT / "docs" / "policy_remediation_plan_v39.md",
    )
    parser.add_argument("--fail-on-incomplete", action="store_true")
    args = parser.parse_args()

    sources = {
        "p1_source": args.audit_root / "p1" / "p1_report.json",
        **{
            f"p{stage}_source": (
                args.audit_root / f"p{stage}" / f"p{stage}_report.json"
            )
            for stage in range(2, 9)
        },
    }
    payload = build_remediation_ledger(
        **sources,
        baseline_revision=args.baseline_revision,
        expected_levers=REGISTRY,
    )
    serialized_errors = validate_remediation_ledger(payload)
    if serialized_errors:
        print(json.dumps({
            "status": "failed",
            "errors": serialized_errors,
        }, indent=2, sort_keys=True))
        return 1
    write_remediation_artifacts(
        payload, args.output_json, args.output_markdown,
    )
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "errors": payload["errors"],
        "r0_acceptance_hash": payload["hashes"]["r0_acceptance"],
    }, indent=2, sort_keys=True))
    if args.fail_on_incomplete and payload["status"] != "accepted":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
