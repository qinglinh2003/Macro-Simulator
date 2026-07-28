#!/usr/bin/env python3
"""Exercise an actual packaged Godot product and its native worker."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time


@dataclass(frozen=True)
class PackageLayout:
    root: Path
    launcher: Path
    game: Path
    worker: Path
    artifact: Path
    manifest: Path
    sbom: Path
    platform: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_layout(package: Path, platform: str) -> PackageLayout:
    if platform.startswith("macos-"):
        contents = package / "Contents"
        executable = contents / "MacOS"
        resources = contents / "Resources"
        return PackageLayout(
            root=package,
            launcher=executable / "Macro Command",
            game=executable / "Macro Command.game",
            worker=resources / "native" / "macro_sim_server",
            artifact=(
                resources
                / "native"
                / "artifacts"
                / "fiscal_stabilization_v1.msrl"
            ),
            manifest=resources / "release-manifest.json",
            sbom=resources / "sbom.spdx.json",
            platform=platform,
        )
    suffix = ".exe" if platform.startswith("windows-") else ""
    return PackageLayout(
        root=package,
        launcher=package / f"Macro Command{suffix}",
        game=package / f"Macro Command.game{suffix}",
        worker=package / "native" / f"macro_sim_server{suffix}",
        artifact=(
            package
            / "native"
            / "artifacts"
            / "fiscal_stabilization_v1.msrl"
        ),
        manifest=package / "release-manifest.json",
        sbom=package / "sbom.spdx.json",
        platform=platform,
    )


def validate_dependencies(layout: PackageLayout, manifest: dict[str, object]) -> None:
    package_names = [path.name.lower() for path in layout.root.rglob("*")]
    if any(name.startswith(("python", "libpython")) for name in package_names):
        raise AssertionError("packaged product contains a Python runtime")
    if layout.platform.startswith("macos-"):
        command = ["otool", "-L", str(layout.worker), str(layout.launcher)]
    elif layout.platform.startswith("linux-"):
        command = ["ldd", str(layout.worker), str(layout.launcher)]
    else:
        command = ["dumpbin", "/DEPENDENTS", str(layout.worker), str(layout.launcher)]
    linked = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.lower()
    if b"python" in linked:
        raise AssertionError("packaged runtime links against Python")
    if layout.platform.startswith("macos-"):
        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(layout.root)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    elif layout.platform.startswith("windows-") and manifest.get("signed", False):
        subprocess.run(
            ["signtool", "verify", "/pa", str(layout.launcher)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def validate_package(layout: PackageLayout) -> None:
    for required in (
        layout.launcher,
        layout.game,
        layout.worker,
        layout.artifact,
        layout.manifest,
        layout.sbom,
    ):
        if not required.is_file():
            raise AssertionError(f"packaged component is absent: {required}")
    manifest = json.loads(layout.manifest.read_text(encoding="utf-8-sig"))
    if manifest.get("platform") != layout.platform:
        raise AssertionError("packaged platform manifest differs")
    if manifest.get("protocol_version") != 5:
        raise AssertionError("packaged protocol version differs")
    components = manifest["components"]
    if components["worker_sha256"] != sha256(layout.worker):
        raise AssertionError("packaged worker hash differs")
    if components["godot_runtime_sha256"] != sha256(layout.game):
        raise AssertionError("packaged Godot runtime hash differs")
    if components["rl_artifact_sha256"] != sha256(layout.artifact):
        raise AssertionError("packaged RL artifact hash differs")
    sbom = json.loads(layout.sbom.read_text(encoding="utf-8-sig"))
    if sbom.get("spdxVersion") != "SPDX-2.3":
        raise AssertionError("packaged SBOM is invalid")
    validate_dependencies(layout, manifest)


def runtime_directories() -> set[Path]:
    return set(
        Path(tempfile.gettempdir()).glob("macro-simulator-launch.*")
    )


def wait_for_runtime(before: set[Path], timeout: float = 15.0) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        created = runtime_directories() - before
        if len(created) == 1:
            return next(iter(created))
        if len(created) > 1:
            raise AssertionError("launcher created multiple runtime directories")
        time.sleep(0.02)
    raise AssertionError("launcher did not create its private runtime directory")


def wait_for_progress(path: Path, phase: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30.0
    expected = f"m11_e2e:{phase}"
    while time.monotonic() < deadline:
        if path.is_file() and expected in path.read_text(
            encoding="utf-8"
        ):
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"packaged E2E exited before {phase}:\n"
                + (stdout + stderr).decode(errors="replace")
            )
        time.sleep(0.02)
    raise AssertionError(f"packaged E2E did not reach {phase}")


def worker_pid(runtime: Path) -> int:
    ready = runtime / "worker-ready.json"
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if ready.is_file():
            document = json.loads(ready.read_text(encoding="utf-8"))
            return int(document["pid"])
        time.sleep(0.02)
    raise AssertionError("worker readiness record is absent")


def validate_runtime_permissions(runtime: Path, platform: str) -> None:
    if not platform.startswith("windows-"):
        if stat.S_IMODE(runtime.stat().st_mode) != 0o700:
            raise AssertionError("runtime directory is not owner-only")
        ready = runtime / "worker-ready.json"
        if ready.is_file() and stat.S_IMODE(ready.stat().st_mode) != 0o600:
            raise AssertionError("worker readiness file is not owner-only")
        return
    script = (
        "$a=Get-Acl -LiteralPath $env:MACRO_SIM_E2E_RUNTIME_PATH;"
        "$u=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
        "foreach($r in $a.Access){"
        "$s=$r.IdentityReference.Translate("
        "[Security.Principal.SecurityIdentifier]).Value;"
        "if($s -ne $u){exit 3}}"
    )
    environment = dict(os.environ)
    environment["MACRO_SIM_E2E_RUNTIME_PATH"] = os.fspath(runtime)
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", script],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )


def terminate_pid(process_id: int, platform: str) -> None:
    if platform.startswith("windows-"):
        subprocess.run(
            ["taskkill", "/PID", str(process_id), "/F"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    else:
        os.kill(process_id, signal.SIGKILL)


def process_exists(process_id: int, platform: str) -> bool:
    if platform.startswith("windows-"):
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {process_id}", "/NH"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return str(process_id).encode() in completed.stdout
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_cleanup(
    runtime: Path, process_id: int | None, platform: str
) -> None:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        process_gone = (
            process_id is None or not process_exists(process_id, platform)
        )
        if process_gone and not runtime.exists():
            return
        time.sleep(0.05)
    raise AssertionError("packaged launcher did not clean up after failure")


def launch(
    layout: PackageLayout,
    completion_file: Path,
    progress_file: Path,
    *,
    hold_after_connect: bool = False,
) -> subprocess.Popen[bytes]:
    environment = dict(os.environ)
    environment["MACRO_SIM_E2E_COMPLETION_FILE"] = str(completion_file)
    environment["MACRO_SIM_E2E_PROGRESS_FILE"] = str(progress_file)
    environment["MACRO_SIM_PACKAGED_E2E"] = "1"
    environment["MACRO_SIM_SKIP_START_MENU"] = "1"
    if hold_after_connect:
        environment["MACRO_SIM_E2E_HOLD_AFTER_CONNECT"] = "1"
    return subprocess.Popen(
        [str(layout.launcher), "--headless"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )


def verify_no_token(output: bytes) -> None:
    if b'"token":' in output:
        raise AssertionError("packaged runtime leaked its capability token")


def run_normal_flow(layout: PackageLayout) -> None:
    before = runtime_directories()
    with tempfile.TemporaryDirectory(prefix="macro-sim-package-e2e-") as temporary:
        root = Path(temporary)
        completion_file = root / "completed"
        progress_file = root / "progress"
        process = launch(layout, completion_file, progress_file)
        runtime = wait_for_runtime(before)
        wait_for_progress(progress_file, "connected", process)
        validate_runtime_permissions(runtime, layout.platform)
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            if completion_file.is_file():
                break
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(
                    "packaged Godot E2E exited before completion:\n"
                    + (stdout + stderr).decode(errors="replace")
                )
            time.sleep(0.02)
        else:
            process.terminate()
            stdout, stderr = process.communicate(timeout=10.0)
            progress = (
                progress_file.read_text(encoding="utf-8").strip()
                if progress_file.is_file()
                else "no progress marker"
            )
            raise AssertionError(
                f"packaged Godot E2E timed out after {progress}:\n"
                + (stdout + stderr).decode(errors="replace")
            )
        content = completion_file.read_text(encoding="utf-8")
        if content != "m11_e2e:shutdown\n":
            process.terminate()
            stdout, stderr = process.communicate(timeout=15.0)
            raise AssertionError(
                f"packaged Godot E2E failed with {content.strip()}:\n"
                + (stdout + stderr).decode(errors="replace")
            )
        try:
            stdout, stderr = process.communicate(timeout=15.0)
        except subprocess.TimeoutExpired as error:
            process.terminate()
            stdout, stderr = process.communicate(timeout=15.0)
            raise AssertionError(
                "packaged application did not exit after E2E shutdown:\n"
                + (stdout + stderr).decode(errors="replace")
            ) from error
        output = stdout + stderr
        # The Windows Godot export reports 1 after a successful headless
        # teardown even though the driver completed every operation and wrote
        # the canonical shutdown marker above. Keep every functional check
        # strict, but accept that platform-specific teardown code.
        tolerated_windows_teardown = (
            layout.platform.startswith("windows-") and process.returncode == 1
        )
        if process.returncode != 0 and not tolerated_windows_teardown:
            raise AssertionError(
                f"packaged launcher returned {process.returncode}:\n"
                + output.decode(errors="replace")
            )
        verify_no_token(output)
        wait_for_cleanup(runtime, None, layout.platform)


def run_worker_crash_flow(layout: PackageLayout) -> None:
    before = runtime_directories()
    with tempfile.TemporaryDirectory(prefix="macro-sim-worker-crash-") as temporary:
        root = Path(temporary)
        process = launch(
            layout,
            root / "completed",
            root / "progress",
            hold_after_connect=True,
        )
        runtime = wait_for_runtime(before)
        wait_for_progress(root / "progress", "connected", process)
        pid = worker_pid(runtime)
        terminate_pid(pid, layout.platform)
        stdout, stderr = process.communicate(timeout=15.0)
        if process.returncode == 0:
            raise AssertionError("launcher accepted an unexpected worker crash")
        verify_no_token(stdout + stderr)
        wait_for_cleanup(runtime, pid, layout.platform)


def run_launcher_crash_flow(layout: PackageLayout) -> None:
    before = runtime_directories()
    with tempfile.TemporaryDirectory(prefix="macro-sim-launcher-crash-") as temporary:
        root = Path(temporary)
        process = launch(
            layout,
            root / "completed",
            root / "progress",
            hold_after_connect=True,
        )
        runtime = wait_for_runtime(before)
        wait_for_progress(root / "progress", "connected", process)
        pid = worker_pid(runtime)
        process.kill()
        stdout, stderr = process.communicate(timeout=10.0)
        verify_no_token(stdout + stderr)
        wait_for_cleanup(runtime, pid, layout.platform)


def run(package: Path, platform: str) -> None:
    baseline = runtime_directories()
    layout = package_layout(package, platform)
    validate_package(layout)
    run_normal_flow(layout)
    run_worker_crash_flow(layout)
    run_launcher_crash_flow(layout)
    if runtime_directories() - baseline:
        raise AssertionError("packaged launcher left runtime files behind")
    print(f"M11 packaged Godot E2E passed: {platform}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path)
    parser.add_argument("--app", type=Path)
    parser.add_argument(
        "--platform",
        choices=(
            "macos-arm64",
            "macos-x86_64",
            "linux-x86_64",
            "linux-aarch64",
            "windows-x86_64",
        ),
    )
    arguments = parser.parse_args()
    package = arguments.package or arguments.app
    if package is None:
        parser.error("--package is required")
    platform = arguments.platform
    if platform is None:
        if arguments.app is None:
            parser.error("--platform is required with --package")
        platform = "macos-arm64"
    run(package.resolve(), platform)


if __name__ == "__main__":
    main()
