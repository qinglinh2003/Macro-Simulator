#!/usr/bin/env python3
"""Generate or verify the deterministic Policy remediation R4 report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from macro_sim.diagnostics.policy_state_machines import build_r4_acceptance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "policy_remediation_r4_acceptance_v39.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = build_r4_acceptance(ROOT)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            print(f"stale R4 acceptance report: {args.output}")
            return 1
    else:
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "errors": report["errors"],
                "r4_acceptance_hash": report["hashes"]["r4_acceptance"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
