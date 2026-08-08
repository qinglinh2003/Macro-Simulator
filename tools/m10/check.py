#!/usr/bin/env python3
"""Run M10 contract checks and the local native acceptance preset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HAN_PATTERN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
INLINE_LOCALE_KEY_PATTERN = re.compile(r"@\{([A-Za-z0-9_.-]+)\}")
EXACT_LOCALE_KEY_PATTERN = re.compile(r"""["']@([A-Za-z0-9_.-]+)""")


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def validate_desktop_locales() -> None:
    catalog_paths = {
        locale: ROOT / f"desktop/godot/i18n/{locale}.json"
        for locale in ("en", "zh_CN")
    }
    catalogs = {
        locale: json.loads(path.read_text(encoding="utf-8"))
        for locale, path in catalog_paths.items()
    }
    if set(catalogs["en"]) != set(catalogs["zh_CN"]):
        missing_en = sorted(set(catalogs["zh_CN"]) - set(catalogs["en"]))
        missing_zh = sorted(set(catalogs["en"]) - set(catalogs["zh_CN"]))
        raise AssertionError(
            f"desktop locale keys differ: en={missing_en}, zh_CN={missing_zh}"
        )
    for key, value in catalogs["en"].items():
        if HAN_PATTERN.search(str(value)):
            raise AssertionError(
                f"English desktop locale {key!r} contains Han text"
            )

    source_paths = sorted((ROOT / "desktop/godot/scripts").rglob("*.gd"))
    source_paths += sorted((ROOT / "desktop/godot/tests").rglob("*.gd"))
    source_paths += sorted((ROOT / "macro_sim/desktop").rglob("*.py"))
    source_paths += [
        ROOT / "scripts/desktop_smoke.py",
        ROOT / "scripts/run_godot_prototype.sh",
    ]
    referenced_keys: set[str] = set()
    for path in source_paths:
        text = path.read_text(encoding="utf-8")
        if HAN_PATTERN.search(text):
            raise AssertionError(
                f"player-facing Han literal remains in source: {path}"
            )
        referenced_keys.update(INLINE_LOCALE_KEY_PATTERN.findall(text))
        referenced_keys.update(EXACT_LOCALE_KEY_PATTERN.findall(text))
    missing = sorted(referenced_keys - set(catalogs["zh_CN"]))
    if missing:
        raise AssertionError(
            f"desktop source references missing locale keys: {missing}"
        )
    localization = (
        ROOT / "desktop/godot/scripts/localization.gd"
    ).read_text(encoding="utf-8")
    if 'requested == "zh-CN"' not in localization:
        raise AssertionError("zh-CN locale alias is not normalized")
    for relative in (
        "desktop/godot/project.godot",
        "desktop/godot/scenes/main.tscn",
        "desktop/godot/i18n/en.json",
        "desktop/godot/i18n/zh_CN.json",
    ):
        if not (ROOT / relative).is_file():
            raise AssertionError(f"packaged desktop asset is absent: {relative}")


