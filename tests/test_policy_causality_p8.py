"""Acceptance tests for P8 institutional delivery evidence."""

from __future__ import annotations

import json
from pathlib import Path

from macro_sim.diagnostics.policy_institutional_delivery import (
    P8_RL_ARTIFACT,
    build_p8_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "policy-audit"
P3 = AUDIT / "p3" / "p3_report.json"
P4 = AUDIT / "p4" / "p4_report.json"
P7 = AUDIT / "p7" / "p7_report.json"
P8 = AUDIT / "p8" / "p8_report.json"
RL_ARTIFACT = ROOT / P8_RL_ARTIFACT


def test_manifest_freezes_one_action_and_all_delivery_paths() -> None:
    manifest = build_p8_manifest(P3, P4, P7, RL_ARTIFACT)
    assert manifest["errors"] == []
    assert manifest["scenario"]["population"] == 100_000
    assert manifest["scenario"]["workers_per_session"] == 8
    assert manifest["action"]["lever"] == "benefit_income_floor"
    assert manifest["action"]["value"] == 0.20
    assert len(manifest["delivery_branches"]) == 8
    assert "human_scheduled" in manifest["delivery_branches"]


def test_manifest_rejects_tampered_p4_action() -> None:
    original = build_p8_manifest(P3, P4, P7, RL_ARTIFACT)
    p4 = json.loads(P4.read_text(encoding="utf-8"))
    row = next(
        item for item in p4["reports"]
        if item["lever"] == "benefit_income_floor"
    )
    arm = next(item for item in row["arms"] if item["dose_class"] == "meaningful")
    arm["actions"][0]["value"] = 0.19
    changed = build_p8_manifest(P3, p4, P7, RL_ARTIFACT)
    assert changed["manifest_hash"] != original["manifest_hash"]
    assert "P8 delivery action differs" in " ".join(changed["errors"])


def test_frozen_report_passes_delivery_and_information_gates() -> None:
    report = json.loads(P8.read_text(encoding="utf-8"))
    assert report["status"] == "accepted_with_explicit_limitations"
    assert report["errors"] == []
    assert report["counts"]["delivery_seeds"] == 8
    assert report["counts"]["delivery_native_paths"] == 64
    assert all(report["delivery"]["gates"].values())
    assert report["protocol"]["legacy_python_simulator_used"] is False
    assert report["protocol"]["released_observations_only"] is True


def test_rl_result_is_explicitly_scoped_to_transfer_probe() -> None:
    report = json.loads(P8.read_text(encoding="utf-8"))
    assessment = report["occupant_evaluation"]["contract_assessment"]
    assert assessment["context_codec_match"] is True
    assert assessment["action_codec_match"] is True
    assert assessment["training_environment_match"] is False
    assert assessment["classification"] == (
        "explicit_cross_backend_transfer_probe"
    )
    assert assessment["superiority_claim_allowed"] is False
    assert report["protocol"]["actual_human_performance_claim"] is False
