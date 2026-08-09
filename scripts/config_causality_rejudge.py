#!/usr/bin/env python3
"""Rejudge stored native effects after a treatment-contract correction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.config_batch import rejudge_contract_report
from macro_sim.diagnostics.config_contracts import (
    activation_contracts,
    invariance_contracts,
    screening_contracts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--field", action="append", required=True, dest="fields")
    arguments = parser.parse_args()

    payload = json.loads(arguments.input.read_text(encoding="utf-8"))
    modules = {
        report["contract"]["module"] for report in payload.get("reports", ())
    }
    contracts = {
        contract.field_name: contract
        for module in modules
        for contract in (
            *screening_contracts(module=module),
            *activation_contracts(module=module),
            *invariance_contracts(module=module),
        )
    }
    requested = set(arguments.fields)
    found = set()
    reports = []
    for report in payload.get("reports", ()):
        field_name = report["contract"]["field_name"]
        if field_name in requested:
            if field_name not in contracts:
                parser.error(f"no executable current contract for {field_name!r}")
            report = rejudge_contract_report(report, contracts[field_name])
            found.add(field_name)
        reports.append(report)
    missing = requested - found
    if missing:
        parser.error(
            "fields are absent from the input report: " + ", ".join(sorted(missing))
        )

    payload["reports"] = reports
    payload["analysis_rejudged_from"] = str(arguments.input)
    payload["analysis_rejudged_fields"] = sorted(found)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    output = arguments.output_dir / "batch_report.json"
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"fields": sorted(found), "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
