"""Generate the current architecture map from the M0 module disposition."""

from __future__ import annotations

from collections import Counter
import json
from typing import Any

from .common import REPO_ROOT


SUBSYSTEMS = (
    ("Simulation scheduler", "macro_sim/economy.py", "Per-economy phase execution and publication."),
    ("World", "macro_sim/world/", "FX, trade, capital, migration, sanctions, pegs, and BSP coordination."),
    ("Configuration", "macro_sim/config/", "Latest Config model, profiles, schema, and new-game normalization."),
    ("Accounting kernel", "macro_sim/core/ledger.py", "Money, credit, reserve, and securities invariants."),
    ("Policy", "macro_sim/core/policy*.py", "Domestic/external live policy state, registry, validation, and control metadata."),
    ("Controller", "macro_sim/controllers/", "Institutional seats, decisions, transactions, replay, costs, and Gym boundary."),
    ("Shocks", "macro_sim/shocks/", "Typed exogenous shock tapes, realization, disclosure, and scenarios."),
    ("Agents", "macro_sim/domain/", "Households, firms, banks, employment, and market state."),
    ("Demography and labor", "macro_sim/demographics/, macro_sim/labor/", "Population, households, relationships, participation, and employment state."),
    ("Markets and behavior", "macro_sim/markets/, macro_sim/behavior/", "Planning, matching, and decentralized trade protocols."),
    ("Economic systems", "macro_sim/systems/", "Banking, production, settlement, housing, energy, fiscal, and securities phases."),
    ("Reporting and diagnostics", "macro_sim/reporting/, macro_sim/diagnostics/", "Metrics, probes, scorecards, and oracle diagnostics."),
    ("RL", "macro_sim/rl/", "Versioned environment, codecs, training, evaluation, and deployable artifact."),
    ("Desktop worker", "macro_sim/desktop/", "Transport-neutral Godot protocol adapter and snapshot service."),
    ("Godot client", "desktop/godot/", "Native desktop presentation, interaction, and local main-menu flow."),
)


def _inventory() -> dict[str, Any]:
    return json.loads(
        (REPO_ROOT / "schemas/m0/inventory/modules.json").read_text(
            encoding="utf-8"
        )
    )


def build_module_map() -> str:
    rows = _inventory()["rows"]
    actions = Counter(row["action"] for row in rows)
    owners = Counter(row["owner_milestone"] for row in rows)
    lines = [
        "# Current Module Map",
        "",
        "This document is generated from the checked M0 module-disposition inventory.",
        "The inventory is authoritative for file coverage, migration action, and owner",
        "milestone; this page provides the human-oriented subsystem view.",
        "",
        "## Runtime Architecture",
        "",
        "| Subsystem | Current path | Responsibility |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {name} | `{path}` | {responsibility} |"
        for name, path, responsibility in SUBSYSTEMS
    )
    lines.extend(
        [
            "",
            "## Migration Disposition Summary",
            "",
            f"Tracked runtime/client/config/script assets: **{len(rows)}**.",
            "",
            "| Action | Files |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| `{name}` | {count} |" for name, count in sorted(actions.items()))
    lines.extend(["", "| Owner milestone | Files |", "|---|---:|"])
    lines.extend(f"| `{name}` | {count} |" for name, count in sorted(owners.items()))
    lines.extend(
        [
            "",
            "The canonical per-file rows and hashes are in",
            "[`schemas/m0/inventory/modules.json`](../../../schemas/m0/inventory/modules.json).",
            "Regenerate this page only through",
            "`uv run python scripts/cpp_migration/generate_module_map.py --write`.",
            "",
        ]
    )
    return "\n".join(lines)
