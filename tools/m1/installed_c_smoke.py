#!/usr/bin/env python3
"""Install the native ABI, compile a C-only consumer, and run it."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=ROOT / "build/native/m1-release",
    )
    parser.add_argument(
        "--prefix",
        type=Path,
        default=ROOT / "build/install/m1",
    )
    args = parser.parse_args()
    compiler = shutil.which("cc") or shutil.which("clang")
    if compiler is None:
        print("installed C ABI smoke requires a C compiler", file=sys.stderr)
        return 2
    run(
        [
            "cmake",
            "--install",
            str(args.build_dir),
            "--prefix",
            str(args.prefix),
        ]
    )
    library_dir = args.prefix / "lib"
    with tempfile.TemporaryDirectory(prefix="macro-sim-c-smoke-") as raw:
        output = Path(raw) / (
            "macro_sim_c_smoke.exe"
            if platform.system() == "Windows"
            else "macro_sim_c_smoke"
        )
        run(
            [
                compiler,
                "-std=c11",
                str(ROOT / "tests/native/installed_c_smoke.c"),
                "-I",
                str(args.prefix / "include"),
                "-L",
                str(library_dir),
                "-lmacro_sim_c",
                "-o",
                str(output),
            ]
        )
        env = os.environ.copy()
        for variable in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH", "PATH"):
            current = env.get(variable, "")
            env[variable] = (
                str(library_dir)
                if not current
                else os.pathsep.join((str(library_dir), current))
            )
        run([str(output)], env=env)
    print("installed C ABI smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
