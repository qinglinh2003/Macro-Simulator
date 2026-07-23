#!/usr/bin/env python3
"""Audit the frozen M0 contract set without mutating checked evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cpp_migration.client_traces import build_client_contracts  # noqa: E402
from scripts.cpp_migration.common import (  # noqa: E402
    M0Error,
    REPO_ROOT,
    canonical_json_bytes,
    environment_metadata,
    git_metadata,
)
from scripts.cpp_migration.fixtures import (  # noqa: E402
    OUTPUT_ROOT,
    build_fixture_manifest,
    load_tape_bundle,
)
from scripts.cpp_migration.inventory import (  # noqa: E402
    INVENTORY_FAMILIES,
    build_all_inventories,
    build_hash_lock,
    validate_cross_references,
)
from scripts.cpp_migration.module_map import build_module_map  # noqa: E402


REFERENCE_IDS = (
    "tiny_refactor_v124",
    "full_playable_10k",
    "m4_v0_cash_loop",
    "m4_v1_capital_fiscal",
)


def audit(*, require_clean: bool) -> dict:
    git = git_metadata()
    if require_clean and git.dirty:
        raise M0Error("M0 final audit requires a clean working tree")
    inventories = build_all_inventories()
    validate_cross_references(inventories)
    for family in INVENTORY_FAMILIES:
        path = REPO_ROOT / f"schemas/m0/inventory/{family}.json"
        if path.read_bytes() != canonical_json_bytes(inventories[family]):
            raise M0Error(f"stale inventory: {family}")
    expected_lock = build_hash_lock()
    actual_lock = json.loads(
        (REPO_ROOT / "schemas/m0/hashes.lock.json").read_text(encoding="utf-8")
    )
    if actual_lock != expected_lock:
        raise M0Error("M0 hash lock is stale")
    generated = {
        OUTPUT_ROOT / "manifests/fixtures.json": build_fixture_manifest(),
        OUTPUT_ROOT / "tapes/bundle.json": load_tape_bundle(),
        OUTPUT_ROOT / "clients/contracts.json": build_client_contracts(),
    }
    for path, expected in generated.items():
        if path.read_bytes() != canonical_json_bytes(expected):
            raise M0Error(f"stale generated contract: {path}")
    module_map = REPO_ROOT / "docs/design/current/module-map.md"
    if module_map.read_text(encoding="utf-8") != build_module_map():
        raise M0Error("generated module map is stale")
    references = {}
    for scenario_id in REFERENCE_IDS:
        path = (
            REPO_ROOT
            / f"benchmarks/results/m0/reference/{scenario_id}.json"
        )
        if not path.is_file():
            raise M0Error(f"missing benchmark reference: {scenario_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["scenario_id"] != scenario_id:
            raise M0Error(f"benchmark reference ID mismatch: {scenario_id}")
        if value["repository"]["dirty"]:
            raise M0Error(f"benchmark reference was captured from a dirty tree: {scenario_id}")
        if value["contract_sha256"] != actual_lock["aggregate_sha256"]:
            raise M0Error(f"benchmark contract hash mismatch: {scenario_id}")
        if value["invariant_status"] != "passed":
            raise M0Error(f"benchmark invariant failure: {scenario_id}")
        references[scenario_id] = value["semantic_result_digest"]
    return {
        "schema_version": "m0-freeze-audit-v1",
        "status": "passed",
        "oracle_commit": inventories["config"]["oracle_commit"],
        "m0_commit": git.commit,
        "clean": not git.dirty,
        "contract_sha256": actual_lock["aggregate_sha256"],
        "inventory_counts": {
            family: len(inventories[family]["rows"])
            for family in INVENTORY_FAMILIES
        },
        "fixture_count": len(build_fixture_manifest()["rows"]),
        "benchmark_semantic_digests": references,
        "environment": environment_metadata(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit(require_clean=args.require_clean)
        sys.stdout.buffer.write(canonical_json_bytes(result))
        return 0
    except (M0Error, OSError, KeyError, ValueError) as exc:
        print(f"M0 final audit error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
