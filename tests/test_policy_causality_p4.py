from __future__ import annotations

from collections import Counter

import pytest

from macro_sim.diagnostics.policy_contracts import build_contracts, build_p0_payload
from macro_sim.diagnostics.policy_crisis_effects import (
    P4_SCENARIO_ID,
    _synthetic_interaction_run,
    build_p4_manifest,
    build_p4_matrix,
    run_p4,
)


def _accepted_inputs() -> tuple[dict[str, object], dict[str, object]]:
    p0 = build_p0_payload()
    reports = [
        {
            "lever": contract.lever,
            "disposition": "accepted",
            "reason": "test fixture",
        }
        for contract in build_contracts()
    ]
    p2 = {
        "p0_root_hash": p0["hashes"]["p0_root"],
        "hashes": {"p2_acceptance": "p2-test"},
        "reports": reports,
    }
    p3 = {
        "p0_root_hash": p0["hashes"]["p0_root"],
        "accepted_crises_for_p4": [P4_SCENARIO_ID],
        "hashes": {
            "p3_manifest": "p3-manifest-test",
            "p3_acceptance": "p3-acceptance-test",
        },
        "reports": {
            "crises": [{
                "scenario_id": P4_SCENARIO_ID,
                "accepted": True,
                "disposition": "accepted",
                "frozen_common_checkpoint_hashes": [],
            }],
        },
    }
    return p2, p3


def test_p4_matrix_closes_every_frozen_policy_cell() -> None:
    p2, p3 = _accepted_inputs()
    rows = build_p4_matrix(p2_payload=p2, p3_payload=p3)
    contracts = build_contracts()
    assert len(rows) == 102
    assert {row["lever"] for row in rows} == {item.lever for item in contracts}
    assert Counter(row["scenario_role"] for row in rows) == {
        "secondary": 46,
        "safety": 28,
        "primary": 27,
        "not_applicable": 1,
    }
    assert all(
        row["runnable"] or row["pre_experiment_disposition"]
        for row in rows
    )


def test_p4_preserves_p2_defects_and_single_country_topology_gap() -> None:
    p2, p3 = _accepted_inputs()
    p2["reports"][0]["disposition"] = "mechanism_defect"
    p2["reports"][0]["reason"] = "frozen failure"
    rows = build_p4_matrix(p2_payload=p2, p3_payload=p3)
    first = next(row for row in rows if row["lever"] == p2["reports"][0]["lever"])
    assert first["pre_experiment_disposition"] == "blocked_by_p2_defect"
    assert "frozen failure" in first["pre_experiment_reason"]
    external = [row for row in rows if row["scope"] == "external"]
    assert external
    assert all(
        not row["runnable"]
        and row["pre_experiment_disposition"] == "blocked_by_scenario_topology"
        for row in external
        if row["p2_disposition"] == "accepted"
    )


def test_primary_meaningful_doses_receive_predeclared_timing_arms() -> None:
    p2, p3 = _accepted_inputs()
    manifest = build_p4_manifest(p2_payload=p2, p3_payload=p3)
    primary = next(
        row for row in manifest["matrix"]
        if row["runnable"]
        and row["scenario_role"] == "primary"
        and any(arm["dose_class"] == "meaningful" for arm in row["arms"])
    )
    local = next(arm for arm in primary["arms"] if arm["dose_class"] == "local")
    meaningful = next(
        arm for arm in primary["arms"] if arm["dose_class"] == "meaningful"
    )
    assert local["timings"] == ["immediate"]
    assert meaningful["timings"] == ["immediate", "delayed_7", "late_30"]


def test_p4_rejects_unaccepted_or_drifted_p3_input() -> None:
    p2, p3 = _accepted_inputs()
    p3["accepted_crises_for_p4"] = []
    with pytest.raises(ValueError, match="did not accept"):
        build_p4_matrix(p2_payload=p2, p3_payload=p3)
    _p2, p3 = _accepted_inputs()
    p3["p0_root_hash"] = "drifted"
    with pytest.raises(ValueError, match="P0 root"):
        build_p4_matrix(p2_payload=p2, p3_payload=p3)


def test_p4_formal_scale_and_worker_contracts_are_hard_gates(tmp_path) -> None:
    p2, p3 = _accepted_inputs()
    with pytest.raises(ValueError, match="100,000"):
        run_p4(
            artifact_dir=tmp_path,
            p2_payload=p2,
            p3_payload=p3,
            source_revision="test",
            population=99_999,
        )
    with pytest.raises(ValueError, match="eight native"):
        run_p4(
            artifact_dir=tmp_path,
            p2_payload=p2,
            p3_payload=p3,
            source_revision="test",
            workers=4,
        )


def _run(values: list[float]) -> dict[str, object]:
    ticks = list(range(1, len(values) + 1))
    rows = [
        {"_tick": tick, "metric.economy.real_output": value}
        for tick, value in zip(ticks, values, strict=True)
    ]
    from dataclasses import asdict

    from macro_sim.diagnostics.config_experiment import summarize_metric_series

    return {
        "metric_series": {
            "metric.economy.real_output": {"ticks": ticks, "values": values},
        },
        "metric_summaries": {
            name: asdict(summary)
            for name, summary in summarize_metric_series(rows).items()
        },
    }


def test_crisis_interaction_is_difference_in_differences() -> None:
    interaction = _synthetic_interaction_run(
        _run([10.0, 10.0, 10.0]),
        _run([8.0, 8.0, 8.0]),
        _run([11.0, 11.0, 11.0]),
        _run([10.0, 10.0, 10.0]),
    )
    values = interaction["metric_series"]["metric.economy.real_output"]["values"]
    assert values == [1.0, 1.0, 1.0]
