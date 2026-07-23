#!/usr/bin/env python3
"""Create a reviewable rebaseline proposal without changing checked evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.common import (  # noqa: E402
    BaselineWriteError,
    M0Error,
    REPO_ROOT,
    aggregate_hash,
    canonical_json_bytes,
    environment_metadata,
    git_metadata,
    reject_checked_baseline_target,
    sha256_bytes,
    tree_hashes,
)


def build_proposal(
    *,
    reason: str,
    before_root: Path | None,
    after_root: Path | None,
    old_oracle_commit: str | None,
    new_oracle_commit: str | None,
) -> dict[str, Any]:
    if not reason.strip():
        raise BaselineWriteError("rebaseline reason must not be empty")
    before = tree_hashes(before_root) if before_root else {}
    after = tree_hashes(after_root) if after_root else {}
    changed = sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )
    git = git_metadata()
    return {
        "schema_version": "m0-rebaseline-proposal-v1",
        "old_oracle_commit": old_oracle_commit,
        "new_oracle_commit": new_oracle_commit or git.commit,
        "current_commit": git.commit,
        "dirty": git.dirty,
        "reason": reason.strip(),
        "reason_sha256": sha256_bytes(reason.strip().encode("utf-8")),
        "before": {
            "root": str(before_root) if before_root else None,
            "files": before,
            "aggregate_sha256": aggregate_hash(before),
        },
        "after": {
            "root": str(after_root) if after_root else None,
            "files": after,
            "aggregate_sha256": aggregate_hash(after),
        },
        "changed_paths": changed,
        "environment": environment_metadata(),
        "application": {
            "automatic": False,
            "review_required": True,
            "checked_files_modified": False,
        },
    }


def write_proposal(output: Path, proposal: dict[str, Any]) -> Path:
    reject_checked_baseline_target(output)
    if output.exists():
        raise BaselineWriteError(f"proposal output already exists: {output}")
    output.mkdir(parents=True)
    path = output / "proposal.json"
    path.write_bytes(canonical_json_bytes(proposal))
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reason-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--before-root", type=Path)
    parser.add_argument("--after-root", type=Path)
    parser.add_argument("--old-oracle-commit")
    parser.add_argument("--new-oracle-commit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        reason = args.reason_file.read_text(encoding="utf-8")
        proposal = build_proposal(
            reason=reason,
            before_root=args.before_root,
            after_root=args.after_root,
            old_oracle_commit=args.old_oracle_commit,
            new_oracle_commit=args.new_oracle_commit,
        )
        path = write_proposal(args.output, proposal)
    except (OSError, M0Error) as exc:
        print(f"rebaseline proposal error: {exc}", file=sys.stderr)
        return 2
    print(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
