"""R6 single-policy calibration design and classification tests."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import asdict

from macro_sim.diagnostics.policy_contracts import build_contracts, build_p0_payload
from macro_sim.diagnostics import policy_crisis_effects
from macro_sim.diagnostics.config_experiment import summarize_metric_series
from macro_sim.diagnostics.policy_crisis_effects import _row_arm_lookup
from scripts.policy_remediation_r6_lib import (
    R6_CANDIDATES,
    R6_CLASSIFICATIONS,
    _classification,
    build_r6_design,
    validate_r6_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
P2_EVIDENCE = ROOT / "docs/policy_remediation_r6_p2_evidence_v39.json"
CRISIS_EVIDENCE = ROOT / "docs/policy_remediation_r6_crisis_evidence_v39.json"
ACCEPTANCE = ROOT / "docs/policy_remediation_r6_acceptance_v39.json"


def _inputs() -> tuple[dict[str, object], dict[str, object]]:
    p0 = build_p0_payload()
    p2 = {
        "p0_root_hash": p0["hashes"]["p0_root"],
        "hashes": {"p2_acceptance": "test-p2"},
        "protocol": {"matched_seeds": [4201, 4213, 4231, 4253]},
        "reports": [
            {
                "lever": lever,
                "disposition": "accepted",
                "reason": "test fixture",
            }
            for lever in R6_CANDIDATES
        ],
    }
    p3 = json.loads(
        (ROOT / "docs/policy_remediation_r5_p3_evidence_v39.json").read_text(
            encoding="utf-8"
        )
    )
    return p2, p3


def test_r6_design_has_two_preregistered_states_per_candidate() -> None:
    p2, p3 = _inputs()
    design = build_r6_design(p3_payload=p3, p2_payload=p2)
    assert len(R6_CANDIDATES) == 36
    assert len(design["rows"]) == 72
    assert sum(row["runnable"] for row in design["rows"]) == 68
    assert {row["state_kind"] for row in design["rows"]} == {
        "anchor", "adverse",
    }
    assert all(
        not row.get("policy_only_negative_control", True)
        for row in design["rows"]
        if row["runnable"]
    )


def test_r6_crisis_rows_do_not_schedule_redundant_policy_only_branch() -> None:
    row = {
        "policy_only_negative_control": False,
        "arms": [{"label": "dose", "timings": ["immediate"]}],
    }
    assert list(_row_arm_lookup(row)) == [
        (row["arms"][0], "immediate", True),
    ]


def _metric_run(value: float) -> dict[str, object]:
    rows = [
        {"_tick": tick, "metric.economy.real_output": value}
        for tick in (1, 2, 3)
    ]
    return {
        "metric_series": {
            "metric.economy.real_output": {
                "ticks": [1, 2, 3],
                "values": [value, value, value],
            },
        },
        "metric_summaries": {
            name: asdict(summary)
            for name, summary in summarize_metric_series(rows).items()
        },
        "missing_metrics_by_economy": {"0": []},
        "integrity": {"passed": True},
    }


def test_r6_analysis_skips_absent_policy_only_comparison(monkeypatch) -> None:
    records = iter([
        {
            "error": None,
            "policy_applied": True,
            "terminal_active_shocks": 0.0,
            "run": _metric_run(11.0),
        },
        {
            "error": None,
            "policy_applied": True,
            "terminal_active_shocks": 0.0,
            "run": _metric_run(12.0),
        },
    ])
    monkeypatch.setattr(
        policy_crisis_effects,
        "_read_result",
        lambda _path: next(records),
    )
    result = policy_crisis_effects._arm_analysis(
        row={
            "lever": "test",
            "policy_only_negative_control": False,
            "mechanism_proximal_metrics": [],
            "tradeoff_metrics": [],
        },
        arm={"label": "dose", "dose_class": "meaningful", "actions": []},
        timing="immediate",
        seeds=(1, 2),
        artifact_dir=Path("unused"),
        ordinary_controls={},
        crisis_controls={1: _metric_run(10.0), 2: _metric_run(10.0)},
        primary_outcomes={"metric.economy.real_output": 1},
    )
    assert result["ordinary_effects"] is None
    assert result["crisis_interactions"] is None


def test_r6_classification_vocabulary_and_silent_lever_rule() -> None:
    contract = next(
        item for item in build_contracts()
        if item.lever == "gov_consumption_share"
    )
    crisis = {"states": []}
    classification, _reason = _classification(
        lever=contract.lever,
        contract=contract,
        mechanism={
            "disposition": "accepted_expert_only",
            "salient_proximal_metrics": [],
        },
        crisis=crisis,
    )
    assert classification == "removed"
    assert classification in R6_CLASSIFICATIONS


def test_manual_rate_atomicity_is_not_an_economic_structural_class() -> None:
    contract = next(
        item for item in build_contracts()
        if item.lever == "manual_policy_rate"
    )
    classification, _reason = _classification(
        lever=contract.lever,
        contract=contract,
        mechanism={
            "disposition": "accepted",
            "salient_proximal_metrics": ["metric.economy.policy_rate"],
        },
        crisis={"states": []},
    )
    assert contract.semantics == "state-transition"
    assert classification == "expert_only"


def test_committed_r6_evidence_is_fresh_native_and_complete() -> None:
    p2 = json.loads(P2_EVIDENCE.read_text(encoding="utf-8"))
    crisis = json.loads(CRISIS_EVIDENCE.read_text(encoding="utf-8"))
    acceptance = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
    assert p2["counts"]["executed_native_runs"] == 104
    assert crisis["counts"]["executed_native_branches"] == 704
    assert p2["counts"]["cache_hits"] == 0
    assert crisis["counts"]["cache_hits"] == 0
    assert p2["protocol"]["native_build"] == crisis["protocol"]["native_build"]
    assert acceptance["counts"]["classifications"] == {
        "conditional": 22,
        "effective": 2,
        "expert_only": 9,
        "removed": 0,
        "structural": 3,
    }


def test_committed_r6_acceptance_reproduces_from_frozen_evidence() -> None:
    p2 = json.loads(P2_EVIDENCE.read_text(encoding="utf-8"))
    crisis = json.loads(CRISIS_EVIDENCE.read_text(encoding="utf-8"))
    acceptance = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
    p3 = json.loads(
        (ROOT / "docs/policy_remediation_r5_p3_evidence_v39.json").read_text(
            encoding="utf-8"
        )
    )
    assert validate_r6_acceptance(
        acceptance,
        p2_payload=p2,
        crisis_payload=crisis,
        p3_payload=p3,
    ) == []
