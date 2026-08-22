#!/usr/bin/env python3
"""Generate and validate the Policy causality audit P0 ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.policy_contracts import (  # noqa: E402
    build_p0_payload,
    render_p0_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--fail-on-incomplete", action="store_true")
    args = parser.parse_args()

    payload = build_p0_payload()
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(
        render_p0_markdown(payload),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "p0_root_hash": payload["hashes"]["p0_root"],
    }, sort_keys=True))
    if args.fail_on_incomplete and payload["status"] != "accepted":
        for error in payload["errors"]:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
