#!/usr/bin/env python3
"""Generate or check compact current-client M0 contracts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.client_traces import build_client_contracts  # noqa: E402
from scripts.cpp_migration.common import (  # noqa: E402
    M0Error,
    REPO_ROOT,
    check_or_write_generated,
)


OUTPUT = REPO_ROOT / "tests/fixtures/m0/clients/contracts.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        matched = check_or_write_generated(
            OUTPUT,
            build_client_contracts(),
            check=args.check,
        )
        print(f"{'ok' if matched else 'written':7} {OUTPUT}")
        return 0
    except M0Error as exc:
        print(f"client contract error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
