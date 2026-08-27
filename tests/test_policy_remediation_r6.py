"""R6 single-policy calibration design and classification tests."""

from __future__ import annotations

import json
from pathlib import Path

from macro_sim.diagnostics.policy_contracts import build_contracts, build_p0_payload
from macro_sim.diagnostics.policy_crisis_effects import _row_arm_lookup
from scripts.policy_remediation_r6_lib import (
    R6_CANDIDATES,
    R6_CLASSIFICATIONS,
    _classification,
    build_r6_design,
)


ROOT = Path(__file__).resolve().parents[1]


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

