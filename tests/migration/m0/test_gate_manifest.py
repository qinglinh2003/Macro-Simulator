from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts.cpp_migration.common import GitMetadata, SchemaError
from scripts.cpp_migration.gates import (
    load_gate_manifest,
    run_gates,
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
    assert [gate.id for gate in manifest.gates] == [
        "framework.tests",
        "inventory.check",
        "inventory.tests",
        "trace.tests",
        "trace.repeatability",
        "fixtures.contracts",
        "fixtures.integration",
        "benchmark.smoke",
        "acceptance.tests",
        "clients.contracts",
        "clients.integration",
        "milestone.references",
        "milestone.desktop-smoke",
        "milestone.full-regression",
        "milestone.freeze",
    ]


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


def test_timeout_bytes_are_recorded_as_canonical_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    path = _write(tmp_path, [_gate("timeout.check")])
    manifest = load_gate_manifest(path)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=10,
            output=b"partial \xff output",
            stderr=b"deadline exceeded",
        )

    monkeypatch.setattr("scripts.cpp_migration.gates.is_ancestor", lambda commit: True)
    monkeypatch.setattr(
        "scripts.cpp_migration.gates.git_metadata",
        lambda: GitMetadata(commit=ORACLE, dirty=False),
    )
    monkeypatch.setattr(
        "scripts.cpp_migration.gates.environment_metadata",
        lambda: {},
    )
    monkeypatch.setattr("scripts.cpp_migration.gates.subprocess.run", raise_timeout)
    artifact_root = tmp_path / "artifacts"
    summary = run_gates(manifest, manifest.gates, artifact_root=artifact_root)

    assert summary["status"] == "failed"
    result = json.loads(
        (artifact_root / "timeout.check.json").read_text(encoding="utf-8")
    )
    assert result["failure_class"] == "timeout"
    assert result["stdout"] == "partial \ufffd output"
    assert result["stderr"] == "deadline exceeded"
