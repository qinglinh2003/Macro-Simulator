#!/usr/bin/env python3
"""Install an M6 wheel in isolation and exercise the securities boundary."""

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

    with tempfile.TemporaryDirectory(prefix="macro-sim-m6-wheel-") as raw:
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
assert version("macro-simulator") == "0.6.0"
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.6.0-m6"
real = native.M4SimulationSpec()
real.vertical = native.M4Vertical.CAPITAL_FISCAL
real.households = 20
real.consumption_firms = 4
real.capital_firms = 2
real.requested_capabilities = 3
monetary_rules = native.M5Rules()
monetary_rules.bank_count = 3
monetary = native.M5SimulationSpec()
monetary.real_economy = real
monetary.rules = monetary_rules
rules = native.M6Rules()
rules.watchlist_size = 3
rules.firm_dynamics = False
rules.bank_dynamics = False
spec = native.M6SimulationSpec()
spec.monetary_economy = monetary
spec.rules = rules
session = native.M6Session(606)
session.initialize_m6(spec)
assert session.advance_m6_ticks(10)["next_tick"] == 10
snapshot = session.m6_snapshot()
assert len(snapshot["equities"]) == 7
assert len(snapshot["firm_statements"]) == 6
clone = native.M6Session(607)
clone.restore_checkpoint(session.checkpoint())
clone.advance_m6_ticks(5)
session.advance_m6_ticks(5)
assert clone.digest() == session.digest()
"""
        subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
    print("isolated M6 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
