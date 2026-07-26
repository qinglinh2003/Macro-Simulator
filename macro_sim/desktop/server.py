"""Newline-delimited JSON server for the local Godot client."""
from __future__ import annotations

import argparse
import json
import socketserver
import threading
from typing import Any

from .runtime import PROTOCOL_VERSION, SimulationRuntime


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], runtime: SimulationRuntime) -> None:
        self.runtime = runtime
        self.runtime_lock = threading.Lock()
        super().__init__(address, _Handler)


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        while raw := self.rfile.readline(1_048_577):
            request_id: Any = None
            try:
                if len(raw) > 1_048_576:
                    raise ValueError("request exceeds 1 MiB")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise TypeError("request must be a JSON object")
                request_id = payload.pop("request_id", None)
                # Reconnects may briefly overlap, but the simulation remains a
                # strict single-writer state machine.
                with self.server.runtime_lock:  # type: ignore[attr-defined]
                    snapshot = self.server.runtime.handle(payload)  # type: ignore[attr-defined]
                response = {
                    "ok": True,
                    "request_id": request_id,
                    "protocol_version": PROTOCOL_VERSION,
                    "snapshot": snapshot,
                }
            except Exception as exc:  # Keep protocol failures contained to one request.
                response = {
                    "ok": False,
                    "request_id": request_id,
                    "protocol_version": PROTOCOL_VERSION,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            self.wfile.write(
                json.dumps(response, separators=(",", ":"), allow_nan=False).encode()
                + b"\n"
            )
            self.wfile.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Godot prototype simulation worker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47_821)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    runtime = SimulationRuntime(seed=args.seed, free_policy_mode=True)
    with _Server((args.host, args.port), runtime) as server:
        print(
            json.dumps({"status": "ready", "host": args.host, "port": args.port}),
            flush=True,
        )
        server.serve_forever()


if __name__ == "__main__":
    main()
