#!/usr/bin/env python3
"""Verify exact M4 continuation after checkpoint transfer to a new process."""

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
    value = native.M4SimulationSpec()
    value.vertical = native.M4Vertical.CAPITAL_FISCAL
    value.households = 40
    value.consumption_firms = 8
    value.capital_firms = 3
    value.requested_capabilities = 3
    value.market_protocol = native.MatchingProtocol.SAMPLED
    value.stochastic = True
    value.seed = 1701
    return value


def write_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.EngineSession(701)
    session.initialize_simulation(spec(native))
    session.advance_ticks(12)
    checkpoint.write_bytes(session.checkpoint())
    session.advance_ticks(17)
    print(json.dumps({"digest": session.digest(), "tick": session.tick}))
    return 0


def read_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.EngineSession(702)
    session.restore_checkpoint(checkpoint.read_bytes())
    session.advance_ticks(17)
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
    with tempfile.TemporaryDirectory(prefix="macro-sim-m4-") as directory:
        checkpoint = Path(directory) / "continuation.m4cp"
        direct = run_child("write", native_dir, checkpoint)
        restored = run_child("read", native_dir, checkpoint)
    if direct != restored or direct["tick"] != 29:
        raise AssertionError(
            f"fresh-process continuation mismatch: {direct!r} != {restored!r}"
        )
    print(json.dumps({
        "schema_version": "m4-fresh-process-result-v1",
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
