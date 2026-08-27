#!/usr/bin/env python3
"""Generate or verify the deterministic Policy remediation R5 evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from policy_remediation_r5_lib import build_r5_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "artifacts/policy-remediation/r5/p3-final/p3_report.json"
DEFAULT_EVIDENCE = ROOT / "docs/policy_remediation_r5_p3_evidence_v39.json"
DEFAULT_OUTPUT = ROOT / "docs/policy_remediation_r5_acceptance_v39.json"


def _render(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.write:
        empirical = json.loads(args.source.read_text(encoding="utf-8"))
        args.evidence.write_text(_render(empirical), encoding="utf-8")

    report = build_r5_acceptance(ROOT, args.evidence)
    rendered = _render(report)
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            print(f"stale R5 acceptance report: {args.output}")
            return 1
    else:
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "errors": report["errors"],
                "accepted_states": report["counts"]["accepted_states"],
                "accepted_crises": report["counts"]["accepted_crises"],
                "r5_acceptance_hash": report["hashes"]["r5_acceptance"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
