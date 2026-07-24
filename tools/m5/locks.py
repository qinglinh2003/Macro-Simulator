#!/usr/bin/env python3
"""Generate or verify canonical M5 contract and source locks."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
HASHES = ROOT / "schemas/m5/hashes.lock.json"
SOURCE = ROOT / "schemas/m5/source.lock.json"
BASE_COMMIT = "49fcd45f8d2289e6ee1b47a52f588505e2b8d88e"


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
    ordered = sorted(
        set(paths),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    for path in ordered:
        content = path.read_bytes()
        rows.append({
            "byte_count": len(content),
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(content).hexdigest(),
        })
    return rows, sha256(canonical_bytes(rows)).hexdigest()


def contract_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in (ROOT / "schemas/m5").rglob("*")
        if path.is_file() and path not in {HASHES, SOURCE}
    )


def build_contract() -> dict[str, Any]:
    files, aggregate = records(contract_paths())
    return {
        "aggregate_sha256": aggregate,
        "files": files,
        "schema_version": "m5-contract-lock-v1",
    }


def source_paths() -> tuple[Path, ...]:
    paths = {
        ROOT / ".github/workflows/native.yml",
        ROOT / "CMakeLists.txt",
        ROOT / "CMakePresets.json",
        ROOT / "docs/cpp_engine_m5_acceptance_v33.md",
        ROOT / "docs/cpp_engine_m5_execution_plan_v33.md",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    }
    for directory in (
        ROOT / "native",
        ROOT / "schemas/m5",
        ROOT / "tests/native",
        ROOT / "tools/m5",
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
        "m5_contract_sha256": contract["aggregate_sha256"],
        "schema_version": "m5-source-lock-v1",
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
