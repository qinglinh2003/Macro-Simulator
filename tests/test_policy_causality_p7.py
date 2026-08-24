"""Acceptance tests for the Policy causality audit P7 freeze."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from macro_sim.diagnostics.policy_empirical_freeze import (
    EMPIRICAL_SOURCES,
    P7_EXPLANATION_FIELDS,
    build_crisis_ledger,
    build_empirical_comparisons,
    build_lever_ledger,
    build_p7_manifest,
    run_p7,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "policy-audit"
P2 = AUDIT / "p2" / "p2_report.json"
P3 = AUDIT / "p3" / "p3_report.json"
P4 = AUDIT / "p4" / "p4_report.json"
P5 = AUDIT / "p5" / "p5_report.json"
P6 = AUDIT / "p6" / "p6_report.json"
EXPLANATIONS = (
    ROOT / "macro_sim" / "data" / "locales" / "zh_CN"
    / "policy_explanations.json"
)


def _manifest() -> dict[str, object]:
    return build_p7_manifest(P2, P3, P4, P5, P6, EXPLANATIONS)


def _run(tmp_path: Path, revision: str = "test-revision") -> dict[str, object]:
    return run_p7(
        artifact_dir=tmp_path,
        source_revision=revision,
        p2_source=P2,
        p3_source=P3,
        p4_source=P4,
        p5_source=P5,
        p6_source=P6,
        explanation_source=EXPLANATIONS,
    )


def test_manifest_binds_upstream_freezes_and_reviewed_sources() -> None:
    manifest = _manifest()
    assert manifest["errors"] == []
    assert len(EMPIRICAL_SOURCES) == 11
    assert sum(
        item.source_class != "research_synthesis"
        for item in EMPIRICAL_SOURCES
    ) == 10
    assert all(item.url.startswith("https://") for item in EMPIRICAL_SOURCES)
    assert set(manifest["upstream_acceptance_hashes"]) == {
        "p2_acceptance", "p3_acceptance", "p4_acceptance",
        "p5_acceptance", "p6_acceptance",
    }


def test_every_lever_has_complete_traceability_and_scoped_ui_preset() -> None:
    ledger = build_lever_ledger(P2, P4, P6, EXPLANATIONS)
    assert len(ledger) == 102
    assert len({item["lever"] for item in ledger}) == 102
    assert sum(bool(item["recommended_ui_actions"]) for item in ledger) == 78
    assert sum(not item["recommended_ui_actions"] for item in ledger) == 24
    assert all(
        set(item["economic_explanation"]) == set(P7_EXPLANATION_FIELDS)
        for item in ledger
    )
    assert all(item["uncertainty_label"].strip() for item in ledger)
    assert all(item["mechanism_metrics"] for item in ledger)
    assert all(item["tradeoff_metrics"] for item in ledger)


def test_claims_retain_upstream_defects_and_scenario_boundaries() -> None:
    ledger = {
        item["lever"]: item
        for item in build_lever_ledger(P2, P4, P6, EXPLANATIONS)
    }
    broken = ledger["fiscal_uses_national_accounts_gdp"]
    assert broken["recommended_ui_preset_status"] == "withheld_upstream_defect"
    assert broken["claim_scope"] == "economic_definition_only"

    benefit = ledger["benefit_income_floor"]
    assert benefit["claim_scope"] == "demand_recession_efficacy_with_tradeoffs"
    assert benefit["recommended_ui_actions"]

    energy = ledger["energy_price_cap"]
    assert energy["claim_scope"] == "mechanism_and_demand_recession_safety_concern"


def test_empirical_comparisons_freeze_conflicts_and_scope_mismatches() -> None:
    comparisons = {
        item["comparison_id"]: item
        for item in build_empirical_comparisons(P2, P3, P4)
    }
    assert len(comparisons) == 10
    assert comparisons["fiscal_spending_multiplier"]["comparison_status"] == (
        "direction_and_monotonicity_conflict"
    )
    assert comparisons["income_tax_output_response"]["comparison_status"] == (
        "direction_conflict"
    )
    assert comparisons["open_market_operations_yield_channel"][
        "comparison_status"
    ] == "missing_empirical_outcome"
    assert comparisons["tariff_import_response"]["comparison_status"] == (
        "direction_and_magnitude_conflict"
    )
    tariff = comparisons["tariff_import_response"]["model_evidence"]
    assert tariff["local_import_relative_change"] == pytest.approx(
        0.0208896681
    )
    assert tariff["meaningful_import_relative_change"] == pytest.approx(
        -0.0119383851
    )


def test_empirical_estimates_and_model_design_priors_are_separate() -> None:
    comparisons = {
        item["comparison_id"]: item
        for item in build_empirical_comparisons(P2, P3, P4)
    }
    manual_rate = comparisons["manual_rate_recession_response"]
    assert manual_rate["claim_basis"] == "model_design_prior"
    assert manual_rate["source_ids"] == []
    assert comparisons["mortgage_ltv_credit"]["claim_basis"] == (
        "empirical_estimate"
    )
    assert comparisons["mortgage_ltv_credit"]["source_ids"] == [
        "macroprudential_ltv"
    ]


def test_only_the_frozen_demand_recession_supports_efficacy_claims() -> None:
    ledger = build_crisis_ledger(P3)
    accepted = [
        item for item in ledger
        if item["accepted_for_player_facing_efficacy"]
    ]
    assert len(ledger) == 11
    assert [item["scenario_id"] for item in accepted] == [
        "CR_DEMAND_RECESSION"
    ]
    assert all(
        item["player_facing_claim"]
        for item in ledger
    )


def test_p7_run_is_deterministic_and_serializes_finite_json(
    tmp_path: Path,
) -> None:
    first = _run(tmp_path / "first")
    second = _run(tmp_path / "second")
    assert first["status"] == "accepted_with_explicit_defects"
    assert first["hashes"] == second["hashes"]
    assert first["counts"]["levers"] == 102
    assert first["counts"]["ui_presets_available"] == 78
    assert first["counts"]["ui_presets_withheld"] == 24
    assert first["counts"]["accepted_crises"] == 1
    assert first["counts"]["explicit_findings"] == 4
    serialized = json.loads(
        (tmp_path / "first" / "p7_report.json").read_text(encoding="utf-8")
    )
    assert serialized["hashes"] == first["hashes"]


def test_manifest_rejects_tampered_upstream_identity() -> None:
    p5 = json.loads(P5.read_text(encoding="utf-8"))
    original = _manifest()
    p5["hashes"]["p5_acceptance"] = "changed"
    changed = build_p7_manifest(P2, P3, P4, p5, P6, EXPLANATIONS)
    assert changed["manifest_hash"] != original["manifest_hash"]
    assert "P6 does not bind the frozen P5 acceptance hash" in changed["errors"]


def test_manifest_rejects_tampered_upstream_evidence() -> None:
    p2 = json.loads(P2.read_text(encoding="utf-8"))
    p2["reports"][0]["reason"] = "tampered"
    changed = build_p7_manifest(p2, P3, P4, P5, P6, EXPLANATIONS)
    assert "P2 evidence hash does not reproduce" in changed["errors"]
    assert "P2 acceptance hash does not reproduce" in changed["errors"]
