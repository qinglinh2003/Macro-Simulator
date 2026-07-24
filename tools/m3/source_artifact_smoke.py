#!/usr/bin/env python3
"""Verify that an M3 source distribution contains its offline inputs."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile


REQUIRED_SUFFIXES = {
    "native/CMakeLists.txt",
    "native/dependencies.lock.json",
    "native/include/macro_sim/algorithms/behavior.hpp",
    "native/include/macro_sim/algorithms/market.hpp",
    "native/include/macro_sim/algorithms/shock_overlay.hpp",
    "schemas/m2/hashes.lock.json",
    "schemas/m3/equation_contract.json",
    "schemas/m3/fixtures/equations.json",
    "schemas/m3/manifests/gates.yaml",
    "schemas/m3/market_contract.json",
    "schemas/m3/performance_budget.json",
    "tools/m3/differential_oracle.py",
    "tools/m3/equation_fixtures.py",
    "tools/m3/performance_gate.py",
}


def select(path: Path | None, directory: Path | None) -> Path:
    if directory is not None:
        candidates = sorted(directory.glob("macro_simulator-*.tar.gz"))
        if len(candidates) != 1:
            raise ValueError(f"expected one source distribution, found {len(candidates)}")
        return candidates[0].resolve()
    assert path is not None
    return path.resolve()


def safe_members(archive: tarfile.TarFile) -> tuple[list[tarfile.TarInfo], str]:
    members = archive.getmembers()
    roots: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"source distribution has unsafe path: {member.name}")
        if member.issym() or member.islnk() or not path.parts:
            raise ValueError(f"source distribution has unsafe member: {member.name}")
        roots.add(path.parts[0])
    if len(roots) != 1:
        raise ValueError("source distribution must have exactly one root")
    return members, next(iter(roots))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sdist", type=Path)
    source.add_argument("--sdist-dir", type=Path)
    arguments = parser.parse_args()
    sdist = select(arguments.sdist, arguments.sdist_dir)
    with tarfile.open(sdist, mode="r:gz") as archive:
        members, root_name = safe_members(archive)
        suffixes = {
            PurePosixPath(member.name).relative_to(root_name).as_posix()
            for member in members
        }
        missing = sorted(REQUIRED_SUFFIXES.difference(suffixes))
        if missing:
            raise ValueError(f"source distribution omits M3 inputs: {missing}")
        with tempfile.TemporaryDirectory(prefix="macro-sim-m3-sdist-") as raw:
            archive.extractall(raw, filter="data")
            root = Path(raw) / root_name
            subprocess.run(
                [sys.executable, "tools/m3/equation_fixtures.py"],
                cwd=root,
                check=True,
            )
    print("M3 source artifact smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
