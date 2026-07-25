#!/usr/bin/env python3
"""Verify exact M7 continuation after checkpoint transfer to a new process."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from semantic_panel import make_spec


def load_native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    return importlib.import_module("_native")


def write_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.M7Session(2707)
    session.initialize_m7(make_spec(native, 2707))
    session.advance_m7_ticks(14)
    checkpoint.write_bytes(session.checkpoint())
    session.advance_m7_ticks(19)
    print(json.dumps({"digest": session.digest(), "tick": session.tick}))
    return 0


def read_mode(native_dir: Path, checkpoint: Path) -> int:
    native = load_native(native_dir)
    session = native.M7Session(2708)
    session.restore_checkpoint(checkpoint.read_bytes())
    session.advance_m7_ticks(19)
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
    with tempfile.TemporaryDirectory(prefix="macro-sim-m7-") as directory:
        checkpoint = Path(directory) / "continuation.m7cp"
        direct = run_child("write", native_dir, checkpoint)
        restored = run_child("read", native_dir, checkpoint)
    if direct != restored or direct["tick"] != 33:
        raise AssertionError(
            f"fresh-process continuation mismatch: {direct!r} != "
            f"{restored!r}"
        )
    print(json.dumps({
        "schema_version": "m7-fresh-process-result-v1",
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
