#!/usr/bin/env python3
"""Test the native launcher with a bundle-shaped Godot runtime."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(
    launcher: Path,
    server: Path,
    godot: Path,
    project: Path,
    artifact: Path,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="macro-sim-launcher-e2e-"
    ) as temporary:
        if sys.platform == "darwin":
            app = Path(temporary) / "Macro Command.app"
            executable_root = app / "Contents" / "MacOS"
            native = app / "Contents" / "Resources" / "native"
        else:
            app = Path(temporary) / "Macro Command"
            executable_root = app
            native = app / "native"
        artifacts = native / "artifacts"
        executable_root.mkdir(parents=True)
        artifacts.mkdir(parents=True)
        packaged_launcher = executable_root / "Macro Command"
        shutil.copy2(launcher, packaged_launcher)
        (executable_root / "Macro Command.game").symlink_to(godot)
        shutil.copy2(server, native / "macro_sim_server")
        shutil.copy2(
            artifact,
            artifacts / "fiscal_stabilization_v1.msrl",
        )
        completed = subprocess.run(
            [
                str(packaged_launcher),
                "--headless",
                "--path",
                str(project),
                "--script",
                "res://tests/test_m11_native_e2e.gd",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60.0,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode != 0:
            raise AssertionError(
                "native launcher E2E failed:\n"
                + output.decode(errors="replace")
            )
        if b"m11_e2e:shutdown" not in output:
            raise AssertionError("native launcher E2E did not finish")
        if b'"token":' in output:
            raise AssertionError("native launcher leaked its capability token")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    arguments = parser.parse_args()
    run(
        arguments.launcher.resolve(),
        arguments.server.resolve(),
        arguments.godot.resolve(),
        arguments.project.resolve(),
        arguments.artifact.resolve(),
    )


if __name__ == "__main__":
    main()
