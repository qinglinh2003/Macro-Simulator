#!/usr/bin/env python3
"""Install an M7 wheel in isolation and exercise population and labor."""

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

    with tempfile.TemporaryDirectory(prefix="macro-sim-m7-wheel-") as raw:
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
assert version("macro-simulator") == "0.7.0"
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.7.0-m7"
real = native.M4SimulationSpec()
real.vertical = native.M4Vertical.CAPITAL_FISCAL
real.consumption_firms = 4
real.capital_firms = 2
real.requested_capabilities = 3
monetary_rules = native.M5Rules()
monetary_rules.bank_count = 3
monetary = native.M5SimulationSpec()
monetary.real_economy = real
monetary.rules = monetary_rules
financial_rules = native.M6Rules()
financial_rules.watchlist_size = 3
financial_rules.firm_dynamics = False
financial_rules.bank_dynamics = False
financial = native.M6SimulationSpec()
financial.monetary_economy = monetary
financial.rules = financial_rules
population = native.M7PopulationSpec()
population.initial_persons = 48
population.target_household_size = 2.5
rules = native.M7Rules()
rules.fertility = False
rules.mortality = False
rules.marriage = False
rules.divorce = False
spec = native.M7SimulationSpec()
spec.financial_economy = financial
spec.population = population
spec.rules = rules
session = native.M7Session(707)
session.initialize_m7(spec)
assert session.advance_m7_ticks(10)["next_tick"] == 10
snapshot = session.m7_snapshot()
assert len(snapshot["persons"]) == 48
assert snapshot["jobs"]
clone = native.M7Session(708)
clone.restore_checkpoint(session.checkpoint())
clone.advance_m7_ticks(5)
session.advance_m7_ticks(5)
assert clone.digest() == session.digest()
"""
        subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
    print("isolated M7 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
