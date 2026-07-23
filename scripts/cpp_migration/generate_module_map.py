#!/usr/bin/env python3
"""Generate or check the current module map from M0 disposition data."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.common import M0Error, REPO_ROOT  # noqa: E402
from scripts.cpp_migration.module_map import build_module_map  # noqa: E402


OUTPUT = REPO_ROOT / "docs/design/current/module-map.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = build_module_map().encode("utf-8")
    try:
        if args.check:
            if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
                raise M0Error(f"generated module map is stale: {OUTPUT}")
            print(f"ok      {OUTPUT}")
            return 0
        OUTPUT.write_bytes(expected)
        print(f"written {OUTPUT}")
        return 0
    except (M0Error, OSError) as exc:
        print(f"module-map error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
