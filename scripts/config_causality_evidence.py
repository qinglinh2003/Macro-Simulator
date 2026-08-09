#!/usr/bin/env python3
"""Generate the field-level Config causal-evidence ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.config_contracts import build_contract_registry
from macro_sim.diagnostics.config_evidence import build_evidence_ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-population", type=int, default=100_000)
    parser.add_argument("--formal-seed-count", type=int, default=4)
    arguments = parser.parse_args()

    reports = []
    for path in sorted(arguments.artifact_root.glob("*/batch_report.json")):
        reports.append((str(path), json.loads(path.read_text(encoding="utf-8"))))
    contracts = build_contract_registry()["contracts"]
    payload = build_evidence_ledger(
        contracts,
        reports,
        minimum_population=arguments.minimum_population,
        formal_seed_count=arguments.formal_seed_count,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["status_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

