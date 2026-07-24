#!/usr/bin/env python3
"""Install an M3 wheel in isolation and exercise algorithms plus M2 state."""

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

    with tempfile.TemporaryDirectory(prefix="macro-sim-m3-wheel-") as raw:
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
assert native.engine_version() == "0.3.0-m3"
assert native.m3_equation_batch([
    {"kind": "adaptive_expectation", "values": [10.0, 14.0, 0.25]}
]) == [[11.0]]
market = native.m3_clear_market(
    [{"order_id": 1, "buyer": 10, "demand": 4.0, "budget": 20.0}],
    [{"offer_id": 1, "seller": 20, "stock": 5.0, "price": 2.0, "attractiveness": 1.0}],
    "price_sorted",
)
assert market["trades"][0]["value"] == 8.0
spec = native.GenesisSpec()
spec.households = 4
spec.consumption_firms = 2
spec.settlement_banks = 2
spec.opening_money = 400.0
session = native.EngineSession(2718)
session.initialize_m2(spec)
clone = native.EngineSession(2719)
clone.restore_checkpoint(session.checkpoint())
assert clone.digest() == session.digest()
"""
        subprocess.run([str(python), "-I", "-c", code], cwd=root, check=True)
    print("isolated M3 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
