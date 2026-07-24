#!/usr/bin/env python3
"""Install an M2 wheel in isolation and exercise its batch interface."""

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

    with tempfile.TemporaryDirectory(prefix="macro-sim-m2-wheel-") as raw:
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
import macro_sim._native as native
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.2.0-m2"
spec = native.GenesisSpec()
spec.households = 4
spec.consumption_firms = 2
spec.settlement_banks = 2
spec.opening_money = 400.0
session = native.EngineSession(2718)
session.initialize_m2(spec)
batch = native.SettlementBatch()
batch.transfer(6, 7, 12.5)
receipt = session.apply_batch(batch)
assert receipt["applied_mutations"] == 4
checkpoint = session.checkpoint()
clone = native.EngineSession(2719)
clone.restore_checkpoint(checkpoint)
assert clone.digest() == session.digest()
"""
        subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
    print("isolated M2 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
