#!/usr/bin/env python3
"""Run the required format and clang-tidy checks for M11 product code."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def matching_files() -> list[Path]:
    paths: set[Path] = set()
    for directory in (
        ROOT / "native/include/macro_sim/control",
        ROOT / "native/include/macro_sim/desktop",
        ROOT / "native/src/control",
        ROOT / "native/tests",
    ):
        paths.update(directory.glob("m11*.hpp"))
        paths.update(directory.glob("m11*.cpp"))
    desktop = ROOT / "native/src/desktop"
    paths.update(desktop.glob("m11*.cpp"))
    paths.update(desktop.glob("macro_sim_launcher*.cpp"))
    paths.add(desktop / "macro_sim_server.cpp")
    return sorted(path for path in paths if path.is_file())


def translation_units() -> list[Path]:
    return [
        path
        for path in matching_files()
        if path.suffix == ".cpp"
        and path.name != "macro_sim_launcher_windows.cpp"
    ]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"{name} is unavailable")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=Path("build/native/m11-debug"),
    )
    parser.add_argument("--skip-format", action="store_true")
    parser.add_argument("--skip-tidy", action="store_true")
    arguments = parser.parse_args()

    if not arguments.skip_format:
        run(
            [
                executable("clang-format"),
                "--dry-run",
                "--Werror",
                *[str(path.relative_to(ROOT)) for path in matching_files()],
            ]
        )

    if not arguments.skip_tidy:
        compile_commands = (ROOT / arguments.build_dir).resolve()
        if not (compile_commands / "compile_commands.json").is_file():
            raise SystemExit(
                f"compile commands are absent from {compile_commands}"
            )
        run(
            [
                executable("clang-tidy"),
                "--quiet",
                "-p",
                str(compile_commands),
                *[
                    str(path.relative_to(ROOT))
                    for path in translation_units()
                ],
            ]
        )

    print("M11 static analysis: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
