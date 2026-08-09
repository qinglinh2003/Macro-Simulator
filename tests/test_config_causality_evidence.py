from __future__ import annotations

from macro_sim.diagnostics.config_evidence import build_evidence_ledger


def _contract(field: str, role: str = "causal_treatment") -> dict:
    return {
        "field_id": f"config.{field}",
        "field_name": field,
        "module": "test_module",
        "experiment_role": role,
    }


def _arm(result: str, *, silent: bool = False) -> dict:
    return {
        "mechanism_silent": silent,
        "direction_checks": {"metric.test": {"result": result}},
    }


def _payload(field: str, arms: list[dict], *, seeds: int = 4, days: int = 365) -> dict:
    return {
        "population_per_country": 100_000,
        "seeds": list(range(seeds)),
        "stage": "formal",
        "reports": [
            {"contract": {"field_name": field}, "days": days, "arms": arms}
        ],
    }


def test_evidence_ledger_distinguishes_complete_partial_and_excluded() -> None:
    contracts = [
        _contract("complete"),
        _contract("partial"),
        _contract("missing"),
        _contract("policy", "excluded_policy"),
    ]
    reports = [
        ("complete.json", _payload("complete", [_arm("pass"), _arm("pass_heterogeneous")])),
        ("partial.json", _payload("partial", [_arm("pass"), _arm("inconclusive")])),
    ]
    payload = build_evidence_ledger(contracts, reports)
    rows = {row["field_name"]: row for row in payload["rows"]}
    assert rows["complete"]["status"] == "formal_complete"
    assert rows["partial"]["status"] == "formal_partial"
    assert rows["partial"]["resolved_arm_count"] == 1
    assert rows["partial"]["silent_arm_count"] == 0
    assert rows["partial"]["inconclusive_arm_count"] == 1
    assert rows["partial"]["direction_failure_arm_count"] == 0
    assert rows["missing"]["status"] == "no_evidence"
    assert rows["policy"]["status"] == "excluded_policy"


def test_evidence_ledger_ignores_small_population_reports() -> None:
    report = _payload("field", [_arm("pass")])
    report["population_per_country"] = 10_000
    payload = build_evidence_ledger([_contract("field")], [("small.json", report)])
    assert payload["rows"][0]["status"] == "no_evidence"


def test_evidence_ledger_prefers_longer_equally_strong_report() -> None:
    reports = [
        ("short.json", _payload("field", [_arm("inconclusive")], days=90)),
        ("long.json", _payload("field", [_arm("inconclusive")], days=7_300)),
    ]
    payload = build_evidence_ledger([_contract("field")], reports)
    row = payload["rows"][0]
    assert row["source"] == "long.json"
    assert row["days"] == 7_300


def test_evidence_ledger_does_not_call_unjudged_arm_silent() -> None:
    arm = {"stability_failure": True, "direction_checks": None}
    payload = build_evidence_ledger([_contract("field")], [("failed.json", _payload("field", [arm]))])
    row = payload["rows"][0]
    assert row["status"] == "formal_unresolved"
    assert row["silent_arm_count"] == 0
    assert row["stability_failure_arm_count"] == 1
    assert row["unjudged_arm_count"] == 1


def test_evidence_ledger_counts_explicit_direction_failures() -> None:
    payload = build_evidence_ledger(
        [_contract("field")], [("failed.json", _payload("field", [_arm("fail")]))]
    )
    row = payload["rows"][0]
    assert row["status"] == "formal_unresolved"
    assert row["direction_failure_arm_count"] == 1
    assert row["inconclusive_arm_count"] == 0


def test_evidence_ledger_labels_single_seed_effect_as_pilot_unresolved() -> None:
    payload = build_evidence_ledger(
        [_contract("field")],
        [("pilot.json", _payload("field", [_arm("inconclusive")], seeds=1))],
    )
    assert payload["rows"][0]["status"] == "pilot_unresolved"


def test_evidence_ledger_rejects_a_stale_causal_contract() -> None:
    contract = {
        **_contract("field"),
        "scope": "root",
        "baseline_value": 1.0,
        "treatment_values": (0.5,),
        "activation_scenario": "pressure",
        "expected_directions": {"metric.test": "increase"},
        "direction_statistics": {"metric.test": "cumulative"},
    }
    report = _payload("field", [_arm("pass")])
    report["reports"][0]["contract"] = {
        **contract,
        "expected_directions": {"metric.test": "decrease"},
    }
    payload = build_evidence_ledger([contract], [("stale.json", report)])
    assert payload["rows"][0]["status"] == "no_evidence"


def test_evidence_ledger_accepts_catalog_growth_for_same_estimand() -> None:
    contract = {
        **_contract("field"),
        "scope": "root",
        "baseline_value": 1.0,
        "treatment_values": (0.5,),
        "activation_scenario": "pressure",
        "expected_directions": {"metric.test": "increase"},
        "direction_statistics": {"metric.test": "post_burnin_mean"},
        "primary_metrics": ("metric.test", "metric.new_spillover"),
    }
    report = _payload("field", [_arm("pass")], days=90)
    report["reports"][0]["contract"] = {
        **contract,
        "primary_metrics": ["metric.test"],
        "horizon_days": 90,
    }
    payload = build_evidence_ledger([contract], [("compatible.json", report)])
    assert payload["rows"][0]["status"] == "formal_complete"


def test_evidence_ledger_keys_duplicate_names_by_full_field_id() -> None:
    root = _contract("shared")
    nested = {
        **_contract("shared", "excluded_non_treatment"),
        "field_id": "config.social.shared",
    }
    report = _payload("shared", [_arm("pass")])
    report["reports"][0]["contract"]["field_id"] = root["field_id"]
    payload = build_evidence_ledger(
        [root, nested], [("root.json", report)]
    )
    rows = {row["field_id"]: row for row in payload["rows"]}
    assert rows["config.shared"]["status"] == "formal_complete"
    assert rows["config.social.shared"]["status"] == "excluded_non_treatment"
