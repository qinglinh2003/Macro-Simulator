"""End-to-end smoke drive of the desktop worker over the real TCP protocol.

Simulates exactly what the Godot client's cross-seat proposal cart sends:
resolve every open context (with real actions on the first regular boundary),
then advance in <=100-tick bursts.  Asserts the verdict flow, the pending
queue, and the world block stay sane over ~1.5 sim years.

Usage: python scripts/desktop_smoke.py [--port 47899] [--ticks 550]
"""
from __future__ import annotations

import argparse
import json
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
    args = parser.parse_args()

    worker = subprocess.Popen(
        [sys.executable, "-m", "macro_sim.desktop.server", "--port", str(args.port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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

        acted = False
        verdict_seen = False
        submitted = {}
        while snap["tick"] < args.ticks:
            if snap.get("awaiting_human"):
                for ctx in list(snap["contexts"]):
                    actions = []
                    if not acted and ctx["decision_group"] in (
                        "fiscal_stance", "monetary_stance"
                    ):
                        for item in ctx["permitted_actions"]:
                            value = item.get("current_value")
                            maximum = item.get("maximum")
                            step = item.get("max_step")
                            if not isinstance(value, (int, float)) or isinstance(value, bool):
                                continue
                            if not isinstance(maximum, (int, float)) or not isinstance(step, (int, float)):
                                continue
                            requested = min(maximum, value + step)
                            if requested == value or not item.get("allowed", True):
                                continue
                            actions.append({"lever": item["lever"], "value": requested})
                            submitted[item["lever"]] = requested
                            break
                    rid += 1
                    snap = request(stream, {
                        "command": "resolve_context",
                        "context_id": ctx["context_id"],
                        "actions": actions,
                    }, rid)
                if submitted and not acted:
                    acted = True
                    print(f"t={snap['tick']}: submitted {submitted}")
                continue
            rid += 1
            snap = request(stream, {"command": "advance", "ticks": 100}, rid)
            verdict = snap.get("last_verdict")
            if verdict and not verdict_seen:
                verdict_seen = True
                print(f"t={snap['tick']}: verdict={verdict['status']}"
                      f" effective_tick={verdict.get('effective_tick')}")
                assert str(verdict["status"]).startswith("accepted"), verdict

        assert acted, "never found an actionable lever"
        assert verdict_seen, "verdict never surfaced"
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
