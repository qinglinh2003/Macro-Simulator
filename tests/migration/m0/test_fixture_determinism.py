from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.cpp_migration.export_phase_trace import trace_fixture
from scripts.cpp_migration.benchmarks import load_benchmark_scenarios, run_worker


ROOT = Path(__file__).resolve().parents[3]


def _expected(name: str) -> dict:
    return json.loads(
        (ROOT / f"tests/fixtures/m0/expected/{name}.json").read_text(
            encoding="utf-8"
        )
    )


def test_refactor_v124_trace_matches_reviewed_expected_digest():
    payload = trace_fixture("refactor_v124")
    expected = _expected("refactor_v124")
    assert hashlib.sha256(payload).hexdigest() == expected["phase_trace_sha256"]
    assert len(payload) == expected["phase_trace_byte_count"]
    result = run_worker(load_benchmark_scenarios()["tiny_refactor_v124"])
    assert result["semantic_result_digest"] == expected["semantic_result_digest"]


def test_world_n2_trace_matches_reviewed_expected_digest():
    payload = trace_fixture("world_n2")
    expected = _expected("world_n2")
    assert hashlib.sha256(payload).hexdigest() == expected["phase_trace_sha256"]
    assert len(payload) == expected["phase_trace_byte_count"]
