#!/usr/bin/env python3
"""Compare matched small- and large-population Config batch reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.config_confirmation import compare_batch_reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--confirmation", required=True, type=Path)
    parser.add_argument("--field")
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    payload = compare_batch_reports(
        arguments.reference,
        arguments.confirmation,
        field_name=arguments.field,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"fields": len(payload["fields"]), "output": str(arguments.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
