#!/usr/bin/env python3
"""Verify that an M1 sdist contains every offline contract input."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile


REQUIRED_SUFFIXES = {
    "CMakeLists.txt",
    "CMakePresets.json",
    "native/CMakeLists.txt",
    "native/dependencies.lock.json",
    "pyproject.toml",
    "schemas/m0/hashes.lock.json",
    "schemas/m1/hashes.lock.json",
    "tools/m1/bootstrap.py",
    "tools/m1/checkpoint_prototype.py",
    "tools/m1/dependency_report.py",
    "tools/m1/generate_contracts.py",
    "tools/m1/generate_rng_vectors.py",
}


def select_sdist(path: Path | None, directory: Path | None) -> Path:
    if directory is not None:
        candidates = sorted(directory.glob("macro_simulator-*.tar.gz"))
        if len(candidates) != 1:
            raise ValueError(
                f"expected exactly one macro-simulator sdist, found {len(candidates)}"
            )
        return candidates[0].resolve()
    assert path is not None
    return path.resolve()


def safe_members(archive: tarfile.TarFile) -> tuple[list[tarfile.TarInfo], str]:
    members = archive.getmembers()
    if not members:
        raise ValueError("sdist is empty")
    roots: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"sdist contains an unsafe path: {member.name}")
        if member.issym() or member.islnk():
            raise ValueError(f"sdist contains a link: {member.name}")
        if not path.parts:
            raise ValueError("sdist contains an empty path")
        roots.add(path.parts[0])
    if len(roots) != 1:
        raise ValueError(f"sdist has multiple roots: {sorted(roots)}")
    return members, next(iter(roots))


def run_checks(root: Path) -> None:
    commands = (
        ["tools/m1/generate_contracts.py", "--check"],
        ["tools/m1/generate_rng_vectors.py", "--check"],
        ["tools/m1/checkpoint_prototype.py", "--check"],
        ["tools/m1/dependency_report.py", "--check"],
    )
    for command in commands:
        subprocess.run(
            [sys.executable, *command],
            cwd=root,
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sdist", type=Path)
    source.add_argument("--sdist-dir", type=Path)
    args = parser.parse_args()
    sdist = select_sdist(args.sdist, args.sdist_dir)
    with tarfile.open(sdist, mode="r:gz") as archive:
        members, root_name = safe_members(archive)
        suffixes = {
            PurePosixPath(member.name).relative_to(root_name).as_posix()
            for member in members
            if PurePosixPath(member.name).parts[0] == root_name
        }
        missing = sorted(REQUIRED_SUFFIXES.difference(suffixes))
        if missing:
            raise ValueError(f"sdist omits required M1 inputs: {missing}")
        with tempfile.TemporaryDirectory(prefix="macro-sim-sdist-") as raw:
            archive.extractall(raw, filter="data")
            run_checks(Path(raw) / root_name)
    print("source artifact offline-input smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
