from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from macro_sim.core.policy_evidence import (
    POLICY_EVIDENCE,
    POLICY_EVIDENCE_SHA256,
)
from macro_sim.core.policy_explanations import POLICY_EXPLANATIONS
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.desktop.native_runtime import NativeSimulationRuntime
from macro_sim.diagnostics.policy_delivery_acceptance import (
    R9_ACCEPTED_PHASES,
    build_policy_evidence_catalog,
    build_r9_acceptance,
    build_r9_manifest,
    validate_r9_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phases() -> dict[str, dict[str, object]]:
    return {
        phase: _load(
            ROOT / f"docs/policy_remediation_{phase.lower()}_acceptance_v39.json"
        )
        for phase in R9_ACCEPTED_PHASES
    }


def test_r9_policy_evidence_reproduces_and_covers_the_registry() -> None:
    expected = build_policy_evidence_catalog(_phases())
    committed = _load(ROOT / "macro_sim/data/policy_evidence_v39.json")
    assert committed == expected
    assert expected["catalog_sha256"] == POLICY_EVIDENCE_SHA256
    assert set(POLICY_EVIDENCE) == set(REGISTRY) == set(POLICY_EXPLANATIONS)
    counts: dict[str, int] = {}
    for row in POLICY_EVIDENCE.values():
        classification = str(row["individual_classification"])
        counts[classification] = counts.get(classification, 0) + 1
        assert row["real_world_empirical_claim"] is False
    assert counts == {
        "conditional": 22,
        "effective": 2,
        "expert_only": 9,
        "not_reclassified": 66,
        "structural": 3,
    }


def test_r9_package_roles_remain_explicitly_package_local() -> None:
    floor = POLICY_EVIDENCE["benefit_income_floor"]
    assert floor["individual_classification"] == "effective"
    recession = next(
        item for item in floor["package_findings"]
        if item["package_id"] == "recession_response"
    )
    assert recession["role"] == "harmful"
    assert recession["package_disposition"] == "package_guardrail_failure"


def test_r9_manifest_binds_current_engine_ui_and_upstream_evidence() -> None:
    manifest = build_r9_manifest(
        phase_acceptances=_phases(),
        policy_evidence=_load(ROOT / "macro_sim/data/policy_evidence_v39.json"),
        rl_artifact=ROOT / "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl",
    )
    assert manifest["population_per_country"] == 100_000
    assert manifest["workers"] == {
        "concurrent_seed_jobs": 8,
        "native_workers_per_session": 8,
    }
    assert len(manifest["seeds"]) == 8
    assert len(manifest["registry_contract_sha256"]) == 64
    assert len(manifest["policy_evidence_sha256"]) == 64


def test_native_product_schema_exposes_definitions_and_evidence_for_all_levers() -> None:
    schema = NativeSimulationRuntime(seed=5101).schema()
    levers = [
        row
        for seat in schema["seats"].values()
        for row in seat["levers"]
    ]
    assert schema["control_mode"] == "free_policy"
    assert schema["policy_evidence_sha256"] == POLICY_EVIDENCE_SHA256
    assert {row["name"] for row in levers} == set(REGISTRY)
    assert all(row["read_point"] for row in levers)
    assert all("state_notes" in row for row in levers)
    assert all(row["evidence_scope"] == POLICY_EVIDENCE[row["name"]]
               for row in levers)
    assert all(set(row["player_help"]) == {
        "meaning", "mechanics", "tradeoffs", "watch",
    } for row in levers)


def test_frozen_r9_acceptance_reproduces_and_passes_all_required_gates() -> None:
    evidence = _load(
        ROOT / "docs/policy_remediation_r9_delivery_evidence_v39.json"
    )
    acceptance = _load(ROOT / "docs/policy_remediation_r9_acceptance_v39.json")
    assert validate_r9_acceptance(evidence, acceptance) == []
    assert acceptance["status"] == "accepted_with_explicit_limitations"
    assert all(acceptance["delivery_gates"].values())
    assert all(acceptance["ui_gates"].values())
    assert all(acceptance["occupant_gates"].values())
    assert acceptance["protocol"]["legacy_python_simulator_used"] is False
    assert acceptance["protocol"]["actual_human_performance_claim"] is False
    assert acceptance["protocol"]["rl_superiority_claim"] is False

    tampered = deepcopy(acceptance)
    tampered["delivery_gates"]["free_immediate_exact_native_parity"] = False
    assert validate_r9_acceptance(evidence, tampered) == [
        "committed R9 acceptance does not reproduce"
    ]


def test_frozen_r9_seed_digests_prove_delivery_path_identity() -> None:
    evidence = _load(
        ROOT / "docs/policy_remediation_r9_delivery_evidence_v39.json"
    )
    assert len(evidence["delivery_seed_evidence"]) == 8
    for row in evidence["delivery_seed_evidence"]:
        digests = row["digests"]
        assert digests["free_immediate"] == digests["free_immediate_direct"]
        assert digests["regular"] == digests["regular_direct"]
        assert digests["human_regular"] == digests["regular_direct"]
        assert digests["emergency"] == digests["emergency_direct"]
