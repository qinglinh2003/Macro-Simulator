from __future__ import annotations

import json
import math
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[2]


def _input_value(item: dict):
    kind = item["kind"]
    if kind == "nonfinite":
        return math.nan
    return item["value"]


def test_generated_contracts_are_sorted_unique_and_complete() -> None:
    contracts = json.loads(
        (ROOT / "schemas/m1/generated/contracts.json").read_text(encoding="utf-8")
    )
    ids = [item["id"] for item in contracts["rows"]]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids)) == 1538
    assert contracts["family_counts"] == {
        "checkpoint": 4,
        "config": 453,
        "controller": 45,
        "event": 24,
        "external_policy": 14,
        "invariant": 13,
        "metric": 551,
        "observation": 143,
        "phase": 16,
        "policy": 88,
        "protocol": 13,
        "rng": 126,
        "scenario": 40,
        "shock": 8,
    }


def test_python_validator_rejects_checked_invalid_corpus() -> None:
    generated = runpy.run_path(
        str(ROOT / "schemas/m1/generated/python/contracts.py")
    )
    corpus = json.loads(
        (ROOT / "schemas/m1/invalid_contract_cases.json").read_text(
            encoding="utf-8"
        )
    )
    validate_scalar = generated["validate_scalar"]
    for case in corpus["cases"]:
        accepted, code = validate_scalar(
            case["contract_id"],
            _input_value(case["input"]),
        )
        assert accepted is False, case["id"]
        assert code == case["expected_code"], case["id"]


def test_aliases_resolve_to_the_same_contract() -> None:
    generated = runpy.run_path(
        str(ROOT / "schemas/m1/generated/python/contracts.py")
    )
    validate_scalar = generated["validate_scalar"]
    assert validate_scalar("policy.policy_rate_override", None) == validate_scalar(
        "policy.manual_policy_rate",
        None,
    )
