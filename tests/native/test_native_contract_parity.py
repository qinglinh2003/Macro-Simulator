from __future__ import annotations

import json
import math
from pathlib import Path
import runpy

import macro_sim._native as native


ROOT = Path(__file__).resolve().parents[2]


def _value(item: dict):
    if item["kind"] == "nonfinite":
        return math.nan
    return item["value"]


def test_invalid_corpus_matches_generated_python_and_native_binding() -> None:
    generated = runpy.run_path(
        str(ROOT / "schemas/m1/generated/python/contracts.py")
    )
    corpus = json.loads(
        (ROOT / "schemas/m1/invalid_contract_cases.json").read_text(
            encoding="utf-8"
        )
    )
    for case in corpus["cases"]:
        value = _value(case["input"])
        python_result = generated["validate_scalar"](case["contract_id"], value)
        native_result = native.validate_scalar(case["contract_id"], value)
        assert python_result == native_result == (False, case["expected_code"])


def test_native_binding_exposes_checked_philox_known_answer() -> None:
    assert native.philox_block((0, 0, 0, 0), (0, 0)) == (
        1713891541,
        3781805453,
        3159862348,
        2600524760,
    )
