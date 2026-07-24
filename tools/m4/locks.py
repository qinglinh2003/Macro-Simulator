#!/usr/bin/env python3
"""Generate or verify canonical M4 contract and source locks."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
HASHES = ROOT / "schemas/m4/hashes.lock.json"
SOURCE = ROOT / "schemas/m4/source.lock.json"
BASE_COMMIT = "02a708cdf4077449ae37f221adf6ec6f33e0c353"


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def records(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        content = path.read_bytes()
        rows.append({
            "byte_count": len(content),
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(content).hexdigest(),
        })
    aggregate = sha256(canonical_bytes(rows)).hexdigest()
    return rows, aggregate


def contract_paths() -> tuple[Path, ...]:
    paths = {
        path
        for path in (ROOT / "schemas/m4").rglob("*")
        if path.is_file() and path not in {HASHES, SOURCE}
    }
    return tuple(paths)


def build_contract() -> dict[str, Any]:
    files, aggregate = records(contract_paths())
    return {
        "aggregate_sha256": aggregate,
        "files": files,
        "schema_version": "m4-contract-lock-v1",
    }


def source_paths() -> tuple[Path, ...]:
    paths = {
        ROOT / ".github/workflows/native.yml",
        ROOT / "CMakeLists.txt",
        ROOT / "CMakePresets.json",
        ROOT / "docs/cpp_engine_m4_acceptance_v33.md",
        ROOT / "docs/cpp_engine_m4_execution_plan_v33.md",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    }
    for directory in (
        ROOT / "native",
        ROOT / "schemas/m4",
        ROOT / "tests/native",
        ROOT / "tools/m4",
    ):
        paths.update(path for path in directory.rglob("*") if path.is_file())
    paths.discard(SOURCE)
    return tuple(
        path
        for path in paths
        if "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def build_source() -> dict[str, Any]:
    files, aggregate = records(source_paths())
    contract = build_contract()
    return {
        "aggregate_sha256": aggregate,
        "base_commit": BASE_COMMIT,
        "files": files,
        "m4_contract_sha256": contract["aggregate_sha256"],
        "schema_version": "m4-source-lock-v1",
    }


def write_or_check(
    path: Path,
    value: dict[str, Any],
    *,
    write: bool,
) -> None:
    encoded = canonical_bytes(value)
    if write:
        path.write_bytes(encoded)
        print(f"write   {path.relative_to(ROOT)}")
        return
    if not path.is_file() or path.read_bytes() != encoded:
        raise SystemExit(f"stale lock: {path.relative_to(ROOT)}")
    print(f"ok      {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    write_or_check(HASHES, build_contract(), write=arguments.write)
    write_or_check(SOURCE, build_source(), write=arguments.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
