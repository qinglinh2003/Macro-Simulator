"""End-to-end smoke drive of the desktop worker over the real TCP protocol.

Simulates exactly what the Godot free-policy workbench sends: replace the
next-boundary policy batch, verify that the current tick remains immutable,
advance one day, and verify that the batch becomes effective before that
day's simulation.  Then advance in <=100-tick bursts and check the world
payload over ~1.5 simulation years.

Usage: python scripts/desktop_smoke.py [--port 47899] [--ticks 550]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def request(stream, payload, rid):
    payload = dict(payload)
    payload["request_id"] = f"smoke:{rid}"
    stream.write((json.dumps(payload) + "\n").encode())
    stream.flush()
    line = stream.readline()
    if not line:
        raise RuntimeError("worker closed the connection")
    response = json.loads(line)
    if not response.get("ok"):
        raise RuntimeError(f"worker error: {response.get('error')}")
    return response["snapshot"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=47899)
    parser.add_argument("--ticks", type=int, default=550)
    parser.add_argument(
        "--backend",
        choices=("native-m10", "python-oracle"),
        default="native-m10",
    )
    parser.add_argument(
        "--native-dir",
        type=Path,
        default=Path("build/native/m10-debug/native"),
    )
    args = parser.parse_args()

    worker_environment = os.environ.copy()
    if args.backend == "native-m10":
        native_dir = args.native_dir.resolve()
        if not native_dir.is_dir():
            raise RuntimeError(
                f"native extension directory does not exist: {native_dir}"
            )
        existing_path = worker_environment.get("PYTHONPATH")
        worker_environment["PYTHONPATH"] = (
            str(native_dir)
            if not existing_path
            else f"{native_dir}{os.pathsep}{existing_path}"
        )
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "macro_sim.desktop.server",
            "--port",
            str(args.port),
            "--backend",
            args.backend,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=worker_environment,
    )
    try:
        connection = None
        for _ in range(120):
            try:
                connection = socket.create_connection(("127.0.0.1", args.port), timeout=5)
                break
            except OSError:
                time.sleep(0.25)
        if connection is None:
            raise RuntimeError("worker never came up")
        connection.settimeout(120)
        stream = connection.makefile("rwb")
        rid = 0

        rid += 1
        snap = request(stream, {"command": "hello"}, rid)
        rid += 1
        schema = request(stream, {"command": "get_schema"}, rid)
        lever_total = sum(len(p["levers"]) for p in schema["seats"].values())
        assert lever_total == 102, f"expected 102 levers, got {lever_total}"

        assert schema["control_mode"] == "free_policy"
        lever = "tax_income_rate"
        before = snap["policy_values"][lever]
        requested = 0.7 if before != 0.7 else 0.6
        start_tick = snap["tick"]

        rid += 1
        snap = request(stream, {
            "command": "stage_policy",
            "actions": [{"lever": lever, "value": requested}],
        }, rid)
        assert snap["tick"] == start_tick
        assert snap["policy_values"][lever] == before
        assert snap["free_policy"]["effective_tick"] == start_tick + 1
        assert snap["free_policy"]["actions"] == [
            {"lever": lever, "value": requested}
        ]

        rid += 1
        snap = request(stream, {"command": "advance", "ticks": 1}, rid)
        assert snap["tick"] == start_tick + 1
        assert snap["policy_values"][lever] == requested
        assert snap["free_policy"]["actions"] == []
        verdict = snap["last_verdict"]
        assert verdict["status"] == "effective", verdict
        assert verdict["effective_tick"] == start_tick + 1
        print(f"t={snap['tick']}: {lever} {before} -> {requested} effective")

        while snap["tick"] < args.ticks:
            rid += 1
            snap = request(stream, {
                "command": "advance",
                "ticks": min(100, args.ticks - snap["tick"]),
            }, rid)

        world = snap["world"]
        assert len(world["latest"]["economies"]) == 3
        assert len(world["latest"]["e"]) == 3
        assert world["history"], "world history empty"
        payload_kb = len(json.dumps(snap)) / 1024.0
        e0 = world["latest"]["economies"][0]
        print(f"t={snap['tick']}: OK — snapshot {payload_kb:.0f}KB, "
              f"E0 gdp={e0['real_output']:.1f} u={e0['unemployment_rate']:.3f} "
              f"e_vec={[round(x, 4) for x in world['latest']['e']]} "
              f"nfa={[round(x, 1) for x in world['latest']['nfa']]}")
        print("DESKTOP SMOKE PASS")
        return 0
    finally:
        worker.terminate()
        worker.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
