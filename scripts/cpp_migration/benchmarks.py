"""Fresh-process Python benchmark scenarios and result assembly."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

import numpy as np
import yaml

from macro_sim.checkpoint import load_checkpoint, save_checkpoint, state_digest
from macro_sim.config import Config
from macro_sim.desktop.runtime import SimulationRuntime
from macro_sim.economy import Economy
from macro_sim.rl.envs import (
    FiscalStabilizationConfig,
    FiscalStabilizationEnvFactory,
)
from macro_sim.world import World

from .common import (
    REPO_ROOT,
    SchemaError,
    canonical_json_bytes,
    environment_metadata,
    git_metadata,
    sha256_bytes,
    sha256_file,
    validate_stable_id,
)


SCENARIO_PATH = REPO_ROOT / "schemas/m0/manifests/benchmark_scenarios.yaml"


def load_benchmark_scenarios() -> dict[str, dict[str, Any]]:
    try:
        raw = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SchemaError(f"cannot load benchmark scenarios: {exc}") from exc
    if raw.get("schema_version") != "python-benchmark-scenarios-v1":
        raise SchemaError("unsupported benchmark scenario schema")
    rows = raw.get("scenarios")
    if not isinstance(rows, list):
        raise SchemaError("benchmark scenarios must be an array")
    result = {}
    for row in rows:
        scenario = dict(row)
        scenario_id = validate_stable_id(scenario["id"])
        if scenario_id in result:
            raise SchemaError(f"duplicate benchmark scenario {scenario_id}")
        for field in (
            "population",
            "firms_c",
            "firms_k",
            "banks",
            "economies",
            "ticks",
            "warmup_ticks",
            "seed",
        ):
            value = scenario[field]
            minimum = 0 if field in {"firms_k", "warmup_ticks", "seed"} else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise SchemaError(f"{scenario_id}: invalid {field}")
        if scenario["kind"] not in {"economy", "world", "rl", "desktop", "checkpoint"}:
            raise SchemaError(f"{scenario_id}: unsupported kind")
        result[scenario_id] = scenario
    return result


def _config(scenario: dict[str, Any], *, seed: int) -> Config:
    common = {
        "seed": seed,
        "n_households": scenario["population"],
        "n_ticks": scenario["ticks"] + scenario["warmup_ticks"] + 1,
    }
    factory = scenario["config_factory"]
    if factory == "base":
        return Config(n_firms=scenario["firms_c"], **common)
    common.update(
        {
            "n_firms_c": scenario["firms_c"],
            "n_firms_k": scenario["firms_k"],
            "n_banks": scenario["banks"],
        }
    )
    constructor = getattr(Config, factory, None)
    if not callable(constructor):
        raise SchemaError(f"unknown Config factory {factory}")
    return constructor(**common)


def _build_workload(scenario: dict[str, Any]):
    kind = scenario["kind"]
    seed = scenario["seed"]
    if kind in {"economy", "checkpoint"}:
        return Economy(_config(scenario, seed=seed))
    if kind == "world":
        configs = [
            _config(scenario, seed=seed + index) for index in range(scenario["economies"])
        ]
        return World(
            configs,
            base_seed=seed,
            couple=scenario["economies"] > 1,
        )
    if kind == "rl":
        config = FiscalStabilizationConfig(
            horizon_ticks=scenario["ticks"],
            decision_period_ticks=15,
            n_households=scenario["population"],
            n_firms_c=scenario["firms_c"],
            n_firms_k=scenario["firms_k"],
            n_banks=scenario["banks"],
        )
        return FiscalStabilizationEnvFactory(config)(seed)
    if kind == "desktop":
        return SimulationRuntime(seed=seed)
    raise SchemaError(f"unsupported benchmark kind {kind}")


def _advance(workload: Any, scenario: dict[str, Any]) -> int:
    ticks = scenario["ticks"]
    kind = scenario["kind"]
    if kind == "rl":
        workload.reset(seed=scenario["seed"])
        decisions = 0
        done = False
        while not done:
            _, _, terminated, truncated, _ = workload.step(
                np.asarray((1,), dtype=np.int64)
            )
            decisions += 1
            done = terminated or truncated
        return decisions
    if kind == "desktop":
        for _ in range(ticks):
            workload.handle({"command": "snapshot"})
        return ticks
    for _ in range(ticks):
        workload.step()
    return ticks


def _warmup(workload: Any, scenario: dict[str, Any]) -> None:
    if scenario["kind"] not in {"economy", "world", "checkpoint"}:
        return
    for _ in range(scenario["warmup_ticks"]):
        workload.step()


def _snapshot_digest(workload: Any, scenario: dict[str, Any]) -> str:
    if scenario["kind"] == "rl":
        value = {
            "boundary_tick": workload.session.boundary_tick,
            "event_head": workload.session.events.head_hash,
        }
    elif scenario["kind"] == "desktop":
        value = workload.snapshot()
    else:
        economies = getattr(workload, "economies", None)
        values = economies if economies is not None else [workload]
        value = {
            "tick": int(getattr(workload, "t", 0)),
            "last_records": [
                economy.records[-1] if economy.records else {} for economy in values
            ],
            "world_record": (
                workload.world_records[-1]
                if getattr(workload, "world_records", None)
                else None
            ),
        }
    return sha256_bytes(canonical_json_bytes(value))


def _semantic_digest(workload: Any, scenario: dict[str, Any]) -> str:
    if scenario["kind"] == "rl":
        return state_digest(workload.session)
    if scenario["kind"] == "desktop":
        return state_digest(workload.session)
    return state_digest(workload)


def _assert_invariants(workload: Any, scenario: dict[str, Any]) -> None:
    if scenario["kind"] == "rl":
        root = workload.session.world
    elif scenario["kind"] == "desktop":
        root = workload.world
    else:
        root = workload
    economies = getattr(root, "economies", None)
    for economy in economies if economies is not None else [root]:
        economy.ledger.assert_conserved()
        economy.ledger.assert_non_negative()


def _checkpoint_timings(
    workload: Any,
    scenario: dict[str, Any],
    root: Path,
) -> tuple[int | None, int | None, int]:
    if scenario["kind"] not in {"economy", "world", "checkpoint"}:
        return None, None, 0
    path = root / "benchmark.msim"
    started = time.perf_counter_ns()
    save_checkpoint(str(path), workload, tick=int(workload.t))
    save_ns = time.perf_counter_ns() - started
    checkpoint_bytes = path.stat().st_size
    started = time.perf_counter_ns()
    loaded, _, _ = load_checkpoint(str(path), require_same_commit=False)
    load_ns = time.perf_counter_ns() - started
    if state_digest(loaded) != state_digest(workload):
        raise RuntimeError("benchmark checkpoint semantic digest mismatch")
    return save_ns, load_ns, checkpoint_bytes


def peak_rss_bytes() -> int | None:
    try:
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (AttributeError, OSError, ValueError):
        return None
    if value <= 0:
        return None
    return value if platform.system() == "Darwin" else value * 1024


def run_worker(scenario: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="macro-m0-benchmark-worker-") as raw:
        started = time.perf_counter_ns()
        workload = _build_workload(scenario)
        genesis_ns = time.perf_counter_ns() - started
        _warmup(workload, scenario)
        started = time.perf_counter_ns()
        operations = _advance(workload, scenario)
        advance_ns = time.perf_counter_ns() - started
        started = time.perf_counter_ns()
        snapshot_digest = _snapshot_digest(workload, scenario)
        snapshot_ns = time.perf_counter_ns() - started
        save_ns, load_ns, checkpoint_bytes = _checkpoint_timings(
            workload,
            scenario,
            Path(raw),
        )
        _assert_invariants(workload, scenario)
        semantic_digest = _semantic_digest(workload, scenario)
        return {
            "genesis_ns": genesis_ns,
            "advance_ns": advance_ns,
            "snapshot_ns": snapshot_ns,
            "save_ns": save_ns,
            "load_ns": load_ns,
            "peak_rss_bytes": peak_rss_bytes(),
            "semantic_result_digest": semantic_digest,
            "snapshot_digest": snapshot_digest,
            "operations": operations,
            "checkpoint_bytes": checkpoint_bytes,
        }


def _percentile(values: list[int], probability: float) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def _statistics(values: list[int]) -> dict[str, int]:
    return {
        "minimum": min(values),
        "median": int(statistics.median(values)),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "maximum": max(values),
        "median_absolute_deviation": int(
            statistics.median(
                abs(value - statistics.median(values)) for value in values
            )
        ),
    }


def assemble_result(
    scenario: dict[str, Any],
    samples: list[dict[str, Any]],
    *,
    command: list[str],
) -> dict[str, Any]:
    semantic = {sample["semantic_result_digest"] for sample in samples}
    snapshots = {sample["snapshot_digest"] for sample in samples}
    if len(semantic) != 1 or len(snapshots) != 1:
        raise RuntimeError("benchmark repetitions have different semantic outputs")
    categories = ("genesis_ns", "advance_ns", "snapshot_ns", "save_ns", "load_ns")
    raw = {
        category.removesuffix("_ns"): [
            int(sample[category])
            for sample in samples
            if sample[category] is not None
        ]
        for category in categories
    }
    stats = {
        name: _statistics(values) if values else None for name, values in raw.items()
    }
    git = git_metadata()
    lock = REPO_ROOT / "uv.lock"
    hash_lock = yaml.safe_load(
        (REPO_ROOT / "schemas/m0/hashes.lock.json").read_text(encoding="utf-8")
    )
    environment = environment_metadata()
    environment.update(
        {
            "cpu_brand": platform.processor() or None,
            "physical_cores": None,
            "memory_bytes": None,
            "power_mode": None,
        }
    )
    result = {
        "schema_version": "python-benchmark-result-v1",
        "scenario_schema_version": "python-benchmark-scenarios-v1",
        "scenario_id": scenario["id"],
        "repository": {"commit": git.commit, "dirty": git.dirty},
        "contract_sha256": hash_lock["aggregate_sha256"],
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "command": command,
        "process_count": len(samples),
        "thread_count": int(os.environ.get("OMP_NUM_THREADS", "1")),
        "warmup_ticks": scenario["warmup_ticks"],
        "repetitions": len(samples),
        "raw_samples_ns": raw,
        "statistics_ns": stats,
        "workload_counters": {
            "population": scenario["population"],
            "firms": scenario["firms_c"] + scenario["firms_k"],
            "banks": scenario["banks"],
            "economies": scenario["economies"],
            "ticks": scenario["ticks"],
            "operations": [sample["operations"] for sample in samples],
            "checkpoint_bytes": [sample["checkpoint_bytes"] for sample in samples],
            "snapshot_digest": next(iter(snapshots)),
        },
        "semantic_result_digest": next(iter(semantic)),
        "invariant_status": "passed",
        "peak_rss_bytes": max(
            (
                sample["peak_rss_bytes"]
                for sample in samples
                if sample["peak_rss_bytes"] is not None
            ),
            default=None,
        ),
        "scenario_contract_sha256": sha256_bytes(canonical_json_bytes(scenario)),
        "dependency_lock_sha256": sha256_file(lock) if lock.is_file() else None,
    }
    validate_benchmark_result(result)
    return result


def validate_benchmark_result(value: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "scenario_schema_version",
        "scenario_id",
        "repository",
        "contract_sha256",
        "captured_at_utc",
        "environment",
        "command",
        "process_count",
        "thread_count",
        "warmup_ticks",
        "repetitions",
        "raw_samples_ns",
        "statistics_ns",
        "workload_counters",
        "semantic_result_digest",
        "invariant_status",
        "peak_rss_bytes",
        "scenario_contract_sha256",
        "dependency_lock_sha256",
    }
    if set(value) != required:
        raise SchemaError(
            "benchmark result fields differ: "
            f"missing={sorted(required - set(value))}, "
            f"extra={sorted(set(value) - required)}"
        )
    if value["schema_version"] != "python-benchmark-result-v1":
        raise SchemaError("unsupported benchmark result schema")
    repetitions = value["repetitions"]
    if repetitions < 1 or value["process_count"] != repetitions:
        raise SchemaError("benchmark process/repetition count mismatch")
    for category, samples in value["raw_samples_ns"].items():
        if category in {"save", "load"} and not samples:
            continue
        if len(samples) != repetitions or any(
            isinstance(sample, bool) or not isinstance(sample, int) or sample < 0
            for sample in samples
        ):
            raise SchemaError(f"invalid raw benchmark samples for {category}")
    if value["invariant_status"] != "passed":
        raise SchemaError("benchmark invariant status is not passed")
    for field in (
        "contract_sha256",
        "semantic_result_digest",
        "scenario_contract_sha256",
    ):
        if len(value[field]) != 64:
            raise SchemaError(f"invalid benchmark digest {field}")


def run_worker_process(scenario_id: str, output: Path) -> None:
    command = [
        sys.executable,
        str(REPO_ROOT / "benchmarks/python_baseline.py"),
        "--worker",
        "--scenario",
        scenario_id,
        "--output",
        str(output),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"benchmark worker failed: {detail}")
