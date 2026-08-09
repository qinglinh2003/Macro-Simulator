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
