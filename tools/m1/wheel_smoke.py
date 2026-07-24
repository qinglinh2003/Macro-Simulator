#!/usr/bin/env python3
"""Install an M1 wheel outside the source tree and exercise the native ABI."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with tempfile.TemporaryDirectory(prefix="macro-sim-wheel-smoke-") as raw:
        root = Path(raw)
        environment = root / "venv"
        subprocess.run(["uv", "venv", str(environment)], check=True, cwd=root)
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                str(wheel),
            ],
            check=True,
            cwd=root,
        )
        code = """
import macro_sim._native as native
assert native.engine_version() == "0.1.0-m1"
session = native.EngineSession(2718)
assert session.session_id == 2718 and session.tick == 0
assert native.validate_scalar("config.a", "bad") == (False, "type_mismatch")
assert native.philox_block((0, 0, 0, 0), (0, 0)) == (
    1713891541, 3781805453, 3159862348, 2600524760
)
session.close()
"""
        subprocess.run([str(python), "-I", "-c", code], check=True, cwd=root)
    print("isolated wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
