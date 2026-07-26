# M10 Execution Plan v34

## Purpose

M10 replaces the Python economic state owner used by controllers, Gym, diagnostics,
and the desktop worker with the M9 native World. Python remains the orchestration
client during this milestone. No Python callback or Python economic phase may occur
inside a native tick.

The baseline is `c7c3bf6`: the accepted five-million-agent M9 engine plus the free
next-day policy desktop protocol. M10 must preserve both.

## Current-state gap matrix

| Required M10 surface | M9 evidence | M10 gap |
|---|---|---|
| Full native World tick | `simulation::M9World::advance` | complete |
| Domestic policy mutation | policy structs exist in M5-M8 | no atomic World API |
| External policy mutation | `update_external_policies` | no combined domestic/external transaction |
| Causal/accounting metrics | nested M4-M9 metrics | no stable metric descriptors or tiered snapshot |
| Release/frontend metrics | Python release system only | no native source frame/history contract |
| Bounded history | none | required |
| Typed diagnostic probes | partial binding dictionaries | no privilege/tier boundary |
| Controller authority | Python object graph | no canonical native-owned envelope |
| Boundary atomicity | M9 copy/commit tick | no prepare/commit/abort bridge lease |
| Hybrid checkpoint | M9 economic checkpoint only | controller/objective envelope absent |
| Gym reset/clone | Python pickle | no native composite clone/reset facade |
| Desktop | Python `World` | must use native-backed facade |
| Free next-day policy | Python transaction | must enter the same native boundary batch |

## Delivery slices

### M10.0 — Contracts and acceptance harness

- Add the M10 execution plan, metric-contract schema, performance budget, and local
  acceptance driver.
- Freeze stable metric IDs, tier, unit, cadence, source path, and parity rule.
- Add CMake/build/test presets and update the native version only when the first
  executable M10 surface lands.
- Gate absence of Python callback hooks in native sources.

### M10.1 — Native reporting and history

- Add `MetricDescriptor`, `MetricFrame`, `FrontendFrame`, and `ProbeFrame`.
- Project every maintained M4-M9 metric to stable IDs without JSON in the core.
- Add a capacity-bounded history ring with explicit cadence and oldest/newest cursor.
- Expose read-only frames and paged history through C++ and nanobind.
- Prove current-frame equality, cursor behavior, bounded memory, and checkpoint
  continuation.

### M10.2 — Atomic World policy boundary

- Add complete domestic policy bundles for M5, M6, M7, energy, and housing.
- Validate all economy policy bundles and external policies before any live write.
- Add a sealed full-World policy batch with expected boundary and policy generation.
- Apply domestic and external policy as one atomic operation.
- Cover manual-rate companions, FX peg constraints, state-transition side effects,
  generation conflicts, injected failure, and exact rollback.

### M10.3 — `HybridControlledBridge`

- Store the canonical controller envelope inside the native bridge.
- Implement operation-keyed `update_controller` with expected hash and idempotent
  receipts.
- Implement exclusive `prepare_boundary`, immutable preview, `commit_boundary`, and
  `abort_boundary` leases.
- Make clone, snapshot, checkpoint, scheduling, and envelope mutation reject while a
  prepared lease is outstanding.
- Cross-check boundary, policy generation, event/release cursors, and envelope hash.
- Add hybrid checkpoints containing native World state, controller envelope, receipt
  cache, and optional Gym objective envelope.

### M10.4 — Python controller and Gym facade

- Add stable Python wrappers; tests must not import raw nanobind classes.
- Reconstruct Python scheduler/coordinator caches from the authoritative envelope.
- Route due-set policy execution through the bridge.
- Replace Python-world Gym factories with native-backed controlled sessions.
- Implement native composite clone/reset and homogeneous vector batches.
- Keep reward, discount, truncation, masks, and current `.msrl` evaluation semantics.

### M10.5 — Releases, diagnostics, and desktop cutover

- Derive role-filtered release snapshots from native source frames plus the envelope.
- Replace maintained diagnostic private-field access with typed native probes.
- Make `macro_sim.desktop.SimulationRuntime` native-backed by default.
- Preserve desktop protocol v4, free next-day policy, all current visualization data,
  and explicit Python-oracle backend selection.
- Reject startup if the requested current gameplay capability is absent natively;
  never fall back per phase.

### M10.6 — Parity, performance, and promotion

- Run native unit/C ABI/binding/checkpoint/fault suites.
- Run controller replay, split-run, release visibility, Gym, RL artifact, diagnostics,
  and desktop end-to-end gates.
- Run P0, P1, P2, P7 and ten-year memory gates.
- Prove a complete headless run contains no Python economic phase.
- Record the copy-versus-COW clone ADR from measured reset throughput and memory.
- Promote only after the synthetic integration result passes all M10 gates.

## Authoritative invariants

1. The native World is the only economic state authority.
2. Python owns orchestration logic during M10 but not an uncheckpointed authoritative
   controller cache.
3. A public boundary exposes either the complete old composite or complete new
   composite.
4. Policy changes are full-batch, generation-checked, and atomic across economies.
5. Free desktop policy bypasses governance costs and timing but not model invariants.
6. Controller/RL observations remain release-filtered; probe data is privileged.
7. History memory is bounded independently of simulation duration.
8. No supported backend mixes Python and native economic phases in one run.

## Exit evidence

M10 is accepted only when every bullet in the original M10 exit gate has a named,
passing local or CI test and an evidence record containing the exact commit, commands,
contract hashes, platform, timing, and memory result. A native tick benchmark or a
desktop screenshot alone is not M10 acceptance.
