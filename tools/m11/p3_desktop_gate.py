#!/usr/bin/env python3
"""Measure the M11 standalone-worker desktop latency gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import tempfile
import time
from typing import Any

from tools.m11.server_smoke import (
    TOKEN,
    receive_line,
    request,
    wait_for_ready,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET = ROOT / "schemas/m10/performance_budget.json"
SEATS = (
    "treasury",
    "central_bank",
    "regulator",
    "external_affairs",
    "energy",
)


def statistics_ns(values: list[int]) -> dict[str, int]:
    ordered = sorted(values)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "maximum_ns": max(ordered),
        "median_ns": int(statistics.median(ordered)),
        "minimum_ns": min(ordered),
        "p95_ns": ordered[p95_index],
        "sample_count": len(ordered),
    }


def checked_response(
    peer: socket.socket,
    buffer: bytearray,
    sequence: int,
    command: str,
    **extra: Any,
) -> dict[str, Any]:
    peer.sendall(request(sequence, command, **extra))
    value = receive_line(peer, buffer)
    if not value.get("ok"):
        raise AssertionError(f"M11 {command} failed: {value}")
    return value


def run_sample(
    server: Path,
    *,
    seed: int,
    batch_days: int,
) -> tuple[int, int]:
    with tempfile.TemporaryDirectory(
        prefix="macro-sim-m11-p3-"
    ) as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        bootstrap = root / "bootstrap.json"
        ready = root / "ready.json"
        bootstrap.write_text(
            json.dumps(
                {
                    "token": TOKEN,
                    "save_root": str(root / "saves"),
                    "ready_file": str(ready),
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(bootstrap, 0o600)
        worker = subprocess.Popen(
            [str(server), "--bootstrap", str(bootstrap)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        peer: socket.socket | None = None
        try:
            readiness = wait_for_ready(ready, worker)
            peer = socket.create_connection(
                ("127.0.0.1", int(readiness["port"])),
                timeout=15.0,
            )
            peer.settimeout(15.0)
            buffer = bytearray()
            sequence = 1
            checked_response(peer, buffer, sequence, "hello")
            sequence += 1
            created = checked_response(
                peer,
                buffer,
                sequence,
                "new_session",
                seed=seed,
            )
            sequence += 1
            session_id = created["result"]["session_id"]
            for economy_id in range(3):
                for seat in SEATS:
                    checked_response(
                        peer,
                        buffer,
                        sequence,
                        "assign_seat",
                        session_id=session_id,
                        operation_id=(
                            f"p3-null-{economy_id}-{seat}"
                        ),
                        economy_id=economy_id,
                        seat=seat,
                        occupant={
                            "kind": "null",
                            "occupant_id": "p3-null",
                        },
                    )
                    sequence += 1

            started = time.perf_counter_ns()
            advanced = checked_response(
                peer,
                buffer,
                sequence,
                "advance",
                session_id=session_id,
                ticks=batch_days,
                stop_after_context_boundary=False,
            )
            batch_ns = time.perf_counter_ns() - started
            sequence += 1
            if (
                int(advanced["result"]["advance"]["elapsed_ticks"])
                != batch_days
            ):
                raise AssertionError("M11 P3 batch ended early")
            projection = advanced["result"]["projection"]
            snapshot = projection.get("snapshot")
            if snapshot is None or int(snapshot["boundary"]) != batch_days:
                raise AssertionError("M11 P3 projection boundary differs")

            started = time.perf_counter_ns()
            snapped = checked_response(
                peer,
                buffer,
                sequence,
                "snapshot",
                session_id=session_id,
            )
            snapshot_ns = time.perf_counter_ns() - started
            sequence += 1
            if (
                int(
                    snapped["result"]["snapshot"]["boundary"]
                )
                != batch_days
            ):
                raise AssertionError("M11 P3 snapshot boundary differs")
            checked_response(
                peer,
                buffer,
                sequence,
                "shutdown",
                session_id=session_id,
            )
            peer.close()
            peer = None
            worker.wait(timeout=10.0)
            return batch_ns, snapshot_ns
        finally:
            if peer is not None:
                peer.close()
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    server = arguments.server.resolve()
    budget = json.loads(
        arguments.budget.read_text(encoding="utf-8")
    )["p3"]
    batch_samples: list[int] = []
    snapshot_samples: list[int] = []
    for index in range(int(budget["repetitions"])):
        batch, snapshot = run_sample(
            server,
            seed=int(budget["seed"]) + index,
            batch_days=int(budget["batch_days"]),
        )
        batch_samples.append(batch)
        snapshot_samples.append(snapshot)
    results = {
        "batch_plus_snapshot": statistics_ns(batch_samples),
        "snapshot": statistics_ns(snapshot_samples),
    }
    failures = []
    if results["batch_plus_snapshot"]["p95_ns"] > int(
        budget["maximum_batch_plus_snapshot_p95_ns"]
    ):
        failures.append("M11 desktop 60-day batch exceeds its P3 budget")
    if results["snapshot"]["p95_ns"] > int(
        budget["maximum_snapshot_p95_ns"]
    ):
        failures.append("M11 desktop snapshot exceeds its P3 budget")
    report = {
        "architecture": platform.machine(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "protocol_version": 5,
        "results": results,
        "schema_version": "m11-p3-desktop-gate-result-v1",
        "status": "failed" if failures else "passed",
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
