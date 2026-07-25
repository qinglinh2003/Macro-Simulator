#!/usr/bin/env python3
"""Install an M9 wheel in isolation and exercise a complete native World."""

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

    with tempfile.TemporaryDirectory(prefix="macro-sim-m9-wheel-") as raw:
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
assert version("macro-simulator") == "0.9.0"
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.9.0-m9"

def domestic(seed, wage):
    spec = native.M8SimulationSpec()
    population = spec.domestic_economy
    monetary = population.financial_economy.monetary_economy
    real = monetary.real_economy
    real.vertical = native.M4Vertical.CAPITAL_FISCAL
    real.households = 12
    real.consumption_firms = 3
    real.capital_firms = 1
    real.seed = seed
    real.requested_capabilities = 3
    real.rules.initial_wage = wage
    population.population.initial_persons = 24
    population.population.target_household_size = 2.0
    population.rules.fertility = False
    population.rules.mortality = False
    population.rules.marriage = False
    population.rules.divorce = False
    population.rules.annual_churn = 0.0
    spec.energy_rules.producer_count = 1
    return spec

spec = native.M9WorldSpec()
spec.economies = [domestic(901, 1.0), domestic(902, 1.5)]
spec.external_policies = [native.ExternalPolicy(), native.ExternalPolicy()]
spec.rules.trade = True
spec.rules.capital = True
spec.rules.migration = True
spec.rules.fx_trade_cap = 0.5
spec.rules.capital_mobility = 0.2
spec.rules.migration_rate = 0.03
spec.rules.wage_smoothing = 1.0
world = native.WorldSession.create(spec)
world.advance(10)
assert world.tick == 10
assert len(world.snapshot()["rates"]) == 2
checkpoint = world.checkpoint()
clone = native.WorldSession.create(spec)
clone.restore_checkpoint(checkpoint)
clone.advance(5, worker_count=8)
world.advance(5, worker_count=1)
assert clone.checkpoint() == world.checkpoint()
"""
        subprocess.run(
            [str(python), "-I", "-c", code], cwd=root, check=True
        )
    print("isolated M9 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
