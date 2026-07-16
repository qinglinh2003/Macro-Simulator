# Checkpoint / Save Design (v24 candidate)

**Branch**: `feat/checkpoint-save` · **Status**: design → implementation
**Goal**: save/resume the full simulation state, so that (a) multi-hour runs survive
crashes and preemption, (b) crash states can be interrogated in minutes instead of
re-simulated for hours, (c) counterfactual forks can branch from any point of a
shared history, and (d) the container format is the seed of the future game's
save-file format.

---

## 1. The one architectural decision

**Engine-NEUTRAL container around an engine-SPECIFIC state blob.**

The eventual game frontend will likely be driven by a compiled engine (C++/Rust).
That engine will *never* load a Python object graph: state layout, RNG streams and
float-op ordering all differ, so cross-language bit-identical resume is a fantasy.
What *does* survive the engine swap is everything around the blob:

| layer | lifetime |
|---|---|
| container layout, `header.json` schema | permanent (game save format) |
| ruleset serialization (= the Config set) | permanent |
| event/command log schema (player interventions) | permanent (becomes the network protocol) |
| history series format (records) | permanent (game charts) |
| `state.pkl.gz` python blob | Python engine only; a compiled engine registers its own blob format tag |

Therefore: do **not** hand-write a field-by-field schema for the world state now.
The model is still evolving weekly (this week alone changed claim-layer semantics
twice); a hand schema would silently drift — worse than a loud pickle failure.
Pickle covers the whole object graph *by construction* (RNGs, ledgers, EMAs,
caches, estate suspense, lot books). The hand schema happens once, when the model
freezes, as part of the compiled-engine port — and this container is where it slots in.

## 2. Container format

`*.msim` = a zip:

```
checkpoint.msim
├── header.json      # engine-neutral, readable by anything (incl. a save-slot UI)
│     container_format: "msim-container-v1"
│     blob_format:      "python-pickle-v0"     # a C++ engine writes "cpp-soa-v1"
│     tick:             3304
│     engine_class:     "World" | "Economy"
│     git_commit:       "<hex>"                # code version that wrote the state
│     config_digest:    "<16 hex>"             # sha256 over the run's Config reprs
│     blob_bytes:       123456789
│     + free-form meta (seed, out_dir, label, ...)
└── state.pkl.gz     # pickle protocol 5, gzip level 1 (state is float-heavy; speed > ratio)
```

Design points:

- **Atomic write**: write `<path>.tmp`, then `os.replace`. A crash mid-save can
  never corrupt the previous checkpoint.
- **Rolling slots**: the runner keeps `checkpoint.msim` (latest) — overwritten
  atomically each interval. Keeping N historical slots is a runner policy, not a
  format concern.
- **Version guard**: `load_checkpoint(..., require_same_commit=True)` refuses
  state written by a different git commit (class layout may have changed; pickle
  would fail loudly at best, resume with stale semantics at worst). Default is a
  warning, hard-refusal is opt-in — day-to-day debugging often wants to load a
  crash dump *after* editing code, and must be able to.
- **Security note**: pickle = arbitrary code execution on load. Fine for a local
  dev tool; **never** load third-party `.msim` files. The game-era structured blob
  removes this hazard; until then `load_checkpoint` documents it loudly.

## 3. What exactly is state? (the inventory)

Everything reachable from the engine object — pickle walks it for us:

- `World`: economies list, FX dealer (inventory, valuation, net worth), rates,
  reserves/peg state, trade/migration machinery, `world_records`, world RNGs,
  `_import_source`, bilateral matrices.
- Per `Economy`: `cfg` (frozen dataclass), ledger (accounts/debt/reserve overlay),
  agents (households, firms C/K, banks, housing), `_bonds` lot book, government,
  CB, Technology object, labor accounts, demographic state (persons, vital-rate
  machinery, `PersonClaimLedger`, `household_to_account`, estate suspense,
  posting-id caches), per-module EMAs and clocks, `records`, `t`, RNGs.
- **Sidecar** (lives outside the engine object, must ride along explicitly):
  the `WorldProbeCollector.records` list (identity-report input). The collector
  itself is `{world, records}` — we persist only the records and rebuild the
  wrapper on resume (avoids pickling a second reference path to `world`).

Known non-state (excluded by construction): open file handles (none held by the
engine), the probe collector wrapper, anything under `scripts/`.

Two failure modes the tests must catch:

1. **Unpicklable member sneaks in later** (file handle, lambda, thread pool) →
   guard test: build small World → save → load in-process, every run of the suite.
