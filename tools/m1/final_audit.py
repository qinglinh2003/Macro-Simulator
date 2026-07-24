#!/usr/bin/env python3
"""Audit the frozen M1 native foundation without changing checked evidence."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "38e7e5b37b8ae55fdd0c5f9180f0390b258e6597"
M0_CONTRACT_SHA256 = (
    "08cb44d8cbdf90ca70d791bb34b0cdb831a64690aca6c57c004890288ea60173"
)
LOCK_PATH = ROOT / "schemas/m1/source.lock.json"
CJK_PATTERN = re.compile(
    "[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)


class AuditError(RuntimeError):
    """Raised when checked M1 evidence is incomplete or stale."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def source_paths() -> tuple[Path, ...]:
    exact = (
        ROOT / ".clang-format",
        ROOT / ".clang-tidy",
        ROOT / ".gitattributes",
        ROOT / ".github/workflows/native.yml",
        ROOT / "CMakeLists.txt",
        ROOT / "CMakePresets.json",
        ROOT / "docs/adr/0001-m1-canonical-encoding-and-checkpoints.md",
        ROOT / "docs/cpp_engine_m1_execution_plan_v33.md",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    )
    paths = set(exact)
    for directory in (
        ROOT / "native",
        ROOT / "schemas/m1",
        ROOT / "tests/native",
        ROOT / "tools/m1",
    ):
        paths.update(path for path in directory.rglob("*") if path.is_file())
    paths.discard(LOCK_PATH)
    paths = {
        path
        for path in paths
        if "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    }
    missing = [path for path in sorted(paths) if not path.is_file()]
    if missing:
        raise AuditError(f"M1 source inputs are absent: {missing}")
    return tuple(
        sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())
    )


def build_source_lock() -> dict[str, Any]:
    files = []
    mapping = {}
    for path in source_paths():
        relative = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        digest = sha256(content).hexdigest()
        mapping[relative] = digest
        files.append(
            {
                "path": relative,
                "byte_count": len(content),
                "sha256": digest,
            }
        )
    aggregate_input = "".join(
        f"{path}\0{mapping[path]}\n" for path in sorted(mapping)
    ).encode("utf-8")
    return {
        "schema_version": "m1-source-lock-v1",
        "base_commit": BASE_COMMIT,
        "m0_contract_sha256": M0_CONTRACT_SHA256,
        "files": files,
        "aggregate_sha256": sha256(aggregate_input).hexdigest(),
    }


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


def check_m0_frozen() -> None:
    roots = (
        "schemas/m0",
        "tests/fixtures/m0/expected",
        "benchmarks/results/m0/reference",
    )
    completed = subprocess.run(
        ["git", "diff", "--quiet", BASE_COMMIT, "--", *roots],
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise AuditError("M0 frozen evidence differs from the M1 base")
    lock = json.loads(
        (ROOT / "schemas/m0/hashes.lock.json").read_text(encoding="utf-8")
    )
    if lock.get("aggregate_sha256") != M0_CONTRACT_SHA256:
        raise AuditError("M0 aggregate contract hash differs")


def check_english_changes() -> None:
    subjects = git("log", "--format=%s", f"{BASE_COMMIT}..HEAD").splitlines()
    if any(CJK_PATTERN.search(subject) for subject in subjects):
        raise AuditError("an M1 commit subject contains CJK text")
    changed = git(
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        BASE_COMMIT,
        "HEAD",
    ).splitlines()
    for relative in changed:
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if CJK_PATTERN.search(text):
            raise AuditError(f"an M1 text file contains CJK text: {relative}")


def audit(*, require_clean: bool) -> dict[str, Any]:
    head = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    if require_clean and dirty:
        raise AuditError("M1 final audit requires a clean working tree")
    check_command(["git", "merge-base", "--is-ancestor", BASE_COMMIT, "HEAD"])
    check_m0_frozen()
    check_english_changes()
    expected_lock = build_source_lock()
    try:
        actual_lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot load M1 source lock: {error}") from error
    if actual_lock != expected_lock:
        raise AuditError("M1 source lock is stale")
    checks = (
        [sys.executable, "tools/m1/bootstrap.py", "--check"],
        [sys.executable, "tools/m1/generate_contracts.py", "--check"],
        [sys.executable, "tools/m1/generate_rng_vectors.py", "--check"],
        [sys.executable, "tools/m1/checkpoint_prototype.py", "--check"],
        [sys.executable, "tools/m1/dependency_report.py", "--check"],
    )
    for command in checks:
        check_command(command)
    native_sources = {
        path.name for path in (ROOT / "native/src").glob("*.cpp")
    }
    expected_native_sources = {
        "c_api.cpp",
        "engine_session.cpp",
        "python_bindings.cpp",
        "rng.cpp",
        "version.cpp",
    }
    if native_sources != expected_native_sources:
        raise AuditError(
            "M1 contains an unexpected native implementation source: "
            f"{sorted(native_sources)}"
        )
    workflow = (ROOT / ".github/workflows/native.yml").read_text(encoding="utf-8")
    platforms = ("macos-14", "ubuntu-24.04", "windows-2022")
    if not all(platform in workflow for platform in platforms):
        raise AuditError("native CI does not declare every required platform")
    contract_lock = json.loads(
        (ROOT / "schemas/m1/hashes.lock.json").read_text(encoding="utf-8")
    )
    return {
        "schema_version": "m1-freeze-audit-v1",
        "status": "passed",
        "base_commit": BASE_COMMIT,
        "m1_commit": head,
        "clean": not dirty,
        "m0_contract_sha256": M0_CONTRACT_SHA256,
        "m1_contract_sha256": contract_lock["aggregate_sha256"],
        "m1_source_sha256": expected_lock["aggregate_sha256"],
        "source_file_count": len(expected_lock["files"]),
        "native_source_count": len(native_sources),
        "ci_platforms": list(platforms),
        "cross_platform_acceptance_source": "same-commit-ci-artifacts",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-lock", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_lock:
            LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOCK_PATH.write_bytes(canonical_bytes(build_source_lock()))
            print(f"write   {LOCK_PATH.relative_to(ROOT)}")
            return 0
        result = audit(require_clean=args.require_clean)
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except (AuditError, OSError, KeyError, ValueError) as error:
        print(f"M1 final audit error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
