#!/usr/bin/env python3
"""Run the Godot client against the standalone native M11 worker."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import tempfile
import time
from typing import Any


def wait_for_ready(
    path: Path, process: subprocess.Popen[bytes]
) -> dict[str, Any]:
    deadline = time.monotonic() + 20.0
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


def run(server: Path, godot: Path, project: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix="macro-sim-godot-e2e-"
    ) as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        token = secrets.token_hex(32)
        bootstrap = root / "worker-bootstrap.json"
        ready = root / "worker-ready.json"
        client = root / "client-bootstrap.json"
        saves = root / "saves"
        bootstrap.write_text(
            json.dumps(
                {
                    "token": token,
                    "save_root": str(saves),
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
        try:
            readiness = wait_for_ready(ready, worker)
            if bootstrap.exists():
                raise AssertionError("worker bootstrap was not consumed")
            if stat.S_IMODE(ready.stat().st_mode) & 0o077:
                raise AssertionError("worker readiness is not user-only")
            client.write_text(
                json.dumps(
                    {
                        "host": "127.0.0.1",
                        "port": readiness["port"],
                        "protocol_version": 5,
                        "token": token,
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            os.chmod(client, 0o600)
            environment = os.environ.copy()
            environment["MACRO_SIM_CLIENT_BOOTSTRAP"] = str(client)
            try:
                completed = subprocess.run(
                    [
                        str(godot),
                        "--headless",
                        "--path",
                        str(project),
                        "--script",
                        "res://tests/test_m11_native_e2e.gd",
                    ],
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=40.0,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                output = (error.stdout or b"") + (error.stderr or b"")
                raise AssertionError(
                    "Godot M11 E2E timed out:\n"
                    + output.decode(errors="replace")
                ) from error
            if completed.returncode != 0:
                raise AssertionError(
                    "Godot M11 E2E failed:\n"
                    + completed.stdout.decode(errors="replace")
                    + completed.stderr.decode(errors="replace")
                )
            if client.exists():
                raise AssertionError("client bootstrap was not consumed")
            return_code = worker.wait(timeout=10.0)
            stdout, stderr = worker.communicate()
            if return_code != 0:
                raise AssertionError(
                    f"worker exited with {return_code}: {stderr!r}"
                )
            if token.encode() in (
                completed.stdout + completed.stderr + stdout + stderr
            ):
                raise AssertionError("capability token leaked into output")
            if ready.exists():
                raise AssertionError("readiness file was not cleaned up")
        finally:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    arguments = parser.parse_args()
    run(
        arguments.server.resolve(),
        arguments.godot.resolve(),
        arguments.project.resolve(),
    )


if __name__ == "__main__":
    main()
