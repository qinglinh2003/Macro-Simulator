#!/usr/bin/env python3
"""Verify exact M5 continuation after checkpoint transfer to a new process."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def load_native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    return importlib.import_module("_native")


def spec(native):
    real = native.M4SimulationSpec()
    real.vertical = native.M4Vertical.CAPITAL_FISCAL
    real.households = 40
    real.consumption_firms = 8
    real.capital_firms = 3
    real.requested_capabilities = 3
    real.market_protocol = native.MatchingProtocol.SAMPLED
    real.stochastic = True
    real.seed = 2505
    rules = native.M5Rules()
    rules.bank_count = 3
    rules.opening_capital_per_bank = 30.0
    rules.bank_runs = True
    value = native.M5SimulationSpec()
    value.real_economy = real
    value.rules = rules
    value.initial_policy_rate = 0.002
    return value


def write_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.EngineSession(2505)
    session.initialize_m5(spec(native))
    session.advance_m5_ticks(12)
    checkpoint.write_bytes(session.checkpoint())
    session.advance_m5_ticks(17)
    print(json.dumps({"digest": session.digest(), "tick": session.tick}))
    return 0


def read_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.EngineSession(2506)
    session.restore_checkpoint(checkpoint.read_bytes())
    session.advance_m5_ticks(17)
    print(json.dumps({"digest": session.digest(), "tick": session.tick}))
    return 0


def run_child(mode: str, native_dir: Path, checkpoint: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--native-dir",
            str(native_dir),
            "--checkpoint",
            str(checkpoint),
            "--mode",
            mode,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def orchestrate(native_dir: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="macro-sim-m5-") as directory:
        checkpoint = Path(directory) / "continuation.m5cp"
        direct = run_child("write", native_dir, checkpoint)
        restored = run_child("read", native_dir, checkpoint)
    if direct != restored or direct["tick"] != 29:
        raise AssertionError(
            f"fresh-process continuation mismatch: {direct!r} != {restored!r}"
        )
    print(json.dumps({
        "schema_version": "m5-fresh-process-result-v1",
        "status": "passed",
        "tick": direct["tick"],
    }, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument(
        "--mode",
        choices=("orchestrate", "write", "read"),
        default="orchestrate",
    )
    arguments = parser.parse_args()
    native_dir = arguments.native_dir.resolve()
    if arguments.mode == "orchestrate":
        return orchestrate(native_dir)
    if arguments.checkpoint is None:
        parser.error("--checkpoint is required for child modes")
    if arguments.mode == "write":
        return write_mode(native_dir, arguments.checkpoint)
    return read_mode(native_dir, arguments.checkpoint)


if __name__ == "__main__":
    raise SystemExit(main())
