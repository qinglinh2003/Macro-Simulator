#!/usr/bin/env python3
"""Verify that an M11 source distribution contains product-cutover inputs."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import tarfile


REQUIRED_SUFFIXES = {
    "CMakePresets.json",
    "desktop/godot/export_presets.cfg",
    "desktop/godot/project.godot",
    "desktop/godot/scripts/main.gd",
    "desktop/godot/scripts/simulation_client.gd",
    "desktop/godot/tests/m11_native_e2e_driver.gd",
    "desktop/godot/tests/test_m11_native_e2e.gd",
    "native/CMakeLists.txt",
    "native/include/macro_sim/control/m11_artifact.hpp",
    "native/include/macro_sim/control/m11_coordinator.hpp",
    "native/include/macro_sim/control/m11_session.hpp",
    "native/include/macro_sim/desktop/m11_protocol.hpp",
    "native/src/control/m11_checkpoint.cpp",
    "native/src/control/m11_coordinator.cpp",
    "native/src/control/m11_session.cpp",
    "native/src/desktop/macro_sim_launcher.cpp",
    "native/src/desktop/macro_sim_launcher_windows.cpp",
    "native/src/desktop/macro_sim_server.cpp",
    "native/tests/m11_protocol_tests.cpp",
    "native/tests/m11_session_tests.cpp",
    "scripts/package_m11_linux.sh",
    "scripts/package_m11_macos.sh",
    "scripts/package_m11_windows.ps1",
    "tools/m11/check.py",
    "tools/m11/godot_e2e.py",
    "tools/m11/launcher_e2e.py",
    "tools/m11/packaged_godot_e2e.py",
    "tools/m11/static_analysis.py",
    "tools/m11/wheel_smoke.py",
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
            parser.error(
                f"expected one source distribution, found {len(candidates)}"
            )
        sdist = candidates[0].resolve()
    else:
        sdist = arguments.sdist.resolve()

    with tarfile.open(sdist, mode="r:gz") as archive:
        members = archive.getmembers()
        roots: set[str] = set()
        suffixes: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
                or not path.parts
            ):
                raise ValueError(
                    f"source artifact has unsafe member: {member.name}"
                )
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError(
                "source distribution must have exactly one root"
            )
        root = next(iter(roots))
        for member in members:
            suffixes.add(
                PurePosixPath(member.name)
                .relative_to(root)
                .as_posix()
            )
        missing = sorted(REQUIRED_SUFFIXES.difference(suffixes))
        if missing:
            raise ValueError(
                f"source distribution omits M11 inputs: {missing}"
            )
    print("M11 source artifact smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
