#!/usr/bin/env python3
"""Build and consume every installed M1 artifact from temporary directories."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="m1-release")
    args = parser.parse_args()
    build_dir = ROOT / "build/native" / args.preset
    run(["cmake", "--preset", args.preset])
    run(["cmake", "--build", "--preset", args.preset])
    run(["ctest", "--preset", args.preset])
    with tempfile.TemporaryDirectory(prefix="macro-sim-package-gate-") as raw:
        temporary = Path(raw)
        prefix = temporary / "install"
        wheel_dir = temporary / "wheel"
        sdist_dir = temporary / "sdist"
        run(
            [
                sys.executable,
                "tools/m1/installed_c_smoke.py",
                "--build-dir",
                str(build_dir),
                "--prefix",
                str(prefix),
            ]
        )
        run(["uv", "build", "--wheel", "--out-dir", str(wheel_dir)])
        run(
            [
                sys.executable,
                "tools/m1/wheel_smoke.py",
                "--wheel-dir",
                str(wheel_dir),
            ]
        )
        run(["uv", "build", "--sdist", "--out-dir", str(sdist_dir)])
        run(
            [
                sys.executable,
                "tools/m1/source_artifact_smoke.py",
                "--sdist-dir",
                str(sdist_dir),
            ]
        )
    print("M1 installed artifact gate: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
