#!/usr/bin/env python3
"""Verify exact M6 continuation after checkpoint transfer to a new process."""

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
    real.households = 48
    real.consumption_firms = 8
    real.capital_firms = 3
    real.requested_capabilities = 3
    real.market_protocol = native.MatchingProtocol.SAMPLED
    real.stochastic = True
    real.seed = 2606
    monetary_rules = native.M5Rules()
    monetary_rules.bank_count = 4
    monetary_rules.opening_capital_per_bank = 30.0
    monetary = native.M5SimulationSpec()
    monetary.real_economy = real
    monetary.rules = monetary_rules
    monetary.initial_policy_rate = 0.002
    rules = native.M6Rules()
    rules.watchlist_size = 5
    rules.entry_beta = 0.0
    rules.bank_entry_beta = 0.0
    value = native.M6SimulationSpec()
    value.monetary_economy = monetary
    value.rules = rules
    return value


def write_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.M6Session(2606)
    session.initialize_m6(spec(native))
    session.advance_m6_ticks(14)
    checkpoint.write_bytes(session.checkpoint())
    session.advance_m6_ticks(19)
    print(json.dumps({"digest": session.digest(), "tick": session.tick}))
    return 0


def read_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.M6Session(2607)
    session.restore_checkpoint(checkpoint.read_bytes())
    session.advance_m6_ticks(19)
    print(json.dumps({"digest": session.digest(), "tick": session.tick}))
    return 0


def run_child(
    mode: str,
    native_dir: Path,
    checkpoint: Path,
) -> dict[str, object]:
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
    with tempfile.TemporaryDirectory(prefix="macro-sim-m6-") as directory:
        checkpoint = Path(directory) / "continuation.m6cp"
        direct = run_child("write", native_dir, checkpoint)
        restored = run_child("read", native_dir, checkpoint)
    if direct != restored or direct["tick"] != 33:
        raise AssertionError(
            f"fresh-process continuation mismatch: {direct!r} != "
            f"{restored!r}"
        )
    print(json.dumps({
        "schema_version": "m6-fresh-process-result-v1",
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
