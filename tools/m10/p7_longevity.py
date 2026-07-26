#!/usr/bin/env python3
"""Run the M10 P7 ten-year resident-memory acceptance gate."""

from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def _resident_bytes() -> int:
    """Return current resident bytes without relying on an optional package."""
    if sys.platform.startswith("linux"):
        resident_pages = int(
            Path("/proc/self/statm").read_text(encoding="ascii").split()[1]
        )
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    if sys.platform == "darwin":
        value = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            text=True,
        )
        return int(value.strip()) * 1024
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        ):
            raise OSError("GetProcessMemoryInfo failed")
        return int(counters.WorkingSetSize)
    raise RuntimeError(f"current RSS is unsupported on {sys.platform}")


def _full_feature_spec(seed: int, population: int, days: int) -> Any:
    from macro_sim.desktop.new_game import NewGameSpec

    raw = NewGameSpec.default(seed=seed).to_dict()
    raw["duration"] = days
    raw["run_mode"] = "batch"
    raw["seats"] = {
        "treasury": "null",
        "cb": "null",
        "regulator": "null",
        "external": "null",
        "energy": "null",
    }
    raw["countries"] = [{
        "name": "P7 Reference Economy",
        "code": "P7R",
        "profile": "advanced",
        "overrides": {
            "demographics_population": population,
            "n_households": max(1, population // 2),
            "n_firms_c": 600,
            "n_firms_k": 100,
            "n_firms_e": 25,
            "n_builders": 25,
            "n_banks": 8,
        },
    }]
    raw["player_country"] = 0
    return NewGameSpec.from_mapping(raw)


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()


def _working_tree_dirty() -> bool:
    return bool(subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True,
    ).strip())


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, int(round((len(ordered) - 1) * fraction))),
    )
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", required=True, type=Path)
    parser.add_argument("--source-dir", default=ROOT, type=Path)
    parser.add_argument("--population", default=10_000, type=int)
    parser.add_argument("--years", default=10, type=int)
    parser.add_argument("--seed", default=1010, type=int)
    parser.add_argument("--worker-count", default=8, type=int)
    parser.add_argument("--window-days", default=30, type=int)
    parser.add_argument("--stream-directory", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.population < 1:
        parser.error("--population must be positive")
    if arguments.years < 2:
        parser.error("--years must be at least two")
    if not 1 <= arguments.window_days <= 365:
        parser.error("--window-days must be in 1..365")

    sys.path.insert(0, str(arguments.native_dir.resolve()))
    sys.path.insert(1, str(arguments.source_dir.resolve()))
    from macro_sim.native_backend import NativeSimulationSession
    from macro_sim.reporting.native_stream import NativeMetricStream

    days = arguments.years * 365
    spec = _full_feature_spec(arguments.seed, arguments.population, days)
    budget = json.loads(
        (ROOT / "schemas/m10/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if arguments.stream_directory is None:
        temporary = tempfile.TemporaryDirectory(prefix="macro-sim-p7-")
        stream_directory = Path(temporary.name) / "history"
    else:
        stream_directory = arguments.stream_directory.resolve()

    started = time.perf_counter()
    session = NativeSimulationSession.create(
        spec,
        worker_count=arguments.worker_count,
        history_capacity_frames=int(budget["history_capacity_frames"]),
    )
    genesis_seconds = time.perf_counter() - started
    diagnostics = session.probe_economy_diagnostics()
    if int(diagnostics["persons_alive"]) != arguments.population:
        raise AssertionError("P7 genesis did not create the requested population")
    if int(diagnostics["firms"]) != 750:
        raise AssertionError("P7 genesis did not create the reference firm count")
    if int(diagnostics["banks"]) != 8:
        raise AssertionError("P7 genesis did not create the reference bank count")

    stream = NativeMetricStream(stream_directory, chunk_frames=128)
    if stream.sync(session) != 1:
        raise AssertionError("P7 stream did not capture genesis")
    year_two_start = 2 * 365 - arguments.window_days + 1
    year_ten_start = days - arguments.window_days + 1
    year_two_rss: list[int] = []
    final_year_rss: list[int] = []
    year_two_native_memory: dict[str, int] | None = None
    final_native_memory: dict[str, int] | None = None
    year_two_store_rows: dict[str, int] | None = None
    final_store_rows: dict[str, int] | None = None
    year_two_storage_counts: dict[str, int] | None = None
    final_storage_counts: dict[str, int] | None = None

    def store_rows() -> dict[str, int]:
        return {
            kind: int(session.probe_page(
                kind, maximum_rows=1,
            )["total_rows"])
            for kind in ("persons", "jobs", "dwellings")
        }

    advance_started = time.perf_counter()
    for day in range(1, days + 1):
        session.advance()
        if stream.sync(session) != 1:
            raise AssertionError("P7 stream did not capture one committed frame")
        if day >= year_two_start and day <= 2 * 365:
            gc.collect()
            year_two_rss.append(_resident_bytes())
            if day == 2 * 365:
                year_two_native_memory = session.memory_usage()
                year_two_store_rows = store_rows()
                year_two_storage_counts = session.storage_counts()
        if day >= year_ten_start:
            gc.collect()
            final_year_rss.append(_resident_bytes())
            if day == days:
                final_native_memory = session.memory_usage()
                final_store_rows = store_rows()
                final_storage_counts = session.storage_counts()
        if day % 365 == 0:
            print(
                json.dumps({
                    "elapsed_seconds": round(
                        time.perf_counter() - advance_started, 3
                    ),
                    "rss_bytes": _resident_bytes(),
                    "tick": day,
                }, sort_keys=True),
                flush=True,
            )
    stream.close()
    advance_seconds = time.perf_counter() - advance_started
    if len(year_two_rss) != arguments.window_days:
        raise AssertionError("P7 year-two RSS window is incomplete")
    if len(final_year_rss) != arguments.window_days:
        raise AssertionError("P7 final-year RSS window is incomplete")
    if (
        year_two_native_memory is None
        or final_native_memory is None
        or year_two_store_rows is None
        or final_store_rows is None
        or year_two_storage_counts is None
        or final_storage_counts is None
    ):
        raise AssertionError("P7 native memory evidence is incomplete")

    year_two_median = int(statistics.median(year_two_rss))
    final_year_median = int(statistics.median(final_year_rss))
    permitted = int(
        year_two_median * 1.05
        + int(budget["ten_year_memory_growth_bytes"])
    )
    failures: list[str] = []
    if final_year_median > permitted:
        failures.append("P7 resident memory exceeds the ten-year growth budget")
    bounds = session.history_bounds()
    if int(bounds["size"]) > int(
        budget["history_capacity_frames"]
    ):
        failures.append("P7 native history ring exceeded its fixed capacity")
    if int(bounds["retained_bytes"]) > int(
        budget["maximum_history_bytes_per_economy"]
    ):
        failures.append("P7 native history ring exceeded its byte budget")

    report = {
        "advance_seconds": advance_seconds,
        "architecture": platform.machine(),
        "commit": _git_commit(),
        "days": days,
        "failures": failures,
        "final_tick": session.tick,
        "genesis_seconds": genesis_seconds,
        "history_bounds": bounds,
        "history_capacity_frames": budget["history_capacity_frames"],
        "native_memory": {
            "year_2": year_two_native_memory,
            "year_final": final_native_memory,
        },
        "population": arguments.population,
        "reference_entities": {
            "banks": int(diagnostics["banks"]),
            "firms": int(diagnostics["firms"]),
            "households": int(diagnostics["households"]),
            "persons_alive": int(diagnostics["persons_alive"]),
        },
        "rss": {
            "permitted_final_bytes": permitted,
            "year_2_median_bytes": year_two_median,
            "year_2_p95_bytes": _percentile(year_two_rss, 0.95),
            "year_final_median_bytes": final_year_median,
            "year_final_p95_bytes": _percentile(final_year_rss, 0.95),
        },
        "store_rows": {
            "year_2": year_two_store_rows,
            "year_final": final_store_rows,
        },
        "storage_counts": {
            "year_2": year_two_storage_counts,
            "year_final": final_storage_counts,
        },
        "schema_version": "m10-p7-longevity-result-v1",
        "status": "failed" if failures else "passed",
        "stream_bytes_excluded_from_rss_gate": _directory_bytes(
            stream_directory
        ),
        "stream_next_sequence": stream.next_sequence,
        "system": platform.system(),
        "worker_count": arguments.worker_count,
        "working_tree_dirty": _working_tree_dirty(),
        "years": arguments.years,
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = arguments.output.with_suffix(
            arguments.output.suffix + ".tmp"
        )
        temporary_path.write_text(payload, encoding="utf-8")
        os.replace(temporary_path, arguments.output)
    print(payload, end="", flush=True)
    if temporary is not None:
        temporary.cleanup()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
