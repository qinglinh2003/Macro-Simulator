from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.cpp_migration.common import SchemaError
from scripts.cpp_migration.gates import (
    load_gate_manifest,
    select_gates,
)


ORACLE = "c0adcf1f8ea7f69cad28b92e27c9a4509dfdac23"


def _gate(gate_id: str, gate_class: str = "pr", dependencies: list[str] | None = None):
    return {
        "id": gate_id,
        "class": gate_class,
        "command": ["python", "-c", "pass"],
        "cwd": ".",
        "dependencies": dependencies or [],
        "timeout_seconds": 10,
        "owner": "test",
    }


def _write(tmp_path: Path, gates: list[dict]) -> Path:
    path = tmp_path / "gates.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "m0-gate-manifest-v1",
                "oracle_commit": ORACLE,
                "gates": gates,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_checked_manifest_loads_and_lists_framework_gate():
    root = Path(__file__).resolve().parents[3]
    manifest = load_gate_manifest(root / "schemas/m0/manifests/gates.yaml")
    assert manifest.oracle_commit == ORACLE
    assert [gate.id for gate in manifest.gates] == ["framework.tests"]


def test_duplicate_gate_id_is_rejected(tmp_path: Path):
    path = _write(tmp_path, [_gate("same"), _gate("same")])
    with pytest.raises(SchemaError, match="duplicate"):
        load_gate_manifest(path)


def test_unknown_dependency_is_rejected(tmp_path: Path):
    path = _write(tmp_path, [_gate("child", dependencies=["missing"])])
    with pytest.raises(SchemaError, match="unknown dependencies"):
        load_gate_manifest(path)


def test_unknown_gate_field_is_rejected(tmp_path: Path):
    gate = _gate("valid")
    gate["typo_field"] = True
    path = _write(tmp_path, [gate])
    with pytest.raises(SchemaError, match="unknown fields"):
        load_gate_manifest(path)


def test_dependency_cycle_is_rejected(tmp_path: Path):
    path = _write(
        tmp_path,
        [
            _gate("first", dependencies=["second"]),
            _gate("second", dependencies=["first"]),
        ],
    )
    with pytest.raises(SchemaError, match="cycle"):
        load_gate_manifest(path)


def test_class_selection_includes_lower_classes_and_dependencies(tmp_path: Path):
    path = _write(
        tmp_path,
        [
            _gate("base", "pr"),
            _gate("nightly.check", "nightly", ["base"]),
            _gate("milestone.check", "milestone", ["nightly.check"]),
            _gate("release.check", "release", ["milestone.check"]),
        ],
    )
    manifest = load_gate_manifest(path)
    assert [gate.id for gate in select_gates(manifest, gate_class="nightly")] == [
        "base",
        "nightly.check",
    ]
    assert [
        gate.id
        for gate in select_gates(
            manifest,
            gate_class="milestone",
            only=("milestone",),
        )
    ] == ["base", "nightly.check", "milestone.check"]
