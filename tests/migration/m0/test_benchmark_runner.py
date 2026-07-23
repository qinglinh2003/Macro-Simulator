from __future__ import annotations

from pathlib import Path

from scripts.cpp_migration.benchmarks import (
    assemble_result,
    load_benchmark_scenarios,
    run_worker,
    validate_benchmark_result,
)


EXPECTED_TINY_DIGEST = (
    "9658208a7f4cadaccdfce42fce60c38884f10bf2a75ef0288124dfc548495bb5"
)


def test_benchmark_matrix_contains_all_frozen_scenarios():
    scenarios = load_benchmark_scenarios()
    assert list(scenarios) == [
        "tiny_refactor_v124",
        "small_closed_daily",
        "medium_closed_daily",
        "large_closed_daily",
        "full_playable_10k",
        "m4_v0_cash_loop",
        "m4_v1_capital_fiscal",
        "world_three_country",
        "rl_fiscal_v1_episode",
        "desktop_e2e",
        "checkpoint_full",
        "marriage_400_3200",
        "employer_roster_scale",
        "history_ten_year",
        "world_scale_2_256",
    ]
    assert scenarios["full_playable_10k"]["population"] == 10_000
    assert scenarios["full_playable_10k"]["ticks"] == 365


def test_tiny_worker_matches_frozen_fixture_semantics():
    scenario = load_benchmark_scenarios()["tiny_refactor_v124"]
    sample = run_worker(scenario)
    assert sample["semantic_result_digest"] == EXPECTED_TINY_DIGEST
    assert sample["operations"] == 80
    assert sample["checkpoint_bytes"] > 0


def test_result_assembly_preserves_raw_samples_and_explicit_metadata():
    scenario = load_benchmark_scenarios()["tiny_refactor_v124"]
    sample = run_worker(scenario)
    result = assemble_result(scenario, [sample], command=["benchmark-test"])
    validate_benchmark_result(result)
    assert result["raw_samples_ns"]["advance"] == [sample["advance_ns"]]
    assert result["statistics_ns"]["advance"]["median"] == sample["advance_ns"]
    assert result["semantic_result_digest"] == EXPECTED_TINY_DIGEST
    assert {"physical_cores", "memory_bytes", "power_mode"} <= set(
        result["environment"]
    )
    assert result["invariant_status"] == "passed"
