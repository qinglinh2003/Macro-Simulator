#!/usr/bin/env python3
"""Run the local M4 contract and acceptance checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def validate_contracts() -> None:
    target = json.loads(
        (ROOT / "schemas/m4/current_engine_target.json").read_text(
            encoding="utf-8"
        )
    )
    if target["playable_model_id"] != "current_playable_v1":
        raise AssertionError("M4 target is not the current playable engine")
    if target["config_field_count"] != 370:
        raise AssertionError("M4 target config inventory is incomplete")
    target_sources = {
        item["path"]
        for item in target["sources"]
    }
    if any(
        not item.get("owner_milestone")
        for item in target["sources"]
    ):
        raise AssertionError(
            "a current product source has no native migration owner"
        )
    required_sources = {
        "macro_sim/config/model.py",
        "macro_sim/controllers/coordinator.py",
        "macro_sim/desktop/new_game.py",
        "macro_sim/desktop/runtime.py",
        "macro_sim/demographics/economic_bridge.py",
        "macro_sim/economy.py",
        "macro_sim/housing/market.py",
        "macro_sim/rl/algorithm.py",
        "macro_sim/shocks/engine.py",
        "macro_sim/systems/banking.py",
        "macro_sim/systems/energy.py",
        "macro_sim/world/world.py",
        "desktop/godot/scripts/simulation_client.gd",
    }
    missing_sources = sorted(required_sources.difference(target_sources))
    if missing_sources:
        raise AssertionError(
            f"M4 target omits current product sources: {missing_sources}"
        )
    if target["playable_feature_override_count"] != len(
        target["playable_feature_overrides"]
    ):
        raise AssertionError("M4 playable override count is inconsistent")
    if set(target["playable_feature_override_owners"]) != set(
        target["playable_feature_overrides"]
    ):
        raise AssertionError("a current playable override has no native owner")
    owned = {
        domain
        for domains in target["milestone_coverage"].values()
        for domain in domains
    }
    if len(owned) != sum(
        len(domains) for domains in target["milestone_coverage"].values()
    ):
        raise AssertionError("a current domain has multiple milestone owners")
    if target["production_cutover_milestone"] != "m11":
        raise AssertionError("M4 cannot be a production cutover")
    budget = json.loads(
        (ROOT / "schemas/m4/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    if budget["maximum_allocations_per_day"] != 0:
        raise AssertionError("M4 steady tick must retain a zero-allocation gate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m4-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m4/current_target.py", "--check"])
    run([sys.executable, "tools/m4/locks.py"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset])
        run(["ctest", "--preset", arguments.preset])
    print("M4 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
