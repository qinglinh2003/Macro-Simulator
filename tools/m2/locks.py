#!/usr/bin/env python3
"""Generate or verify deterministic M2 contract, vendor, and source locks."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
M1_COMMIT = "d7af86944a840d2f0465001cdf971dc4fdc1cd88"
M1_CONTRACT_SHA256 = (
    "3a1079107ac9979c2e66f49accf1faefb8436aa2419f121cd07b21537f3f9623"
)
HASHES_PATH = ROOT / "schemas/m2/hashes.lock.json"
SOURCE_PATH = ROOT / "schemas/m2/source.lock.json"
VENDOR_PATH = ROOT / "schemas/m2/vendor.lock.json"


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
    ).encode()


def file_records(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], str]:
    records: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    for path in sorted(set(paths), key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        digest = sha256(content).hexdigest()
        mapping[relative] = digest
        records.append(
            {
                "byte_count": len(content),
                "path": relative,
                "sha256": digest,
            }
        )
    aggregate_input = "".join(
        f"{path}\0{mapping[path]}\n" for path in sorted(mapping)
    ).encode()
    return records, sha256(aggregate_input).hexdigest()


def build_vendor_lock() -> dict[str, Any]:
    dependency_lock = json.loads(
        (ROOT / "native/dependencies.lock.json").read_text(encoding="utf-8")
    )
    selected = {
        item["name"]: {
            "immutable_ref": item["immutable_ref"],
            "source_sha256": item["source_sha256"],
            "source_url": item["source_url"],
        }
        for item in dependency_lock["dependencies"]
        if item["name"] in {"FlatBuffers", "nlohmann-json", "PicoSHA2"}
    }
    paths = [
        path
        for path in (ROOT / "native/vendor").rglob("*")
        if path.is_file()
    ]
    files, aggregate = file_records(paths)
    return {
        "aggregate_sha256": aggregate,
        "dependencies": selected,
        "files": files,
        "schema_version": "m2-vendor-lock-v1",
    }


def contract_paths() -> tuple[Path, ...]:
    excluded = {HASHES_PATH, SOURCE_PATH}
    return tuple(
        path
        for path in (ROOT / "schemas/m2").rglob("*")
        if path.is_file() and path not in excluded
    )


def build_contract_lock() -> dict[str, Any]:
    files, aggregate = file_records(contract_paths())
    return {
        "aggregate_sha256": aggregate,
        "files": files,
        "m1_contract_sha256": M1_CONTRACT_SHA256,
        "schema_version": "m2-contract-lock-v1",
    }


def source_paths() -> tuple[Path, ...]:
    exact = {
        ROOT / ".gitattributes",
        ROOT / ".github/workflows/native.yml",
        ROOT / "CMakeLists.txt",
        ROOT / "CMakePresets.json",
        ROOT / "docs/cpp_engine_m2_execution_plan_v33.md",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    }
    paths = set(exact)
    for directory in (
        ROOT / "native",
        ROOT / "schemas/m2",
        ROOT / "tests/native",
        ROOT / "tools/m2",
    ):
        paths.update(path for path in directory.rglob("*") if path.is_file())
    paths.discard(SOURCE_PATH)
    paths = {
        path
        for path in paths
        if "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }
    return tuple(paths)


def build_source_lock() -> dict[str, Any]:
    files, aggregate = file_records(source_paths())
    contract = build_contract_lock()
    return {
        "aggregate_sha256": aggregate,
        "base_commit": M1_COMMIT,
        "files": files,
        "m2_contract_sha256": contract["aggregate_sha256"],
        "schema_version": "m2-source-lock-v1",
    }


def write_or_check(path: Path, value: dict[str, Any], *, write: bool) -> None:
    expected = canonical_bytes(value)
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected)
        print(f"write   {path.relative_to(ROOT)}")
        return
    try:
        actual = path.read_bytes()
    except OSError as error:
        raise SystemExit(f"cannot read {path.relative_to(ROOT)}: {error}") from error
    if actual != expected:
        raise SystemExit(f"stale lock: {path.relative_to(ROOT)}")
    print(f"ok      {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    write_or_check(VENDOR_PATH, build_vendor_lock(), write=arguments.write)
    write_or_check(HASHES_PATH, build_contract_lock(), write=arguments.write)
    write_or_check(SOURCE_PATH, build_source_lock(), write=arguments.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
