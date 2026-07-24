#!/usr/bin/env python3
"""Run the local M3 pure-algorithm verification stack."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]
M2_COMMIT = "86e5448a1b700ce0b587bdc5550ffb1f6c219e7d"
CJK_PATTERN = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def check_frozen_predecessors() -> None:
    roots = (
        "schemas/m0",
        "schemas/m1",
        "schemas/m2",
        "benchmarks/results/m0/reference",
        "tests/fixtures/m0/expected",
    )
    completed = subprocess.run(
        ["git", "diff", "--quiet", M2_COMMIT, "--", *roots],
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise SystemExit("M0-M2 frozen evidence differs from the M2 milestone")
    lock = json.loads(
        subprocess.run(
            ["git", "show", f"{M2_COMMIT}:schemas/m2/source.lock.json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    for item in lock["files"]:
        content = subprocess.run(
            ["git", "show", f"{M2_COMMIT}:{item['path']}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        if sha256(content).hexdigest() != item["sha256"]:
            raise SystemExit(f"M2 Git object differs from its lock: {item['path']}")


def check_contracts() -> None:
    required = (
        "equation_contract.json",
        "market_contract.json",
        "performance_budget.json",
        "fixtures/equations.json",
        "fixtures/markets.json",
        "fixtures/shock_overlay.json",
    )
    for relative in required:
        path = ROOT / "schemas/m3" / relative
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not value.get("schema_version"):
            raise SystemExit(f"invalid M3 contract: {path.relative_to(ROOT)}")
    gates = yaml.safe_load(
        (ROOT / "schemas/m3/manifests/gates.yaml").read_text(encoding="utf-8")
    )
    identifiers = [gate["id"] for gate in gates["gates"]]
    if len(identifiers) != len(set(identifiers)):
        raise SystemExit("M3 gate IDs are duplicated")


def check_english_delta() -> None:
    subjects = subprocess.run(
        ["git", "log", "--format=%s", f"{M2_COMMIT}..HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if any(CJK_PATTERN.search(subject) for subject in subjects):
        raise SystemExit("an M3 commit subject contains CJK text")
    changed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", M2_COMMIT, "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    uncommitted = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for relative in sorted(set(changed + uncommitted)):
        path = ROOT / relative
        if not path.is_file() or "vendor" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if CJK_PATTERN.search(text):
            raise SystemExit(f"an M3 text file contains CJK text: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="m3-debug")
    parser.add_argument("--skip-build", action="store_true")
    arguments = parser.parse_args()
    check_frozen_predecessors()
    check_contracts()
    check_english_delta()
    run([sys.executable, "tools/m3/equation_fixtures.py"])
    if (ROOT / "schemas/m3/source.lock.json").is_file():
        run([sys.executable, "tools/m3/locks.py"])
    run([sys.executable, "-m", "pytest", "-q", "tests/native"])
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset])
        run(["ctest", "--preset", arguments.preset])
    print("M3 local verification: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
