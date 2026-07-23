from __future__ import annotations

import json
from pathlib import Path

from scripts.cpp_migration.common import canonical_json_bytes
from scripts.cpp_migration.fixtures import (
    build_fixture_manifest,
    load_tape_bundle,
)


ROOT = Path(__file__).resolve().parents[3]


def test_checked_fixture_manifest_is_current_and_complete():
    path = ROOT / "tests/fixtures/m0/manifests/fixtures.json"
    actual = path.read_bytes()
    expected = build_fixture_manifest()
    assert actual == canonical_json_bytes(expected)
    assert {row["tier"] for row in expected["rows"]} == {
        f"F{index}" for index in range(12)
    }
    assert len(expected["aggregate_sha256"]) == 64
    assert all(len(row["config_contract_sha256"]) == 64 for row in expected["rows"])


def test_policy_shock_action_and_realization_tapes_are_typed_and_current():
    path = ROOT / "tests/fixtures/m0/tapes/bundle.json"
    checked = json.loads(path.read_text(encoding="utf-8"))
    expected = load_tape_bundle()
    assert path.read_bytes() == canonical_json_bytes(expected)
    assert len(checked["policy"]) == 5
    assert len(checked["shock"]["specs"]) == 8
    assert checked["action"]
    assert checked["realization"]
