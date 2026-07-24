#!/usr/bin/env python3
"""Validate the reproducible local toolchain used by native M1 builds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
MINIMUMS = {
    "cmake": (3, 26, 0),
    "ninja": (1, 11, 0),
    "ccache": (4, 8, 0),
    "uv": (0, 7, 0),
}


def _version(command: str, arguments: tuple[str, ...] = ("--version",)) -> dict:
    path = shutil.which(command)
    if path is None:
        return {"command": command, "found": False, "path": None, "version": None}
    completed = subprocess.run(
        [path, *arguments],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    output = (completed.stdout or completed.stderr).strip()
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", output)
    version = tuple(int(part or 0) for part in match.groups()) if match else None
    return {
        "command": command,
        # MSVC's `cl /Bv` prints a valid version and then exits nonzero because
        # no source file was supplied. A resolved executable with a parseable
        # version is a successful toolchain probe regardless of that exit code.
        "found": version is not None,
        "path": path,
        "version": list(version) if version else None,
        "first_line": output.splitlines()[0] if output else "",
        "return_code": completed.returncode,
    }


def inspect() -> dict:
    compiler = "cl" if platform.system() == "Windows" else "cc"
    compiler_arguments = ("/Bv",) if compiler == "cl" else ("--version",)
    tools = {
        "cmake": _version("cmake"),
        "ninja": _version("ninja", ("--version",)),
        "ccache": _version("ccache"),
        "uv": _version("uv"),
        "git": _version("git"),
        "c_compiler": _version(compiler, compiler_arguments),
    }
    failures: list[str] = []
    for name, minimum in MINIMUMS.items():
        item = tools[name]
        version = tuple(item["version"] or ())
        if not item["found"]:
            failures.append(f"{name} is missing")
        elif version < minimum:
            failures.append(f"{name} {version} is older than {minimum}")
    if sys.version_info[:2] != (3, 12):
        failures.append(f"Python 3.12 is required, found {platform.python_version()}")
    if not tools["git"]["found"]:
        failures.append("git is missing")
    if not tools["c_compiler"]["found"]:
        failures.append(f"{compiler} compiler is missing")
    return {
        "schema_version": "m1-bootstrap-v1",
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "tools": tools,
        "failures": failures,
        "status": "passed" if not failures else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = inspect()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    if args.check and result["failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
