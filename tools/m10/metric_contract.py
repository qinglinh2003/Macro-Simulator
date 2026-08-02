#!/usr/bin/env python3
"""Generate the M10 maintained metric contract from native source catalogs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CATALOG = (
    ROOT / "native/include/macro_sim/reporting/m10_metric_sources.inc"
)
DASHBOARD = (
    ROOT / "native/include/macro_sim/reporting/m10_dashboard_metrics.inc"
)
NATIONAL_ACCOUNTS = (
    ROOT / "native/include/macro_sim/reporting/m10_national_accounts.inc"
)
IMPLEMENTATION = ROOT / "native/src/reporting/m10.cpp"
PUBLIC = ROOT / "schemas/m10/public_metrics.json"
OUTPUT = ROOT / "schemas/m10/maintained_metrics.json"

_SOURCE = re.compile(
    r'^MACRO_SIM_(M4|M5|M6|M7|M8_ENERGY|M8_HOUSING|'
    r'M9_COUNTRY|M9_WORLD)_SOURCE'
    r'\(([a-z0-9_]+), "([^"]+)"\)$'
)
_NATIONAL_ACCOUNT = re.compile(
    r'^MACRO_SIM_NATIONAL_ACCOUNT'
    r'\(([a-z0-9_]+), "([^"]+)"\)$'
)
_LITERAL_DESCRIPTOR = re.compile(
    r'\{"([^"]+)",\s*"([^"]+)",\s*(\d+)U,\s*'
    r'MetricTier::[a-z]+,\s*MetricAggregation::([a-z]+),\s*'
    r'"([^"]*)"\}'
)
_DASHBOARD = re.compile(
    r'MACRO_SIM_DASHBOARD_METRIC\(\s*([a-z0-9_]+),\s*'
    r'"([^"]+)",\s*"([^"]+)",\s*"([^"]*)"\s*\)',
    re.MULTILINE,
)
_PREFIX = {
    "M4": ("metric.source.m4.", "simulation::M4Metrics::"),
    "M5": ("metric.source.m5.", "simulation::M5Metrics::"),
    "M6": ("metric.source.m6.", "simulation::M6Metrics::"),
    "M7": ("metric.source.m7.", "simulation::M7Metrics::"),
    "M8_ENERGY": (
        "metric.source.m8.energy.",
        "simulation::EnergyMetrics::",
    ),
    "M8_HOUSING": (
        "metric.source.m8.housing.",
        "simulation::HousingMetrics::",
    ),
    "M9_COUNTRY": (
        "metric.source.m9.country.",
        "simulation::CountryExternalMetrics::",
    ),
    "M9_WORLD": (
        "metric.source.m9.world.",
        "simulation::M9WorldMetrics::",
    ),
}


def build_contract() -> dict:
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    rows = [{
        "id": item["id"],
        "unit": item["unit"],
        "cadence_ticks": 1,
        "tier": "public_source",
        "aggregation": item["aggregation"],
        "parity_rule": item["parity_rule"],
        "source_kind": "derived_or_release",
    } for item in public["metrics"]]
    public_ids = {row["id"] for row in rows}
    literal_rows = _LITERAL_DESCRIPTOR.findall(
        IMPLEMENTATION.read_text(encoding="utf-8")
    )
    extra_literal_rows = [
        item for item in literal_rows if item[0] not in public_ids
    ]
    for metric_id, unit, cadence, aggregation, parity_rule in extra_literal_rows:
        rows.append({
            "id": metric_id,
            "unit": unit,
            "cadence_ticks": int(cadence),
            "tier": "analytic",
            "aggregation": aggregation,
            "parity_rule": parity_rule,
            "source_kind": "derived_or_release",
        })
    dashboard_rows = _DASHBOARD.findall(DASHBOARD.read_text(encoding="utf-8"))
    for _, metric_id, unit, parity_rule in dashboard_rows:
        rows.append({
            "id": metric_id,
            "unit": unit,
            "cadence_ticks": 30,
            "tier": "analytic",
            "aggregation": "last",
            "parity_rule": parity_rule,
            "source_kind": "derived_or_release",
        })
    dashboard_count = len(extra_literal_rows) + len(dashboard_rows)
    source_count = 0
    for line_number, line in enumerate(
        CATALOG.read_text(encoding="utf-8").splitlines(), start=1,
    ):
        if not line.startswith("MACRO_SIM_"):
            continue
        match = _SOURCE.fullmatch(line)
        if match is None:
            raise ValueError(
                f"invalid native metric source at line {line_number}"
            )
        family, field, unit = match.groups()
        stable_prefix, parity_prefix = _PREFIX[family]
        rows.append({
            "id": stable_prefix + field,
            "unit": unit,
            "cadence_ticks": 1,
            "tier": "analytic",
            "aggregation": "last",
            "parity_rule": parity_prefix + field,
            "source_kind": "committed_native_stage",
        })
        source_count += 1
    identifiers = [row["id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("M10 maintained metric IDs are not unique")
    national_account_count = 0
    for line_number, line in enumerate(
        NATIONAL_ACCOUNTS.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.startswith("MACRO_SIM_NATIONAL_ACCOUNT"):
            continue
        match = _NATIONAL_ACCOUNT.fullmatch(line)
        if match is None:
            raise ValueError(
                "invalid native national-account metric at "
                f"line {line_number}"
            )
        field, unit = match.groups()
        rows.append({
            "id": "metric.economy.na." + field,
            "unit": unit,
            "cadence_ticks": 1,
            "tier": "analytic",
            "aggregation": "last",
            "parity_rule": "native_national_accounts::" + field,
            "source_kind": "native_national_account",
        })
        national_account_count += 1
    identifiers = [row["id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("M10 maintained metric IDs are not unique")
    if (
        len(public["metrics"]) != 41
        or len(extra_literal_rows) != 35
        or len(dashboard_rows) != 85
        or source_count != 229
        or national_account_count != 63
    ):
        raise ValueError("M10 metric catalog width changed unexpectedly")
    return {
        "schema_version": "m10-maintained-metrics-v1",
        "snapshot_epoch": "committed_boundary",
        "counts": {
            "public_sources": len(public["metrics"]),
            "native_dashboard_analytics": dashboard_count,
            "native_stage_sources": source_count,
            "national_accounts": national_account_count,
            "total": len(rows),
        },
        "metrics": rows,
    }


def encoded_contract() -> str:
    return json.dumps(
        build_contract(), ensure_ascii=True, indent=2, sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    expected = encoded_contract()
    if arguments.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(
            encoding="utf-8"
        ) != expected:
            raise SystemExit("M10 maintained metric contract is stale")
        print("M10 maintained metric contract: current")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
