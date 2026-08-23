from __future__ import annotations

from collections import Counter
import itertools

import pytest

from macro_sim.diagnostics.policy_combinations import (
    build_p5_manifest,
    fractional_package_design,
    interaction_alias_groups,
    run_p5,
)
from macro_sim.diagnostics.policy_contracts import build_contracts, build_p0_payload
from macro_sim.diagnostics.policy_crisis_effects import build_p4_manifest


def _accepted_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    p0 = build_p0_payload()
    p2 = {
        "p0_root_hash": p0["hashes"]["p0_root"],
        "hashes": {"p2_acceptance": "p2-test"},
        "reports": [
            {"lever": item.lever, "disposition": "accepted", "reason": "test"}
            for item in build_contracts()
        ],
    }
    p3 = {
        "p0_root_hash": p0["hashes"]["p0_root"],
        "accepted_crises_for_p4": ["CR_DEMAND_RECESSION"],
        "hashes": {
            "p3_manifest": "p3-manifest-test",
            "p3_acceptance": "p3-acceptance-test",
        },
        "reports": {
            "crises": [{
                "scenario_id": "CR_DEMAND_RECESSION",
                "accepted": True,
                "disposition": "accepted",
                "frozen_common_checkpoint_hashes": [],
            }],
            "states": [
                {"scenario_id": "BASE_SLACK", "accepted": True},
                {"scenario_id": "STRUCT_HIGH_POVERTY", "accepted": True},
            ],
        },
    }
    p4_manifest = build_p4_manifest(p2_payload=p2, p3_payload=p3)
    p4 = {
        "status": "accepted_with_explicit_defects",
        "p0_root_hash": p0["hashes"]["p0_root"],
        "hashes": {"p4_acceptance": "p4-acceptance-test"},
        "reports": [
            {
                **row,
                "disposition": "accepted_crisis_efficacy",
                "reason": "test",
            }
            for row in p4_manifest["matrix"]
        ],
    }
    return p2, p3, p4


def test_p5_freezes_all_nine_packages_and_only_runs_eligible_two() -> None:
    p2, p3, p4 = _accepted_inputs()
    manifest = build_p5_manifest(
        p2_payload=p2,
        p3_payload=p3,
        p4_payload=p4,
    )
    assert len(manifest["packages"]) == 9
    assert Counter(item["runnable"] for item in manifest["packages"]) == {
        False: 7,
        True: 2,
    }
    runnable = {item["package_id"]: item for item in manifest["packages"] if item["runnable"]}
    assert set(runnable) == {"recession_response", "poverty_and_employment"}
    assert all(len(item["factors"]) == 5 for item in runnable.values())
    assert all(item["design"]["resolution"] == "IV" for item in runnable.values())


def test_p5_does_not_bypass_an_accepted_scenario_component_defect() -> None:
    p2, p3, p4 = _accepted_inputs()
    report = next(
        item for item in p2["reports"] if item["lever"] == "job_guarantee"
    )
    report["disposition"] = "mechanism_defect"
    report["reason"] = "frozen failure"
    manifest = build_p5_manifest(
        p2_payload=p2,
        p3_payload=p3,
        p4_payload=p4,
    )
    recession = next(
        item for item in manifest["packages"]
        if item["package_id"] == "recession_response"
    )
    assert not recession["runnable"]
    assert any(
        item["layer"] == "P2" and item["lever"] == "job_guarantee"
        for item in recession["blockers"]
    )


def test_regular_fraction_is_balanced_and_main_effect_orthogonal() -> None:
    p2, p3, p4 = _accepted_inputs()
    manifest = build_p5_manifest(
        p2_payload=p2,
        p3_payload=p3,
        p4_payload=p4,
    )
    package = next(item for item in manifest["packages"] if item["runnable"])
    design = fractional_package_design(package["factors"])
    assert len(design) == 16
    assert len({item["arm_id"] for item in design}) == 16
    for index in range(5):
        assert Counter(item["signs"][index] for item in design) == {-1: 8, 1: 8}
    for main in range(5):
        for left, right in itertools.combinations(range(5), 2):
            dot = sum(
                arm["signs"][main] * arm["signs"][left] * arm["signs"][right]
                for arm in design
            )
            assert dot == 0


def test_regular_fraction_reports_every_pair_and_alias_group() -> None:
    p2, p3, p4 = _accepted_inputs()
    package = next(
        item for item in build_p5_manifest(
            p2_payload=p2, p3_payload=p3, p4_payload=p4
        )["packages"]
        if item["runnable"]
    )
    aliases = interaction_alias_groups(package["factors"])
    assert len(aliases) == 10
    assert all(name in group for name, group in aliases.items())
    assert any(len(group) > 1 for group in aliases.values())


def test_factor_actions_are_p4_doses_with_atomic_manual_regime_link() -> None:
    p2, p3, p4 = _accepted_inputs()
    recession = next(
        item for item in build_p5_manifest(
            p2_payload=p2, p3_payload=p3, p4_payload=p4
        )["packages"]
        if item["package_id"] == "recession_response"
    )
    manual = next(
        item for item in recession["factors"]
        if item["factor_id"] == "manual_policy_rate"
    )
    assert {item["lever"]: item["value"] for item in manual["high_actions"]} == {
        "manual_policy_rate": 0.001,
        "monetary_regime": "manual",
    }
    assert {item["lever"]: item["value"] for item in manual["low_actions"]} == {
        "manual_policy_rate": None,
        "monetary_regime": "taylor",
    }


def test_p5_formal_scale_and_worker_contracts_are_hard_gates(tmp_path) -> None:
    p2, p3, p4 = _accepted_inputs()
    with pytest.raises(ValueError, match="100,000"):
        run_p5(
            artifact_dir=tmp_path,
            p2_payload=p2,
            p3_payload=p3,
            p4_payload=p4,
            source_revision="test",
            population=99_999,
        )
    with pytest.raises(ValueError, match="eight native"):
        run_p5(
            artifact_dir=tmp_path,
            p2_payload=p2,
            p3_payload=p3,
            p4_payload=p4,
            source_revision="test",
            workers=4,
        )
