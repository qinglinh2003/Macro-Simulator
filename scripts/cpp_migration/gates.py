"""Validated gate-manifest loading, selection, and execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Any

import yaml

from .common import (
    M0Error,
    REPO_ROOT,
    SchemaError,
    canonical_json_bytes,
    environment_metadata,
    git_metadata,
    is_ancestor,
    require_unique_ids,
    validate_stable_id,
)


GATE_CLASSES = ("pr", "nightly", "milestone", "release")
GATE_KEYS = frozenset(
    {
        "id",
        "class",
        "command",
        "cwd",
        "dependencies",
        "timeout_seconds",
        "owner",
        "artifacts",
        "fixture_ids",
        "platform_profiles",
        "process_count",
        "thread_count",
        "repetitions",
        "seeds",
        "threshold_ref",
    }
)


@dataclass(frozen=True)
class Gate:
    id: str
    gate_class: str
    command: tuple[str, ...]
    cwd: str
    dependencies: tuple[str, ...]
    timeout_seconds: int
    owner: str
    artifacts: tuple[str, ...]
    fixture_ids: tuple[str, ...]
    platform_profiles: tuple[str, ...]
    process_count: int
    thread_count: int
    repetitions: int
    seeds: tuple[int, ...]
    threshold_ref: str | None


@dataclass(frozen=True)
class GateManifest:
    schema_version: str
    oracle_commit: str
    gates: tuple[Gate, ...]

    @property
    def by_id(self) -> dict[str, Gate]:
        return {gate.id: gate for gate in self.gates}


def _expect_sequence(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaError(f"{field} must be a list")
    return value


def _expect_positive_int(value: Any, *, field: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(f"{field} must be an integer")
    if value < (0 if allow_zero else 1):
        raise SchemaError(f"{field} is out of range: {value}")
    return value


def _subprocess_output_text(value: str | bytes | None) -> str:
    """Normalize subprocess output, including TimeoutExpired byte payloads."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def load_gate_manifest(path: Path) -> GateManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SchemaError(f"cannot load gate manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SchemaError("gate manifest root must be an object")
    unknown_root = set(raw) - {"schema_version", "oracle_commit", "gates"}
    if unknown_root:
        raise SchemaError(f"unknown gate manifest fields: {sorted(unknown_root)}")
    if raw.get("schema_version") != "m0-gate-manifest-v1":
        raise SchemaError("unsupported gate manifest schema_version")
    oracle_commit = raw.get("oracle_commit")
    if not isinstance(oracle_commit, str) or len(oracle_commit) != 40:
        raise SchemaError("oracle_commit must be a full 40-character commit")

    rows = _expect_sequence(raw.get("gates"), field="gates")
    require_unique_ids(rows)
    gates: list[Gate] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SchemaError(f"gates[{index}] must be an object")
        unknown = set(row) - GATE_KEYS
        if unknown:
            raise SchemaError(f"gates[{index}] has unknown fields: {sorted(unknown)}")
        gate_class = row.get("class")
        if gate_class not in GATE_CLASSES:
            raise SchemaError(f"gates[{index}].class is invalid: {gate_class!r}")
        command_raw = _expect_sequence(row.get("command"), field=f"gates[{index}].command")
        if not command_raw or not all(isinstance(item, str) and item for item in command_raw):
            raise SchemaError(f"gates[{index}].command must contain strings")
        dependencies = tuple(
            validate_stable_id(item, field=f"gates[{index}].dependencies")
            for item in _expect_sequence(
                row.get("dependencies", []),
                field=f"gates[{index}].dependencies",
            )
        )
        seeds = tuple(
            _expect_positive_int(
                item,
                field=f"gates[{index}].seeds",
                allow_zero=True,
            )
            for item in _expect_sequence(row.get("seeds", []), field=f"gates[{index}].seeds")
        )
        owner = row.get("owner")
        if not isinstance(owner, str) or not owner:
            raise SchemaError(f"gates[{index}].owner must be a non-empty string")
        cwd = row.get("cwd", ".")
        if not isinstance(cwd, str) or Path(cwd).is_absolute() or ".." in Path(cwd).parts:
            raise SchemaError(f"gates[{index}].cwd must stay inside the repository")
        gates.append(
            Gate(
                id=validate_stable_id(row["id"]),
                gate_class=gate_class,
                command=tuple(command_raw),
                cwd=cwd,
                dependencies=dependencies,
                timeout_seconds=_expect_positive_int(
                    row.get("timeout_seconds", 300),
                    field=f"gates[{index}].timeout_seconds",
                ),
                owner=owner,
                artifacts=tuple(
                    str(item)
                    for item in _expect_sequence(
                        row.get("artifacts", []),
                        field=f"gates[{index}].artifacts",
                    )
                ),
                fixture_ids=tuple(
                    validate_stable_id(item, field=f"gates[{index}].fixture_ids")
                    for item in _expect_sequence(
                        row.get("fixture_ids", []),
                        field=f"gates[{index}].fixture_ids",
                    )
                ),
                platform_profiles=tuple(
                    str(item)
                    for item in _expect_sequence(
                        row.get("platform_profiles", []),
                        field=f"gates[{index}].platform_profiles",
                    )
                ),
                process_count=_expect_positive_int(
                    row.get("process_count", 1),
                    field=f"gates[{index}].process_count",
                ),
                thread_count=_expect_positive_int(
                    row.get("thread_count", 1),
                    field=f"gates[{index}].thread_count",
                ),
                repetitions=_expect_positive_int(
                    row.get("repetitions", 1),
                    field=f"gates[{index}].repetitions",
                ),
                seeds=seeds,
                threshold_ref=(
                    None if row.get("threshold_ref") is None else str(row["threshold_ref"])
                ),
            )
        )
    manifest = GateManifest(
        schema_version=raw["schema_version"],
        oracle_commit=oracle_commit,
        gates=tuple(gates),
    )
    validate_gate_graph(manifest)
    return manifest


