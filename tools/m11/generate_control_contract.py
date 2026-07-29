#!/usr/bin/env python3
"""Generate the checked-in native M11 policy-control contract."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from macro_sim.core.policy_registry import (
    Bool,
    Choices,
    EconomyId,
    EconomySet,
    IntRange,
    NullableRange,
    Range,
    REGISTRY,
)


JSON_OUTPUT = ROOT / "schemas/m11/control_contract.json"
CPP_OUTPUT = (
    ROOT
    / "native/include/macro_sim/control/generated_m11_policy_contract.inc"
)
CPP_ROUTES_OUTPUT = (
    ROOT
    / "native/src/control/generated_m11_policy_routes.inc"
)
SPECIAL_POLICY_LEVERS = frozenset(
    {"monetary_regime", "energy_rationing", "bank_resolution_fund"}
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _native_policy_bindings() -> dict[str, tuple[str, str]]:
    source = ast.parse(
        (ROOT / "macro_sim/native_backend.py").read_text(encoding="utf-8")
    )
    names = {
        "M5_POLICY_FIELDS": "fiscal_monetary",
        "M6_POLICY_FIELDS": "financial",
        "M7_POLICY_FIELDS": "population",
        "ENERGY_POLICY_FIELDS": "energy",
        "HOUSING_POLICY_FIELDS": "housing",
    }
    dictionaries: dict[str, dict[str, str]] = {}
    for node in source.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if (
            isinstance(target, ast.Name)
            and target.id in names
            and value is not None
        ):
            parsed = ast.literal_eval(value)
            if not isinstance(parsed, dict):
                raise AssertionError(f"{target.id} must be a dictionary")
            dictionaries[target.id] = parsed
    if set(dictionaries) != set(names):
        raise AssertionError("native policy binding maps are incomplete")
    result: dict[str, tuple[str, str]] = {}
    for dictionary_name, section in names.items():
        for target_field, source_name in dictionaries[dictionary_name].items():
            if source_name in SPECIAL_POLICY_LEVERS:
                continue
            if source_name in result:
                raise AssertionError(
                    f"duplicate native policy binding for {source_name}"
                )
            result[source_name] = (section, target_field)
    return result


DOMESTIC_POLICY_BINDINGS = _native_policy_bindings()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _kind(validation: Any) -> str:
    if isinstance(validation, IntRange):
        return "integer"
    if isinstance(validation, NullableRange):
        return "nullable_number"
    if isinstance(validation, Range):
        return "number"
    if isinstance(validation, Bool):
        return "boolean"
    if isinstance(validation, Choices):
        return "choice"
    if isinstance(validation, EconomyId):
        return "economy_id"
    if isinstance(validation, EconomySet):
        return "economy_set"
    raise TypeError(f"unsupported validation type {type(validation).__name__}")


def _route(name: str, scope: str) -> tuple[str, str]:
    if name in SPECIAL_POLICY_LEVERS:
        return "special", name
    if scope == "external":
        return "external", name
    try:
        return DOMESTIC_POLICY_BINDINGS[name]
    except KeyError as exc:
        raise AssertionError(f"domestic route missing for {name}") from exc


def _rows() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, lever in sorted(REGISTRY.items()):
        validation = lever.validation
        kind = _kind(validation)
        section, field = _route(name, lever.scope)
        row = {
            "name": name,
            "scope": lever.scope,
            "kind": kind,
            "minimum": (
                validation.lo if isinstance(validation, Range) else None
            ),
            "maximum": (
                validation.hi if isinstance(validation, Range) else None
            ),
            "choices": (
                list(validation.values)
                if isinstance(validation, Choices)
                else []
            ),
            "owner_role": lever.owner_role,
            "decision_group": lever.decision_group,
            "implementation_lag": lever.implementation_lag,
            "emergency_implementation_lag":
                lever.emergency_implementation_lag,
            "min_hold_ticks": lever.min_hold_ticks,
            "emergency": lever.emergency,
            "control_scale": lever.control_scale,
            "max_step": (
                validation.max_step
                if isinstance(validation, Range)
                else None
            ),
            "admin_weight": lever.admin_weight,
            "cost_class": lever.cost_class,
            "semantics": lever.semantics,
            "handler_id": lever.handler_id,
            "enabled_if": sorted(lever.enabled_if),
            "requires": sorted(lever.requires),
            "route_section": section,
            "route_field": field,
        }
        result.append(row)
    return result


def _json_contract(rows: list[dict[str, Any]]) -> str:
    body = {
        "schema_version": "m11-native-control-contract-v1",
        "seat_count": len({row["owner_role"] for row in rows}),
        "decision_group_count": len(
            {row["decision_group"] for row in rows}
        ),
        "lever_count": len(rows),
        "rows": rows,
    }
    semantic = canonical_json(body)
    body["semantic_sha256"] = hashlib.sha256(
        semantic.encode("utf-8")
    ).hexdigest()
    return canonical_json(body) + "\n"


def _cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _cpp_optional(value: Any) -> str:
    if value is None:
        return "std::nullopt"
    if isinstance(value, int):
        return f"std::optional<double>{{{value}.0}}"
    return f"std::optional<double>{{{float(value):.17g}}}"


def _cpp_contract(rows: list[dict[str, Any]], digest: str) -> str:
    lines = [
        "// Generated by tools/m11/generate_control_contract.py; do not edit.",
        f'inline constexpr std::string_view kM11PolicyContractSha256 = "{digest}";',
        "inline constexpr std::array<PolicyLeverDescriptor, "
        f"{len(rows)}> kM11PolicyLevers{{{{",
    ]
    for row in rows:
        choices = "|".join(row["choices"])
        enabled = "|".join(row["enabled_if"])
        requires = "|".join(row["requires"])
        emergency_lag = (
            "std::nullopt"
            if row["emergency_implementation_lag"] is None
            else "std::optional<std::uint32_t>{"
            f"{row['emergency_implementation_lag']}U"
            "}"
        )
        lines.append(
            "    {"
            + ", ".join(
                (
                    _cpp_string(row["name"]),
                    f"PolicyScope::{row['scope']}",
                    f"PolicyValueKind::{row['kind']}",
                    _cpp_optional(row["minimum"]),
                    _cpp_optional(row["maximum"]),
                    _cpp_string(choices),
                    _cpp_string(row["owner_role"]),
                    _cpp_string(row["decision_group"]),
                    f"{row['implementation_lag']}U",
                    emergency_lag,
                    f"{row['min_hold_ticks']}U",
                    str(row["emergency"]).lower(),
                    _cpp_optional(row["control_scale"]),
                    _cpp_optional(row["max_step"]),
                    f"{float(row['admin_weight']):.17g}",
                    _cpp_string(row["cost_class"]),
                    _cpp_string(row["semantics"]),
                    _cpp_string(row["handler_id"] or ""),
                    _cpp_string(enabled),
                    _cpp_string(requires),
                    _cpp_string(row["route_section"]),
                    _cpp_string(row["route_field"]),
                )
            )
            + "},"
        )
    lines.extend(("}};", ""))
    return "\n".join(lines)


def _cpp_routes(rows: list[dict[str, Any]]) -> str:
    lines = [
        "// Generated by tools/m11/generate_control_contract.py; do not edit."
    ]
    for row in rows:
        section = row["route_section"]
        kind = row["kind"]
        if section == "special":
            macro = "MACRO_SIM_M11_SPECIAL"
            arguments = (_cpp_string(row["name"]),)
        elif section == "external":
            macro = f"MACRO_SIM_M11_EXTERNAL_{kind.upper()}"
            arguments = (
                _cpp_string(row["name"]),
                row["route_field"],
            )
        else:
            macro = f"MACRO_SIM_M11_DOMESTIC_{kind.upper()}"
            arguments = (
                _cpp_string(row["name"]),
                section,
                row["route_field"],
            )
        lines.append(f"{macro}({', '.join(arguments)})")
    lines.append("")
    return "\n".join(lines)


def _replace_or_check(path: Path, content: str, *, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"stale generated M11 contract: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = _arguments()
    rows = _rows()
    if len(rows) != 102:
        raise AssertionError(f"expected 102 policy levers, got {len(rows)}")
    if len({row["owner_role"] for row in rows}) != 6:
        raise AssertionError("native control contract must contain six seats")
    if len({row["decision_group"] for row in rows}) != 12:
        raise AssertionError(
            "native control contract must contain twelve decision groups"
        )
    json_contract = _json_contract(rows)
    parsed = json.loads(json_contract)
    digest = parsed["semantic_sha256"]
    cpp_contract = _cpp_contract(rows, digest)
    cpp_routes = _cpp_routes(rows)
    _replace_or_check(JSON_OUTPUT, json_contract, check=args.check)
    _replace_or_check(CPP_OUTPUT, cpp_contract, check=args.check)
    _replace_or_check(CPP_ROUTES_OUTPUT, cpp_routes, check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
