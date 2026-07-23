#!/usr/bin/env python3
"""Generate or verify the checked M0 Python-oracle inventories."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.common import (  # noqa: E402
    M0Error,
    REPO_ROOT,
    check_or_write_generated,
)
from scripts.cpp_migration.inventory import (  # noqa: E402
    INVENTORY_FAMILIES,
    build_all_inventories,
    build_hash_lock,
    validate_cross_references,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--family", action="append", choices=INVENTORY_FAMILIES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        inventories = build_all_inventories()
        validate_cross_references(inventories)
        selected = set(args.family or INVENTORY_FAMILIES)
        for family in INVENTORY_FAMILIES:
            if family not in selected:
                continue
            path = REPO_ROOT / "schemas/m0/inventory" / f"{family}.json"
            matched = check_or_write_generated(
                path,
                inventories[family],
                check=args.check,
            )
            state = "ok" if matched else "written"
            print(f"{state:7} {family:18} {len(inventories[family]['rows']):5d} rows")
        if selected == set(INVENTORY_FAMILIES):
            lock_path = REPO_ROOT / "schemas/m0/hashes.lock.json"
            lock = build_hash_lock()
            matched = check_or_write_generated(lock_path, lock, check=args.check)
            print(f"{'ok' if matched else 'written':7} hash-lock")
    except M0Error as exc:
        print(f"inventory error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
