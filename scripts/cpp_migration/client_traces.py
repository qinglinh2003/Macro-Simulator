"""Current desktop, Controller, RL, and persistence migration contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from macro_sim.desktop.runtime import (
    BUILTIN_RL_ARTIFACT,
    BUILTIN_RL_ARTIFACT_SHA256,
    PROTOCOL_VERSION,
)
from macro_sim.rl.envs import FiscalStabilizationEnvFactory

from .common import REPO_ROOT, SchemaError, canonical_json_bytes, sha256_bytes


def _inventory(family: str) -> dict[str, Any]:
    return json.loads(
        (REPO_ROOT / f"schemas/m0/inventory/{family}.json").read_text(
            encoding="utf-8"
        )
    )


def build_client_contracts() -> dict[str, Any]:
    desktop = _inventory("desktop_protocol")
    observations = _inventory("observations")
    events = _inventory("events")
    controller = _inventory("controller")
    desktop_ids = {row["id"] for row in desktop["rows"]}
    observation_ids = {row["id"] for row in observations["rows"]}
    event_ids = {row["id"] for row in events["rows"]}
    controller_ids = {row["id"] for row in controller["rows"]}
    flow_commands = [
        "desktop.command.new_game",
        "desktop.command.get_schema",
        "desktop.command.snapshot",
        "desktop.command.advance",
        "desktop.command.resolve_context",
        "desktop.command.trigger_shock",
    ]
    missing_commands = set(flow_commands) - desktop_ids
    if missing_commands:
        raise SchemaError(f"desktop client trace has unknown commands: {missing_commands}")
    rl_features = sorted(
        row["id"]
        for row in observations["rows"]
        if row["kind"] == "rl_feature"
    )
    release_series = sorted(
        row["id"]
        for row in observations["rows"]
        if row["kind"] == "observation_release"
    )
    factory = FiscalStabilizationEnvFactory()
    artifact_digest = hashlib.sha256(BUILTIN_RL_ARTIFACT.read_bytes()).hexdigest()
    if artifact_digest != BUILTIN_RL_ARTIFACT_SHA256:
        raise SchemaError("built-in RL artifact digest drift")
    rows = [
        {
            "id": "client.desktop.current-flow",
            "client": "godot",
            "protocol_version": PROTOCOL_VERSION,
            "commands": flow_commands,
            "response_ids": [
                "desktop.response.success",
                "desktop.response.error",
            ],
            "observation_ids": release_series,
            "persistence_adapter": "macro_sim.checkpoint",
            "main_menu_transition": "desktop/godot/scripts/main.gd::_return_to_main_menu",
            "evidence": "tests/test_desktop_runtime.py",
        },
        {
            "id": "client.controller.shared-transaction",
            "client": "controller",
            "occupants": [
                "direct",
                "human",
                "scripted",
                "heuristic",
                "random_walk",
                "rl",
            ],
            "event_ids": [
                "event.controller.proposal_submitted",
                "event.controller.decision_accepted",
                "event.controller.policy_transaction_effective",
            ],
            "controller_ids": [
                "controller.protocol.case-policy-proposal",
                "controller.protocol.case-policy-decision",
                "controller.protocol.case-policy-action",
            ],
            "evidence": "tests/test_controller_terminal_human_replay.py",
        },
        {
            "id": "client.rl.fiscal-stabilization-v1",
            "client": "rl",
            "task_id": factory.task_id,
            "environment_contract_hash": factory.environment_contract_hash,
            "observation_contract_hash": observations["metadata"][
                "fiscal_v1_context_contract_hash"
            ],
            "action_contract_hash": observations["metadata"][
                "fiscal_v1_action_contract_hash"
            ],
            "observation_ids": rl_features,
            "artifact_path": BUILTIN_RL_ARTIFACT.relative_to(REPO_ROOT).as_posix(),
            "artifact_sha256": artifact_digest,
            "evidence": "tests/test_rl_model_deployment.py",
        },
        {
            "id": "client.persistence.python-oracle",
            "client": "checkpoint",
            "container_format": "msim-container-v1",
            "blob_format": "python-pickle-v0",
            "operations": ["save", "fresh_process_load", "continue"],
            "evidence": "tests/test_checkpoint.py",
        },
    ]
    for row in rows:
        if not (REPO_ROOT / row["evidence"]).is_file():
            raise SchemaError(f"{row['id']}: missing evidence")
    if not set(rows[0]["response_ids"]) <= desktop_ids:
        raise SchemaError("desktop trace has unknown response IDs")
    if not set(rows[0]["observation_ids"]) <= observation_ids:
        raise SchemaError("desktop trace has unknown observations")
    if not set(rows[1]["event_ids"]) <= event_ids:
        raise SchemaError("Controller trace has unknown events")
    if not set(rows[1]["controller_ids"]) <= controller_ids:
        raise SchemaError("Controller trace has unknown protocol IDs")
    if not set(rows[2]["observation_ids"]) <= observation_ids:
        raise SchemaError("RL trace has unknown observations")
    rows.sort(key=lambda row: row["id"])
    return {
        "schema_version": "m0-client-contracts-v1",
        "rows": rows,
        "aggregate_sha256": sha256_bytes(canonical_json_bytes(rows)),
    }
