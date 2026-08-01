#!/usr/bin/env python3
"""Generate the static Config-to-native causality inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.config_causality import (
    build_audit_inventory,
    render_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--fail-on-disabled-module",
        action="store_true",
        help="return a nonzero status when the playable baseline misses a required module",
    )
    args = parser.parse_args()

    payload = build_audit_inventory()
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(payload), encoding="utf-8")
    if args.fail_on_disabled_module and not payload["all_required_modules_enabled"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
