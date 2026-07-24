#!/usr/bin/env python3
"""Generate deterministic M1 C++, Python, and JSON contract skeletons."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import pprint
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
M0_INVENTORY = ROOT / "schemas/m0/inventory"
M1_ROOT = ROOT / "schemas/m1"
CPP_OUTPUT = ROOT / "native/include/macro_sim/generated/contracts.hpp"
CPP_CASE_OUTPUT = ROOT / "native/include/macro_sim/generated/invalid_cases.hpp"
JSON_OUTPUT = M1_ROOT / "generated/contracts.json"
PYTHON_OUTPUT = M1_ROOT / "generated/python/contracts.py"
CASE_OUTPUT = M1_ROOT / "invalid_contract_cases.json"
LOCK_OUTPUT = M1_ROOT / "hashes.lock.json"

M0_FAMILIES = {
    "config": "config",
    "policy": "policy",
    "shock": "shocks",
    "metric": "metrics",
    "observation": "observations",
    "phase": "phases",
    "rng": "rng",
    "event": "events",
    "invariant": "invariants",
    "controller": "controller",
    "protocol": "desktop_protocol",
    "scenario": "scenarios",
}

OPTIONAL_LOCKED_ARTIFACTS = (
    ROOT / "schemas/m1/rng_vectors.json",
    ROOT / "native/include/macro_sim/generated/rng_vectors.hpp",
    ROOT / "schemas/m1/checkpoint_prototype.json",
    ROOT / "schemas/m1/canonical_encoding_vectors.json",
    ROOT / "native/dependencies.lock.json",
)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_inventory(name: str) -> dict[str, Any]:
    return json.loads((M0_INVENTORY / f"{name}.json").read_text(encoding="utf-8"))


def scalar_metadata(family: str, row: dict[str, Any]) -> dict[str, Any]:
    kind = "any"
    nullable = False
    minimum = None
    maximum = None
    choices: list[str] = []
    if family == "config":
        annotation = row.get("annotation", "Any")
        mapping = {
            "bool": ("boolean", False),
            "float": ("number", False),
            "float | None": ("number", True),
            "int": ("integer", False),
            "int | None": ("integer", True),
            "str": ("string", False),
        }
        kind, nullable = mapping.get(annotation, ("any", False))
    elif family in {"policy", "external_policy"}:
        validation = row["validation"]
        value_kind = validation["value_kind"]
        mapping = {
            "boolean": ("boolean", False),
            "choice": ("choice", False),
            "economy_id_set": ("id_set", False),
            "integer": ("integer", False),
            "nullable_economy_id": ("integer", True),
            "nullable_number": ("number", True),
            "number": ("number", False),
        }
        kind, nullable = mapping[value_kind]
        minimum = validation.get("minimum")
        maximum = validation.get("maximum")
        choices = list(validation.get("choices", []))
    return {
        "scalar_kind": kind,
        "nullable": nullable,
        "minimum": minimum,
        "maximum": maximum,
        "choices": choices,
    }


def skeleton_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "checkpoint.field.canonical_encoding_version",
            "kind": "checkpoint",
            "owner_milestone": "m1",
            "status": "skeleton",
        },
        {
            "id": "checkpoint.field.engine_version",
            "kind": "checkpoint",
            "owner_milestone": "m2",
            "status": "skeleton",
        },
        {
            "id": "checkpoint.field.payload",
            "kind": "checkpoint",
            "owner_milestone": "m2",
            "status": "skeleton",
        },
        {
            "id": "checkpoint.field.payload_sha256",
            "kind": "checkpoint",
            "owner_milestone": "m2",
            "status": "skeleton",
        },
        {
            "id": "protocol.frame.command",
            "kind": "protocol",
            "owner_milestone": "m11",
            "status": "skeleton",
        },
        {
            "id": "protocol.frame.protocol_version",
            "kind": "protocol",
            "owner_milestone": "m11",
            "status": "skeleton",
        },
        {
            "id": "protocol.frame.request_id",
            "kind": "protocol",
            "owner_milestone": "m11",
            "status": "skeleton",
        },
    ]


def build_contracts() -> dict[str, Any]:
    m0_lock = json.loads(
        (ROOT / "schemas/m0/hashes.lock.json").read_text(encoding="utf-8")
    )
    aliases: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    source_hashes: dict[str, str] = {}
    for output_family, input_family in M0_FAMILIES.items():
        path = M0_INVENTORY / f"{input_family}.json"
        source_hashes[path.relative_to(ROOT).as_posix()] = digest(path)
        inventory = load_inventory(input_family)
        for row in inventory["rows"]:
            family = output_family
            if output_family == "policy" and row.get("scope") == "external":
                family = "external_policy"
            elif output_family == "policy" and row.get("scope") != "economy":
                continue
            item = {
                "id": row["id"],
                "family": family,
                "kind": row["kind"],
                "owner_milestone": row["owner_milestone"],
                "status": row["status"],
                **scalar_metadata(family, row),
            }
            rows.append(item)
        for alias, canonical in inventory.get("aliases", {}).items():
            prefix = "policy" if input_family == "policy" else output_family
            aliases[f"{prefix}.{alias}"] = f"{prefix}.{canonical}"

    for row in skeleton_rows():
        family = row["kind"]
        rows.append(
            {
                **row,
                "family": family,
                "scalar_kind": "any",
                "nullable": False,
                "minimum": None,
                "maximum": None,
                "choices": [],
            }
        )
    rows.sort(key=lambda item: item["id"])
    for index, row in enumerate(rows):
        row["index"] = index
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("generated contract IDs are not unique")
    family_counts: dict[str, int] = {}
    for row in rows:
        family_counts[row["family"]] = family_counts.get(row["family"], 0) + 1
    return {
        "schema_version": "m1-contract-skeleton-v1",
        "canonical_encoding_version": 1,
        "m0_contract_sha256": m0_lock["aggregate_sha256"],
        "m0_source_hashes": dict(sorted(source_hashes.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "aliases": dict(sorted(aliases.items())),
        "rows": rows,
    }


def select(rows: list[dict[str, Any]], *, kind: str, nullable: bool | None = None):
    for row in rows:
        if row["scalar_kind"] != kind:
            continue
        if nullable is not None and row["nullable"] != nullable:
            continue
        return row
    raise ValueError(f"no generated row for kind={kind!r}, nullable={nullable!r}")


def build_invalid_cases(contracts: dict[str, Any]) -> dict[str, Any]:
    rows = contracts["rows"]
    number = select(rows, kind="number", nullable=False)
    boolean = select(rows, kind="boolean", nullable=False)
    integer = select(rows, kind="integer", nullable=False)
    choice = select(rows, kind="choice", nullable=False)
    nullable_number = select(rows, kind="number", nullable=True)
    ranged = next(
        row
        for row in rows
        if row["scalar_kind"] == "number"
        and row["minimum"] is not None
        and row["maximum"] is not None
    )
    cases = [
        {
            "id": "invalid.unknown-contract",
            "contract_id": "policy.not_a_real_lever",
            "input": {"kind": "number", "value": 0.0},
            "expected_code": "unknown_contract",
        },
        {
            "id": "invalid.number-type",
            "contract_id": number["id"],
            "input": {"kind": "string", "value": "not-a-number"},
            "expected_code": "type_mismatch",
        },
        {
            "id": "invalid.boolean-type",
            "contract_id": boolean["id"],
            "input": {"kind": "integer", "value": 1},
            "expected_code": "type_mismatch",
        },
        {
            "id": "invalid.integer-type",
            "contract_id": integer["id"],
            "input": {"kind": "number", "value": 1.5},
            "expected_code": "type_mismatch",
        },
        {
            "id": "invalid.choice",
            "contract_id": choice["id"],
            "input": {"kind": "string", "value": "not-a-choice"},
            "expected_code": "invalid_choice",
        },
        {
            "id": "invalid.nonfinite",
            "contract_id": number["id"],
            "input": {"kind": "nonfinite", "value": "nan"},
            "expected_code": "nonfinite",
        },
        {
            "id": "invalid.null",
            "contract_id": number["id"],
            "input": {"kind": "null", "value": None},
            "expected_code": "type_mismatch",
        },
        {
            "id": "invalid.below-minimum",
            "contract_id": ranged["id"],
            "input": {"kind": "number", "value": float(ranged["minimum"]) - 1.0},
            "expected_code": "below_minimum",
        },
        {
            "id": "invalid.above-maximum",
            "contract_id": ranged["id"],
            "input": {"kind": "number", "value": float(ranged["maximum"]) + 1.0},
            "expected_code": "above_maximum",
        },
        {
            "id": "invalid.nullable-number-type",
            "contract_id": nullable_number["id"],
            "input": {"kind": "string", "value": "none"},
            "expected_code": "type_mismatch",
        },
    ]
    return {
        "schema_version": "m1-invalid-contract-corpus-v1",
        "m0_contract_sha256": contracts["m0_contract_sha256"],
        "cases": cases,
    }


def cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def cpp_number(value: float | int | None) -> str:
    if value is None:
        return "0.0"
    return format(float(value), ".17g")


def render_cpp(contracts: dict[str, Any]) -> bytes:
    rows = contracts["rows"]
    aliases = contracts["aliases"]
    lines = [
        "#ifndef MACRO_SIM_GENERATED_CONTRACTS_HPP",
        "#define MACRO_SIM_GENERATED_CONTRACTS_HPP",
        "",
        "#include <array>",
        "#include <cmath>",
        "#include <cstddef>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        "namespace macro_sim::generated {",
        "",
        "inline constexpr std::uint32_t kCanonicalEncodingVersion = 1;",
        f"inline constexpr std::string_view kM0ContractSha256 = {cpp_string(contracts['m0_contract_sha256'])};",
        "",
        "enum class ScalarKind : std::uint8_t { any, boolean, integer, number, string, choice, id_set };",
        "enum class InputKind : std::uint8_t { null_value, boolean, integer, number, string, id_set };",
        "enum class ValidationCode : std::uint8_t { ok, unknown_contract, type_mismatch, nonfinite, below_minimum, above_maximum, invalid_choice };",
        "",
        "struct ContractSpec final {",
        "    std::string_view id;",
        "    std::string_view family;",
        "    ScalarKind scalar_kind;",
        "    bool nullable;",
        "    bool has_minimum;",
        "    bool has_maximum;",
        "    double minimum;",
        "    double maximum;",
        "    std::string_view choices;",
        "};",
        "",
        "struct ScalarValue final {",
        "    InputKind kind;",
        "    double number{};",
        "    std::string_view text{};",
        "};",
        "",
        f"inline constexpr std::array<ContractSpec, {len(rows)}> kContractSpecs{{{{",
    ]
    for row in rows:
        choices = "|".join(row["choices"])
        lines.append(
            "    {"
            f"{cpp_string(row['id'])}, {cpp_string(row['family'])}, "
            f"ScalarKind::{row['scalar_kind']}, "
            f"{str(row['nullable']).lower()}, "
            f"{str(row['minimum'] is not None).lower()}, "
            f"{str(row['maximum'] is not None).lower()}, "
            f"{cpp_number(row['minimum'])}, {cpp_number(row['maximum'])}, "
            f"{cpp_string(choices)}"
            "},"
        )
    lines.extend(
        [
            "}};",
            "",
            "struct AliasSpec final { std::string_view alias; std::string_view canonical; };",
            f"inline constexpr std::array<AliasSpec, {len(aliases)}> kAliases{{{{",
        ]
    )
    for alias, canonical in aliases.items():
        lines.append(f"    {{{cpp_string(alias)}, {cpp_string(canonical)}}},")
    lines.extend(
        [
            "}};",
            "",
            "[[nodiscard]] inline const ContractSpec* find_contract(std::string_view id) noexcept {",
            "    for (const auto& item : kContractSpecs) {",
            "        if (item.id == id) { return &item; }",
            "    }",
            "    for (const auto& alias : kAliases) {",
            "        if (alias.alias == id) { return find_contract(alias.canonical); }",
            "    }",
            "    return nullptr;",
            "}",
            "",
            "[[nodiscard]] inline bool choice_contains(std::string_view choices, std::string_view value) noexcept {",
            "    std::size_t start = 0;",
            "    while (start <= choices.size()) {",
            "        const auto end = choices.find('|', start);",
            "        const auto length = end == std::string_view::npos ? choices.size() - start : end - start;",
            "        if (choices.substr(start, length) == value) { return true; }",
            "        if (end == std::string_view::npos) { break; }",
            "        start = end + 1;",
            "    }",
            "    return false;",
            "}",
            "",
            "[[nodiscard]] inline ValidationCode validate_scalar(std::string_view id, const ScalarValue& value) noexcept {",
            "    const auto* spec = find_contract(id);",
            "    if (spec == nullptr) { return ValidationCode::unknown_contract; }",
            "    if (value.kind == InputKind::null_value) {",
            "        return spec->nullable || spec->scalar_kind == ScalarKind::any",
            "            ? ValidationCode::ok : ValidationCode::type_mismatch;",
            "    }",
            "    bool type_matches = false;",
            "    switch (spec->scalar_kind) {",
            "        case ScalarKind::any: type_matches = true; break;",
            "        case ScalarKind::boolean: type_matches = value.kind == InputKind::boolean; break;",
            "        case ScalarKind::integer: type_matches = value.kind == InputKind::integer; break;",
            "        case ScalarKind::number: type_matches = value.kind == InputKind::integer || value.kind == InputKind::number; break;",
            "        case ScalarKind::string: type_matches = value.kind == InputKind::string; break;",
            "        case ScalarKind::choice: type_matches = value.kind == InputKind::string; break;",
            "        case ScalarKind::id_set: type_matches = value.kind == InputKind::id_set; break;",
            "    }",
            "    if (!type_matches) { return ValidationCode::type_mismatch; }",
            "    if ((value.kind == InputKind::integer || value.kind == InputKind::number) && !std::isfinite(value.number)) {",
            "        return ValidationCode::nonfinite;",
            "    }",
            "    if (spec->has_minimum && value.number < spec->minimum) { return ValidationCode::below_minimum; }",
            "    if (spec->has_maximum && value.number > spec->maximum) { return ValidationCode::above_maximum; }",
            "    if (spec->scalar_kind == ScalarKind::choice && !choice_contains(spec->choices, value.text)) {",
            "        return ValidationCode::invalid_choice;",
            "    }",
            "    return ValidationCode::ok;",
            "}",
            "",
            "}  // namespace macro_sim::generated",
            "",
            "#endif",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def render_python(contracts: dict[str, Any]) -> bytes:
    rows = tuple(contracts["rows"])
    aliases = contracts["aliases"]
    prelude = f'''"""Checked Python view of the generated M1 contract skeletons."""

from __future__ import annotations

import math

CANONICAL_ENCODING_VERSION = 1
M0_CONTRACT_SHA256 = {contracts["m0_contract_sha256"]!r}
CONTRACTS = {pprint.pformat(rows, sort_dicts=True, width=100)}
ALIASES = {pprint.pformat(aliases, sort_dicts=True, width=100)}
BY_ID = {{item["id"]: item for item in CONTRACTS}}


def _resolve(contract_id: str):
    return BY_ID.get(ALIASES.get(contract_id, contract_id))


def validate_scalar(contract_id: str, value):
    spec = _resolve(contract_id)
    if spec is None:
        return False, "unknown_contract"
    if value is None:
        return (True, "ok") if spec["nullable"] or spec["scalar_kind"] == "any" else (False, "type_mismatch")
    kind = spec["scalar_kind"]
    if kind == "boolean":
        matches = type(value) is bool
    elif kind == "integer":
        matches = type(value) is int
    elif kind == "number":
        matches = type(value) in (int, float)
    elif kind in ("string", "choice"):
        matches = type(value) is str
    elif kind == "id_set":
        matches = isinstance(value, (set, frozenset, list, tuple)) and all(type(item) is int for item in value)
    else:
        matches = True
    if not matches:
        return False, "type_mismatch"
    if type(value) in (int, float) and not math.isfinite(value):
        return False, "nonfinite"
    if spec["minimum"] is not None and type(value) in (int, float) and value < spec["minimum"]:
        return False, "below_minimum"
    if spec["maximum"] is not None and type(value) in (int, float) and value > spec["maximum"]:
        return False, "above_maximum"
    if kind == "choice" and value not in spec["choices"]:
        return False, "invalid_choice"
    return True, "ok"
'''
    return prelude.encode("utf-8")


def render_cpp_cases(corpus: dict[str, Any]) -> bytes:
    lines = [
        "#ifndef MACRO_SIM_GENERATED_INVALID_CASES_HPP",
        "#define MACRO_SIM_GENERATED_INVALID_CASES_HPP",
        "",
        "#include <array>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        '#include "macro_sim/generated/contracts.hpp"',
        "",
        "namespace macro_sim::generated {",
        "",
        "enum class InvalidInputKind : std::uint8_t { null_value, boolean, integer, number, string, nonfinite };",
        "struct InvalidContractCase final {",
        "    std::string_view id;",
        "    std::string_view contract_id;",
        "    InvalidInputKind input_kind;",
        "    double number;",
        "    std::string_view text;",
        "    ValidationCode expected;",
        "};",
        "",
        f"inline constexpr std::array<InvalidContractCase, {len(corpus['cases'])}> kInvalidContractCases{{{{",
    ]
    for case in corpus["cases"]:
        input_value = case["input"]
        kind = input_value["kind"]
        number = input_value["value"] if kind in {"integer", "number"} else 0
        text = input_value["value"] if kind == "string" else ""
        lines.append(
            "    {"
            f"{cpp_string(case['id'])}, {cpp_string(case['contract_id'])}, "
            f"InvalidInputKind::{kind if kind != 'null' else 'null_value'}, "
            f"{cpp_number(number)}, {cpp_string(str(text))}, "
            f"ValidationCode::{case['expected_code']}"
            "},"
        )
    lines.extend(
        [
            "}};",
            "",
            "}  // namespace macro_sim::generated",
            "",
            "#endif",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def aggregate_hash(mapping: dict[str, str]) -> str:
    payload = "".join(f"{path}\0{value}\n" for path, value in sorted(mapping.items()))
    return sha256(payload.encode("utf-8")).hexdigest()


def write_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if path.exists() and path.read_bytes() == content:
        print(f"ok      {path.relative_to(ROOT)}")
        return
    if check:
        state = "missing" if not path.exists() else "stale"
        raise RuntimeError(f"{state} generated artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(f"written {path.relative_to(ROOT)}")


def build_lock(paths: list[Path], contracts: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        path.relative_to(ROOT).as_posix(): digest(path)
        for path in paths
        if path.is_file()
    }
    return {
        "schema_version": "m1-hash-lock-v1",
        "m0_contract_sha256": contracts["m0_contract_sha256"],
        "artifacts": [
            {"path": path, "sha256": value}
            for path, value in sorted(mapping.items())
        ],
        "aggregate_sha256": aggregate_hash(mapping),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        contracts = build_contracts()
        corpus = build_invalid_cases(contracts)
        outputs = {
            JSON_OUTPUT: canonical_bytes(contracts),
            PYTHON_OUTPUT: render_python(contracts),
            CPP_OUTPUT: render_cpp(contracts),
            CASE_OUTPUT: canonical_bytes(corpus),
            CPP_CASE_OUTPUT: render_cpp_cases(corpus),
        }
        for path, content in outputs.items():
            write_or_check(path, content, check=args.check)
        locked_paths = [*outputs, *OPTIONAL_LOCKED_ARTIFACTS]
        lock = build_lock(locked_paths, contracts)
        write_or_check(LOCK_OUTPUT, canonical_bytes(lock), check=args.check)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"M1 contract generation error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
