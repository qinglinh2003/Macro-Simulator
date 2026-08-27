"""Build the deterministic R5 crisis-library acceptance report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from macro_sim.diagnostics.policy_contracts import build_p0_payload
from macro_sim.diagnostics.policy_validation_parity import canonical_hash


R5_SCHEMA_VERSION = "policy-remediation-r5-v1"
R5_BASE_REVISION = "6f3a007bd7b6b7d447923109375cf07eb3e9e4f2"
R5_IMPLEMENTATION_REVISION = "95930333ce7ae8df11933af6c3d7be9e391cfbc5"
R5_P3_SCHEMA_VERSION = "policy-causality-p3-v3"
R5_P3_LEGACY_STATUS = "accepted_with_explicit_defects"
R5_EVIDENCE_PATH = "docs/policy_remediation_r5_p3_evidence_v39.json"

R5_SEEDS = (5_101, 5_113, 5_129, 5_143, 5_159, 5_177, 5_193, 5_209)
R5_STATE_IDS = (
    "BASE_NORMAL",
    "BASE_SLACK",
    "BASE_TIGHT",
    "STRUCT_HIGH_POVERTY",
    "STRUCT_HIGH_INEQUALITY",
    "STRUCT_LOW_PARTICIPATION",
    "STRUCT_HOUSING_SHORTAGE",
    "STRUCT_LOW_PRODUCTIVITY",
    "STRUCT_ENERGY_DEPENDENCE",
    "STRUCT_POPULATION_AGING",
    "STRUCT_EXTERNAL_IMBALANCE",
)
R5_CRISIS_IDS = (
    "CR_DEMAND_RECESSION",
    "CR_SUPPLY_STAGFLATION",
    "CR_ENERGY_EMBARGO",
    "CR_CREDIT_CRUNCH",
    "CR_PANDEMIC",
    "CR_NATURAL_DISASTER",
    "CR_TRADE_INTERRUPTION",
    "CR_PEG_PRESSURE",
    "CR_BANK_RUN",
    "CR_HOUSING_BUST",
    "CR_SOVEREIGN_STRESS",
)
R5_GATE_NAMES = (
    "entry_gate",
    "propagation_gate",
    "severity_gate",
    "recovery_gate",
    "integrity_gate",
)
R5_SHOCK_KINDS = (
    "capital_destruction",
    "capital_outflow_pressure",
    "credit_supply",
    "energy_capacity",
    "export_capacity",
    "household_demand",
    "import_capacity",
    "labor_availability",
    "productivity",
    "sovereign_risk_premium",
)

R5_TEST_MARKERS = {
    "tests/test_config_causality_experiment.py": (
        "test_world_activation_scenarios_create_the_shared_identification_state",
        "test_energy_activation_preserves_the_audited_field",
    ),
    "native/tests/m6_simulation_tests.cpp": (
        "test_sovereign_risk_premium_reprices_existing_bonds",
    ),
    "native/tests/m8_housing_market_tests.cpp": (
        "test_mortgage_credit_supply_multiplier_is_sector_specific",
    ),
    "native/tests/m9_world_tests.cpp": (
        "test_capital_outflow_pressure_drains_peg_reserves",
    ),
    "native/tests/m10_reporting_tests.cpp": (
        "test_capital_destruction_is_active_for_realization_boundary_only",
        "test_sovereign_risk_premium_is_reported_on_its_stable_metric",
        "test_capital_outflow_pressure_is_reported_on_its_stable_metric",
    ),
    "tests/test_policy_causality_p3.py": (
        "test_every_runnable_crisis_freezes_three_ordered_tapes",
        "test_sovereign_scenario_has_an_observed_risk_premium_tape",
        "test_peg_scenario_uses_capital_outflow_pressure",
        "test_housing_severity_uses_the_acute_mortgage_window",
        "test_replay_comparison_accepts_only_roundoff_scale_metric_drift",
    ),
}

R5_SOURCE_PATHS = (
    "macro_sim/controllers/gym_adapter.py",
    "macro_sim/controllers/native_observation.py",
    "macro_sim/controllers/observation.py",
    "macro_sim/diagnostics/config_experiment.py",
    "macro_sim/diagnostics/policy_catalog.py",
    "macro_sim/diagnostics/policy_scenarios.py",
    "macro_sim/native_backend.py",
    "macro_sim/rl/envs.py",
    "macro_sim/rl/native_envs.py",
    "macro_sim/shocks/registry.py",
    "native/include/macro_sim/c_api.h",
    "native/include/macro_sim/control/generated_m11_observation_contract.inc",
    "native/include/macro_sim/generated/contracts.hpp",
    "native/include/macro_sim/reporting/m10.hpp",
    "native/include/macro_sim/simulation/m6.hpp",
    "native/include/macro_sim/simulation/m8.hpp",
    "native/include/macro_sim/simulation/m9.hpp",
    "native/src/c_api.cpp",
    "native/src/control/m11_checkpoint.cpp",
    "native/src/control/m11_release.cpp",
    "native/src/control/m11_session.cpp",
    "native/src/desktop/m11_protocol.cpp",
    "native/src/python_bindings.cpp",
    "native/src/reporting/m10.cpp",
    "native/src/simulation/m6.cpp",
    "native/src/simulation/m8.cpp",
    "native/src/simulation/m9.cpp",
    "native/tests/m10_reporting_tests.cpp",
    "native/tests/m11_release_tests.cpp",
    "native/tests/m6_simulation_tests.cpp",
    "native/tests/m8_housing_market_tests.cpp",
    "native/tests/m9_world_tests.cpp",
    "schemas/m0/hashes.lock.json",
    "schemas/m0/inventory/modules.json",
    "schemas/m0/inventory/observations.json",
    "schemas/m0/inventory/policy.json",
    "schemas/m0/inventory/shocks.json",
    "schemas/m1/generated/contracts.json",
    "schemas/m1/generated/python/contracts.py",
    "schemas/m1/hashes.lock.json",
    "schemas/m1/invalid_contract_cases.json",
    "schemas/m10/maintained_metrics.json",
    "schemas/m10/performance_budget.json",
    "schemas/m11/observation_contract.json",
    "scripts/cpp_migration/inventory.py",
    "tests/fixtures/m0/clients/contracts.json",
    "tests/migration/m0/test_inventory_contracts.py",
    "tests/native/test_generated_contracts.py",
    "tests/test_config_causality_experiment.py",
    "tests/test_policy_causality_p3.py",
    "tools/m10/metric_contract.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _p3_hashes(payload: Mapping[str, Any]) -> dict[str, str]:
    manifest_hash = canonical_hash(payload["manifest"])
    evidence_hash = canonical_hash(payload["reports"])
    acceptance_hash = canonical_hash(
        {
            "status": payload["status"],
            "errors": payload["errors"],
            "p0_root": payload["p0_root_hash"],
            "protocol": payload["protocol"],
            "manifest": manifest_hash,
            "evidence": evidence_hash,
            "accepted_crises_for_p4": payload["accepted_crises_for_p4"],
        }
    )
    return {
        "p3_manifest": manifest_hash,
        "p3_evidence": evidence_hash,
        "p3_acceptance": acceptance_hash,
    }


def _passed_rows(rows: list[Mapping[str, Any]]) -> int:
    return sum(bool(row.get("passed")) for row in rows)


def build_r5_acceptance(
    repo_root: Path,
    evidence_path: Path | None = None,
) -> dict[str, Any]:
    """Build the compact R5 acceptance from the committed full P3 evidence."""

    if evidence_path is None:
        evidence_path = repo_root / R5_EVIDENCE_PATH
    p3 = _load_json(evidence_path)
    errors: list[str] = []

    if p3.get("schema_version") != R5_P3_SCHEMA_VERSION:
        errors.append(f"unexpected P3 schema {p3.get('schema_version')!r}")
    if p3.get("status") != R5_P3_LEGACY_STATUS:
        errors.append(f"unexpected legacy P3 status {p3.get('status')!r}")
    if p3.get("source_revision") != R5_IMPLEMENTATION_REVISION:
        errors.append(f"unexpected implementation revision {p3.get('source_revision')!r}")
    if p3.get("errors") != []:
        errors.append(f"P3 execution errors remain: {p3.get('errors')!r}")

    protocol = p3.get("protocol", {})
    expected_protocol = {
        "population_per_country": 100_000,
        "matched_seeds": list(R5_SEEDS),
        "native_engine_workers": 8,
        "independent_seed_jobs": 8,
        "entry_required_seeds": 6,
        "legacy_python_simulator_used": False,
    }
    if protocol != expected_protocol:
        errors.append(f"unexpected R5 protocol {protocol!r}")

    counts = p3.get("counts", {})
    expected_counts = {
        "ordinary_states": 3,
        "structural_states": 8,
        "crises": 11,
        "accepted_states": 11,
        "accepted_crises": 11,
        "unaccepted_crises": 0,
        "native_run_records": 176,
        "executed_native_runs": 176,
        "cache_hits": 0,
    }
    if counts != expected_counts:
        errors.append(f"unexpected R5 run counts {counts!r}")

    reports = p3.get("reports", {})
    state_reports = {
        row["scenario_id"]: row for row in reports.get("states", [])
    }
    crisis_reports = {
        row["scenario_id"]: row for row in reports.get("crises", [])
    }
    if set(state_reports) != set(R5_STATE_IDS):
        errors.append(f"unexpected state scenarios {sorted(state_reports)!r}")
    if set(crisis_reports) != set(R5_CRISIS_IDS):
        errors.append(f"unexpected crisis scenarios {sorted(crisis_reports)!r}")

    state_checks: dict[str, dict[str, Any]] = {}
    for scenario_id in R5_STATE_IDS:
        row = state_reports.get(scenario_id, {})
        all_seed_rows_passed = _passed_rows(row.get("by_seed", [])) == len(R5_SEEDS)
        checkpoint_count = len(row.get("frozen_checkpoint_hashes", []))
        accepted = bool(row.get("accepted"))
        state_checks[scenario_id] = {
            "accepted": accepted,
            "disposition": row.get("disposition"),
            "scenario_class": row.get("scenario_class"),
            "passed_seed_count": row.get("passed_seed_count"),
            "required_seed_count": row.get("required_seed_count"),
            "checkpoint_count": checkpoint_count,
            "all_seed_rows_passed": all_seed_rows_passed,
        }
        if not accepted or row.get("disposition") != "accepted":
            errors.append(f"{scenario_id}: state was not accepted")
        if row.get("passed_seed_count") != len(R5_SEEDS) or not all_seed_rows_passed:
            errors.append(f"{scenario_id}: not all state seeds passed")
        if checkpoint_count != len(R5_SEEDS):
            errors.append(f"{scenario_id}: incomplete checkpoint evidence")

    manifest_crises = {
        row["scenario_id"]: row for row in p3.get("manifest", {}).get("crises", [])
    }
    shock_kinds: set[str] = set()
    crisis_checks: dict[str, dict[str, Any]] = {}
    for scenario_id in R5_CRISIS_IDS:
        row = crisis_reports.get(scenario_id, {})
        manifest = manifest_crises.get(scenario_id, {})
        scenario_shocks = sorted(
            {leg["kind"] for leg in manifest.get("shock_legs", [])}
        )
        shock_kinds.update(scenario_shocks)
        gates = {
            name.removesuffix("_gate"): bool(row.get(name, {}).get("passed"))
            for name in R5_GATE_NAMES
        }
        integrity = row.get("integrity_gate", {})
        replay_evidence_count = integrity.get("replay_evidence_count", 0)
        all_integrity_rows_passed = (
            _passed_rows(integrity.get("by_seed", [])) == len(R5_SEEDS)
        )
        crisis_checks[scenario_id] = {
            "accepted": bool(row.get("accepted")),
            "disposition": row.get("disposition"),
            "declared_readiness": row.get("declared_readiness"),
            "countries": manifest.get("countries"),
            "shock_kinds": scenario_shocks,
            "primary_metric": row.get("severity_gate", {}).get("primary_metric"),
            "gates": gates,
            "entry_passed_seed_count": row.get("entry_gate", {}).get(
                "passed_seed_count"
            ),
            "propagation_passed_seed_count": row.get("propagation_gate", {}).get(
                "passed_seed_count"
            ),
            "severity_ordered_seed_count": row.get("severity_gate", {}).get(
                "ordered_seed_count"
            ),
            "recovery_passed_seed_count": row.get("recovery_gate", {}).get(
                "passed_seed_count"
            ),
            "replay_evidence_count": replay_evidence_count,
            "all_integrity_rows_passed": all_integrity_rows_passed,
        }
        if not row.get("accepted") or row.get("disposition") != "accepted":
            errors.append(f"{scenario_id}: crisis was not accepted")
        if not all(gates.values()):
            errors.append(f"{scenario_id}: one or more crisis gates failed {gates!r}")
        if replay_evidence_count < 1 or not all_integrity_rows_passed:
            errors.append(f"{scenario_id}: incomplete replay or integrity evidence")
        if "policy_treatment" in manifest:
            errors.append(f"{scenario_id}: crisis calibration contains Policy treatment")

    if shock_kinds != set(R5_SHOCK_KINDS):
        errors.append(f"unexpected shock-kind coverage {sorted(shock_kinds)!r}")
    if set(p3.get("accepted_crises_for_p4", [])) != set(R5_CRISIS_IDS):
        errors.append("not every R5 crisis is accepted for downstream calibration")
    if p3.get("excluded_crises_for_p4") != []:
        errors.append(f"crises remain excluded: {p3.get('excluded_crises_for_p4')!r}")

    recomputed_hashes = _p3_hashes(p3)
    if p3.get("hashes") != recomputed_hashes:
        errors.append("P3 manifest, evidence, or acceptance hash does not reproduce")
    current_p0_root = build_p0_payload()["hashes"]["p0_root"]
    if p3.get("p0_root_hash") != current_p0_root:
        errors.append("P3 evidence is not bound to the current P0 contract root")

    test_markers: dict[str, list[str]] = {}
    for relative, markers in R5_TEST_MARKERS.items():
        source = (repo_root / relative).read_text(encoding="utf-8")
        found = [marker for marker in markers if marker in source]
        test_markers[relative] = found
        missing = sorted(set(markers) - set(found))
        if missing:
            errors.append(f"{relative}: missing R5 test markers {missing!r}")

    evidence = {
        "phase": "R5",
        "base_revision": R5_BASE_REVISION,
        "implementation_revision": R5_IMPLEMENTATION_REVISION,
        "legacy_p3_status": p3.get("status"),
        "legacy_status_note": (
            "P3 v3 uses this historical completion label regardless of the number "
            "of excluded crises; R5 acceptance is determined by the explicit gates."
        ),
        "p0_root_hash": current_p0_root,
        "protocol": protocol,
        "counts": counts,
        "accepted_crises": list(p3.get("accepted_crises_for_p4", [])),
        "excluded_crises": list(p3.get("excluded_crises_for_p4", [])),
        "shock_kinds": sorted(shock_kinds),
        "state_checks": state_checks,
        "crisis_checks": crisis_checks,
        "p3_hashes": recomputed_hashes,
        "p3_evidence_file": R5_EVIDENCE_PATH,
        "p3_evidence_file_sha256": _sha256(evidence_path),
        "native_behavior_test_markers": test_markers,
        "source_sha256": {
            path: _sha256(repo_root / path) for path in R5_SOURCE_PATHS
        },
        "supersession": {
            "previous_accepted_crisis_count": 1,
            "current_accepted_crisis_count": len(p3.get("accepted_crises_for_p4", [])),
            "historical_p3_evidence_superseded": True,
            "policy_calibration_performed": False,
        },
        "verification_commands": [
            (
                "PYTHONPATH=build/native/m11-release/native:. .venv/bin/python "
                "scripts/policy_causality_p3.py --artifact-dir "
                "artifacts/policy-remediation/r5/p3-final --population 100000 "
                "--workers 8 --jobs 8 --no-resume --fail-on-incomplete"
            ),
            "ctest --preset m11-release -j 8 --output-on-failure",
            (
                "PYTHONPATH=build/native/m11-release/native:. .venv/bin/python "
                "-m pytest -q tests/test_policy_causality_p3.py "
                "tests/test_policy_remediation_r5.py"
            ),
            (
                "PYTHONPATH=build/native/m11-release/native:. .venv/bin/python "
                "scripts/policy_remediation_r5.py --check"
            ),
        ],
    }
    return {
        "schema_version": R5_SCHEMA_VERSION,
        "status": "accepted" if not errors else "rejected",
        **evidence,
        "errors": errors,
        "hashes": {"r5_acceptance": canonical_hash(evidence)},
    }


def validate_r5_acceptance(payload: Mapping[str, Any], repo_root: Path) -> list[str]:
    """Validate the committed compact report and its full empirical evidence."""

    current = build_r5_acceptance(repo_root)
    errors = list(current["errors"])
    if canonical_hash(payload) != canonical_hash(current):
        errors.append("committed R5 acceptance report does not reproduce")
    return errors


__all__ = [
    "R5_CRISIS_IDS",
    "R5_GATE_NAMES",
    "R5_SHOCK_KINDS",
    "R5_STATE_IDS",
    "build_r5_acceptance",
    "validate_r5_acceptance",
]
