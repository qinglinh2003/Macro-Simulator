"""Deterministic R2 Policy contract-observability acceptance report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_catalog import LEVER_PROXIMAL_METRICS
from macro_sim.diagnostics.policy_contracts import build_p0_payload
from macro_sim.diagnostics.policy_validation_parity import canonical_hash


R2_SCHEMA_VERSION = "policy-remediation-r2-v1"
R2_BASE_REVISION = "6848cd67b5bb3ef9b58b7596e76d1cc572bcd905"
R2_HISTORICAL_P0_ROOT = (
    "6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6"
)
R2_INVALIDATED_AUDIT_STAGES = tuple(f"P{stage}" for stage in range(9))

R2_CONTRACTS: dict[str, dict[str, Any]] = {
    "bond_coupon": {
        "read_point": "native/src/simulation/m6.cpp::run_bond_issuance",
        "semantics": "new-contracts-only",
        "handler_id": "bond_coupon_cohort",
        "metrics": (
            "metric.source.m6.bond_issued_coupon_rate",
            "metric.source.m6.bond_weighted_coupon_rate",
        ),
    },
    "bond_maturity": {
        "read_point": "native/src/simulation/m6.cpp::run_bond_issuance",
        "semantics": "new-contracts-only",
        "handler_id": "bond_tenor_at_issuance",
        "metrics": (
            "metric.source.m6.bond_issued_maturity_days",
            "metric.source.m6.bond_weighted_remaining_maturity_days",
        ),
    },
    "omo": {
        "read_point": "native/src/simulation/m5.cpp::run_omo",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m6.bond_duration_adjusted_omo_flow",
            "metric.source.m5.omo_flow",
            "metric.source.m5.total_reserves",
        ),
    },
    "mortgage_underwriting": {
        "read_point": "native/src/simulation/m8.cpp::buy_listing",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.mortgage_underwriting_applications",
            "metric.source.m8.housing.mortgage_dsti_rejections",
        ),
    },
    "mortgage_dsti_cap": {
        "read_point": "native/src/simulation/m8.cpp::buy_listing",
        "semantics": "new-contracts-only",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.mortgage_dsti_cap_applied",
            "metric.source.m8.housing.mortgage_cohort_weighted_dsti_cap",
            "metric.source.m8.housing.mortgage_dsti_rejections",
        ),
    },
    "mortgage_stress_rate_addon": {
        "read_point": "native/src/simulation/m8.cpp::buy_listing",
        "semantics": "new-contracts-only",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.mortgage_stress_rate_addon_applied",
            "metric.source.m8.housing.mortgage_cohort_weighted_stress_rate_addon",
            "metric.source.m8.housing.mortgage_dsti_rejections",
        ),
    },
    "housing_in_wealth_tax": {
        "read_point": "native/src/simulation/m8.cpp::prepare_household_net_wealth",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.housing_wealth_tax_base_included",
            "metric.source.m8.housing.housing_wealth_tax_paid",
        ),
    },
    "firm_credit_min_dscr": {
        "read_point": "native/src/simulation/m5.cpp::extend_firm_credit",
        "semantics": "new-contracts-only",
        "handler_id": "underwriting_read_at_origination",
        "metrics": (
            "metric.source.m5.firm_credit_min_dscr_applied",
            "metric.source.m5.firm_credit_applications",
            "metric.source.m5.firm_dscr_credit_shortfall",
            "metric.source.m5.firm_credit_originated",
        ),
    },
    "regulatory_firm_capital_haircut": {
        "read_point": "native/src/simulation/m6.cpp::build_firm_statements",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m6.firm_capital_haircut_applied",
            "metric.source.m6.firm_eligible_collateral_value",
        ),
    },
    "regulatory_firm_inventory_haircut": {
        "read_point": "native/src/simulation/m6.cpp::build_firm_statements",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m6.firm_inventory_haircut_applied",
            "metric.source.m6.firm_eligible_collateral_value",
        ),
    },
    "land_fee_share": {
        "read_point": "native/src/simulation/m8.cpp::complete_construction",
        "semantics": "new-contracts-only",
        "handler_id": "land_fee_at_construction_completion",
        "metrics": (
            "metric.source.m8.housing.land_fee_share_applied",
            "metric.source.m8.housing.land_fee_assessments",
            "metric.source.m8.housing.land_fee_paid",
        ),
    },
    "land_fee_stock_elasticity": {
        "read_point": "native/src/simulation/m8.cpp::complete_construction",
        "semantics": "new-contracts-only",
        "handler_id": "land_fee_at_construction_completion",
        "metrics": (
            "metric.source.m8.housing.land_fee_stock_elasticity_applied",
            "metric.source.m8.housing.land_fee_stock_pressure_applied",
            "metric.source.m8.housing.land_fee_assessments",
        ),
    },
}

R2_TEST_MARKERS = {
    "native/tests/m5_monetary_tests.cpp": (
        "test_firm_credit_reports_existing_stock_and_current_dscr_gate",
    ),
    "native/tests/m6_simulation_tests.cpp": (
        "test_bond_cohorts_and_duration_adjusted_omo_are_observable",
        "test_firm_collateral_haircuts_report_the_applied_borrowing_base",
    ),
    "native/tests/m8_housing_market_tests.cpp": (
        "test_mortgage_origination_is_canonical_and_collateralized",
        "test_housing_enters_the_integrated_net_wealth_tax_base_once",
    ),
    "native/tests/m8_housing_genesis_tests.cpp": (
        "test_builders_create_permitted_real_stock",
    ),
}

R2_SOURCE_PATHS = (
    "macro_sim/core/native_policy_routes.py",
    "macro_sim/core/policy_registry.py",
    "macro_sim/diagnostics/policy_catalog.py",
    "macro_sim/diagnostics/policy_observability.py",
    "native/include/macro_sim/reporting/m10_metric_sources.inc",
    "native/include/macro_sim/simulation/m5.hpp",
    "native/include/macro_sim/simulation/m5_checkpoint.hpp",
    "native/include/macro_sim/simulation/m6.hpp",
    "native/include/macro_sim/simulation/m6_checkpoint.hpp",
    "native/include/macro_sim/simulation/m8.hpp",
    "native/include/macro_sim/simulation/m8_checkpoint.hpp",
    "native/src/simulation/m5.cpp",
    "native/src/simulation/m5_checkpoint.cpp",
    "native/src/simulation/m6.cpp",
    "native/src/simulation/m6_checkpoint.cpp",
    "native/src/simulation/m8.cpp",
    "native/src/simulation/m8_checkpoint.cpp",
    "native/tests/m5_monetary_tests.cpp",
    "native/tests/m6_simulation_tests.cpp",
    "native/tests/m8_housing_genesis_tests.cpp",
    "native/tests/m8_housing_market_tests.cpp",
    "schemas/m10/maintained_metrics.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint_version(path: Path, symbol: str) -> int | None:
    match = re.search(
        rf"{re.escape(symbol)}\s*=\s*(\d+)",
        path.read_text(encoding="utf-8"),
    )
    return int(match.group(1)) if match is not None else None


def build_r2_acceptance(repo_root: Path) -> dict[str, Any]:
    """Build the R2 report from native reporting and Policy contracts."""

    errors: list[str] = []
    maintained_payload = json.loads(
        (repo_root / "schemas/m10/maintained_metrics.json").read_text(encoding="utf-8")
    )
    maintained = {row["id"] for row in maintained_payload["metrics"]}
    contract_checks: dict[str, dict[str, Any]] = {}

    for lever, expected in R2_CONTRACTS.items():
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
            errors.append(f"{lever}: observable contract does not match R2 ruling")
        if missing_metrics:
            errors.append(f"{lever}: unmaintained metrics {missing_metrics!r}")

    test_markers: dict[str, list[str]] = {}
    for relative, markers in R2_TEST_MARKERS.items():
        source = (repo_root / relative).read_text(encoding="utf-8")
        found = [marker for marker in markers if marker in source]
        test_markers[relative] = found
        missing = sorted(set(markers) - set(found))
        if missing:
            errors.append(f"{relative}: missing R2 test markers {missing!r}")

    checkpoint_versions = {
        "m5": _checkpoint_version(
            repo_root / "native/include/macro_sim/simulation/m5_checkpoint.hpp",
            "kM5CheckpointSchemaVersion",
        ),
        "m6": _checkpoint_version(
            repo_root / "native/include/macro_sim/simulation/m6_checkpoint.hpp",
            "kM6CheckpointSchemaVersion",
        ),
        "m8": _checkpoint_version(
            repo_root / "native/include/macro_sim/simulation/m8_checkpoint.hpp",
            "kM8CheckpointSchemaVersion",
        ),
    }
    if checkpoint_versions != {"m5": 3, "m6": 3, "m8": 3}:
        errors.append(f"unexpected checkpoint schema versions {checkpoint_versions!r}")

    current_p0_root = build_p0_payload()["hashes"]["p0_root"]
    invalidation = {
        "historical_p0_root": R2_HISTORICAL_P0_ROOT,
        "current_contract_root": current_p0_root,
        "historical_evidence_invalidated": current_p0_root != R2_HISTORICAL_P0_ROOT,
    }
    if not invalidation["historical_evidence_invalidated"]:
        errors.append("R2 contract changes did not invalidate the historical P0 root")

    evidence = {
        "base_revision": R2_BASE_REVISION,
        "phase": "R2",
        "contracts": R2_CONTRACTS,
        "contract_checks": contract_checks,
        "checkpoint_schema_versions": checkpoint_versions,
        "native_behavior_test_markers": test_markers,
        "invalidated_audit_stages": list(R2_INVALIDATED_AUDIT_STAGES),
        "invalidation": invalidation,
        "source_sha256": {
            path: _sha256(repo_root / path) for path in R2_SOURCE_PATHS
        },
        "verification_commands": [
            "uv run pytest -n 8 tests/test_policy_remediation_r2.py",
            "uv run python tools/m10/metric_contract.py --check",
            "uv run python tools/m11/generate_control_contract.py --check",
            "cmake --build build/native/m11-release --parallel 8",
            "ctest --test-dir build/native/m11-release --parallel 8 --output-on-failure",
        ],
    }
    return {
        "schema_version": R2_SCHEMA_VERSION,
        "status": "accepted" if not errors else "rejected",
        **evidence,
        "errors": errors,
        "hashes": {"r2_acceptance": canonical_hash(evidence)},
    }


def validate_r2_acceptance(payload: dict[str, Any], repo_root: Path) -> list[str]:
    current = build_r2_acceptance(repo_root)
    errors = list(current["errors"])
    if canonical_hash(payload) != canonical_hash(current):
        errors.append("committed R2 acceptance report does not reproduce")
    return errors


__all__ = [
    "R2_CONTRACTS",
    "build_r2_acceptance",
    "validate_r2_acceptance",
]
