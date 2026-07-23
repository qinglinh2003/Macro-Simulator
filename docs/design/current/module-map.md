# Current Module Map

This document is generated from the checked M0 module-disposition inventory.
The inventory is authoritative for file coverage, migration action, and owner
milestone; this page provides the human-oriented subsystem view.

## Runtime Architecture

| Subsystem | Current path | Responsibility |
|---|---|---|
| Simulation scheduler | `macro_sim/economy.py` | Per-economy phase execution and publication. |
| World | `macro_sim/world/` | FX, trade, capital, migration, sanctions, pegs, and BSP coordination. |
| Configuration | `macro_sim/config/` | Latest Config model, profiles, schema, and new-game normalization. |
| Accounting kernel | `macro_sim/core/ledger.py` | Money, credit, reserve, and securities invariants. |
| Policy | `macro_sim/core/policy*.py` | Domestic/external live policy state, registry, validation, and control metadata. |
| Controller | `macro_sim/controllers/` | Institutional seats, decisions, transactions, replay, costs, and Gym boundary. |
| Shocks | `macro_sim/shocks/` | Typed exogenous shock tapes, realization, disclosure, and scenarios. |
| Agents | `macro_sim/domain/` | Households, firms, banks, employment, and market state. |
| Demography and labor | `macro_sim/demographics/, macro_sim/labor/` | Population, households, relationships, participation, and employment state. |
| Markets and behavior | `macro_sim/markets/, macro_sim/behavior/` | Planning, matching, and decentralized trade protocols. |
| Economic systems | `macro_sim/systems/` | Banking, production, settlement, housing, energy, fiscal, and securities phases. |
| Reporting and diagnostics | `macro_sim/reporting/, macro_sim/diagnostics/` | Metrics, probes, scorecards, and oracle diagnostics. |
| RL | `macro_sim/rl/` | Versioned environment, codecs, training, evaluation, and deployable artifact. |
| Desktop worker | `macro_sim/desktop/` | Transport-neutral Godot protocol adapter and snapshot service. |
| Godot client | `desktop/godot/` | Native desktop presentation, interaction, and local main-menu flow. |

## Migration Disposition Summary

Tracked runtime/client/config/script assets: **199**.

| Action | Files |
|---|---:|
| `adapter` | 18 |
| `keep` | 7 |
| `keep_client` | 16 |
| `oracle_only` | 30 |
| `port` | 91 |
| `port_or_adapter` | 33 |
| `wrap_native_worker` | 4 |

| Owner milestone | Files |
|---|---:|
| `m0` | 35 |
| `m1` | 14 |
| `m10` | 46 |
| `m11` | 20 |
| `m3` | 4 |
| `m4` | 20 |
| `m5` | 5 |
| `m6` | 7 |
| `m7` | 27 |
| `m8` | 8 |
| `m9` | 13 |

The canonical per-file rows and hashes are in
[`schemas/m0/inventory/modules.json`](../../../schemas/m0/inventory/modules.json).
Regenerate this page only through
`uv run python scripts/cpp_migration/generate_module_map.py --write`.
