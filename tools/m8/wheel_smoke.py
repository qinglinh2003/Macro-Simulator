#!/usr/bin/env python3
"""Install an M8 wheel in isolation and exercise energy and housing."""

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

    with tempfile.TemporaryDirectory(prefix="macro-sim-m8-wheel-") as raw:
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
assert version("macro-simulator") == "0.8.0"
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.8.0-m8"
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
population_rules = native.M7Rules()
population_rules.fertility = False
population_rules.mortality = False
population_rules.marriage = False
population_rules.divorce = False
domestic = native.M7SimulationSpec()
domestic.financial_economy = financial
domestic.population = population
domestic.rules = population_rules
housing = native.HousingRules()
housing.enabled = True
housing.initial_homeownership_share = 0.75
spec = native.M8SimulationSpec()
spec.domestic_economy = domestic
spec.housing_rules = housing
session = native.M8Session(808)
session.initialize_m8(spec)
result = session.advance_m8_ticks(10)
assert result["next_tick"] == 10
snapshot = session.m8_snapshot()
assert len(snapshot["persons"]) == 48
assert snapshot["energy_producers"]
assert snapshot["dwellings"]
clone = native.M8Session(809)
clone.restore_checkpoint(session.checkpoint())
clone.advance_m8_ticks(5)
session.advance_m8_ticks(5)
assert clone.digest() == session.digest()
"""
        subprocess.run(
            [str(python), "-I", "-c", code], cwd=root, check=True
        )
    print("isolated M8 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
