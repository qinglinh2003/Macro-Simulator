"""Deterministic R4 opportunity and state-machine acceptance report."""

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


R4_SCHEMA_VERSION = "policy-remediation-r4-v1"
R4_BASE_REVISION = "160dcbcfe2380679c4ab5ecab36a3f27e3a26e38"
R4_PREVIOUS_CONTRACT_ROOT = (
    "9f680833f206ddf7ebc1bb2594824f21a0bd6c1d1bace207e798c35a81bc46cf"
)
R4_INVALIDATED_AUDIT_STAGES = tuple(f"P{stage}" for stage in range(9))

R4_CONTRACTS: dict[str, dict[str, Any]] = {
    "lolr": {
        "read_point": "native/src/simulation/m5.cpp::close_end_of_day_liquidity",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m5.lolr_liquidity_shortfall",
            "metric.source.m5.lolr_advances",
            "metric.source.m5.bank_failures",
        ),
    },
    "bank_resolution_fund": {
        "read_point": "native/src/simulation/m5.cpp::resolve_bank",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m5.resolution_funding_need",
            "metric.source.m5.resolution_cost",
            "metric.source.m5.resolution_mutualized_cost",
            "metric.source.m5.bank_failures",
        ),
    },
    "margin_max": {
        "read_point": "native/src/simulation/m6.cpp::generate_firm_equity_orders",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m6.margin_max_applied",
            "metric.source.m6.margin_target_equity",
            "metric.source.m6.margin_max_binding_shortfall",
            "metric.source.m6.margin_originated",
        ),
    },
    "housing_permits": {
        "read_point": "native/src/simulation/m8.cpp::complete_construction",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m8.housing.housing_permit_cap_applied",
            "metric.source.m8.housing.housing_units_ready_for_permits",
            "metric.source.m8.housing.housing_units_blocked_by_permits",
            "metric.source.m8.housing.permits_used",
            "metric.source.m8.housing.dwellings_completed",
        ),
    },
    "household_bankruptcy": {
        "read_point": "native/src/simulation/m6.cpp::service_margin",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m6.household_bankruptcy_candidates",
            "metric.source.m6.household_bankruptcies_blocked_by_policy",
            "metric.source.m6.household_bankruptcies",
            "metric.source.m6.margin_writeoffs",
        ),
    },
    "bank_migrate_on_failure": {
        "read_point": "native/src/simulation/m5.cpp::resolve_bank",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m5.failed_account_migration_candidates",
            "metric.source.m5.failed_accounts_migrated",
            "metric.source.m5.failed_loan_migration_candidates",
            "metric.source.m5.failed_loans_migrated",
        ),
    },
    "unified_bank_rwa": {
        "read_point": "native/src/simulation/m5.cpp::bank_rwa_capacity",
        "semantics": "immediate",
        "handler_id": None,
        "metrics": (
            "metric.source.m5.unified_bank_rwa_applied",
            "metric.source.m5.bank_rwa_headroom",
            "metric.source.m5.bank_rwa_credit_shortfall",
            "metric.source.m8.housing.mortgage_bank_risk_weighted_assets",
            "metric.source.m8.housing.mortgage_rwa_rejections",
        ),
    },
}

R4_TEST_MARKERS = {
    "native/tests/m5_monetary_tests.cpp": (
        "test_bank_resolution_fund_has_activation_nonactivation_and_withdrawal_contract",
        "test_bank_migration_has_activation_nonactivation_and_withdrawal_contract",
        "test_lolr_has_activation_nonactivation_and_withdrawal_contract",
        "test_unified_bank_rwa_has_activation_nonactivation_and_withdrawal_contract",
        "test_unified_bank_rwa_weights_one_common_asset_envelope",
    ),
    "native/tests/m6_simulation_tests.cpp": (
        "test_margin_max_has_activation_nonactivation_and_withdrawal_contract",
        "test_household_bankruptcy_has_activation_nonactivation_and_withdrawal_contract",
    ),
    "native/tests/m8_housing_genesis_tests.cpp": (
        "test_housing_permits_have_activation_nonactivation_and_withdrawal_contract",
    ),
}

