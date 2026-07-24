#!/usr/bin/env python3
"""Install the native ABI, compile a C-only consumer, and run it."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
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
    run(
        [
            "cmake",
            "--install",
            str(args.build_dir),
            "--prefix",
            str(args.prefix),
        ]
    )
    with tempfile.TemporaryDirectory(prefix="macro-sim-c-smoke-") as raw:
        build_dir = Path(raw) / "build"
        run(
            [
                "cmake",
                "-S",
                str(ROOT / "tests/native/installed_consumer"),
                "-B",
                str(build_dir),
                "-G",
                "Ninja",
                f"-DCMAKE_PREFIX_PATH={args.prefix.resolve()}",
                "-DCMAKE_BUILD_TYPE=Release",
            ]
        )
        run(["cmake", "--build", str(build_dir)])
        run(
            [
                "ctest",
                "--test-dir",
                str(build_dir),
                "--output-on-failure",
                "-C",
                "Release",
            ]
        )
    print("installed C ABI smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
