from __future__ import annotations

import json
from pathlib import Path

import pytest

from macro_sim.diagnostics.policy_scale_confirmation import (
    P6_POPULATIONS,
    P6_SCALE_EXECUTION_BLOCKERS,
    P6_SEEDS,
    RARE_EVENT_MECHANISMS,
    REPRESENTATIVES,
    build_p6_manifest,
    run_p6,
)


ROOT = Path(__file__).resolve().parents[1]
P2 = ROOT / "artifacts" / "policy-audit" / "p2" / "p2_report.json"
P5 = ROOT / "artifacts" / "policy-audit" / "p5" / "p5_report.json"


def test_manifest_covers_twelve_groups_and_every_rare_event() -> None:
    manifest = build_p6_manifest(P2, P5)
    assert manifest["errors"] == []
    groups = [
        item["decision_group"]
        for item in manifest["representatives"]
        if item["role"] == "group"
    ]
    assert len(groups) == len(set(groups)) == 12
    assert len(manifest["representatives"]) == 14
    assert {
        item["lever"]: item["metric_id"] for item in manifest["rare_event_ledger"]
    } == dict(RARE_EVENT_MECHANISMS)
    assert sum(item["runnable"] for item in manifest["rare_event_ledger"]) == 4


def test_every_selected_arm_is_frozen_and_salient() -> None:
    manifest = build_p6_manifest(P2, P5)
    selected = {item["lever"]: item for item in manifest["representatives"]}
    assert set(selected) == {item.lever for item in REPRESENTATIVES}
    assert all(item["actions"] for item in selected.values())
    assert all(item["salient_metrics"] for item in selected.values())
    assert all(item["frozen_effects"] for item in selected.values())


def test_manifest_rejects_a_new_unclassified_count_first_mechanism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_sim.diagnostics import policy_scale_confirmation as p6

    monkeypatch.setattr(
        p6,
        "_runtime_rare_contract",
        lambda: {**RARE_EVENT_MECHANISMS, "new_rare_lever": "metric.new.count"},
    )
    manifest = build_p6_manifest(P2, P5)
    assert "the runtime count-first rare-event contract changed" in manifest["errors"]


def test_formal_protocol_rejects_nonfrozen_scale_or_seeds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="eight frozen matched seeds"):
        run_p6(
            artifact_dir=tmp_path,
            source_revision="test",
            p2_source=P2,
            p5_source=P5,
            seeds=P6_SEEDS[:-1],
        )
    with pytest.raises(ValueError, match="100k and 1M"):
        run_p6(
            artifact_dir=tmp_path,
            source_revision="test",
            p2_source=P2,
            p5_source=P5,
            populations=(P6_POPULATIONS[0],),
        )


def test_p5_identity_is_part_of_manifest_hash() -> None:
    p5 = json.loads(P5.read_text(encoding="utf-8"))
    original = build_p6_manifest(P2, p5)
    p5["hashes"]["p5_acceptance"] = "changed"
    changed = build_p6_manifest(P2, p5)
    assert original["manifest_hash"] != changed["manifest_hash"]


def test_preflight_surfaces_raw_runtime_or_integrity_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from macro_sim.diagnostics import policy_scale_confirmation as p6

    manifest = build_p6_manifest(P2, P5)
    broken = {
        "lever": manifest["representatives"][0]["lever"],
        "population": P6_POPULATIONS[0],
        "seed": P6_SEEDS[0],
        "error": {"type": "Synthetic", "message": "broken"},
        "policy_applied": False,
        "control_integrity": {},
        "treatment_integrity": {},
        "treatment": None,
    }

    monkeypatch.setattr(
        p6,
        "_run_batch",
        lambda *args, **kwargs: ([broken], 0, 1),
    )
    payload = run_p6(
        artifact_dir=tmp_path,
        source_revision="test",
        p2_source=P2,
        p5_source=P5,
        seeds=(P6_SEEDS[0],),
        populations=(P6_POPULATIONS[0],),
        formal=False,
    )
    assert payload["status"] == "failed"
    assert "runtime or integrity defect" in payload["errors"][0]


def test_manifest_freezes_million_person_population() -> None:
    manifest = build_p6_manifest(P2, P5)
    assert manifest["populations"] == [100_000, 1_000_000]
    assert len(manifest["matched_seeds"]) == 8


def test_integrity_gate_holds_per_person_tolerance_constant() -> None:
    from macro_sim.diagnostics.policy_scale_confirmation import (
        _integrity_by_economy,
    )

    capture = {
        "metric_series_by_economy": {
            "0": {
                "metric.source.m4.conservation_drift": {"values": [1.9e-4]},
                "metric.source.m6.clearing_residual": {"values": [2.0e-12]},
                "metric.economy.na.production_reconciliation_residual": {
                    "values": [0.0]
                },
            }
        }
    }
    small = _integrity_by_economy(capture, population=100_000)["0"]
    large = _integrity_by_economy(capture, population=1_000_000)["0"]
    assert not small["passed"]
    assert large["passed"]
    assert large["applied_absolute_limits"][
        "metric.source.m4.conservation_drift"
    ] == pytest.approx(1.0e-3)
    assert large["maximum_residuals_per_person"][
        "metric.source.m4.conservation_drift"
    ] == pytest.approx(1.9e-10)


def test_scale_execution_blockers_are_explicit_and_selected() -> None:
    manifest = build_p6_manifest(P2, P5)
    selected = {item["lever"] for item in manifest["representatives"]}
    assert set(P6_SCALE_EXECUTION_BLOCKERS) == {
        "tariff",
        "fx_regime",
        "mortgage_foreclosure_ltv",
        "rental_eviction_arrears",
    }
    assert set(P6_SCALE_EXECUTION_BLOCKERS) <= selected
    assert P6_SCALE_EXECUTION_BLOCKERS["tariff"]["evidence_kind"] == "direct_observation"
    assert all(
        item["reference_100k_elapsed_seconds"] > 0.0
        for item in P6_SCALE_EXECUTION_BLOCKERS.values()
    )


def test_analyzer_withholds_large_scale_claim_for_execution_blocker() -> None:
    from macro_sim.diagnostics.policy_scale_confirmation import analyze_base

    selection = {
        "lever": "tariff",
        "decision_group": "trade_and_migration",
        "role": "group",
        "arm_label": "arm_2",
        "activation_metrics": ["metric.activation"],
        "salient_metrics": ["metric.activation"],
        "rare_event_metric": None,
    }
    runs = []
    for seed in P6_SEEDS:
        capture = {
            "metric_series": {"metric.activation": {"values": [1.0]}},
        }
        runs.append({
            "lever": "tariff",
            "population": P6_POPULATIONS[0],
            "seed": seed,
            "error": None,
            "policy_applied": True,
            "control": capture,
            "treatment": capture,
            "control_integrity": {"0": {"passed": True}},
            "treatment_integrity": {"0": {"passed": True}},
        })
    reports, errors = analyze_base(
        {"representatives": [selection], "matched_seeds": list(P6_SEEDS)},
        runs,
    )
    assert errors == []
    assert reports[0]["disposition"] == "scale_execution_blocked"
    assert reports[0]["million_person_effect_claimed"] is False
    assert reports[0]["missing_run_count"] == len(P6_SEEDS)
