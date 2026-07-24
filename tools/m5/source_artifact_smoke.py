#!/usr/bin/env python3
"""Verify that an M5 source distribution contains its offline inputs."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import tarfile


REQUIRED_SUFFIXES = {
    "native/CMakeLists.txt",
    "native/include/macro_sim/core/financial.hpp",
    "native/include/macro_sim/simulation/m5.hpp",
    "native/include/macro_sim/simulation/m5_checkpoint.hpp",
    "native/src/core/financial.cpp",
    "native/src/simulation/m5.cpp",
    "native/src/simulation/m5_checkpoint.cpp",
    "schemas/m5/performance_budget.json",
    "tools/m5/fresh_process_checkpoint.py",
    "tools/m5/performance_gate.py",
    "tools/m5/semantic_panel.py",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sdist", type=Path)
    source.add_argument("--sdist-dir", type=Path)
    arguments = parser.parse_args()
    if arguments.sdist_dir is not None:
        candidates = sorted(
            arguments.sdist_dir.glob("macro_simulator-*.tar.gz")
        )
        if len(candidates) != 1:
            parser.error(f"expected one source distribution, found {len(candidates)}")
        sdist = candidates[0].resolve()
    else:
        sdist = arguments.sdist.resolve()
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = archive.getmembers()
        roots: set[str] = set()
        suffixes: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"source artifact has unsafe path: {member.name}")
            if member.issym() or member.islnk() or not path.parts:
                raise ValueError(f"source artifact has unsafe member: {member.name}")
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("source distribution must have exactly one root")
        root = next(iter(roots))
        for member in members:
            suffixes.add(
                PurePosixPath(member.name).relative_to(root).as_posix()
            )
        missing = sorted(REQUIRED_SUFFIXES.difference(suffixes))
        if missing:
            raise ValueError(f"source distribution omits M5 inputs: {missing}")
    print("M5 source artifact smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
