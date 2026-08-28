from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from macro_sim.diagnostics.policy_package_robustness import (
    R8_ACCEPTED_PHASES,
    R8_PACKAGE_BLUEPRINTS,
    build_r8_acceptance,
    build_r8_manifest,
    reduce_r8_evidence,
    validate_r8_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _inputs() -> tuple[
    dict[str, dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    phases = {
        phase: _load(
            ROOT / f"docs/policy_remediation_{phase.lower()}_acceptance_v39.json"
        )
        for phase in R8_ACCEPTED_PHASES
    }
    return (
        phases,
        _load(ROOT / "docs/policy_remediation_r5_p3_evidence_v39.json"),
        _load(ROOT / "docs/policy_remediation_ledger_v39.json"),
    )


def test_r8_manifest_rebuilds_all_nine_current_packages() -> None:
    phases, p3, ledger = _inputs()
    manifest = build_r8_manifest(
        phase_acceptances=phases,
        r5_p3_payload=p3,
        remediation_ledger=ledger,
    )
    assert len(manifest["packages"]) == 9
    assert {item["package_id"] for item in manifest["packages"]} == {
        item.package_id for item in R8_PACKAGE_BLUEPRINTS
    }
    for package in manifest["packages"]:
        assert package["runnable"]
        assert len(package["factors"]) == 5
        assert len(package["primary_outcomes"]) >= 2
        assert package["design"]["resolution"] == "IV"
        assert package["design"]["component_ablations"] == 5
        assert package["design"]["withdrawal"]
        assert package["design"]["alternative_state"]


def test_r8_factor_actions_preserve_atomic_regime_transitions() -> None:
    phases, p3, ledger = _inputs()
    manifest = build_r8_manifest(
        phase_acceptances=phases,
        r5_p3_payload=p3,
        remediation_ledger=ledger,
    )
    recession = next(
        item for item in manifest["packages"]
        if item["package_id"] == "recession_response"
    )
    manual = next(
        item for item in recession["factors"]
        if item["factor_id"] == "manual_policy_rate"
    )
    assert {item["lever"]: item["value"] for item in manual["high_actions"]} == {
        "manual_policy_rate": 0.0001,
        "monetary_regime": "manual",
    }
    assert {item["lever"]: item["value"] for item in manual["low_actions"]} == {
        "manual_policy_rate": None,
        "monetary_regime": "taylor",
    }
    external = next(
        item for item in manifest["packages"]
        if item["package_id"] == "external_crisis"
    )
    peg = next(
        item for item in external["factors"] if item["factor_id"] == "fx_regime"
    )
    assert {item["lever"]: item["value"] for item in peg["high_actions"]} == {
        "fx_regime": "peg",
        "peg_anchor": 1,
    }
    assert {item["lever"]: item["value"] for item in peg["low_actions"]} == {
        "fx_regime": "float",
        "peg_anchor": None,
    }


def test_r8_rejects_tampered_upstream_bindings_and_removed_components() -> None:
    phases, p3, ledger = _inputs()
    tampered_p3 = deepcopy(p3)
    tampered_p3["hashes"]["p3_evidence"] = "tampered"
    with pytest.raises(ValueError, match="does not bind"):
        build_r8_manifest(
            phase_acceptances=phases,
            r5_p3_payload=tampered_p3,
            remediation_ledger=ledger,
        )

    tampered_phases = deepcopy(phases)
    report = next(
        item for item in tampered_phases["R6"]["reports"]
        if item["lever"] == "benefit_income_floor"
    )
    report["classification"] = "removed"
    with pytest.raises(ValueError, match="removed R6 lever"):
        build_r8_manifest(
            phase_acceptances=tampered_phases,
            r5_p3_payload=p3,
            remediation_ledger=ledger,
        )


def _synthetic_full_payload() -> dict[str, object]:
    reports = []
    for blueprint in R8_PACKAGE_BLUEPRINTS:
        factor_ids = [item.lever for item in blueprint.factors]
        reports.append({
            "package_id": blueprint.package_id,
            "scenario_id": blueprint.scenario_id,
            "alternative_state": blueprint.alternative_state,
            "disposition": "package_no_supported_benefit",
            "reason": "synthetic",
            "gate_summary": {
                "primary_benefit": False,
                "guardrails": True,
                "withdrawal": True,
                "severity": False,
                "alternative_state": False,
                "factorial_complete": True,
                "ablations_complete": True,
            },
            "component_roles": {
                "essential": [],
                "supportive": [],
                "redundant": factor_ids,
                "harmful": [],
            },
            "full_package": {
                "supported_primary_metrics": [],
                "primary_harms": [],
                "guardrail_failures": [],
            },
            "dominance": {"dominant_components": []},
            "isolated_pair_followup": {"pair": list(blueprint.isolated_pair)},
        })
    return {
        "schema_version": "policy-remediation-r8-v1",
        "status": "accepted",
        "source_revision": "test",
        "protocol": {"population_per_country": 100_000, "seeds": list(range(8))},
        "manifest": {"upstream_acceptance_hashes": {"R7": "test"}},
        "counts": {
            "packages": 9,
            "executed_native_branches": 0,
            "cache_hits": 0,
            "dispositions": {"package_no_supported_benefit": 9},
        },
        "reports": reports,
        "errors": [],
        "hashes": {"r8_acceptance": "execution", "r8_evidence": "execution"},
    }


def test_r8_reduced_acceptance_is_deterministic_and_classifies_every_factor() -> None:
    evidence = reduce_r8_evidence(_synthetic_full_payload())
    first = build_r8_acceptance(evidence)
    second = build_r8_acceptance(evidence)
    assert first == second
    assert first["status"] == "accepted"
    assert first["component_role_counts"] == {
        "essential": 0,
        "supportive": 0,
        "redundant": 45,
        "harmful": 0,
    }
    assert validate_r8_acceptance(evidence, first) == []
    tampered = deepcopy(first)
    tampered["gate_counts"]["guardrails"] -= 1
    assert validate_r8_acceptance(evidence, tampered) == [
        "committed R8 acceptance does not reproduce"
    ]
