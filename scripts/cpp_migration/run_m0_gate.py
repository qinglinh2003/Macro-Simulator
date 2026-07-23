#!/usr/bin/env python3
"""List or execute the machine-readable M0 gate graph."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.common import M0Error, REPO_ROOT  # noqa: E402
from scripts.cpp_migration.gates import (  # noqa: E402
    GATE_CLASSES,
    load_gate_manifest,
    run_gates,
    select_gates,
)


DEFAULT_MANIFEST = REPO_ROOT / "schemas" / "m0" / "manifests" / "gates.yaml"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "migration" / "gates"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class", dest="gate_class", choices=GATE_CLASSES, default="pr")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--list", action="store_true", help="validate and list selected gates")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_gate_manifest(args.manifest)
        gates = select_gates(
            manifest,
            gate_class=args.gate_class,
            only=tuple(args.only),
        )
        if args.list:
            for gate in gates:
                print(f"{gate.id}\t{gate.gate_class}\t{' '.join(gate.command)}")
            return 0
        summary = run_gates(manifest, gates, artifact_root=args.artifact_root)
    except M0Error as exc:
        print(f"M0 gate error: {exc}", file=sys.stderr)
        return 2
    for result in summary["results"]:
        print(f"{result['status'].upper():7} {result['id']}")
    print(f"M0 gate run: {summary['status']}")
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
