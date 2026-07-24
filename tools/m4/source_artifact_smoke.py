#!/usr/bin/env python3
"""Verify that an M4 source distribution contains its offline inputs."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile


REQUIRED_SUFFIXES = {
    "native/CMakeLists.txt",
    "native/include/macro_sim/simulation/m4.hpp",
    "native/include/macro_sim/simulation/m4_checkpoint.hpp",
    "native/src/simulation/m4.cpp",
    "native/src/simulation/m4_checkpoint.cpp",
    "schemas/m4/current_engine_target.json",
    "schemas/m4/performance_budget.json",
    "schemas/m4/stochastic_envelopes.json",
    "tools/m4/current_target.py",
    "tools/m4/differential_oracle.py",
    "tools/m4/performance_gate.py",
}


def select(path: Path | None, directory: Path | None) -> Path:
    if directory is not None:
        candidates = sorted(directory.glob("macro_simulator-*.tar.gz"))
        if len(candidates) != 1:
            raise ValueError(
                f"expected one source distribution, found {len(candidates)}"
            )
        return candidates[0].resolve()
    assert path is not None
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sdist", type=Path)
    source.add_argument("--sdist-dir", type=Path)
    arguments = parser.parse_args()
    sdist = select(arguments.sdist, arguments.sdist_dir)
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = archive.getmembers()
        roots: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"source artifact has unsafe path: {member.name}")
            if member.issym() or member.islnk() or not path.parts:
                raise ValueError(
                    f"source artifact has unsafe member: {member.name}"
                )
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("source distribution must have exactly one root")
        root_name = next(iter(roots))
        suffixes = {
            PurePosixPath(member.name).relative_to(root_name).as_posix()
            for member in members
        }
        missing = sorted(REQUIRED_SUFFIXES.difference(suffixes))
        if missing:
            raise ValueError(f"source distribution omits M4 inputs: {missing}")
        with tempfile.TemporaryDirectory(prefix="macro-sim-m4-sdist-") as raw:
            archive.extractall(raw, filter="data")
            root = Path(raw) / root_name
            subprocess.run(
                [sys.executable, "tools/m4/current_target.py", "--check"],
                cwd=root,
                check=True,
            )
    print("M4 source artifact smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
