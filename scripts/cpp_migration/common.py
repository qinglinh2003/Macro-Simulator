"""Shared M0 artifact, hashing, metadata, and validation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any


M0_JSON_VERSION = "m0-json-v1"
STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._:/-][a-z0-9]+)*$")
REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKED_BASELINE_ROOTS = (
    REPO_ROOT / "schemas" / "m0",
    REPO_ROOT / "tests" / "fixtures" / "m0" / "expected",
    REPO_ROOT / "benchmarks" / "results" / "m0" / "reference",
)


class M0Error(RuntimeError):
    """Base class for actionable M0 contract failures."""


class SchemaError(M0Error):
    """Raised when a machine-readable M0 contract is malformed."""


class BaselineWriteError(M0Error):
    """Raised when a command attempts to overwrite reviewed evidence."""


@dataclass(frozen=True)
class GitMetadata:
    commit: str
    dirty: bool


def canonical_json_bytes(value: Any) -> bytes:
    """Encode an M0 artifact in the checked ``m0-json-v1`` format."""

    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"value is not canonical JSON: {exc}") from exc
    return (text + "\n").encode("utf-8")


def canonical_json_load(path: Path) -> Any:
    """Load JSON and reject non-standard NaN/Infinity tokens."""

    def reject_constant(token: str) -> None:
        raise SchemaError(f"{path}: non-finite JSON token {token}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=reject_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"cannot load {path}: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate_hash(entries: Mapping[str, str]) -> str:
    """Hash a sorted path-to-digest mapping without depending on insertion order."""

    payload = "".join(f"{path}\0{entries[path]}\n" for path in sorted(entries))
    return sha256_bytes(payload.encode("utf-8"))


def tree_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise SchemaError(f"artifact tree does not exist: {root}")
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def validate_stable_id(value: str, *, field: str = "id") -> str:
    if not isinstance(value, str) or not STABLE_ID_PATTERN.fullmatch(value):
        raise SchemaError(
            f"{field} must match {STABLE_ID_PATTERN.pattern!r}, got {value!r}"
        )
    return value


def require_unique_ids(rows: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for index, row in enumerate(rows):
        value = validate_stable_id(row.get("id"), field=f"rows[{index}].id")
        if value in seen:
            raise SchemaError(f"duplicate stable id: {value}")
        seen.add(value)
        result.append(value)
    return tuple(result)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def reject_checked_baseline_target(path: Path) -> None:
    resolved = path.resolve()
    for root in CHECKED_BASELINE_ROOTS:
        if is_relative_to(resolved, root.resolve()):
            raise BaselineWriteError(
                f"proposal output cannot be inside checked baseline root {root}"
            )


def write_new_canonical_json(path: Path, value: Any) -> None:
    """Write a new transient artifact and refuse all overwrites."""

    if path.exists():
        raise BaselineWriteError(f"refusing to overwrite existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def check_or_write_generated(path: Path, value: Any, *, check: bool) -> bool:
    """Check or update a generated checked artifact.

    Returns ``True`` when existing bytes already match. In check mode, a
    missing or stale file raises. In write mode, only the named generated file
    is replaced; expected fixture and reference-baseline files use the
    proposal-first rebaseline path instead.
    """

    expected = canonical_json_bytes(value)
    if path.exists() and path.read_bytes() == expected:
        return True
    if check:
        state = "missing" if not path.exists() else "stale"
        raise M0Error(f"generated artifact is {state}: {path}")
    if is_relative_to(path.resolve(), (REPO_ROOT / "tests" / "fixtures" / "m0" / "expected").resolve()):
        raise BaselineWriteError(f"cannot directly update expected fixture: {path}")
    if is_relative_to(path.resolve(), (REPO_ROOT / "benchmarks" / "results" / "m0" / "reference").resolve()):
        raise BaselineWriteError(f"cannot directly update benchmark reference: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(expected)
    return False


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def git_metadata(cwd: Path = REPO_ROOT) -> GitMetadata:
    return GitMetadata(
        commit=_git("rev-parse", "HEAD", cwd=cwd),
        dirty=bool(_git("status", "--porcelain", cwd=cwd)),
    )


def is_ancestor(ancestor: str, descendant: str = "HEAD", cwd: Path = REPO_ROOT) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise M0Error(completed.stderr.strip() or "git merge-base failed")
    return completed.returncode == 0


def environment_metadata() -> dict[str, Any]:
    """Return detectable provenance without guessing unavailable details."""

    cpu_count = os.cpu_count()
    return {
        "m0_json_version": M0_JSON_VERSION,
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpus": cpu_count,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
    }
