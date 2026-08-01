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
CONFIG_MODEL = ROOT / "macro_sim/config/model.py"

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

PLAYABLE_OVERRIDE_OWNERS = {
    "alpha1": "m4",
    "a_K": "m4",
    "amort": "m5",
    "bank_realized_pnl": "m5",
    "bank_relationship_lock_in": "m5",
    "benefit_income_floor": "m5",
    "bond_maturity_bucket": "m6",
    "builder_demand_seed": "m8",
    "builder_land_fee_credit": "m8",
    "capital_annual_clock": "m6",
    "capital_clock_demand_smoothing": "m6",
    "capital_firm_entry": "m6",
    "capital_rationed_signal": "m6",
    "capital_service_min_utilization": "m6",
    "capital_service_pricing": "m6",
    "cb_uses_fixed_basket_cpi": "m5",
    "claims_reconcile_interval": "m6",
    "consumption_rationed_signal": "m4",
    "consumption_strata": "m7",
    "cpi_item_link_cap": "m10",
    "demographic_lifecycle_consumption": "m7",
    "demographics_enabled": "m7",
    "deprivation_gauges": "m7",
    "demand_e_firm0": "m8",
    "energy_coverage_ticks": "m8",
    "energy_enabled": "m8",
    "energy_gap_close": "m8",
    "energy_hoarding_beta": "m8",
    "energy_household": "m8",
    "energy_mortality_gamma": "m8",
    "family_transfers": "m7",
    "fertility_income_elasticity": "m7",
    "fertility_rank_gradient": "m7",
    "firm_full_pnl": "m6",
    "firm_subscale_exit": "m6",
    "fiscal_uses_national_accounts_gdp": "m5",
    "gov_consumption_share": "m5",
    "hh_amort": "m5",
    "household_interest_arrears": "m5",
    "housing_construction_enabled": "m8",
    "housing_ask_decay": "m8",
    "housing_ask_floor_wage_share": "m8",
    "housing_demand_step": "m8",
    "housing_enabled": "m8",
    "housing_fertility_elasticity": "m8",
    "housing_leave_elasticity": "m8",
    "housing_market_enabled": "m8",
    "housing_rental_enabled": "m8",
    "housing_wealth_effect": "m8",
    "labor_fractional_hours": "m7",
    "labor_job_ladder": "m7",
    "labor_matching": "m7",
    "labor_matching_friction": "m7",
    "labor_participation": "m7",
    "labor_person_efficiency": "m7",
    "labor_relationship_wages": "m7",
    "labor_second_job": "m7",
    "labor_suspension": "m7",
    "ledger_rel_tol": "m2",
    "inv_firm0": "m4",
    "inv_kfirm0": "m4",
    "job_guarantee": "m5",
    "marriage_assortativity": "m7",
    "monetary_direct_transmission": "m5",
    "mortality_income_elasticity": "m7",
    "mortality_rank_gradient": "m7",
    "mortgage_enabled": "m8",
    "mortgage_underwriting": "m8",
    "national_accounts_metrics": "m10",
    "priced_firm_balance_sheet": "m6",
    "p_efirm0": "m8",
    "p_firm0": "m4",
    "p_kfirm0": "m4",
    "pension_replacement": "m5",
    "rental_eviction_arrears": "m8",
    "rental_rent_floor_wage_share": "m8",
    "rental_vacancy_deadband": "m8",
    "sector_switching": "m7",
    "switch_retool_loss": "m7",
    "tax_income_rate": "m5",
    "tfp_drift_rate": "m4",
    "unified_bank_rwa": "m5",
}

TARGET_SOURCE_ROOTS = (
    ROOT / "macro_sim",
    ROOT / "desktop/godot",
)
TARGET_SOURCE_FILES = (
    ROOT / "configs/base.yaml",
    ROOT / "configs/calibrations/daily_tick.yaml",
)
TARGET_SOURCE_SUFFIXES = {
    ".gd",
    ".godot",
    ".json",
    ".py",
    ".tscn",
    ".yaml",
    ".yml",
}


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


def file_digest(relative: str, owner_milestone: str) -> dict[str, Any]:
    content = (ROOT / relative).read_bytes()
    return {
        "byte_count": len(content),
        "owner_milestone": owner_milestone,
        "path": relative,
        "sha256": sha256(content).hexdigest(),
    }


