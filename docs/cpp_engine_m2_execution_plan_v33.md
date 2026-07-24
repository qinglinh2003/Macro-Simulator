# C++ Engine M2 Execution Plan (V33)

Status: executable plan  
Branch: `refactor/cpp-m2-v33`  
Frozen base: `m1-native-foundation-v33`  
Base commit: `d7af86944a840d2f0465001cdf971dc4fdc1cd88`  
Scope: canonical state and transactional accounting; no production Python phase
is replaced in M2

## 1. Outcome

M2 turns the empty native session from M1 into the canonical state and
accounting root required by the first native economic tick in M4. It delivers
deterministic entity stores, account/reserve/loan/ownership books, atomic
multi-book transactions, exact rollback, state digests, and a real checkpoint
round trip.

M2 is accepted only when:

1. every authoritative fact has one declared native owner;
2. all financial mutations pass through one transaction boundary;
3. a rejected transaction restores the exact pre-transaction digest,
   allocators, free lists, and named RNG counters;
4. the hand-authored and randomized Python-oracle corpora agree with C++;
5. the canonical checkpoint reloads to the same state digest;
6. the steady transfer hot path performs no lookup by string and no allocation;
7. the native posting benchmark meets the frozen M2 budget;
8. M1 evidence remains immutable and the full existing Python suite stays
   green.

This milestone does not run production economic phases and does not replace
`macro_sim.core.ledger.Ledger`.

## 2. Frozen inputs and derived budget

M2 consumes, but never rewrites:

- tag `m1-native-foundation-v33`;
- `schemas/m0/hashes.lock.json`;
- `schemas/m0/manifests/invariants.yaml`;
- `schemas/m0/manifests/m4_v0_v1.yaml`;
- `schemas/m0/manifests/benchmark_scenarios.yaml`;
- `benchmarks/results/m0/reference/m4_v0_cash_loop.json`;
- `benchmarks/results/m0/reference/m4_v1_capital_fiscal.json`;
- `schemas/m1/canonical_encoding_vectors.json`;
- `schemas/m1/checkpoint_prototype.json`;
- `native/dependencies.lock.json`;
- ADR 0001.

The V33 roadmap records 247,938 Python `Ledger.transfer` calls taking 1.047
seconds cumulatively. M0 did not emit a separate transfer microbenchmark
artifact, so M2 records this explicit derivation instead of silently inventing
an M0 artifact:

```text
python_profile_ns_per_transfer = 1.047e9 / 247938 = 4222.83 ns
m2_native_median_budget        = 20%             = 844.57 ns
```

The checked M2 budget is therefore:

- median no-journal transfer at most 844 ns;
- median committed batch of 1,024 transfers at most 1,200 ns per transfer;
- median rollback batch of 1,024 transfers at most 1,500 ns per transfer;
- zero measured allocations after capacity reservation in all three loops.

Timing is reported on every platform but the absolute rejection threshold is
enforced only on the M0-pinned Apple arm64 performance host. Cross-platform CI
enforces correctness, warnings-as-errors, and sanitizer cleanliness.

## 3. Binding decisions

### 3.1 Identity and slots

- Stable public IDs are monotonic unsigned 64-bit values and are never reused.
- Dense store slots are `{index: u32, generation: u32}` handles.
- A freed slot increments its generation before reuse.
- Free-list ordering is canonical and journaled.
- Stable iteration order uses a never-reused append sequence, not physical slot
  order.
- `AccountId`, `LoanId`, and `OwnershipLotId` identify records. Account
  semantics live in an immutable typed `AccountKey`, never in encoded strings.

`AccountKey` contains account kind, economy, owner kind/value, currency, and
settlement node. Institutional owners include Treasury, central bank, dealer,
rounding residual, and commercial bank.

### 3.2 Money and residual policy

- Money remains finite IEEE-754 binary64.
- Commands reject negative or non-finite amounts.
- Transaction balance uses deterministic Neumaier summation.
- Exactly balanced transactions commit without a residual entry.
- A representational residual no larger than
  `8 * epsilon * max(1, sum(abs(legs)))` may be closed only through the
  transaction's declared rounding-residual account.
- A larger residual rejects the transaction as unbalanced.
- The correction is a normal journaled posting and contributes to the tracked
  representational-drift metric.
- No store privately repairs money.
- Nonnegative-balance validation uses the M0 registered absolute tolerance
  `1e-8`; values inside the tolerance remain visible and are never silently
  clamped.

