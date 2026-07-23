#!/usr/bin/env python3
"""Generate or check M0 fixture manifests and canonical tape bundles."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.common import (  # noqa: E402
    M0Error,
    check_or_write_generated,
)
from scripts.cpp_migration.fixtures import (  # noqa: E402
    OUTPUT_ROOT,
    build_fixture_manifest,
    load_tape_bundle,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        outputs = {
            OUTPUT_ROOT / "manifests/fixtures.json": build_fixture_manifest(),
            OUTPUT_ROOT / "tapes/bundle.json": load_tape_bundle(),
        }
        for path, value in outputs.items():
            matched = check_or_write_generated(path, value, check=args.check)
            print(f"{'ok' if matched else 'written':7} {path}")
        return 0
    except M0Error as exc:
        print(f"fixture generation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
