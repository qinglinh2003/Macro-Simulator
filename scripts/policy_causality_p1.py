#!/usr/bin/env python3
"""Generate and validate the Policy causality audit P1 route ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.policy_routing import (  # noqa: E402
    ACCEPTED_STATUSES,
    build_p1_payload,
    render_p1_markdown,
    run_p1_native_smoke,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--population", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=3_801)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--countries", type=int, default=3)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--fail-on-incomplete", action="store_true")
    arguments = parser.parse_args()

    smoke = None if arguments.static_only else run_p1_native_smoke(
        population=arguments.population,
        seed=arguments.seed,
        workers=arguments.workers,
        countries=arguments.countries,
    )
    payload = build_p1_payload(smoke)
    arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.json_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    arguments.markdown_output.write_text(
        render_p1_markdown(payload),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "p1_root_hash": payload["hashes"]["p1_root"],
        "p1_acceptance_hash": payload["hashes"]["p1_acceptance"],
        "native_smoke_passed": bool(smoke and smoke["passed"]),
    }, sort_keys=True))
    if arguments.fail_on_incomplete and payload["status"] not in ACCEPTED_STATUSES:
        for error in payload["errors"]:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
