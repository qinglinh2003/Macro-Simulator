from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/m1"))

from final_audit import (  # noqa: E402
    BASE_COMMIT,
    LOCK_PATH,
)
from scripts.cpp_migration.gates import load_gate_manifest, select_gates  # noqa: E402


def test_m1_source_lock_matches_every_frozen_input() -> None:
    checked = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert checked["base_commit"] == BASE_COMMIT
    assert len(checked["files"]) >= 40
    milestone = "m1-native-foundation-v33"
    mapping: dict[str, str] = {}
    for item in checked["files"]:
        content = subprocess.run(
            ["git", "show", f"{milestone}:{item['path']}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        digest = sha256(content).hexdigest()
        assert digest == item["sha256"]
        assert len(content) == item["byte_count"]
        mapping[item["path"]] = digest
    aggregate_input = "".join(
        f"{path}\0{mapping[path]}\n" for path in sorted(mapping)
    ).encode()
    assert sha256(aggregate_input).hexdigest() == checked["aggregate_sha256"]


def test_m1_gate_graph_has_all_acceptance_layers() -> None:
    manifest = load_gate_manifest(ROOT / "schemas/m1/manifests/gates.yaml")
    assert manifest.oracle_commit == BASE_COMMIT
    ids = {gate.id for gate in manifest.gates}
    assert {
        "native.debug",
        "native.release",
        "native.sanitizers",
        "artifacts.installed",
        "oracle.full-regression",
        "milestone.m1-audit",
        "release.m1-audit",
    } <= ids
    milestone = select_gates(manifest, gate_class="milestone")
    assert milestone[-1].id == "milestone.m1-audit"
    assert "oracle.full-regression" in {gate.id for gate in milestone}


def test_m1_native_scope_contains_no_economic_phase() -> None:
    sources = {
        path.name for path in (ROOT / "native/src").glob("*.cpp")
    }
    assert sources == {
        "c_api.cpp",
        "engine_session.cpp",
        "python_bindings.cpp",
        "rng.cpp",
        "version.cpp",
    }
