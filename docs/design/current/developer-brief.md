# Developer Brief

This is the first document to read before changing the simulator.

## Current Frontier

The production oracle is the latest `Config.v124` Python engine. It is no
longer a closed-economy prototype: the current product includes coupled
multi-country `World` execution, FX and pegs, trade, external capital,
migration, sanctions, population dynamics, housing, energy, banking and
securities, institutional Policy/Controller decisions, exogenous shocks, a
deployed RL task, checkpoints, and the Godot desktop client.

The active architecture program is v33: preserve this complete Python behavior
as a measured oracle while moving economic execution incrementally to a C++20
engine. M0 freezes contracts, traces, fixtures, benchmarks, acceptance rules,
and current-client flows before any native economic implementation begins.

## Authoritative Runtime Boundaries

- `Config` is immutable creation state. New games always use the latest model
  constructor and country-profile overlays.
- `Policy` and `ExternalPolicy` are the live in-run control surfaces.
- `ControlledSimulationSession` is the only supported orchestration root for
  institutional, human, scripted, heuristic, random, and RL control.
- `ShockTape` and `ShockEngine` are the only supported exogenous-disturbance
  surface.
- `Economy.step` and `World.step` own execution order. The stable M0 phase
  registry names their observable boundaries.
- The Godot client talks to the single-writer desktop runtime protocol; it does
  not mutate engine state directly.

## Non-Negotiable Invariants

1. Every financial movement uses an explicit ledger primitive or an equivalent
   paired accounting operation.
2. Deposit, loan, securities, reserve, and external-position identities remain
   hard gates at their registered phase boundaries.
3. Existing capability-off and historical-version tripwires remain
   behavior-preserving unless a separately reviewed model correction is
   rebaselined.
4. Public observations respect release clocks and never read future or
   privileged state.
5. Controller actions are validated, committed, replayed, and costed at one
   shared transaction boundary.
6. Migration evidence uses stable typed IDs and canonical semantic projections,
   never Python object addresses or localized labels.

## Current Structural Risks

- Python execution is too slow for the intended population scale, long
  simulations, and RL throughput. The v33 migration addresses language and
  boundary cost, but algorithmic complexity still requires independent work.
- `Economy` remains a large orchestration/state carrier. Native migration must
  follow the frozen phase and ownership manifests instead of copying that class
  wholesale.
- Diagnostics still include privileged Python-oracle probes. Their checked
  disposition distinguishes future typed snapshots from oracle-only access.
- Python pickle checkpoints are intentionally engine-specific and are not a
  native save-file compatibility promise.

## Development Entry Points

- Architecture: [`module-map.md`](module-map.md)
- Change discipline: [`development-rules.md`](development-rules.md)
- C++ target design:
  [`../../cpp_engine_refactor_v33.md`](../../cpp_engine_refactor_v33.md)
- M0 execution and acceptance:
  [`../../cpp_engine_m0_execution_plan_v33.md`](../../cpp_engine_m0_execution_plan_v33.md)
- Durable economic rules: [`../core/`](../core/README.md)
- Historical evidence: [`../history/`](../history/README.md)
