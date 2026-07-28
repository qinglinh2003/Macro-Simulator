#!/usr/bin/env python3
"""Exercise the standalone native desktop worker over its real socket."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import time
from typing import Any


TOKEN = "0123456789abcdef" * 4


def request(sequence: int, command: str, **extra: Any) -> bytes:
    payload: dict[str, Any] = {
        "protocol_version": 5,
        "request_id": f"smoke-{sequence}",
        "connection_id": "packaged-smoke-client",
        "sequence": sequence,
        "token": TOKEN,
        "command": command,
    }
    payload.update(extra)
    return json.dumps(payload, separators=(",", ":")).encode() + b"\n"


def receive_line(peer: socket.socket, buffer: bytearray) -> dict[str, Any]:
    while b"\n" not in buffer:
        chunk = peer.recv(65_536)
        if not chunk:
            raise RuntimeError("worker closed before returning a response")
        buffer.extend(chunk)
        if len(buffer) > 4 * 1024 * 1024 + 1:
            raise RuntimeError("worker response exceeded the protocol limit")
    line, _, remaining = buffer.partition(b"\n")
    buffer[:] = remaining
    value = json.loads(line)
    if not isinstance(value, dict):
        raise RuntimeError("worker response was not an object")
    return value


def wait_for_ready(path: Path, process: subprocess.Popen[bytes]) -> dict[str, Any]:
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("status") == "ready":
                return value
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"worker exited early: {stdout!r} {stderr!r}"
            )
        time.sleep(0.02)
    raise TimeoutError("worker did not publish readiness")


def run(server: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix="macro-sim-server-smoke-"
    ) as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        bootstrap = root / "bootstrap.json"
        ready = root / "ready.json"
        saves = root / "saves"
        bootstrap.write_text(
            json.dumps(
                {
                    "token": TOKEN,
                    "save_root": str(saves),
                    "ready_file": str(ready),
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(bootstrap, 0o600)
        command = [str(server), "--bootstrap", str(bootstrap)]
        if TOKEN in " ".join(command):
            raise AssertionError("token leaked into the process arguments")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            readiness = wait_for_ready(ready, process)
            if bootstrap.exists():
                raise AssertionError("bootstrap file was not consumed")
            if readiness["protocol_version"] != 5:
                raise AssertionError("worker protocol version differs")
            if os.name != "nt":
                mode = stat.S_IMODE(ready.stat().st_mode)
                if mode & 0o077:
                    raise AssertionError("readiness file is not user-only")

            peer = socket.create_connection(
                ("127.0.0.1", int(readiness["port"])),
                timeout=10.0,
            )
            peer.settimeout(10.0)
            buffer = bytearray()
            hello = request(1, "hello")
            midpoint = len(hello) // 2
            peer.sendall(hello[:midpoint])
            peer.sendall(hello[midpoint:] + request(2, "hello"))
            first = receive_line(peer, buffer)
            second = receive_line(peer, buffer)
            if not first.get("ok") or not second.get("ok"):
                raise AssertionError("split/coalesced requests failed")

            peer.sendall(request(3, "new_session", seed=31))
            created = receive_line(peer, buffer)
            if not created.get("ok"):
                raise AssertionError(f"new session failed: {created}")
            session_id = created["result"]["session_id"]
            peer.close()
            peer = socket.create_connection(
                ("127.0.0.1", int(readiness["port"])),
                timeout=10.0,
            )
            peer.settimeout(10.0)
            buffer.clear()
            peer.sendall(
                request(4, "shutdown", session_id=session_id)
            )
            shutdown = receive_line(peer, buffer)
            if not shutdown.get("ok"):
                raise AssertionError(f"shutdown failed: {shutdown}")
            peer.close()
            return_code = process.wait(timeout=10.0)
            stdout, stderr = process.communicate()
            if return_code != 0:
                raise AssertionError(
                    f"worker exited with {return_code}: {stderr!r}"
                )
            if TOKEN.encode() in stdout or TOKEN.encode() in stderr:
                raise AssertionError("token leaked into worker output")
            if ready.exists():
                raise AssertionError("readiness file was not cleaned up")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    args = parser.parse_args()
    run(args.server.resolve())


if __name__ == "__main__":
    main()
