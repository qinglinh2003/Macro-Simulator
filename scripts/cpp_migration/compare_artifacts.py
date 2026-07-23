#!/usr/bin/env python3
"""Compare M0 artifacts, self-test rules, or audit repeated gate trees."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.common import M0Error, SchemaError  # noqa: E402
from scripts.cpp_migration.comparator import (  # noqa: E402
    first_artifact_difference,
    load_tolerance_registry,
    repeatability_tree_digest,
    run_comparator_self_test,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="*", type=Path)
    parser.add_argument("--self-test", type=Path)
    parser.add_argument("--repeatability", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_test is not None:
            if args.artifacts or args.repeatability:
                raise SchemaError("--self-test cannot be combined with artifacts")
            run_comparator_self_test(args.self_test)
            print("comparator self-test: passed")
            return 0
        if args.repeatability:
            if len(args.artifacts) < 2:
                raise SchemaError("repeatability requires at least two roots")
            digests = [repeatability_tree_digest(path) for path in args.artifacts]
            if len(set(digests)) != 1:
                raise SchemaError(f"repeatability digests differ: {digests}")
            print(f"repeatability: passed sha256={digests[0]}")
            return 0
        if len(args.artifacts) != 2:
            raise SchemaError("comparison requires exactly two JSON artifacts")
        expected = json.loads(args.artifacts[0].read_text(encoding="utf-8"))
        actual = json.loads(args.artifacts[1].read_text(encoding="utf-8"))
        failure = first_artifact_difference(
            expected,
            actual,
            load_tolerance_registry(),
        )
        if failure is not None:
            raise SchemaError(
                f"{failure.reason} at {failure.path} "
                f"(rule={failure.rule_id}, expected={failure.expected!r}, "
                f"actual={failure.actual!r})"
            )
        print("artifact comparison: passed")
        return 0
    except (M0Error, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"artifact comparison error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
