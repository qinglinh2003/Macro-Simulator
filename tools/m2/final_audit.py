#!/usr/bin/env python3
"""Audit the frozen M2 canonical-accounting milestone."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from locks import (
    HASHES_PATH,
    M1_COMMIT,
    SOURCE_PATH,
    VENDOR_PATH,
    build_contract_lock,
    build_source_lock,
    build_vendor_lock,
    canonical_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
CJK_PATTERN = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class AuditError(RuntimeError):
    """Raised when M2 evidence is incomplete or stale."""


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def check_command(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise AuditError(f"check failed ({' '.join(command)}): {detail}")


def check_frozen_predecessors() -> None:
    roots = (
        "schemas/m0",
        "schemas/m1",
        "benchmarks/results/m0/reference",
        "tests/fixtures/m0/expected",
    )
    completed = subprocess.run(
        ["git", "diff", "--quiet", M1_COMMIT, "--", *roots],
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise AuditError("M0 or M1 frozen evidence differs from the M1 milestone")
    m1_lock = json.loads(
        (ROOT / "schemas/m1/source.lock.json").read_text(encoding="utf-8")
    )
    for item in m1_lock["files"]:
        content = subprocess.run(
            ["git", "show", f"{M1_COMMIT}:{item['path']}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        if sha256(content).hexdigest() != item["sha256"]:
            raise AuditError(f"M1 Git object differs from its lock: {item['path']}")


def check_english_delta() -> None:
    subjects = git("log", "--format=%s", f"{M1_COMMIT}..HEAD").splitlines()
    if any(CJK_PATTERN.search(subject) for subject in subjects):
        raise AuditError("an M2 commit subject contains CJK text")
    changed = git(
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        M1_COMMIT,
        "HEAD",
    ).splitlines()
    for relative in changed:
        path = ROOT / relative
        if not path.is_file() or "vendor" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if CJK_PATTERN.search(text):
            raise AuditError(f"an M2 text file contains CJK text: {relative}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot load {path.relative_to(ROOT)}: {error}") from error


def audit(*, require_clean: bool) -> dict[str, Any]:
    dirty = bool(git("status", "--porcelain"))
    if require_clean and dirty:
        raise AuditError("M2 final audit requires a clean working tree")
    check_command(["git", "merge-base", "--is-ancestor", M1_COMMIT, "HEAD"])
    check_frozen_predecessors()
    check_english_delta()
    if load_json(VENDOR_PATH) != build_vendor_lock():
        raise AuditError("M2 vendor lock is stale")
    if load_json(HASHES_PATH) != build_contract_lock():
        raise AuditError("M2 contract lock is stale")
    if load_json(SOURCE_PATH) != build_source_lock():
        raise AuditError("M2 source lock is stale")
    check_command([sys.executable, "tools/m2/check.py", "--skip-build"])

    workflow = (ROOT / ".github/workflows/native.yml").read_text(encoding="utf-8")
    platforms = ("macos-14", "ubuntu-24.04", "windows-2022")
    if not all(platform in workflow for platform in platforms):
        raise AuditError("M2 CI does not declare every required platform")
    c_header = (ROOT / "native/include/macro_sim/c_api.h").read_text(
        encoding="utf-8"
    )
    if (
        "#define MACRO_SIM_ABI_VERSION 1u" not in c_header
        or "MACRO_SIM_CAPABILITY_M2_ACCOUNTING" not in c_header
    ):
        raise AuditError("M2 C ABI version or capability declaration is absent")

    contract = load_json(HASHES_PATH)
    source = load_json(SOURCE_PATH)
    vendor = load_json(VENDOR_PATH)
    return {
        "base_commit": M1_COMMIT,
        "ci_platforms": list(platforms),
        "clean": not dirty,
        "head": git("rev-parse", "HEAD"),
        "m2_contract_sha256": contract["aggregate_sha256"],
        "m2_source_sha256": source["aggregate_sha256"],
        "schema_version": "m2-freeze-audit-v1",
        "source_file_count": len(source["files"]),
        "status": "passed",
        "vendor_sha256": vendor["aggregate_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true")
    arguments = parser.parse_args()
    try:
        sys.stdout.buffer.write(
            canonical_bytes(audit(require_clean=arguments.require_clean))
        )
        return 0
    except (AuditError, OSError, KeyError, ValueError) as error:
        print(f"M2 final audit error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
