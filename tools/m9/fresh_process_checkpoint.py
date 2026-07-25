#!/usr/bin/env python3
"""Verify exact M9 continuation after checkpoint transfer to a new process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def _native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    import _native as native  # type: ignore[import-not-found]

    return native


def _domestic(native, seed: int, wage: float):
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


def _create(native):
    spec = native.M9WorldSpec()
    spec.economies = [
        _domestic(native, 9001, 1.0),
        _domestic(native, 9002, 1.5),
        _domestic(native, 9003, 2.0),
    ]
    spec.external_policies = [
        native.ExternalPolicy(),
        native.ExternalPolicy(),
        native.ExternalPolicy(),
    ]
    spec.rules.trade = True
    spec.rules.capital = True
    spec.rules.migration = True
    spec.rules.fx_trade_cap = 0.5
    spec.rules.capital_mobility = 0.2
    spec.rules.migration_rate = 0.03
    spec.rules.wage_smoothing = 1.0
    return native.WorldSession.create(spec)


def _restore_mode(native_dir: Path, checkpoint: Path, days: int) -> int:
    native = _native(native_dir)
    world = _create(native)
    world.restore_checkpoint(checkpoint.read_bytes())
    world.advance(days)
    print(
        json.dumps(
            {
                "checkpoint": bytes(world.checkpoint()).hex(),
                "digest": world.digest(),
                "tick": world.tick,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--days", type=int, default=19)
    arguments = parser.parse_args()
    native_dir = arguments.native_dir.resolve()
    if arguments.restore is not None:
        return _restore_mode(native_dir, arguments.restore, arguments.days)

    native = _native(native_dir)
    world = _create(native)
    world.advance(14)
    checkpoint = bytes(world.checkpoint())
    world.advance(arguments.days)
    expected = {
        "checkpoint": bytes(world.checkpoint()).hex(),
        "digest": world.digest(),
        "tick": world.tick,
    }
    with tempfile.TemporaryDirectory(prefix="macro-sim-m9-") as raw:
        path = Path(raw) / "continuation.m9cp"
        path.write_bytes(checkpoint)
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--native-dir",
                str(native_dir),
                "--restore",
                str(path),
                "--days",
                str(arguments.days),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    actual = json.loads(completed.stdout)
    if actual != expected:
        raise AssertionError("M9 fresh-process continuation diverged")
    print(
        json.dumps(
            {
                "digest": expected["digest"],
                "schema_version": "m9-fresh-process-result-v1",
                "status": "passed",
                "tick": expected["tick"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