### 3.3 Canonical owners

| Fact | M2 owner |
|---|---|
| household/firm/bank identity and alive state | typed slot store |
| common M4 V0/V1 household and firm columns | component stores |
| cash and deposits | `PostingBook` |
| bank reserves | `ReserveBook` |
| loan principal, lender, borrower, and terms | `LoanBook` |
| beneficial ownership fractions | `OwnershipBook` |
| institutional account identities | `InstitutionRegistry` |
| stable IDs, free lists, and append order | store allocators |
| named global RNG counters | `NamedCounterBook` |
| mutations and inverse records | `TickTransaction` |

Indexes are deterministic projections. Validation may detect an invalid index
but may not repair authoritative state.

### 3.4 Transaction boundary

A `TickTransaction` has these stages:

1. collect typed commands;
2. stable-sort by command ordinal and typed IDs;
3. validate the complete cumulative batch;
4. reserve book and undo-journal capacity;
5. capture allocator, free-list, counter, and mutated-value inverses;
6. apply no-fail/no-allocation primitives;
7. run registered invariants;
8. commit and discard undo data, or roll back in reverse order.

`WorldTransaction` in M2 coordinates multiple root states and proves atomic
rollback, but it does not yet execute World economic phases.

Fault injection uses deterministic ordinals:

- before validation;
- after capacity reservation;
- after each applied command;
- before each invariant;
- immediately before commit.

### 3.5 Genesis

The M2 `GenesisSpec` is deliberately smaller than the production `Config`. It
contains only state required by the frozen M4 V0/V1 verticals:

- economy and currency IDs;
- household count;
- consumption-firm and capital-firm counts;
- settlement-bank count;
- government capability;
- aggregate opening money;
- opening physical capital;
- seed and named-counter declarations.

The deterministic builder:

- creates identities in manifest order;
- creates one primary account per household and firm;
- creates required bank, Treasury, central-bank, dealer, and residual accounts;
- distributes aggregate opening money with one explicit final residual;
- assigns firms and households to settlement banks deterministically;
- rejects unsupported capabilities rather than creating inert state;
- emits a genesis digest and component counts.

### 3.6 Checkpoint

ADR 0001 remains binding. M2 writes a canonical ZIP/STORE archive containing:

```text
manifest.fb
metadata.json
arrays/<stable-id>.npy
```

The first M2 checkpoint contains every M2 authoritative store, allocator state,
append order, named counter, and contract identity. It contains no C++ object
layout, pointer, unordered-container layout, Python object, or pickle.

Loading validates limits, paths, the `MSCP` FlatBuffers identifier, required
features, entry hashes, canonical JSON, strict NPY 2.0 headers, dimensions,
IDs, references, and all M2 invariants before publishing a newly constructed
state.

The native implementation must reproduce the checked M1 canonical encoding
vectors byte-for-byte.

## 4. Work packages

### M2-01 — Contracts, layout, and dependency preparation

Deliver:

- this execution plan;
- `schemas/m2/manifests/gates.yaml`;
- checked performance budget and fixture schemas;
- new typed IDs, account/owner enums, slot handles, and component contracts;
- deterministic native dependency integration from the M1 source lock.

Exit:

- M1 frozen schemas and evidence differ by zero bytes;
- all public structs have compile-time layout/size assertions where ABI-facing;
- no account or institution lookup depends on a magic string.

### M2-02 — Canonical stores and genesis

Deliver:

- reusable generation-safe slot store;
- household, firm, bank, and account identity stores;
- M4 V0/V1 component columns;
- institution registry and deterministic genesis builder;
- stable iteration views and allocator snapshots.

Exit:

- create/remove/reuse corpus rejects stale handles;
- two independent genesis builds have identical digests;
- V0/V1 component and account counts match checked fixtures;
- unsupported capability combinations fail without partially published state.

### M2-03 — Accounting books

Deliver:

- `PostingBook`;
- `ReserveBook`;
- `LoanBook`;
- `OwnershipBook`;
- typed account lifecycle and settlement-node lookup;
- no-journal mutation primitives used only after batch validation.

Exit:

- exact same-bank, cross-bank, Treasury, central-bank, loan-origination,
  repayment, and ownership fixtures pass;
- all mandatory indexes reconcile;
- steady transfer hot path has no string lookup and no allocation.

### M2-04 — Transactions and rollback

Deliver:

