#!/usr/bin/env python3
"""Write the native product baseline comparison artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.config_native_baseline import build_native_baseline_audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--countries", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_native_baseline_audit(
        population=args.population,
        seed=args.seed,
        countries=args.countries,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["status_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