def validate_contracts() -> None:
    budget = json.loads(
        (ROOT / "schemas/m10/performance_budget.json").read_text(
            encoding="utf-8"
        )
    )
    if budget["schema_version"] != "m10-performance-budget-v1":
        raise AssertionError("M10 performance contract changed")
    if budget["history_capacity_frames"] <= 0:
        raise AssertionError("M10 history must be bounded")
    maintained = json.loads(
        (ROOT / "schemas/m10/maintained_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    metric_count = int(maintained["counts"]["total"])
    dense_history_bytes = budget["history_capacity_frames"] * (
        metric_count * (8 + 1) + 8
    )
    if dense_history_bytes > budget["maximum_history_bytes_per_economy"]:
        raise AssertionError("M10 default history exceeds its memory budget")
    if set(budget["p1"]) != {
        "banks", "builders", "firms", "firms_c", "firms_e", "firms_k",
        "matched_python_median_ns_per_day",
        "maximum_native_to_python_ratio", "maximum_p95_ns",
        "measured_days", "population", "requested_households", "seed",
        "warmup_days",
    }:
        raise AssertionError("M10 P1 performance contract is incomplete")
    if budget["p1"]["maximum_p95_ns"] != 75_000_000:
        raise AssertionError("M10 P1 p95 budget drifted")
    if budget["p2"]["maximum_p95_ns"] != 25_000_000:
        raise AssertionError("M10 P2 p95 budget drifted")
    if (
        budget["p3"]["maximum_batch_plus_snapshot_p95_ns"]
        != 750_000_000
        or budget["p3"]["maximum_snapshot_p95_ns"] != 100_000_000
    ):
        raise AssertionError("M10 P3 desktop budget drifted")
    if (
        budget["p5"]["environment_count"] != 8
        or budget["p5"]["minimum_engine_days_per_second"] != 3_200.0
    ):
        raise AssertionError("M10 P5 throughput budget drifted")
    if budget["clone_reset"]["maximum_p95_ns"] != 250_000_000:
        raise AssertionError("M10 clone/reset budget drifted")

    metrics = json.loads(
        (ROOT / "schemas/m10/public_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    if metrics["schema_version"] != "m10-public-metrics-v2":
        raise AssertionError("M10 public metric contract changed")
    metric_ids = [item["id"] for item in metrics["metrics"]]
    if len(metric_ids) != 41 or len(metric_ids) != len(set(metric_ids)):
        raise AssertionError(
            "M10 must expose exactly 41 unique native observation sources"
        )
    from macro_sim.controllers.observation import DEFAULT_OBSERVATION_SPEC

    aliases = metrics["observation_aliases"]
    for field in DEFAULT_OBSERVATION_SPEC.fields:
        if field.series_id in aliases:
            expected_id = aliases[field.series_id]
        else:
            namespace = {
                "economy": "metric.economy.",
                "world": "metric.world.",
                "shock": "metric.shock.",
            }.get(field.source)
            if namespace is None:
                raise AssertionError(
                    f"M10 observation source {field.source!r} is unsupported"
                )
            expected_id = namespace + field.source_key
        if expected_id not in metric_ids:
            raise AssertionError(
                f"M10 observation series {field.series_id!r} lacks "
                f"native source {expected_id!r}"
            )

    maintained = json.loads(
        (ROOT / "schemas/m10/maintained_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    if maintained["schema_version"] != "m10-maintained-metrics-v1":
        raise AssertionError("M10 maintained metric contract changed")
    if maintained["counts"] != {
        "national_accounts": 63,
        "native_dashboard_analytics": 120,
        "native_stage_sources": 249,
        "public_sources": 41,
        "total": 473,
    }:
        raise AssertionError("M10 maintained metric coverage is incomplete")
    maintained_ids = [item["id"] for item in maintained["metrics"]]
    if len(maintained_ids) != len(set(maintained_ids)):
        raise AssertionError("M10 maintained metric IDs are not unique")
    for item in maintained["metrics"]:
        if (
            not item["unit"]
            or not item["parity_rule"]
            or item["cadence_ticks"] <= 0
        ):
            raise AssertionError(
                f"M10 metric {item['id']!r} lacks required metadata"
            )

    probes = json.loads(
        (ROOT / "schemas/m10/typed_probes.json").read_text(
            encoding="utf-8"
        )
    )
    if probes["schema_version"] != "m10-typed-probes-v2":
        raise AssertionError("M10 typed probe contract changed")
    probe_ids = [item["id"] for item in probes["probes"]]
    if len(probe_ids) != 10 or len(probe_ids) != len(set(probe_ids)):
        raise AssertionError("M10 typed probes must contain ten unique IDs")
    if probes["maximum_page_rows"] != 1024:
        raise AssertionError("M10 native probe page ceiling drifted")
    for probe in probes["probes"]:
        if not probe["fields"] or len(probe["fields"]) != len(
            set(probe["fields"])
        ):
            raise AssertionError(
                f"M10 typed probe {probe['id']!r} has invalid fields"
            )

    required = (
        "docs/cpp_engine_m10_execution_plan_v34.md",
        "docs/adr/0002-m10-controller-reset-strategy.md",
        "schemas/m10/performance_budget.json",
        "schemas/m10/public_metrics.json",
        "schemas/m10/maintained_metrics.json",
        "schemas/m10/typed_probes.json",
        "macro_sim/native_backend.py",
        "macro_sim/reporting/native_stream.py",
        "macro_sim/controllers/native_observation.py",
        "macro_sim/desktop/native_projection.py",
        "macro_sim/desktop/native_runtime.py",
        "macro_sim/diagnostics/native_probes.py",
        "macro_sim/rl/native_envs.py",
        "native/include/macro_sim/reporting/probes.hpp",
        "native/include/macro_sim/reporting/m10_metric_sources.inc",
        "native/include/macro_sim/reporting/m10_national_accounts.inc",
        "native/src/reporting/probes.cpp",
        "tools/m10/check.py",
        "tools/m10/metric_contract.py",
        "tools/m10/native_facade_smoke.py",
        "tools/m10/native_history_stream_smoke.py",
        "tools/m10/performance_gate.py",
        "tools/m10/p7_longevity.py",
        "tools/m10/native_controller_smoke.py",
        "tools/m10/native_desktop_smoke.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            raise AssertionError(f"M10 input is absent: {relative}")

    forbidden = ("PyObject_Call", "PyObject_CallObject", "nb::call", "py::call")
    for path in sorted((ROOT / "native/src").rglob("*.cpp")):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            raise AssertionError(f"native callback hook found in {path}")
    validate_desktop_locales()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preset", default="m10-debug")
    arguments = parser.parse_args()
    run([sys.executable, "tools/m9/check.py", "--skip-build"])
    run([sys.executable, "tools/m10/metric_contract.py", "--check"])
    validate_contracts()
    if not arguments.skip_build:
        run(["cmake", "--preset", arguments.preset])
        run(["cmake", "--build", "--preset", arguments.preset, "-j", "8"])
        run(["ctest", "--preset", arguments.preset, "-j", "8"])
    print("M10 local acceptance: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
