"""Deterministic R1 Policy validation-parity acceptance report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from macro_sim.core.policy_control_specs import CONTROL_SPECS
from macro_sim.core.policy_registry import NullableRange, Range, REGISTRY


R1_SCHEMA_VERSION = "policy-remediation-r1-v1"
R1_BASE_REVISION = "585b1e87043eb0564562e19b28cb520576e4a516"
R1_INVALIDATED_AUDIT_STAGES = tuple(f"P{stage}" for stage in range(9))

R1_DOMAINS: dict[str, dict[str, Any]] = {
    "margin_ltv": {
        "minimum": 0.0,
        "maximum": 1.0,
        "nullable": False,
        "control_scale": 0.025,
        "max_step": 0.10,
    },
    "margin_max": {
        "minimum": 0.0,
        "maximum": 10.0,
        "nullable": False,
        "control_scale": 0.25,
        "max_step": 1.0,
    },
    "import_quota": {
        "minimum": 0.0,
        "maximum": 1.0,
        "nullable": True,
        "control_scale": 0.05,
        "max_step": 0.20,
    },
    "immigration_cap": {
        "minimum": 0.0,
        "maximum": 1.0,
        "nullable": True,
        "control_scale": 0.025,
        "max_step": 0.10,
    },
}

R1_SOURCE_PATHS = (
    "macro_sim/config/model.py",
    "macro_sim/core/policy_control_specs.py",
    "macro_sim/core/policy_registry.py",
    "macro_sim/world/world.py",
    "native/src/simulation/m6.cpp",
    "native/src/simulation/m9.cpp",
    "native/tests/m6_simulation_tests.cpp",
    "native/tests/m9_world_tests.cpp",
    "native/tests/m11_policy_contract_tests.cpp",
    "schemas/m0/inventory/policy.json",
    "schemas/m1/generated/contracts.json",
    "schemas/m11/control_contract.json",
)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_rows(path: Path, key: str) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(row[key]): row for row in payload["rows"]}


def build_r1_acceptance(repo_root: Path) -> dict[str, Any]:
    """Build an R1 report from canonical and generated contract sources."""

    errors: list[str] = []
    checks: dict[str, dict[str, dict[str, Any]]] = {
        "registry": {},
        "controller": {},
        "m0_inventory": {},
        "m1_contract": {},
        "m11_contract": {},
    }
    m0 = _load_rows(repo_root / "schemas/m0/inventory/policy.json", "lever_name")
    m1 = _load_rows(repo_root / "schemas/m1/generated/contracts.json", "id")
    m11 = _load_rows(repo_root / "schemas/m11/control_contract.json", "name")

    for lever, expected in R1_DOMAINS.items():
        validation = REGISTRY[lever].validation
        registry_actual = {
            "minimum": validation.lo,
            "maximum": validation.hi,
            "nullable": isinstance(validation, NullableRange),
        }
        checks["registry"][lever] = registry_actual
        control = CONTROL_SPECS[lever]
        controller_actual = {
            "control_scale": control.control_scale,
            "max_step": control.max_step,
        }
        checks["controller"][lever] = controller_actual

        m0_validation = m0[lever]["validation"]
        m0_actual = {
            "minimum": m0_validation["minimum"],
            "maximum": m0_validation["maximum"],
            "nullable": m0_validation["value_kind"] == "nullable_number",
            "control_scale": m0[lever]["control_scale"],
            "max_step": m0_validation["max_step"],
        }
        checks["m0_inventory"][lever] = m0_actual
        m1_row = m1[f"policy.{lever}"]
        m1_actual = {
            "minimum": m1_row["minimum"],
            "maximum": m1_row["maximum"],
            "nullable": m1_row["nullable"],
        }
        checks["m1_contract"][lever] = m1_actual
        m11_row = m11[lever]
        m11_actual = {
            "minimum": m11_row["minimum"],
            "maximum": m11_row["maximum"],
            "nullable": m11_row["kind"] == "nullable_number",
            "control_scale": m11_row["control_scale"],
            "max_step": m11_row["max_step"],
        }
        checks["m11_contract"][lever] = m11_actual

        for layer, actual in (
            ("registry", registry_actual),
            ("controller", controller_actual),
            ("m0_inventory", m0_actual),
            ("m1_contract", m1_actual),
            ("m11_contract", m11_actual),
        ):
            expected_subset = {key: expected[key] for key in actual}
            if actual != expected_subset:
                errors.append(
                    f"{lever}: {layer} {actual!r} != {expected_subset!r}"
                )

        if not isinstance(validation, Range):
            errors.append(f"{lever}: Registry validation is not a numeric range")

    evidence = {
        "base_revision": R1_BASE_REVISION,
        "phase": "R1",
        "domains": R1_DOMAINS,
        "contract_checks": checks,
        "invalidated_audit_stages": list(R1_INVALIDATED_AUDIT_STAGES),
        "source_sha256": {
            path: _sha256(repo_root / path) for path in R1_SOURCE_PATHS
        },
        "verification_commands": [
            "uv run pytest -n 8 tests/test_policy_remediation_r1.py",
            "ctest --test-dir build/native/r1-release -j 8 --output-on-failure",
        ],
    }
    return {
        "schema_version": R1_SCHEMA_VERSION,
        "status": "accepted" if not errors else "rejected",
        **evidence,
        "errors": errors,
        "hashes": {"r1_acceptance": canonical_hash(evidence)},
    }


def validate_r1_acceptance(payload: dict[str, Any], repo_root: Path) -> list[str]:
    current = build_r1_acceptance(repo_root)
    errors = list(current["errors"])
    if payload != current:
        errors.append("committed R1 acceptance report does not reproduce")
    return errors


__all__ = [
    "R1_DOMAINS",
    "build_r1_acceptance",
    "canonical_hash",
    "validate_r1_acceptance",
]