def target_source_paths() -> tuple[str, ...]:
    paths = set(TARGET_SOURCE_FILES)
    for root in TARGET_SOURCE_ROOTS:
        paths.update(
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix in TARGET_SOURCE_SUFFIXES
        )
    return tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted(paths)
    )


def _constant_value(node: ast.AST) -> Any:
    """Evaluate a restricted literal expression without executing source."""
    try:
        return ast.literal_eval(node)
    except (TypeError, ValueError):
        pass
    if isinstance(node, ast.Dict):
        return {
            _constant_value(key): _constant_value(value)
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(
        node.op, (ast.UAdd, ast.USub)
    ):
        operand = _constant_value(node.operand)
        if isinstance(operand, bool) or not isinstance(operand, (int, float)):
            raise ValueError("constant unary operand must be numeric")
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
    ):
        left = _constant_value(node.left)
        right = _constant_value(node.right)
        if (
            isinstance(left, bool)
            or isinstance(right, bool)
            or not isinstance(left, (int, float))
            or not isinstance(right, (int, float))
        ):
            raise ValueError("constant binary operands must be numeric")
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        return left / right
    raise ValueError(f"unsupported constant expression: {ast.dump(node)}")


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
                return _constant_value(value)
    raise RuntimeError(f"cannot find literal assignment {name}")


def config_field_count() -> int:
    tree = ast.parse(CONFIG_MODEL.read_text(encoding="utf-8"))
    config = next(
        (
            statement
            for statement in tree.body
            if isinstance(statement, ast.ClassDef)
            and statement.name == "Config"
        ),
        None,
    )
    if config is None:
        raise RuntimeError("cannot find the current Config dataclass")
    return sum(
        isinstance(statement, ast.AnnAssign)
        for statement in config.body
    )


def module_owners() -> dict[str, str]:
    value = json.loads(
        (ROOT / "schemas/m0/inventory/modules.json").read_text(
            encoding="utf-8"
        )
    )
    owners = {
        row["source_path"]: row["owner_milestone"]
        for row in value["rows"]
        if row["status"] == "active"
    }
    if len(owners) != len(value["rows"]):
        raise RuntimeError("module inventory has duplicate or inactive rows")
    return owners


def inventory_metadata(name: str) -> dict[str, Any]:
    value = json.loads(
        (ROOT / f"schemas/m0/inventory/{name}.json").read_text(
            encoding="utf-8"
        )
    )
    metadata = dict(value["metadata"])
    # Product-target evidence describes the current builder. Historical
    # sampling labels belong to regression fixtures, not engine capabilities.
    metadata.pop("sampling_profiles", None)
    return {
        "aggregate_sha256": sha256(canonical_bytes(value)).hexdigest(),
        "metadata": metadata,
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
    if set(overrides) != set(PLAYABLE_OVERRIDE_OWNERS):
        missing = sorted(set(overrides).difference(PLAYABLE_OVERRIDE_OWNERS))
        stale = sorted(set(PLAYABLE_OVERRIDE_OWNERS).difference(overrides))
        raise RuntimeError(
            f"playable override ownership is stale: missing={missing}, "
            f"removed={stale}"
        )
    source_paths = target_source_paths()
    owners = module_owners()
    missing_owners = sorted(set(source_paths).difference(owners))
    if missing_owners:
        raise RuntimeError(
            f"current product sources have no migration owner: "
            f"{missing_owners}"
        )
    sources = [
        file_digest(path, owners[path])
        for path in source_paths
    ]
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
    current_config_field_count = config_field_count()
    inventoried_config_field_count = inventories["config"]["metadata"][
        "root_config_field_count"
    ]
    if current_config_field_count != inventoried_config_field_count:
        raise RuntimeError(
            "current Config fields no longer match the complete inventory: "
            f"{current_config_field_count} != "
            f"{inventoried_config_field_count}"
        )
    return {
        "config_field_count": current_config_field_count,
        "inventory": inventories,
        "milestone_coverage": MILESTONE_COVERAGE,
        "playable_feature_overrides": overrides,
        "playable_feature_override_count": len(overrides),
        "playable_feature_override_owners": PLAYABLE_OVERRIDE_OWNERS,
        "playable_model_id": model_id,
        "product_builder": "macro_sim.desktop.new_game.NewGameSpec.configs",
        "production_cutover_milestone": "m11",
        "schema_version": "m4-current-engine-target-v1",
        "source_aggregate_sha256": sha256(
            canonical_bytes(sources)
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
