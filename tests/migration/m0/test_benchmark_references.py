from __future__ import annotations

import json
from pathlib import Path

from scripts.cpp_migration.benchmarks import (
    load_benchmark_scenarios,
    validate_benchmark_result,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_IDS = (
    "tiny_refactor_v124",
    "full_playable_10k",
    "m4_v0_cash_loop",
    "m4_v1_capital_fiscal",
)


def test_checked_reference_results_are_valid_and_semantically_distinct():
    scenarios = load_benchmark_scenarios()
    digests = {}
    for scenario_id in REFERENCE_IDS:
        path = ROOT / f"benchmarks/results/m0/reference/{scenario_id}.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        validate_benchmark_result(value)
        assert scenario_id in scenarios
        assert value["scenario_id"] == scenario_id
        assert value["repository"]["dirty"] is False
        assert value["invariant_status"] == "passed"
        assert value["raw_samples_ns"]["advance"]
        digests[scenario_id] = value["semantic_result_digest"]
    assert len(set(digests.values())) == len(digests)
