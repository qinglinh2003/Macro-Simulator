#!/usr/bin/env python3
"""Install an M4 wheel in isolation and exercise the native tick boundary."""

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

    with tempfile.TemporaryDirectory(prefix="macro-sim-m4-wheel-") as raw:
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
import math
import macro_sim._native as native
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.4.0-m4"
spec = native.M4SimulationSpec()
spec.vertical = native.M4Vertical.CAPITAL_FISCAL
spec.households = 20
spec.consumption_firms = 4
spec.capital_firms = 2
spec.requested_capabilities = 3
spec.stochastic = True
session = native.EngineSession(2718)
session.initialize_simulation(spec)
result = session.advance_ticks(10)
assert result["next_tick"] == 10
assert math.isclose(
    result["metrics"]["total_money"],
    3200.0,
    rel_tol=1e-12,
    abs_tol=1e-9,
)
clone = native.EngineSession(2719)
clone.restore_checkpoint(session.checkpoint())
assert clone.digest() == session.digest()
clone.advance_ticks(5)
session.advance_ticks(5)
assert clone.digest() == session.digest()
"""
        subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
    print("isolated M4 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