- balanced multi-leg commands;
- `TickTransaction` and minimal `WorldTransaction`;
- undo arena and reverse application;
- allocator/free-list/named-counter journaling;
- deterministic fault injection;
- commit receipts with pre/post state digests.

Exit:

- every fault ordinal restores the exact prior digest;
- nested or concurrent mutation of one root is rejected;
- a failed final invariant publishes no receipt or state;
- a successful commit cannot be rolled back.

### M2-05 — Invariants and differential oracle

Deliver:

- A4 deposit conservation;
- A5 net financial worth identity;
- reserve conservation;
- loan lender/borrower ownership identity;
- finite and nonnegative balance gates;
- deterministic structured state digest;
- simple Python reference model and generated randomized command tapes.

Exit:

- hand-authored fixtures are exact;
- at least 100 seeds and 10,000 total randomized operations match the oracle;
- invalid cases return the same normalized error family;
- invariant failure reports the first stable invariant ID and pre-failure
  digest.

### M2-06 — Native checkpoint

Deliver:

- canonical JSON encoder/decoder matching M1 vectors;
- checked FlatBuffers manifest generation;
- deterministic ZIP/STORE writer/reader;
- strict NPY 2.0 arrays;
- M2 state save/load API;
- corruption, limit, feature-evolution, clone, and continuation tests.

Exit:

- save bytes are identical across repeated runs;
- save/load preserves the exact M2 state digest;
- corrupt or unsupported archives fail before state publication;
- macOS, Linux, and Windows produce the same semantic manifest digest.

### M2-07 — Bindings and installed artifacts

Deliver:

- session-level batch APIs for genesis, transaction tapes, digest, and
  checkpoint bytes;
- C ABI capability/version query additions without breaking M1 ABI;
- nanobind batch surface;
- installed C and isolated-wheel smokes.

Exit:

- no per-transfer Python callback exists;
- Python can submit one batch and receive one receipt;
- an M1 client still negotiates ABI version 1 successfully.

### M2-08 — Performance, gates, and freeze

Deliver:

- same-bank, cross-bank, reserve, commit, and rollback benchmarks;
- allocation counter in benchmark builds;
- PR, nightly, milestone, and release gates;
- deterministic M2 source/contract locks and final audit;
- macOS/Linux/Windows CI plus ASan/UBSan on supported Unix platforms.

Exit:

- local milestone graph passes from a clean worktree;
- full Python regression is green;
- same-commit cross-platform CI artifacts pass;
- M2 performance budget passes on the pinned host;
- `refactor/cpp-engine-v33` fast-forwards to the accepted commit;
- accepted commit receives tag `m2-canonical-accounting-v33`.

## 5. Test matrix

| Layer | Required coverage |
|---|---|
| compile-time | strong-ID separation, record layout, exhaustive enums |
| store | slot reuse, stale handles, stable order, free-list rollback |
| fixture | exact postings, reserves, loans, ownership, genesis |
| model-based | randomized operations against the Python reference |
| fault | every deterministic injection ordinal and allocation failure |
| invariant | A4, A5, reserves, loans, finite, nonnegative |
| persistence | vector parity, round trip, corruption, limits, evolution |
| adapter | C ABI and isolated wheel batch lifecycle |
| performance | median/p95/p99, allocations, invariant status |
| regression | complete existing Python suite |

Sanitizers:

- ASan and UBSan are mandatory on macOS and Linux;
- TSan is a non-blocking diagnostic until M2 introduces shared mutation;
- Windows runs MSVC warnings-as-errors, native tests, C consumer, and wheel
  smoke.

## 6. Commit sequence

1. `docs: define M2 canonical accounting execution plan`
2. `feat: add canonical identity stores and genesis`
3. `feat: add native posting reserve and loan books`
4. `feat: add transactional commit and exact rollback`
5. `test: add M2 invariants and differential oracle`
6. `feat: add native canonical checkpoint round trip`
7. `feat: expose M2 batch accounting interfaces`
8. `perf: gate native accounting hot paths`
9. `ci: add M2 cross-platform acceptance`
10. `test: freeze M2 canonical accounting milestone`

Commits may be split when a generated artifact, dependency, or portability fix
needs independent review. No translated production economic phase may enter
M2.

## 7. Branch and integration policy

- Development remains in `refactor/cpp-m2-v33`.
- `refactor/cpp-engine-v33` moves only by `--ff-only` after acceptance.
- M0 and M1 audit branches/worktrees remain available and unchanged.
- M2 does not merge to `dev`.
- The freeze tag is `m2-canonical-accounting-v33`.
