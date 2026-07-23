"""Validated M0 fixture manifests and typed input tapes."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from macro_sim.config import Config
from macro_sim.controllers.coordinator import SEATS
from macro_sim.core.external_policy import ExternalPolicy
from macro_sim.core.policy import Policy
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.shocks.spec import ShockTape

from .common import (
    REPO_ROOT,
    SchemaError,
    aggregate_hash,
    canonical_json_bytes,
    require_unique_ids,
    sha256_bytes,
    validate_stable_id,
)
from .inventory import normalize


SOURCE_ROOT = REPO_ROOT / "schemas/m0/manifests"
OUTPUT_ROOT = REPO_ROOT / "tests/fixtures/m0"
TRACE_PROJECTION = (
    "policy_rate",
    "public_capital",
    "house_price",
    "ledger_total_money",
    "ledger_total_credit",
    "record_count",
)


def _load_yaml(name: str) -> dict[str, Any]:
    path = SOURCE_ROOT / name
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SchemaError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SchemaError(f"{path}: document root must be an object")
    return value


def build_config(factory: str, overrides: dict[str, Any]) -> Config:
    if factory == "base":
        return Config(**overrides)
    constructor = getattr(Config, factory, None)
    if not callable(constructor) or not factory.startswith("v"):
        raise SchemaError(f"unknown Config factory: {factory}")
    return constructor(**overrides)


def load_tape_bundle() -> dict[str, Any]:
    raw = _load_yaml("tapes.yaml")
    if raw.get("schema_version") != "m0-tape-source-v1":
        raise SchemaError("unsupported tape bundle schema")
    start = date.fromisoformat(raw["calendar_start"])
    seats = set(SEATS)
    semantics = set()
    represented_seats = set()
    for row in raw.get("policy", []):
        validate_stable_id(row["transaction_id"])
        tick = int(row["reference_tick"])
        if date.fromisoformat(row["decision_date"]) != start + timedelta(days=tick):
            raise SchemaError(f"{row['transaction_id']}: decision date/tick mismatch")
        lag = int(row["declared_lag_ticks"])
        if date.fromisoformat(row["expected_effective_date"]) != (
            start + timedelta(days=tick + lag)
        ):
            raise SchemaError(f"{row['transaction_id']}: effective date/lag mismatch")
        if row["seat"] not in seats:
            raise SchemaError(f"{row['transaction_id']}: unknown seat")
        represented_seats.add(row["seat"])
        for action in row["actions"]:
            lever = REGISTRY.get(action["lever"])
            if lever is None:
                raise SchemaError(
                    f"{row['transaction_id']}: unknown lever {action['lever']}"
                )
            if lever.owner_role != row["seat"]:
                raise SchemaError(f"{row['transaction_id']}: lever/seat mismatch")
            if lever.decision_group != row["group"]:
                raise SchemaError(f"{row['transaction_id']}: lever/group mismatch")
            error = lever.validation.check(action["value"], action["value"])
            if error:
                raise SchemaError(f"{row['transaction_id']}: {error}")
            semantics.add(lever.semantics)
    if represented_seats != seats:
        raise SchemaError("policy tape must represent every seat")
    if semantics != {"immediate", "new-contracts-only", "state-transition"}:
        raise SchemaError("policy tape must represent every policy semantic type")

    ShockTape.from_dict(raw["shock"])
    rng_ids = {
        row["id"]
        for row in _load_inventory("rng")["rows"]
        if row["kind"] == "rng_stream"
    }
    for row in raw.get("realization", []):
        validate_stable_id(row["realization_id"])
        if row["stream_id"] not in rng_ids:
            raise SchemaError(f"{row['realization_id']}: unknown RNG stream")
    for row in raw.get("action", []):
        validate_stable_id(row["action_id"])
        if row["task_id"] != "fiscal_stabilization_v1":
            raise SchemaError(f"{row['action_id']}: unknown task")
        if row["action"] not in ([0], [1], [2]):
            raise SchemaError(f"{row['action_id']}: invalid directional action")
    return normalize(raw)


def _load_inventory(family: str) -> dict[str, Any]:
    import json

    return json.loads(
        (REPO_ROOT / f"schemas/m0/inventory/{family}.json").read_text(
            encoding="utf-8"
        )
    )


def build_fixture_manifest() -> dict[str, Any]:
    raw = _load_yaml("fixtures.yaml")
    if raw.get("schema_version") != "m0-fixture-source-v1":
        raise SchemaError("unsupported fixture source schema")
    source_rows = raw.get("rows")
    if not isinstance(source_rows, list):
        raise SchemaError("fixture source rows must be an array")
    require_unique_ids(source_rows)
    tape = load_tape_bundle()
    tape_sha = sha256_bytes(canonical_json_bytes(tape))
    rows = []
    for source in source_rows:
        row = dict(source)
        fixture_id = validate_stable_id(row["id"])
        config = build_config(row["config_factory"], row["config_overrides"])
        config_value = normalize(asdict(config))
        policy_value = normalize(asdict(Policy.from_config(config)))
        external_value = normalize(asdict(ExternalPolicy()))
        for evidence in row["evidence_tests"]:
            if not (REPO_ROOT / evidence).is_file():
                raise SchemaError(f"{fixture_id}: missing evidence test {evidence}")
        expected = row.get("expected_artifact")
        if expected is not None and not (REPO_ROOT / expected).is_file():
            raise SchemaError(f"{fixture_id}: missing expected artifact {expected}")
        result = {
            **normalize(row),
            "config_contract_sha256": sha256_bytes(
                canonical_json_bytes(config_value)
            ),
            "initial_policy_sha256": sha256_bytes(
                canonical_json_bytes(policy_value)
            ),
            "initial_external_policy_sha256": sha256_bytes(
                canonical_json_bytes(external_value)
            ),
            "genesis_contract_sha256": sha256_bytes(
                canonical_json_bytes(
                    {
                        "algorithm": "python-genesis-v124",
                        "config_sha256": sha256_bytes(
                            canonical_json_bytes(config_value)
                        ),
                        "seed": config.seed,
                    }
                )
            ),
            "tape_bundle_sha256": tape_sha,
            "trace_projection": list(TRACE_PROJECTION),
        }
        rows.append(result)
    rows.sort(key=lambda item: item["id"])
    row_hashes = {
        row["id"]: sha256_bytes(canonical_json_bytes(row)) for row in rows
    }
    return {
        "schema_version": "m0-fixture-manifest-v1",
        "rows": rows,
        "aggregate_sha256": aggregate_hash(row_hashes),
    }
