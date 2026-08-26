"""Acceptance tests for Policy remediation planning milestone R0."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from macro_sim.core.policy_registry import REGISTRY
from macro_sim.diagnostics.policy_remediation import (
    BEHAVIOR_REVIEW_LEVERS,
    SCALE_REVALIDATION_LEVERS,
    build_source_freeze,
    canonical_hash,
    validate_remediation_ledger,
)


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "docs" / "policy_remediation_ledger_v39.json"
PLAN_PATH = ROOT / "docs" / "policy_remediation_plan_v39.md"


def _ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _synthetic_sources() -> list[dict]:
    root = "p0-root"
    hashes = {f"p{i}": f"p{i}-acceptance" for i in range(1, 9)}
    statuses = {
        f"p{i}": (
            "accepted_with_explicit_limitations"
            if i == 8 else "accepted_with_explicit_defects"
        )
        for i in range(1, 9)
    }
    reports = [
        {
            "status": statuses["p1"],
            "hashes": {"p0_root": root, "p1_acceptance": hashes["p1"]},
        },
        {
            "status": statuses["p2"],
            "p0_root_hash": root,
            "hashes": {"p2_acceptance": hashes["p2"]},
            "counts": {"levers": 102},
        },
        {
            "status": statuses["p3"],
            "p0_root_hash": root,
            "hashes": {"p3_acceptance": hashes["p3"]},
        },
        {
            "status": statuses["p4"],
            "hashes": {"p4_acceptance": hashes["p4"]},
            "counts": {"matrix_cells": 102},
            "manifest": {
                "p0_root_hash": root,
                "p2_acceptance_hash": hashes["p2"],
                "p3_acceptance_hash": hashes["p3"],
            },
        },
        {
            "status": statuses["p5"],
            "hashes": {"p5_acceptance": hashes["p5"]},
            "manifest": {
                "p0_root_hash": root,
                "p2_acceptance_hash": hashes["p2"],
                "p3_acceptance_hash": hashes["p3"],
                "p4_acceptance_hash": hashes["p4"],
            },
        },
        {
            "status": statuses["p6"],
            "hashes": {"p6_acceptance": hashes["p6"]},
            "manifest": {
                "p0_root_hash": root,
                "p2_acceptance_hash": hashes["p2"],
                "p5_acceptance_hash": hashes["p5"],
            },
        },
        {
            "status": statuses["p7"],
            "hashes": {"p7_acceptance": hashes["p7"]},
            "counts": {"levers": 102, "accepted_crises": 1},
            "manifest": {
                "p0_root_hash": root,
                "upstream_acceptance_hashes": {
                    f"p{i}_acceptance": hashes[f"p{i}"]
                    for i in range(2, 7)
                },
            },
            "freeze": {
                "scenario_manifests": {
                    "accepted_scenarios": ["CR_DEMAND_RECESSION"],
                },
            },
        },
        {
            "status": statuses["p8"],
            "hashes": {"p8_acceptance": hashes["p8"]},
            "manifest": {
                "upstream_acceptance_hashes": {
                    "p3_acceptance": hashes["p3"],
                    "p4_acceptance": hashes["p4"],
                    "p7_acceptance": hashes["p7"],
                },
            },
        },
    ]
    return reports


def test_r0_ledger_is_accepted_complete_and_matches_registry() -> None:
    payload = _ledger()
    assert payload["status"] == "accepted"
    assert payload["errors"] == []
    assert payload["counts"]["levers"] == 102
    assert payload["counts"]["mandatory_repair"] == 27
    assert payload["counts"]["behavior_review"] == 36
    assert payload["counts"]["no_change_evidence"] == 39
    assert {item["lever"] for item in payload["policies"]} == set(REGISTRY)
    assert validate_remediation_ledger(payload) == []


def test_source_freeze_rejects_a_broken_cross_stage_binding() -> None:
    sources = _synthetic_sources()
    freeze, _, errors = build_source_freeze(*sources)
    assert errors == []
    assert freeze["p0_root_hash"] == "p0-root"
    changed = deepcopy(sources)
    changed[7]["manifest"]["upstream_acceptance_hashes"][
        "p7_acceptance"
    ] = "tampered"
    _, _, errors = build_source_freeze(*changed)
    assert any(error.startswith("P8 binds P7") for error in errors)


def test_primary_classes_are_disjoint_and_exhaustive() -> None:
    policies = _ledger()["policies"]
    classes = {
        name: {
            item["lever"] for item in policies
            if item["remediation_class"] == name
        }
        for name in (
            "mandatory_repair", "behavior_review", "no_change_evidence",
        )
    }
    assert classes["mandatory_repair"].isdisjoint(classes["behavior_review"])
    assert classes["mandatory_repair"].isdisjoint(classes["no_change_evidence"])
    assert classes["behavior_review"].isdisjoint(classes["no_change_evidence"])
    assert set.union(*classes.values()) == set(REGISTRY)
    assert classes["behavior_review"] == set(BEHAVIOR_REVIEW_LEVERS)


def test_repair_queues_preserve_defect_taxonomy_and_dependencies() -> None:
    payload = _ledger()
    phases = {item["phase_id"]: set(item["policy_levers"]) for item in payload["phases"]}
    assert len(phases["R1"]) == 4
    assert len(phases["R2"]) == 12
    assert len(phases["R3"]) == 6
    assert len(phases["R4"]) == 7
    assert len(phases["R6"]) == 36
    assert phases["R7"] == set(SCALE_REVALIDATION_LEVERS)
    assert "margin_max" in phases["R1"] & phases["R4"]
    assert "omo" in phases["R2"] & phases["R6"]


def test_every_actionable_entry_has_evidence_and_acceptance_gates() -> None:
    for item in _ledger()["policies"]:
        contract = item["repair_contract"]
        assert contract["intent"]
        assert contract["acceptance_gates"]
        if item["remediation_class"] != "no_change_evidence":
            assert item["phase_ids"]
            assert item["findings"]


def test_invalidation_graph_is_conservative_and_ordered() -> None:
    payload = _ledger()
    graph = {
        item["repair_phase"]: item["invalidates_audit_stages"]
        for item in payload["invalidation_graph"]
    }
    assert list(graph) == [f"R{i}" for i in range(10)]
    assert graph["R0"] == []
    assert graph["R1"] == [f"P{i}" for i in range(9)]
    assert graph["R6"] == ["P2", "P4", "P5", "P6", "P7", "P8"]
    assert graph["R7"] == ["P6", "P7", "P8"]
    assert graph["R9"] == ["P8"]


def test_serialized_hashes_reject_tampering() -> None:
    payload = _ledger()
    changed = deepcopy(payload)
    changed["policies"][0]["repair_contract"]["intent"] = "tampered"
    errors = validate_remediation_ledger(changed)
    assert "R0 evidence hash does not reproduce" in errors
    changed = deepcopy(payload)
    changed["baseline_revision"] = "tampered"
    errors = validate_remediation_ledger(changed)
    assert "R0 acceptance hash does not reproduce" in errors


def test_committed_plan_and_json_share_acceptance_identity() -> None:
    payload = _ledger()
    plan = PLAN_PATH.read_text(encoding="utf-8")
    assert payload["hashes"]["r0_acceptance"] in plan
    assert "R0 stops after this ledger" in plan
    assert "P2 does not expose a P1 acceptance binding" in plan
    assert canonical_hash({
        "source_freeze": payload["source_freeze"],
        "policies": payload["policies"],
        "phases": payload["phases"],
        "invalidation_graph": payload["invalidation_graph"],
    }) == payload["hashes"]["r0_evidence"]
