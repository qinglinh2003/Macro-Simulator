#!/usr/bin/env python3
"""Install an M5 wheel in isolation and exercise the monetary boundary."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wheel", type=Path)
    source.add_argument("--wheel-dir", type=Path)
    arguments = parser.parse_args()
    if arguments.wheel_dir is not None:
        wheels = sorted(arguments.wheel_dir.glob("macro_simulator-*.whl"))
        if len(wheels) != 1:
            parser.error(f"expected one wheel, found {len(wheels)}")
        wheel = wheels[0].resolve()
    else:
        wheel = arguments.wheel.resolve()

    with tempfile.TemporaryDirectory(prefix="macro-sim-m5-wheel-") as raw:
        root = Path(raw)
        environment = root / "venv"
        subprocess.run(["uv", "venv", str(environment)], cwd=root, check=True)
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
            cwd=root,
            check=True,
        )
        code = """
from importlib.metadata import version
import macro_sim._native as native
assert version("macro-simulator") == "0.5.0"
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.5.0-m5"
real = native.M4SimulationSpec()
real.vertical = native.M4Vertical.CAPITAL_FISCAL
real.households = 20
real.consumption_firms = 4
real.capital_firms = 2
real.requested_capabilities = 3
rules = native.M5Rules()
rules.bank_count = 3
spec = native.M5SimulationSpec()
spec.real_economy = real
spec.rules = rules
session = native.EngineSession(505)
session.initialize_m5(spec)
assert session.advance_m5_ticks(10)["next_tick"] == 10
assert len(session.m5_snapshot()["banks"]) == 3
clone = native.EngineSession(506)
clone.restore_checkpoint(session.checkpoint())
clone.advance_m5_ticks(5)
session.advance_m5_ticks(5)
assert clone.digest() == session.digest()
"""
        subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
    print("isolated M5 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