2. **Hidden global state outside the object graph** (module-level cache, global
   RNG use) → the bit-identity gate below is the detector: any global state lost
   across a process boundary diverges the continuation.

## 4. The acceptance gate: bit-identity across a process boundary

The contract is absolute — a resumed run is *indistinguishable* from an
uninterrupted one:

```
digest(run 2N ticks straight)
  == digest(run N → save → LOAD IN A FRESH PROCESS → run N more)
```

- Digest = sha256 over json-serialized `records` + `world_records` rows
  (the same discipline as the frontier digest `43ed38f7...`).
- **Fresh process is non-negotiable**: same-process load can hide global-state
  leaks and hash-seed dependence. The test spawns a subprocess for the
  resume leg (PYTHONHASHSEED deliberately NOT pinned — if set-iteration order
  affects arithmetic anywhere, we want the gate red, not masked).
- Run the gate on BOTH engine shapes: single `Economy` (fast, catches domestic
  modules) and small coupled `World` with peg + migration (catches FX dealer,
  cross-border state, world RNGs).

## 5. Runner integration

`run_portrait(..., checkpoint_every=0, resume=None)` (and CLI flags
`--checkpoint N` / `--resume PATH` on `openecon_production.py`):

- The `collector.run(ticks)` call unrolls into an explicit `for t in range(start, ticks)`
  loop (the collector is already `run = N × step()`, so this is a no-op refactor —
  same call sequence, verified by the frontier digest).
- Every `checkpoint_every` ticks: atomic save of `checkpoint.msim` (world + probe
  records sidecar) into the run's out dir. Skipped on the final tick (the run is
  about to write its real outputs).
- **Crash forensics**: `except AssertionError` → save `crash_state.msim` at the
  failing tick, print the path, **re-raise unchanged**. A failed save must never
  mask the original assertion (save wrapped in its own try/except).
- Resume: load container → `start_tick = header["tick"]` → rebuild collector
  around the loaded world with the sidecar records → continue the loop. The
  post-run CSV/summary code path is untouched (it only reads `world` + records).
- Default (`checkpoint_every=0, resume=None`) is behaviorally identical — the
  loop refactor is covered by the frontier digest check.

## 6. Costs (measured envelope, to verify during implementation)

- Save time: pickle+gzip of the 14k-agent World ≈ O(state size); target < 5 s per
  save. At `--checkpoint 1000` (≈ every 25 min of wall time) overhead ≪ 1%.
- Size: records dominate late-run state (850 cols × N ticks × 6 economies, floats).
  Acceptable for v1 (disk is cheap, single rolling slot). If it becomes painful:
  v1.1 splits records into an append-only `history/` member and checkpoints only
  the live state + row counts — format has room for this without breaking readers.

## 7. Test plan (rich, as agreed)

`tests/test_checkpoint.py`:

1. **Round-trip smoke (Economy)**: tiny closed frontier economy → 40t → save →
   load in-process → fields match (`t`, ledger balance sum, record count).
2. **Bit-identity, Economy, cross-process**: 60t straight vs 30t + save + resume
   in a `subprocess` → sha256 of records identical.
3. **Bit-identity, World, cross-process**: small coupled world (n=2, peg on,
   migration on) → same split-run digest equality over world_records + both
   economies' records.
4. **Probe-collector continuity**: same split World run under `WorldProbeCollector`;
   the identity report (`diagnose_world`) over stitched records equals the straight
   run's report (checks-pass booleans + finding ids).
5. **Atomicity**: monkeypatched failure mid-write → previous checkpoint file intact
   and loadable.
6. **Header integrity**: `read_header` without unpickling; wrong `blob_format` /
   `container_format` → clean `ValueError` (no partial unpickle).
7. **Version guard**: header with a different `git_commit` + `require_same_commit=True`
   → refusal; default → loads with warning.
8. **Crash dump**: force a failing assertion inside a run (monkeypatch a gate) →
   `crash_state.msim` exists, loads, and its `world.t` matches the crash tick;
   original AssertionError still propagates.
9. **Frontier digest unchanged**: the existing digest check (43ed38f7) re-run —
   proves the loop unroll + default-off flags change nothing.

## 8. Explicit non-goals (v1)

- No structured/language-neutral world-state schema (game-era work, post-freeze).
- No save-file forward-migration between commits (guard + refuse instead).
- No events.log yet — there are no player interventions in headless runs; the
  member slot in the container is reserved, the schema lands with the frontend
  protocol design.
- No UI/thumbnail metadata (game-era header extensions; header is free-form).
