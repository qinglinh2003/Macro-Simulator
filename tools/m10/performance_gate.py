#!/usr/bin/env python3
"""Run the mandatory M10 P0/P1/P2/P3/P5 and clone/reset gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET = ROOT / "schemas/m10/performance_budget.json"


def _percentile(values: list[int], probability: float) -> int:
    if not values:
        raise ValueError("performance sample set must not be empty")
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def _statistics(values: list[int]) -> dict[str, int]:
    return {
        "maximum_ns": max(values),
        "median_ns": int(statistics.median(values)),
        "minimum_ns": min(values),
        "p95_ns": _percentile(values, 0.95),
        "p99_ns": _percentile(values, 0.99),
        "sample_count": len(values),
    }


def _git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()


def _working_tree_dirty() -> bool:
    return bool(subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True,
    ).strip())


def _assert_release_build(native_dir: Path) -> None:
    cache = native_dir.parent / "CMakeCache.txt"
    if not cache.is_file():
        raise FileNotFoundError(f"native CMake cache is absent: {cache}")
    text = cache.read_text(encoding="utf-8", errors="replace")
    if "CMAKE_BUILD_TYPE:STRING=Release" not in text:
        raise RuntimeError(
            "M10 performance acceptance requires a Release native build"
        )


def _timed_days(
    session: Any, *, warmup_days: int, measured_days: int,
) -> list[int]:
    for _ in range(warmup_days):
        session.advance()
    samples: list[int] = []
    for _ in range(measured_days):
        started = time.perf_counter_ns()
        session.advance()
        samples.append(time.perf_counter_ns() - started)
    return samples


def _single_country_spec(
    *, seed: int, population: int, duration: int,
    households: int, firms_c: int, firms_k: int, firms_e: int,
    builders: int, banks: int,
) -> Any:
    from macro_sim.desktop.new_game import NewGameSpec

    raw = NewGameSpec.default(seed=seed).to_dict()
    raw["duration"] = duration
    raw["run_mode"] = "batch"
    raw["seats"] = {
        "treasury": "null",
        "cb": "null",
        "regulator": "null",
        "external": "null",
        "energy": "null",
    }
    raw["countries"] = [{
        "name": "M10 Reference Economy",
        "code": "M10R",
        "profile": "advanced",
        "overrides": {
            "demographics_population": population,
            "n_households": households,
            "n_firms_c": firms_c,
            "n_firms_k": firms_k,
            "n_firms_e": firms_e,
            "n_builders": builders,
            "n_banks": banks,
        },
    }]
    raw["player_country"] = 0
    return NewGameSpec.from_mapping(raw)


def _run_p0(build_dir: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "tools/m4/performance_gate.py"),
        "--build-dir",
        str(build_dir),
        "--budget",
        str(ROOT / "schemas/m4/performance_budget.json"),
    ]
    completed = subprocess.run(
        command, cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


def _run_p1(budget: dict[str, Any]) -> dict[str, Any]:
    from macro_sim.native_backend import NativeSimulationSession

    contract = budget["p1"]
    spec = _single_country_spec(
        seed=int(contract["seed"]),
        population=int(contract["population"]),
        duration=(
            int(contract["warmup_days"])
            + int(contract["measured_days"])
            + 1
        ),
        households=int(contract["requested_households"]),
        firms_c=int(contract["firms_c"]),
        firms_k=int(contract["firms_k"]),
        firms_e=int(contract["firms_e"]),
        builders=int(contract["builders"]),
        banks=int(contract["banks"]),
    )
    session = NativeSimulationSession.create(
        spec, worker_count=1, history_capacity_frames=512,
    )
    diagnostics = session.probe_economy_diagnostics()
    if int(diagnostics["persons_alive"]) != int(contract["population"]):
        raise AssertionError("P1 genesis population differs from its contract")
    if int(diagnostics["firms"]) != int(contract["firms"]):
        raise AssertionError("P1 genesis firm count differs from its contract")
    if int(diagnostics["banks"]) != int(contract["banks"]):
        raise AssertionError("P1 genesis bank count differs from its contract")
    samples = _timed_days(
        session,
        warmup_days=int(contract["warmup_days"]),
        measured_days=int(contract["measured_days"]),
    )
    measured = _statistics(samples)
    measured["native_to_python_median_ratio"] = (
        measured["median_ns"]
        / float(contract["matched_python_median_ns_per_day"])
    )
    measured["reference_entities"] = {
        key: int(diagnostics[key])
        for key in ("banks", "firms", "households", "persons_alive")
    }
    return measured


def _run_p2(budget: dict[str, Any]) -> dict[str, Any]:
    from macro_sim.native_backend import NativeSimulationSession

    contract = budget["p2"]
    spec = _single_country_spec(
        seed=int(contract["seed"]),
        population=int(contract["population"]),
        duration=(
            int(contract["warmup_days"])
            + int(contract["measured_days"])
            + 1
        ),
        households=int(contract["requested_households"]),
        firms_c=int(contract["firms_c"]),
        firms_k=int(contract["firms_k"]),
        firms_e=int(contract["firms_e"]),
        builders=int(contract["builders"]),
        banks=int(contract["banks"]),
    )
    session = NativeSimulationSession.create(
        spec, worker_count=1, history_capacity_frames=512,
    )
    diagnostics = session.probe_economy_diagnostics()
    if int(diagnostics["households"]) != int(
        contract["expected_households"]
    ):
        raise AssertionError(
            "P2 historical-scale household anchor differs from its contract"
        )
    if int(diagnostics["firms"]) != int(contract["firms"]):
        raise AssertionError("P2 genesis firm count differs from its contract")
    samples = _timed_days(
        session,
        warmup_days=int(contract["warmup_days"]),
        measured_days=int(contract["measured_days"]),
    )
    measured = _statistics(samples)
    measured["native_to_historical_median_ratio"] = (
        measured["median_ns"]
        / float(contract["historical_python_median_ns_per_day"])
    )
    measured["reference_entities"] = {
        key: int(diagnostics[key])
        for key in ("banks", "firms", "households", "persons_alive")
    }
    return measured


def _run_p3(budget: dict[str, Any]) -> dict[str, Any]:
    from macro_sim.desktop.native_runtime import NativeSimulationRuntime

    contract = budget["p3"]
    batch_samples: list[int] = []
    snapshot_samples: list[int] = []
    for index in range(int(contract["repetitions"])):
        runtime = NativeSimulationRuntime(
            seed=int(contract["seed"]) + index,
        )
        batch_started = time.perf_counter_ns()
        result = runtime.advance(int(contract["batch_days"]))
        if int(result["advanced_ticks"]) != int(contract["batch_days"]):
            raise AssertionError("P3 desktop batch ended before 60 days")
        snapshot_started = time.perf_counter_ns()
        snapshot = runtime.snapshot()
        snapshot_samples.append(time.perf_counter_ns() - snapshot_started)
        batch_samples.append(time.perf_counter_ns() - batch_started)
        if int(snapshot["tick"]) != int(contract["batch_days"]):
            raise AssertionError("P3 desktop snapshot has the wrong boundary")
        if int(snapshot["protocol_version"]) != 4:
            raise AssertionError("P3 desktop protocol version drifted")
    return {
        "batch_plus_snapshot": _statistics(batch_samples),
        "snapshot": _statistics(snapshot_samples),
    }


def _run_clone_reset(budget: dict[str, Any]) -> dict[str, Any]:
    from macro_sim.native_backend import NativeSimulationSession

    contract = budget["clone_reset"]
    spec = _single_country_spec(
        seed=int(contract["seed"]),
        population=int(contract["population"]),
        duration=365,
        households=int(contract["requested_households"]),
        firms_c=int(contract["firms_c"]),
        firms_k=int(contract["firms_k"]),
        firms_e=int(contract["firms_e"]),
        builders=int(contract["builders"]),
        banks=int(contract["banks"]),
    )
    session = NativeSimulationSession.create(
        spec, worker_count=1, history_capacity_frames=64,
    )
    session.advance()
    expected_digest = session.native_snapshot()["digest"]
    samples: list[int] = []
    clone_known_bytes = 0
    for _ in range(int(contract["repetitions"])):
        started = time.perf_counter_ns()
        clone = session.clone()
        samples.append(time.perf_counter_ns() - started)
        if clone.native_snapshot()["digest"] != expected_digest:
            raise AssertionError("100k reset clone changed the native state")
        clone_known_bytes = int(clone.memory_usage()["total_known"])
    measured = _statistics(samples)
    measured.update({
        "native_known_bytes_per_clone": clone_known_bytes,
        "population": int(
            session.probe_economy_diagnostics()["persons_alive"]
        ),
        "strategy": "deep_copy_native_composite",
    })
    return measured


def _p5_worker(
    connection: Any, native_dir: str, source_dir: str, seed: int,
) -> None:
    environment = None
    try:
        sys.path.insert(0, native_dir)
        sys.path.insert(1, source_dir)
        import numpy as np

        from macro_sim.rl.native_envs import (
            NativeFiscalStabilizationEnvFactory,
        )

        environment = NativeFiscalStabilizationEnvFactory(
            worker_count=1,
        )(seed)
        environment.reset(seed=seed)
        connection.send(("ready", None))
        command = connection.recv()
        if command != "run":
            raise RuntimeError(f"unexpected P5 worker command {command!r}")
        elapsed_days = 0
        decisions = 0
        action = np.ones((1,), dtype=np.int64)
        while True:
            _observation, _reward, terminated, truncated, info = (
                environment.step(action)
            )
            elapsed_days += int(info["elapsed_ticks"])
            decisions += 1
            if terminated or truncated:
                if not terminated or truncated:
                    raise RuntimeError(
                        "P5 worker ended without clean termination"
                    )
                break
        connection.send(("ok", {
            "decisions": decisions,
            "elapsed_days": elapsed_days,
        }))
    except BaseException as exc:
        try:
            connection.send(("error", {
                "message": str(exc),
                "type": type(exc).__name__,
            }))
        except (BrokenPipeError, EOFError):
            pass
    finally:
        if environment is not None:
            environment.close()
        connection.close()


def _run_p5(
    budget: dict[str, Any], native_dir: Path,
) -> dict[str, Any]:
    contract = budget["p5"]
    environment_count = int(contract["environment_count"])
    seeds = tuple(
        int(contract["seed"]) + index for index in range(environment_count)
    )
    context = mp.get_context("spawn")
    parents = []
    processes = []
    try:
        for index, seed in enumerate(seeds):
            parent, child = context.Pipe(duplex=True)
            process = context.Process(
                target=_p5_worker,
                args=(
                    child,
                    str(native_dir),
                    str(ROOT),
                    seed,
                ),
                name=f"macro-sim-m10-p5-{index}",
            )
            process.start()
            child.close()
            parents.append(parent)
            processes.append(process)
        for index, (parent, process) in enumerate(
            zip(parents, processes, strict=True)
        ):
            if not parent.poll(300.0):
                raise RuntimeError(f"P5 worker {index} initialization timed out")
            status, payload = parent.recv()
            if status != "ready":
                raise RuntimeError(
                    f"P5 worker {index} failed to initialize: {payload}"
                )
            if not process.is_alive():
                raise RuntimeError(
                    f"P5 worker {index} exited during initialization"
                )
        started = time.perf_counter()
        for parent in parents:
            parent.send("run")
        rows = []
        for index, (parent, process) in enumerate(
            zip(parents, processes, strict=True)
        ):
            if not parent.poll(300.0):
                raise RuntimeError(f"P5 worker {index} execution timed out")
            status, payload = parent.recv()
            if status != "ok":
                raise RuntimeError(
                    f"P5 worker {index} execution failed: {payload}"
                )
            rows.append(payload)
            process.join(timeout=10.0)
            if process.exitcode != 0:
                raise RuntimeError(
                    f"P5 worker {index} exited with code {process.exitcode}"
                )
        elapsed_seconds = time.perf_counter() - started
    finally:
        for parent in parents:
            parent.close()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=10.0)
    elapsed_days = sum(int(row["elapsed_days"]) for row in rows)
    decisions = sum(int(row["decisions"]) for row in rows)
    expected_days = environment_count * int(contract["horizon_days"])
    if elapsed_days != expected_days:
        raise AssertionError(
            f"P5 advanced {elapsed_days} engine days, expected {expected_days}"
        )
    return {
        "decision_steps": decisions,
        "elapsed_seconds": elapsed_seconds,
        "engine_days": elapsed_days,
        "engine_days_per_second": elapsed_days / elapsed_seconds,
        "environment_count": environment_count,
    }


def _evaluate(
    budget: dict[str, Any], results: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if results["p0"]["status"] != "passed":
        failures.append("P0 first vertical performance gate failed")
    p1 = results["p1"]
    if p1["p95_ns"] > int(budget["p1"]["maximum_p95_ns"]):
        failures.append("P1 full-feature p95 exceeds 75 ms/day")
    if p1["native_to_python_median_ratio"] > float(
        budget["p1"]["maximum_native_to_python_ratio"]
    ):
        failures.append("P1 native/Python median ratio exceeds 10%")
    p2 = results["p2"]
    if p2["p95_ns"] > int(budget["p2"]["maximum_p95_ns"]):
        failures.append("P2 historical-scale p95 exceeds 25 ms/day")
    p3 = results["p3"]
    if p3["batch_plus_snapshot"]["p95_ns"] > int(
        budget["p3"]["maximum_batch_plus_snapshot_p95_ns"]
    ):
        failures.append("P3 desktop 60-day batch exceeds 750 ms")
    if p3["snapshot"]["p95_ns"] > int(
        budget["p3"]["maximum_snapshot_p95_ns"]
    ):
        failures.append("P3 desktop snapshot exceeds 100 ms")
    if results["clone_reset"]["p95_ns"] > int(
        budget["clone_reset"]["maximum_p95_ns"]
    ):
        failures.append("100k native clone/reset exceeds 250 ms")
    if results["p5"]["engine_days_per_second"] < float(
        budget["p5"]["minimum_engine_days_per_second"]
    ):
        failures.append("P5 eight-environment throughput is below 3,200 days/s")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    parser.add_argument("--budget", default=DEFAULT_BUDGET, type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    native_dir = arguments.native_dir.resolve()
    _assert_release_build(native_dir)
    sys.path.insert(0, str(native_dir))
    sys.path.insert(1, str(ROOT))
    budget = json.loads(arguments.budget.read_text(encoding="utf-8"))

    build_dir = native_dir.parent
    runners: tuple[tuple[str, Callable[[], dict[str, Any]]], ...] = (
        ("p0", lambda: _run_p0(build_dir)),
        ("p1", lambda: _run_p1(budget)),
        ("p2", lambda: _run_p2(budget)),
        ("p3", lambda: _run_p3(budget)),
        ("clone_reset", lambda: _run_clone_reset(budget)),
        ("p5", lambda: _run_p5(budget, native_dir)),
    )
    results: dict[str, Any] = {}
    for name, runner in runners:
        started = time.perf_counter()
        results[name] = runner()
        results[name]["gate_seconds"] = time.perf_counter() - started
        print(
            json.dumps(
                {"gate": name.upper(), "result": results[name]},
                sort_keys=True,
            ),
            flush=True,
        )
    failures = _evaluate(budget, results)
    report = {
        "architecture": platform.machine(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit": _git_commit(),
        "failures": failures,
        "native_dir": str(native_dir),
        "platform": sys.platform,
        "results": results,
        "schema_version": "m10-performance-gate-result-v1",
        "status": "failed" if failures else "passed",
        "system": platform.system(),
        "working_tree_dirty": _working_tree_dirty(),
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = arguments.output.with_suffix(
            arguments.output.suffix + ".tmp"
        )
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, arguments.output)
    print(payload, end="", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
