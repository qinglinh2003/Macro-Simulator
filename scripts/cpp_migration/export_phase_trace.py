#!/usr/bin/env python3
"""Export deterministic phase traces and verify fresh-process repeatability."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from macro_sim.config import Config  # noqa: E402
from macro_sim.core.phase_trace import (  # noqa: E402
    MemoryTraceSink,
    TraceSpec,
    install_phase_trace,
)
from macro_sim.economy import Economy  # noqa: E402
from macro_sim.world import World  # noqa: E402
from scripts.cpp_migration.common import (  # noqa: E402
    BaselineWriteError,
    M0Error,
    write_new_canonical_json,
)


FIXTURES = ("refactor_v124", "world_n2")


def build_fixture(fixture: str):
    if fixture == "refactor_v124":
        return Economy(
            Config.v124(
                n_firms_c=8,
                n_firms_k=4,
                n_households=80,
                n_ticks=80,
                seed=0,
            )
        ), 80
    if fixture == "world_n2":
        configs = [
            Config.v124(
                n_firms_c=4,
                n_firms_k=2,
                n_households=24,
                n_ticks=10,
                seed=100 + index,
            )
            for index in range(2)
        ]
        return World(configs, base_seed=100, couple=True), 10
    raise M0Error(f"unknown phase-trace fixture: {fixture}")


def trace_fixture(fixture: str) -> bytes:
    engine, ticks = build_fixture(fixture)
    sink = MemoryTraceSink(
        TraceSpec(run_id=f"m0-{fixture}", scenario_id=fixture)
    )
    install_phase_trace(engine, sink)
    for _ in range(ticks):
        engine.step()
    return sink.canonical_bytes()


def _worker(fixture: str, output: Path) -> int:
    if output.exists():
        raise BaselineWriteError(f"refusing to overwrite trace output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(trace_fixture(fixture))
    return 0


def _fresh_process_trace(fixture: str, output: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--fixture",
            fixture,
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise M0Error(f"fresh-process trace failed: {detail}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=FIXTURES, required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--require-byte-identical", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.repeat < 1:
            raise M0Error("--repeat must be positive")
        if args.worker:
            if args.output is None:
                raise M0Error("--worker requires --output")
            return _worker(args.fixture, args.output)

        with tempfile.TemporaryDirectory(prefix="macro-m0-trace-") as raw:
            root = Path(raw)
            paths = []
            for repetition in range(args.repeat):
                path = root / f"trace-{repetition:03d}.jsonl"
                _fresh_process_trace(args.fixture, path)
                paths.append(path)
            payloads = [path.read_bytes() for path in paths]

        digests = [hashlib.sha256(payload).hexdigest() for payload in payloads]
        identical = len(set(payloads)) == 1
        if args.require_byte_identical and not identical:
            raise M0Error(f"trace repetitions differ: {digests}")
        if args.output is not None:
            write_new_canonical_json(
                args.output,
                {
                    "schema_version": "phase-trace-export-v1",
                    "fixture_id": args.fixture,
                    "repetitions": args.repeat,
                    "byte_identical": identical,
                    "trace_sha256": digests[0],
                    "trace_byte_count": len(payloads[0]),
                    "repeat_digests": digests,
                },
            )
        print(
            f"{args.fixture}: repetitions={args.repeat} "
            f"byte_identical={str(identical).lower()} sha256={digests[0]}"
        )
        return 0
    except (M0Error, OSError, ValueError) as exc:
        print(f"phase trace export error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
