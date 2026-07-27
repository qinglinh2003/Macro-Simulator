#!/usr/bin/env python3
"""Install an M11 wheel and exercise its native engine, artifact, and worker."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from server_smoke import run as run_server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wheel", type=Path)
    source.add_argument("--wheel-dir", type=Path)
    parser.add_argument("--python", default="3.12")
    arguments = parser.parse_args()
    if arguments.wheel_dir is not None:
        wheels = sorted(
            arguments.wheel_dir.glob("macro_simulator-*.whl")
        )
        if len(wheels) != 1:
            parser.error(f"expected one wheel, found {len(wheels)}")
        wheel = wheels[0].resolve()
    else:
        wheel = arguments.wheel.resolve()

    with tempfile.TemporaryDirectory(
        prefix="macro-sim-m11-wheel-"
    ) as raw:
        root = Path(raw)
        environment = root / "venv"
        subprocess.run(
            [
                "uv",
                "venv",
                "--python",
                arguments.python,
                str(environment),
            ],
            cwd=root,
            check=True,
        )
        scripts = environment / (
            "Scripts" if os.name == "nt" else "bin"
        )
        python = scripts / (
            "python.exe" if os.name == "nt" else "python"
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                str(wheel),
            ],
            cwd=root,
            check=True,
        )
        code = """
from importlib.metadata import version
from pathlib import Path
import macro_sim
import macro_sim._native as native

assert version("macro-simulator") == "0.11.0"
assert native.ABI_VERSION == 1
assert native.engine_version() == "0.11.0-m11"
artifact_path = (
    Path(macro_sim.__file__).parent
    / "rl/artifacts/fiscal_stabilization_v1.msrl"
)
artifact = native.NativePolicyArtifact.load_file(str(artifact_path))
assert (
    artifact.info["inference_capability"]
    == "msrl_v1_deterministic_inference"
)
assert artifact.info["action_dimension"] > 0

real = native.M4SimulationSpec()
real.vertical = native.M4Vertical.CAPITAL_FISCAL
real.households = 8
real.consumption_firms = 2
real.capital_firms = 1
real.requested_capabilities = 3
session = native.EngineSession()
session.initialize_simulation(real)
session.advance_ticks(2)
assert session.tick == 2
"""
        subprocess.run(
            [str(python), "-I", "-c", code],
            cwd=root,
            check=True,
        )
        server_name = "macro_sim_server.exe" if os.name == "nt" \
            else "macro_sim_server"
        native_bin = Path(
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-c",
                    "from pathlib import Path; import macro_sim; "
                    "print(Path(macro_sim.__file__).parent / 'bin')",
                ],
                cwd=root,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
        )
        server = native_bin / server_name
        if not server.is_file():
            raise AssertionError(
                "the wheel did not install macro_sim_server"
            )
        run_server(server)
    print("isolated M11 wheel smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
