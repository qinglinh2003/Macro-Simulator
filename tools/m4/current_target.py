#!/usr/bin/env python3
"""Generate the M4 migration target from the current playable product builder."""

from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "schemas/m4/current_engine_target.json"
NEW_GAME = ROOT / "macro_sim/desktop/new_game.py"

MILESTONE_COVERAGE = {
    "m4": [
        "basic_households",
        "basic_firms",
        "spot_labor",
        "production",
        "goods_market",
        "physical_capital",
        "capital_goods_market",
    ],
    "m5": [
        "fiscal",
        "credit",
        "banks",
        "central_bank",
        "reserves",
        "rtgs",
        "interbank",
    ],
    "m6": [
        "bonds",
        "equity",
        "valuation",
        "firm_dynamics",
        "bank_resolution",
    ],
    "m7": [
        "persons",
        "families",
        "estates",
        "ownership",
        "persistent_labor",
    ],
    "m8": ["energy", "housing"],
    "m9": [
        "trade",
        "fx",
        "international_capital",
        "migration",
        "peg",
        "sanctions",
        "shocks",
    ],
    "m10": [
        "metrics",
        "releases",
        "controllers",
        "gym",
        "rl",
        "diagnostics_adapters",
    ],
    "m11": [
        "native_policy_inference",
        "desktop_worker",
        "packaging",
        "production_cutover",
    ],
}

TARGET_SOURCES = (
    "macro_sim/config/model.py",
    "macro_sim/desktop/new_game.py",
    "macro_sim/desktop/runtime.py",
    "macro_sim/economy.py",
    "macro_sim/world/world.py",
    "macro_sim/core/policy_registry.py",
    "macro_sim/controllers/coordinator.py",
    "macro_sim/shocks/engine.py",
)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def file_digest(relative: str) -> dict[str, Any]:
    content = (ROOT / relative).read_bytes()
    return {
        "byte_count": len(content),
        "path": relative,
        "sha256": sha256(content).hexdigest(),
    }


def assigned_literal(module: ast.Module, name: str) -> Any:
    for statement in module.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            names: list[str] = []
            value = statement.value
            if isinstance(statement, ast.Assign):
                names = [
                    target.id
                    for target in statement.targets
                    if isinstance(target, ast.Name)
                ]
            elif isinstance(statement.target, ast.Name):
                names = [statement.target.id]
            if name in names and value is not None:
                return ast.literal_eval(value)
    raise RuntimeError(f"cannot find literal assignment {name}")


def inventory_metadata(name: str) -> dict[str, Any]:
    value = json.loads(
        (ROOT / f"schemas/m0/inventory/{name}.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "aggregate_sha256": sha256(canonical_bytes(value)).hexdigest(),
        "metadata": value["metadata"],
        "row_count": len(value["rows"]),
    }


def build_target() -> dict[str, Any]:
    tree = ast.parse(NEW_GAME.read_text(encoding="utf-8"))
    model_id = assigned_literal(tree, "PLAYABLE_MODEL_ID")
    overrides = assigned_literal(tree, "PLAYABLE_FEATURE_OVERRIDES")
    if model_id != "current_playable_v1":
        raise RuntimeError("unexpected current playable model ID")
    if not isinstance(overrides, dict) or not overrides:
        raise RuntimeError("current playable overrides are absent")
    sources = [file_digest(path) for path in TARGET_SOURCES]
    source_hashes = {item["path"]: item["sha256"] for item in sources}
    inventories = {
        name: inventory_metadata(name)
        for name in (
            "capabilities",
            "config",
            "controller",
            "events",
            "metrics",
            "modules",
            "observations",
            "phases",
            "policy",
            "rng",
            "shocks",
        )
    }
    config_field_count = inventories["config"]["metadata"][
        "root_config_field_count"
    ]
    return {
        "config_field_count": config_field_count,
        "historical_factory_policy": {
            "full_product_target": False,
            "permitted_use": "historical_regression_tripwire",
            "retained_fixture": "fixture.f0.refactor-tripwires",
            "symbol": "Config.v124",
        },
        "inventory": inventories,
        "milestone_coverage": MILESTONE_COVERAGE,
        "playable_feature_overrides": overrides,
        "playable_feature_override_count": len(overrides),
        "playable_model_id": model_id,
        "product_builder": "macro_sim.desktop.new_game.NewGameSpec.configs",
        "production_cutover_milestone": "m11",
        "schema_version": "m4-current-engine-target-v1",
        "source_aggregate_sha256": sha256(
            canonical_bytes(source_hashes)
        ).hexdigest(),
        "sources": sources,
        "supersedes_m0_fixture_factory_labels": [
            "fixture.f2.capital-fiscal",
            "fixture.f3.full-playable",
            "fixture.f4.world-n2",
            "fixture.f5.policy-semantics",
            "fixture.f6.shock-semantics",
            "fixture.f7.controller-lifecycle",
            "fixture.f8.rl-contract",
            "fixture.f9.desktop-flow",
            "fixture.f10.persistence",
            "fixture.f11.stochastic-panels",
        ],
        "world_builder": "macro_sim.world.world.World",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    encoded = canonical_bytes(build_target())
    if arguments.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != encoded:
            raise SystemExit("M4 current engine target is stale")
        print("M4 current engine target: current")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(encoded)
    print(OUTPUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
