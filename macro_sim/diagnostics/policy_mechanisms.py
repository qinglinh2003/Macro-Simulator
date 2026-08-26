"""Deterministic R3 direct-route and mechanism acceptance report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from macro_sim.core.native_policy_routes import NATIVE_ROUTE_DEFECTS
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_catalog import LEVER_PROXIMAL_METRICS
from macro_sim.diagnostics.policy_contracts import build_p0_payload
from macro_sim.diagnostics.policy_routing import verify_p1_static
from macro_sim.diagnostics.policy_validation_parity import canonical_hash


R3_SCHEMA_VERSION = "policy-remediation-r3-v1"
R3_BASE_REVISION = "78a384f701d751f017054be9eb7314d14e6f18a1"
R3_PREVIOUS_CONTRACT_ROOT = (
    "1537900dd4a934db233f471f62fd4b81f2905a8f66d5b27f9468b7cefa121532"
)
R3_INVALIDATED_AUDIT_STAGES = tuple(f"P{stage}" for stage in range(9))

R3_CONTRACTS: dict[str, dict[str, Any]] = {
    "fiscal_uses_national_accounts_gdp": {
        "read_point": "native/src/simulation/m4.cpp::fiscal_output_reference",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m4.fiscal_output_reference_applied",
            "metric.economy.na.nominal_gdp",
        ),
    },
    "bank_capital_constraint": {
        "read_point": "native/src/simulation/m5.cpp::bank_capacity",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m5.bank_capital_constraint_applied",
            "metric.source.m5.bank_gross_capital_headroom",
            "metric.source.m5.bank_gross_capital_credit_shortfall",
            "metric.source.m5.new_credit",
        ),
    },
    "mortgage_risk_weight": {
        "read_point": (
            "native/src/simulation/m8.cpp::m5_bank_rwa_principal_capacity"
        ),
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.mortgage_risk_weight_applied",
            "metric.source.m8.housing.mortgage_rwa_principal_capacity",
            "metric.source.m8.housing.mortgage_rwa_rejections",
        ),
    },
    "mortgage_min_capital_ratio": {
        "read_point": (
            "native/src/simulation/m8.cpp::m5_bank_rwa_principal_capacity"
        ),
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.mortgage_minimum_capital_ratio_applied",
            "metric.source.m8.housing.mortgage_rwa_principal_capacity",
            "metric.source.m8.housing.mortgage_rwa_rejections",
        ),
    },
    "mortgage_arrears_floor": {
        "read_point": "native/src/simulation/m8.cpp::synchronize_mortgages",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.mortgage_arrears_floor_applied",
            "metric.source.m8.housing.mortgage_foreclosure_candidates",
            (
                "metric.source.m8.housing."
                "mortgage_foreclosures_prevented_by_liquidity"
            ),
            "metric.source.m8.housing.foreclosures",
        ),
    },
    "deficit_u_cap": {
        "read_point": "native/src/simulation/m4.cpp::run_government_procurement",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m4.fiscal_unemployment_multiplier_applied",
            "metric.source.m4.fiscal_deficit_target_applied",
            "metric.source.m4.government_procurement_budget",
            "metric.source.m4.government_deficit",
        ),
    },
}

R3_TEST_MARKERS = {
    "native/tests/m4_tick_tests.cpp": (
        "test_fiscal_output_basis_has_dose_and_withdrawal_contract",
        "test_deficit_unemployment_cap_has_dose_and_withdrawal_contract",
    ),
    "native/tests/m5_monetary_tests.cpp": (
        "test_bank_capital_constraint_has_dose_and_withdrawal_contract",
    ),
    "native/tests/m8_housing_market_tests.cpp": (
        "test_mortgage_capital_rules_have_dose_and_withdrawal_contract",
        "test_mortgage_arrears_floor_has_dose_and_withdrawal_contract",
    ),
}

R3_SOURCE_PATHS = (
    "macro_sim/core/native_policy_routes.py",
    "macro_sim/diagnostics/policy_catalog.py",
    "macro_sim/diagnostics/policy_mechanisms.py",
    "macro_sim/diagnostics/policy_routing.py",
    "native/include/macro_sim/reporting/m10_metric_sources.inc",
    "native/include/macro_sim/simulation/m4.hpp",
    "native/include/macro_sim/simulation/m4_checkpoint.hpp",
    "native/include/macro_sim/simulation/m5.hpp",
    "native/include/macro_sim/simulation/m5_checkpoint.hpp",
    "native/include/macro_sim/simulation/m8.hpp",
    "native/include/macro_sim/simulation/m8_checkpoint.hpp",
    "native/src/simulation/m4.cpp",
    "native/src/simulation/m4_checkpoint.cpp",
    "native/src/simulation/m5.cpp",
    "native/src/simulation/m5_checkpoint.cpp",
    "native/src/simulation/m8.cpp",
    "native/src/simulation/m8_checkpoint.cpp",
    "native/tests/m4_tick_tests.cpp",
    "native/tests/m5_monetary_tests.cpp",
    "native/tests/m8_housing_market_tests.cpp",
    "native/tests/m10_reporting_tests.cpp",
    "schemas/m10/maintained_metrics.json",
    "tools/m10/metric_contract.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint_version(path: Path, symbol: str) -> int | None:
    match = re.search(
        rf"{re.escape(symbol)}\s*=\s*(\d+)",
        path.read_text(encoding="utf-8"),
    )
    return int(match.group(1)) if match is not None else None


def build_r3_acceptance(repo_root: Path) -> dict[str, Any]:
    """Build acceptance evidence for the six R3 mechanism repairs."""

    errors = list(verify_p1_static())
    if NATIVE_ROUTE_DEFECTS:
        errors.append(f"native route defects remain: {sorted(NATIVE_ROUTE_DEFECTS)!r}")

    maintained_payload = json.loads(
        (repo_root / "schemas/m10/maintained_metrics.json").read_text(encoding="utf-8")
    )
    maintained = {row["id"] for row in maintained_payload["metrics"]}
    counts = maintained_payload["counts"]
    if counts.get("native_stage_sources") != 338 or counts.get("total") != 562:
        errors.append(f"unexpected maintained metric counts {counts!r}")

    contract_checks: dict[str, dict[str, Any]] = {}
    for lever, expected in R3_CONTRACTS.items():
        registry = REGISTRY[lever]
        actual = {
            "read_point": registry.read_point,
            "semantics": registry.semantics,
            "handler_id": registry.handler_id,
            "metrics": tuple(LEVER_PROXIMAL_METRICS[lever]),
        }
        missing_metrics = sorted(set(expected["metrics"]) - maintained)
        contract_checks[lever] = {
            **actual,
            "all_metrics_maintained": not missing_metrics,
        }
        if actual != expected:
            errors.append(f"{lever}: route or proximal contract disagrees with R3")
        if missing_metrics:
            errors.append(f"{lever}: unmaintained metrics {missing_metrics!r}")

    test_markers: dict[str, list[str]] = {}
    for relative, markers in R3_TEST_MARKERS.items():
        source = (repo_root / relative).read_text(encoding="utf-8")
        found = [marker for marker in markers if marker in source]
        test_markers[relative] = found
        missing = sorted(set(markers) - set(found))
        if missing:
            errors.append(f"{relative}: missing R3 test markers {missing!r}")

    checkpoint_versions = {
        "m4": _checkpoint_version(
            repo_root / "native/include/macro_sim/simulation/m4_checkpoint.hpp",
            "kM4CheckpointSchemaVersion",
        ),
        "m5": _checkpoint_version(
            repo_root / "native/include/macro_sim/simulation/m5_checkpoint.hpp",
            "kM5CheckpointSchemaVersion",
        ),
        "m8": _checkpoint_version(
            repo_root / "native/include/macro_sim/simulation/m8_checkpoint.hpp",
            "kM8CheckpointSchemaVersion",
        ),
    }
    if checkpoint_versions != {"m4": 11, "m5": 4, "m8": 4}:
        errors.append(f"unexpected checkpoint schema versions {checkpoint_versions!r}")

    current_p0_root = build_p0_payload()["hashes"]["p0_root"]
    invalidation = {
        "previous_contract_root": R3_PREVIOUS_CONTRACT_ROOT,
        "current_contract_root": current_p0_root,
        "historical_evidence_invalidated": current_p0_root != R3_PREVIOUS_CONTRACT_ROOT,
    }
    if not invalidation["historical_evidence_invalidated"]:
        errors.append("R3 route changes did not invalidate the previous contract root")

    evidence = {
        "base_revision": R3_BASE_REVISION,
        "phase": "R3",
        "contracts": R3_CONTRACTS,
        "contract_checks": contract_checks,
        "checkpoint_schema_versions": checkpoint_versions,
        "native_behavior_test_markers": test_markers,
        "native_route_defects": sorted(NATIVE_ROUTE_DEFECTS),
        "maintained_metric_counts": counts,
        "invalidated_audit_stages": list(R3_INVALIDATED_AUDIT_STAGES),
        "invalidation": invalidation,
        "source_sha256": {path: _sha256(repo_root / path) for path in R3_SOURCE_PATHS},
        "verification_commands": [
            "uv run pytest -n 8 tests/test_policy_remediation_r3.py",
            "uv run python tools/m10/metric_contract.py --check",
            "uv run python tools/m11/generate_control_contract.py --check",
            "cmake --build build/native/m11-release --parallel 8",
            "ctest --test-dir build/native/m11-release --parallel 8 --output-on-failure",
        ],
    }
    return {
        "schema_version": R3_SCHEMA_VERSION,
        "status": "accepted" if not errors else "rejected",
        **evidence,
        "errors": errors,
        "hashes": {"r3_acceptance": canonical_hash(evidence)},
    }


def validate_r3_acceptance(payload: dict[str, Any], repo_root: Path) -> list[str]:
    current = build_r3_acceptance(repo_root)
    errors = list(current["errors"])
    if canonical_hash(payload) != canonical_hash(current):
        errors.append("committed R3 acceptance report does not reproduce")
    return errors


__all__ = ["R3_CONTRACTS", "build_r3_acceptance", "validate_r3_acceptance"]
