#!/usr/bin/env python3
"""Run the local M11 product-cutover contract and acceptance checks."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def validate_contracts() -> None:
    required = (
        "desktop/godot/export_presets.cfg",
        "desktop/godot/scripts/main.gd",
        "desktop/godot/scripts/simulation_client.gd",
        "desktop/godot/tests/m11_native_e2e_driver.gd",
        "desktop/godot/tests/test_m11_native_e2e.gd",
        "native/include/macro_sim/control/m11_artifact.hpp",
        "native/include/macro_sim/control/m11_coordinator.hpp",
        "native/include/macro_sim/control/m11_frontend.hpp",
        "native/include/macro_sim/control/m11_session.hpp",
        "native/include/macro_sim/desktop/m11_protocol.hpp",
        "native/src/desktop/macro_sim_launcher.cpp",
        "native/src/desktop/macro_sim_launcher_windows.cpp",
        "native/src/desktop/macro_sim_server.cpp",
        "native/tests/m11_parser_fuzz_smoke.cpp",
        "scripts/package_m11_linux.sh",
        "scripts/package_m11_macos.sh",
        "scripts/package_m11_windows.ps1",
        "tools/m11/godot_e2e.py",
        "tools/m11/launcher_e2e.py",
        "tools/m11/p3_desktop_gate.py",
        "tools/m11/packaged_godot_e2e.py",
        "tools/m11/source_artifact_smoke.py",
        "tools/m11/static_analysis.py",
        "tools/m11/wheel_smoke.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            raise AssertionError(f"M11 product input is absent: {relative}")

    version = (
        ROOT / "native/include/macro_sim/version.hpp"
    ).read_text(encoding="utf-8")
    if '"0.11.0-m11"' not in version:
        raise AssertionError("M11 is not the current native engine")
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if 'version = "0.11.0"' not in metadata:
        raise AssertionError("M11 package version is stale")
    if (
        'cibuildwheel==3.4.1' not in metadata
        or '[tool.cibuildwheel]' not in metadata
        or 'wheel.py-api = "cp312"' not in metadata
    ):
        raise AssertionError("M11 abi3 wheel pipeline is incomplete")
    native_cmake = (
        ROOT / "native/CMakeLists.txt"
    ).read_text(encoding="utf-8")
    if (
        "STABLE_ABI" not in native_cmake
        or "Development.SABIModule" not in native_cmake
    ):
        raise AssertionError("M11 extension does not use the CPython stable ABI")
    protocol = (
        ROOT / "native/include/macro_sim/desktop/m11_protocol.hpp"
    ).read_text(encoding="utf-8")
    if "kM11DesktopProtocolVersion = 5U" not in protocol:
        raise AssertionError("M11 desktop protocol version differs")
    client = (
        ROOT / "desktop/godot/scripts/simulation_client.gd"
    ).read_text(encoding="utf-8")
    if "MACRO_SIM_CLIENT_BOOTSTRAP" not in client:
        raise AssertionError("Godot does not consume the native bootstrap")
    launcher = (
        ROOT / "scripts/run_godot_prototype.sh"
    ).read_text(encoding="utf-8")
    if "macro_sim_server" not in launcher or "python" in launcher.lower():
        raise AssertionError("the desktop runtime is not native-only")
    exports = (
        ROOT / "desktop/godot/export_presets.cfg"
    ).read_text(encoding="utf-8")
    for preset in (
        "macOS universal",
        "Linux x86_64",
        "Linux arm64",
        "Windows x86_64",
    ):
        if f'name="{preset}"' not in exports:
            raise AssertionError(f"M11 export preset is absent: {preset}")
    workflow = (
        ROOT / ".github/workflows/native.yml"
    ).read_text(encoding="utf-8")
    if "cibuildwheel --output-dir dist" not in workflow:
        raise AssertionError("M11 CI does not use cibuildwheel")
    for platform in (
        "macos-arm64",
        "macos-x86_64",
        "linux-x86_64",
        "linux-aarch64",
        "windows-x86_64",
    ):
        if platform not in workflow:
            raise AssertionError(f"M11 package CI is absent: {platform}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m11-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m10/check.py", "--skip-build"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(
            [
                "cmake",
                "--build",
                "--preset",
                arguments.preset,
                "-j",
                "8",
            ]
        )
        run(
            [
                "ctest",
                "--preset",
                arguments.preset,
                "-j",
                "8",
            ]
        )
    print("M11 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
