#!/usr/bin/env python3
"""Run the local M2 canonical-accounting verification stack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]
M1_COMMIT = "d7af86944a840d2f0465001cdf971dc4fdc1cd88"
CJK_PATTERN = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def check_frozen_evidence() -> None:
    roots = (
        "schemas/m0",
        "schemas/m1",
        "benchmarks/results/m0/reference",
        "tests/fixtures/m0/expected",
    )
    completed = subprocess.run(
        ["git", "diff", "--quiet", M1_COMMIT, "--", *roots],
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise SystemExit("M0 or M1 frozen evidence differs from the M1 milestone")


def check_contracts() -> None:
    required_json = (
        ROOT / "schemas/m2/checkpoint_contract.json",
        ROOT / "schemas/m2/differential_contract.json",
        ROOT / "schemas/m2/performance_budget.json",
        ROOT / "schemas/m2/fixtures/genesis.json",
    )
    for path in required_json:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not value.get("schema_version"):
            raise SystemExit(f"invalid M2 contract: {path.relative_to(ROOT)}")
    gates = yaml.safe_load(
        (ROOT / "schemas/m2/manifests/gates.yaml").read_text(encoding="utf-8")
    )
    identifiers = [gate["id"] for gate in gates["gates"]]
    if len(identifiers) != len(set(identifiers)):
        raise SystemExit("M2 gate IDs are duplicated")


def check_english_delta() -> None:
    subjects = subprocess.run(
        ["git", "log", "--format=%s", f"{M1_COMMIT}..HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if any(CJK_PATTERN.search(subject) for subject in subjects):
        raise SystemExit("an M2 commit subject contains CJK text")
    changed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            M1_COMMIT,
            "HEAD",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for relative in changed:
        path = ROOT / relative
        if not path.is_file() or "vendor" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if CJK_PATTERN.search(text):
            raise SystemExit(f"an M2 text file contains CJK text: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="m2-debug")
    parser.add_argument("--skip-build", action="store_true")
    arguments = parser.parse_args()
    check_frozen_evidence()
    check_contracts()
    check_english_delta()
    run([sys.executable, "-m", "pytest", "-q", "tests/native"])
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset])
        run(["ctest", "--preset", arguments.preset])
    print("M2 local verification: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
