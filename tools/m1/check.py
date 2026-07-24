#!/usr/bin/env python3
"""Run the local M1 native-foundation verification stack."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def native_sources() -> list[str]:
    suffixes = {".c", ".cpp", ".h", ".hpp"}
    paths = [
        path
        for root in (ROOT / "native", ROOT / "tests/native")
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in suffixes
        and "generated" not in path.parts
    ]
    return [str(path.relative_to(ROOT)) for path in sorted(paths)]


def check_format() -> None:
    executable = shutil.which("clang-format")
    if executable is None:
        raise SystemExit(
            "clang-format is unavailable; install LLVM and rerun with --format"
        )
    run([executable, "--dry-run", "--Werror", *native_sources()])


def check_tidy(build_dir: Path) -> None:
    executable = shutil.which("clang-tidy")
    if executable is None:
        raise SystemExit(
            "clang-tidy is unavailable; install LLVM and rerun with --tidy"
        )
    compile_commands = build_dir / "compile_commands.json"
    if not compile_commands.exists():
        raise SystemExit(
            f"{compile_commands} is absent; configure the selected preset first"
        )
    sources = sorted((ROOT / "native/src").glob("*.cpp"))
    run(
        [
            executable,
            "-p",
            str(build_dir),
            *[str(path.relative_to(ROOT)) for path in sources],
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="m1-debug")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--format", action="store_true")
    parser.add_argument("--tidy", action="store_true")
    args = parser.parse_args()
    python = sys.executable
    checks = (
        [python, "tools/m1/bootstrap.py", "--check"],
        [python, "tools/m1/generate_contracts.py", "--check"],
        [python, "tools/m1/generate_rng_vectors.py", "--check"],
        [python, "tools/m1/checkpoint_prototype.py", "--check"],
        [python, "tools/m1/dependency_report.py", "--check"],
        [
            python,
            "-m",
            "pytest",
            "-q",
            "tests/native",
        ],
    )
    for command in checks:
        run(command)
    build_dir = ROOT / "build/native" / args.preset
    if not args.skip_build:
        run(["cmake", "--preset", args.preset])
        run(["cmake", "--build", "--preset", args.preset])
        run(["ctest", "--preset", args.preset])
    if args.format:
        check_format()
    if args.tidy:
        check_tidy(build_dir)
    print("M1 local verification: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