R4_SOURCE_PATHS = (
    "macro_sim/core/native_policy_routes.py",
    "macro_sim/diagnostics/policy_catalog.py",
    "macro_sim/diagnostics/policy_state_machines.py",
    "macro_sim/diagnostics/policy_routing.py",
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


def build_r4_acceptance(repo_root: Path) -> dict[str, Any]:
    """Build acceptance evidence for all seven R4 state-machine repairs."""

    errors = list(verify_p1_static())
    if NATIVE_ROUTE_DEFECTS:
        errors.append(f"native route defects remain: {sorted(NATIVE_ROUTE_DEFECTS)!r}")

    maintained_payload = json.loads(
        (repo_root / "schemas/m10/maintained_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    maintained = {row["id"] for row in maintained_payload["metrics"]}
    counts = maintained_payload["counts"]
    if counts.get("native_stage_sources") != 358 or counts.get("total") != 582:
        errors.append(f"unexpected maintained metric counts {counts!r}")

    contract_checks: dict[str, dict[str, Any]] = {}
    for lever, expected in R4_CONTRACTS.items():
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
            errors.append(f"{lever}: route or proximal contract disagrees with R4")
        if missing_metrics:
            errors.append(f"{lever}: unmaintained metrics {missing_metrics!r}")

    test_markers: dict[str, list[str]] = {}
    for relative, markers in R4_TEST_MARKERS.items():
        source = (repo_root / relative).read_text(encoding="utf-8")
        found = [marker for marker in markers if marker in source]
        test_markers[relative] = found
        missing = sorted(set(markers) - set(found))
        if missing:
            errors.append(f"{relative}: missing R4 test markers {missing!r}")

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
    if checkpoint_versions != {"m5": 5, "m6": 4, "m8": 5}:
        errors.append(f"unexpected checkpoint schema versions {checkpoint_versions!r}")

    current_p0_root = build_p0_payload()["hashes"]["p0_root"]
    invalidation = {
        "previous_contract_root": R4_PREVIOUS_CONTRACT_ROOT,
        "current_contract_root": current_p0_root,
        "historical_evidence_invalidated": current_p0_root
        != R4_PREVIOUS_CONTRACT_ROOT,
    }
    if not invalidation["historical_evidence_invalidated"]:
        errors.append("R4 route changes did not invalidate the previous contract root")

    evidence = {
        "base_revision": R4_BASE_REVISION,
        "phase": "R4",
        "contracts": R4_CONTRACTS,
        "contract_checks": contract_checks,
        "checkpoint_schema_versions": checkpoint_versions,
        "native_behavior_test_markers": test_markers,
        "native_route_defects": sorted(NATIVE_ROUTE_DEFECTS),
        "maintained_metric_counts": counts,
        "invalidated_audit_stages": list(R4_INVALIDATED_AUDIT_STAGES),
        "invalidation": invalidation,
        "source_sha256": {path: _sha256(repo_root / path) for path in R4_SOURCE_PATHS},
        "verification_commands": [
            "uv run pytest -n 8 tests/test_policy_remediation_r4.py",
            "uv run python tools/m10/metric_contract.py --check",
            "uv run python tools/m11/generate_control_contract.py --check",
            "cmake --build build/native/m11-release --parallel 8",
            "ctest --test-dir build/native/m11-release --parallel 8 --output-on-failure",
        ],
    }
    return {
        "schema_version": R4_SCHEMA_VERSION,
        "status": "accepted" if not errors else "rejected",
        **evidence,
        "errors": errors,
        "hashes": {"r4_acceptance": canonical_hash(evidence)},
    }


def validate_r4_acceptance(payload: dict[str, Any], repo_root: Path) -> list[str]:
    current = build_r4_acceptance(repo_root)
    errors = list(current["errors"])
    if canonical_hash(payload) != canonical_hash(current):
        errors.append("committed R4 acceptance report does not reproduce")
    return errors


__all__ = ["R4_CONTRACTS", "build_r4_acceptance", "validate_r4_acceptance"]