def validate_gate_graph(manifest: GateManifest) -> None:
    by_id = manifest.by_id
    for gate in manifest.gates:
        unknown = set(gate.dependencies) - set(by_id)
        if unknown:
            raise SchemaError(f"{gate.id}: unknown dependencies {sorted(unknown)}")
        if gate.id in gate.dependencies:
            raise SchemaError(f"{gate.id}: gate cannot depend on itself")

    state: dict[str, int] = {}

    def visit(gate_id: str, stack: tuple[str, ...]) -> None:
        marker = state.get(gate_id, 0)
        if marker == 2:
            return
        if marker == 1:
            raise SchemaError(f"gate dependency cycle: {' -> '.join((*stack, gate_id))}")
        state[gate_id] = 1
        for dependency in by_id[gate_id].dependencies:
            visit(dependency, (*stack, gate_id))
        state[gate_id] = 2

    for gate in manifest.gates:
        visit(gate.id, ())


def select_gates(
    manifest: GateManifest,
    *,
    gate_class: str,
    only: tuple[str, ...] = (),
) -> tuple[Gate, ...]:
    if gate_class not in GATE_CLASSES:
        raise SchemaError(f"invalid gate class: {gate_class}")
    maximum = GATE_CLASSES.index(gate_class)
    selected = {
        gate.id
        for gate in manifest.gates
        if GATE_CLASSES.index(gate.gate_class) <= maximum
        and (not only or any(token in gate.id for token in only))
    }
    by_id = manifest.by_id

    def add_dependencies(gate_id: str) -> None:
        for dependency in by_id[gate_id].dependencies:
            if dependency not in selected:
                selected.add(dependency)
                add_dependencies(dependency)

    for gate_id in tuple(selected):
        add_dependencies(gate_id)

    ordered: list[Gate] = []
    emitted: set[str] = set()

    def emit(gate_id: str) -> None:
        if gate_id in emitted:
            return
        for dependency in by_id[gate_id].dependencies:
            emit(dependency)
        emitted.add(gate_id)
        ordered.append(by_id[gate_id])

    for gate in manifest.gates:
        if gate.id in selected:
            emit(gate.id)
    return tuple(ordered)


def run_gates(
    manifest: GateManifest,
    gates: tuple[Gate, ...],
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    if not is_ancestor(manifest.oracle_commit):
        raise M0Error(
            f"oracle commit {manifest.oracle_commit} is not an ancestor of HEAD"
        )
    artifact_root.mkdir(parents=True, exist_ok=True)
    git = git_metadata()
    results: list[dict[str, Any]] = []
    failed: set[str] = set()

    def failure_class(gate_id: str) -> str:
        prefix = gate_id.split(".", 1)[0]
        return {
            "framework": "schema_contract",
            "inventory": "inventory",
            "trace": "determinism",
            "fixtures": "semantic",
            "benchmark": "performance",
            "acceptance": "statistical",
            "clients": "client",
            "milestone": "tool_error",
        }.get(prefix, "tool_error")

    for gate in gates:
        blocked_by = [item for item in gate.dependencies if item in failed]
        if blocked_by:
            failed.add(gate.id)
            results.append(
                {
                    "id": gate.id,
                    "status": "blocked",
                    "blocked_by": blocked_by,
                    "failure_class": "dependency",
                }
            )
            continue
        started = time.perf_counter_ns()
        try:
            completed = subprocess.run(
                list(gate.command),
                cwd=(REPO_ROOT / gate.cwd).resolve(),
                capture_output=True,
                text=True,
                timeout=gate.timeout_seconds,
            )
            duration_ns = time.perf_counter_ns() - started
            status = "passed" if completed.returncode == 0 else "failed"
            if status == "failed":
                failed.add(gate.id)
            result = {
                "id": gate.id,
                "status": status,
                "returncode": completed.returncode,
                "duration_ns": duration_ns,
                "failure_class": (
                    None if status == "passed" else failure_class(gate.id)
                ),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            failed.add(gate.id)
            result = {
                "id": gate.id,
                "status": "failed",
                "returncode": None,
                "duration_ns": time.perf_counter_ns() - started,
                "failure_class": "timeout",
                "stdout": _subprocess_output_text(exc.stdout),
                "stderr": _subprocess_output_text(exc.stderr),
            }
        results.append(result)
        (artifact_root / f"{gate.id}.json").write_bytes(canonical_json_bytes(result))

    summary = {
        "schema_version": "m0-gate-run-v1",
        "oracle_commit": manifest.oracle_commit,
        "current_commit": git.commit,
        "dirty": git.dirty,
        "environment": environment_metadata(),
        "results": results,
        "status": "failed" if failed else "passed",
    }
    (artifact_root / "summary.json").write_bytes(canonical_json_bytes(summary))
    return summary
