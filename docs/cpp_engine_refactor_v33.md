# C++ Engine Refactor v33

**Status:** implementation-ready design

**Branch:** `refactor/cpp-engine-v33`

**Baseline:** `dev@c0adcf1`

**Date:** 2026-07-23

**Primary platform:** macOS arm64, Apple Silicon

## 1. Executive decision

The simulator should gain a C++20 engine, but it must not be implemented as a
line-by-line translation of the current Python object graph.

The target is a native library that:

- owns the complete authoritative simulation state;
- advances whole phases or decision intervals in one native call;
- preserves the model's economic semantics and hard invariants;
- exposes a narrow versioned C ABI;
- exposes a high-throughput nanobind adapter to the existing Python controller,
  diagnostics, and RL stack;
- is used by a standalone native desktop worker while Godot continues to speak
  a process protocol;
- replaces duplicated state, dynamic private-field coupling, and periodic
  reconciliation with explicit ownership and transactional mutations.

The migration is intentionally incremental. Python remains the production
backend until a native vertical slice passes differential, invariant,
determinism, performance, and end-to-end gates. A backend switch may select
`python`, `native`, or `shadow`; it must never mix individual Python and C++
cash-flow calls in a production tick.

### 1.1 Decisions fixed by this document

1. The core engine uses C++20.
2. `macro_sim_core` has no dependency on Python, Godot, PyTorch, JSON objects,
   or UI types.
3. Python training remains Python/PyTorch. The simulation beneath Gym becomes
   native.
4. Python binding uses nanobind and a CPython 3.12 Stable ABI wheel where the
   chosen nanobind release supports it.
5. Godot keeps a loopback process boundary. GDExtension is not the first
   integration path.
6. A stable C ABI exists independently of nanobind.
7. The current `.msrl` numeric policy artifact remains the deployment contract.
8. The current `.msim` outer container may remain, but Python pickle state is
   not a native save format.
9. Old Python saves do not need to load in the C++ engine.
10. Python/C++ bit identity is not required. Native replay within a supported
    build is exact; cross-engine acceptance is semantic and tolerance based.
11. Counter-based named random streams replace manually allocated seed offsets.
12. C++ starts with `double` for money, prices, rates, and quantities so the
    migration does not also change economic units. All money movement is still
    centralized, typed, checked, and deterministically reduced.
13. Fast-math is forbidden in deterministic builds.
14. The first performance strategy is data ownership and algorithm repair, then
    native compilation, then deterministic parallelism. GPU execution is not a
    first-stage dependency.

## 2. Why this is now necessary

The Python engine is not merely paying interpreter overhead. Its hottest path
combines:

- per-transfer dictionary and callback dispatch;
- string and heterogeneous account identifiers;
- repeated `getattr` and private dynamic fields;
- duplicated household/person/security ownership books;
- every-tick full reconciliation of some mirrors;
- full scans for reporting and behavioral sensors;
- large mutable agent dataclasses containing persistent state, tick scratch,
  and several sector-specific variants;
- Python process fan-out for RL because a single engine cannot release useful
  CPU parallelism.

A small native extension around `Ledger.transfer()` would retain those
architectural costs and add tens of thousands of Python/C++ boundary crossings.
The useful boundary is therefore an `EngineSession` that owns state and executes
entire phases, ticks, tick batches, or decision intervals.

## 3. Goals and non-goals

### 3.1 Goals

- Increase practical person, household, firm, bank, dwelling, and world scale.
- Sustain the desktop's natural-time speed controls without blocking input.
- Make headless RL sampling an order of magnitude faster before considering a
  GPU for the small policy network.
- Preserve stock-flow consistency, monetary conservation, housing ownership,
  labor flow identities, securities identities, and balance-of-payments gates.
- Preserve policy, controller, shock, observation-release, and SMDP semantics.
- Make phase dependencies, read/write sets, and barriers inspectable.
- Give every economic fact one canonical owner.
- Make a failed phase or hard gate recoverable without a half-mutated world.
- Make native saves language neutral and independent of in-memory layout.
- Package and test on macOS arm64/x86_64, Linux x86_64/aarch64, and Windows x64.
- Keep source identifiers, source comments, generated schemas, and commit
  messages in English. Human-facing Chinese and future English text come from
  locale data.

### 3.2 Non-goals

- Rewriting PPO, experiment statistics, plotting, or economic diagnostics in
  C++ merely for language uniformity.
- Loading old Python pickle checkpoints in the native engine.
- Preserving Python object identity or Python private attributes.
- Reproducing Python's exact RNG streams or floating-point operation order.
- Changing economic equations and calibration during a mechanical migration.
- Embedding Python in the shipping Godot application.
- Making Godot a state owner.
- Using GDExtension as the initial simulation transport.
- Porting every visualization or test oracle to C++.
- Claiming that C++ alone fixes quadratic algorithms or unrestricted history.

## 4. Current baseline and measured evidence

### 4.1 Codebase shape

At the baseline commit:

- Python engine and application code: approximately 58,175 lines in 143 modules.
- Test files: 165.
- Largest runtime areas:

| Package | Approximate lines | Main responsibility |
|---|---:|---|
| `diagnostics` | 8,109 | probes, empirical checks, reports |
| `controllers` | 7,467 | institutional control and SMDP boundary |
| `demographics` | 7,406 | persons, relationships, lifecycle, claims |
| `rl` | 6,802 | PPO, codecs, vector environments, artifact |
| `systems` | 5,842 | real and financial economy phases |
| `reporting` | 3,890 | metrics and national accounts |
| `world` | 3,021 | FX, trade, capital, migration, BSP |
| `desktop` | 2,701 | new-game and frontend runtime |
| `config` | 2,539 | roughly 370 structural fields |
| `core` | 2,348 | ledger, policy, state, external policy |

Large cross-cutting runtime files include
`demographics/economic_bridge.py`, `reporting/metrics.py`,
`config/model.py`, `desktop/runtime.py`, `controllers/coordinator.py`,
`world/world.py`, and `systems/banking.py`. Their size is not by itself a bug,
but each currently crosses several ownership boundaries.

### 4.2 Product workload

The playable new-game preset enables the current feature set rather than a
historical model:

- full firm P&L and balance sheets;
- banks, reserves, household credit, interbank, bonds, and capital markets;
- demographics, household genesis, lifecycle, relationships, and estates;
- persistent fractional labor, second jobs, suspension, wage ladder, and
  participation;
- housing resale, mortgage, rental, and construction;
- energy, strategic reserves, deprivation, and energy mortality;
- consumption strata and family transfers;
- firm entry, exit, switching, technology, and sector dynamics;
- trade, FX, capital, migration, peg regimes, sanctions, and shocks;
- policy/controller/event/release contracts.

The start menu allows populations and firm counts far beyond what Python can
currently advance interactively. The Godot client exposes speeds of
1, 5, 15, and 60 simulation days per real second. At 60x, the complete backend
and snapshot path has an average budget of 16.7 ms per simulated day.

### 4.3 Local unprofiled benchmark

Reference machine:

- Apple Silicon arm64, 10 CPU cores, 24 GiB RAM;
- macOS 26.5.2;
- Apple Clang 21.0.0;
- Python 3.12.13 managed by `uv`;
- Godot 4.7.1.

Method: one playable full-feature economy, firm counts scaled with population,
three warm-up days, ten timed days.

| Persons | Households | Firms | Banks | Python ms/day |
|---:|---:|---:|---:|---:|
| 100 | 67 | 20 | 2 | 8.47 |
| 500 | 319 | 100 | 8 | 56.14 |
| 1,000 | 633 | 200 | 8 | 115.03 |

This is approximately linear over the measured range, but at roughly
0.11 ms per person when firms also scale. A simple extrapolation puts one
10,000-person economy near one second per day before frontend serialization.
That extrapolation is diagnostic, not a performance promise.

A separate three-country, 585-day desktop smoke on the current small preset took
about 24 seconds, or roughly 41 ms per simulated day. Even the small game is
therefore unable to sustain a true 60x continuously.

These are provisional audit measurements, not checked-in gate artifacts. M0
must rerun the exact committed scenarios and commands, record warmup and
hardware metadata, and check in raw JSON before any value becomes an acceptance
baseline.

### 4.4 Profiled hot path

`cProfile` adds substantial overhead, so the numbers below rank work rather
than predict release latency. A 1,000-person / 200-firm / 8-bank economy over ten
days produced about 31.2 million Python calls:

| Area | Profile evidence |
|---|---:|
| settlement and commit | 81% of profiled runtime |
| `Ledger.transfer` | 247,938 calls; 1.047 s cumulative |
| bank P&L finalization | 1.017 s cumulative |
| per-firm equity | 0.942 s cumulative |
| valuation / bank stock market | about 0.714 s |
| person claim identity | 0.460 s |
| all metrics | 0.316 s |
| goods / matching | about 0.263 / 0.205 s |
| planning | 0.169 s |
| energy | 0.141 s |
| labor | 0.092 s |

Across ten days the profile also recorded approximately:

- 5.37 million `dict.get` calls;
- 4.85 million `getattr` calls;
- 1.95 million `math.fsum` calls.

The dominant opportunity is not one equation. It is the combination of state
layout, transaction granularity, duplicated ownership, and repeated dynamic
dispatch.

These profile percentages are also provisional audit evidence. M0 checks in the
profiler command, scenario hash, raw profile, and summarized JSON before
milestone budgets depend on them.

### 4.5 Existing RL evidence

The documented Apple Silicon learning run simulated 116,800 engine days with
eight workers in 376 seconds, approximately 311 engine days/second across all
workers. The small MLP is not the limiting workload.

The built-in deployment artifact is already framework neutral:

- ZIP members: `manifest.json` and `weights.npz`;
- architecture: float32 `101 -> 128 -> 128 -> 3`;
- activation: `tanh`;
- action: one `gov_deficit_target` categorical direction;
- strict context/action/model hashes;
- `allow_pickle=False`, bounded sizes, finite-value and shape validation.

This means Python-trained policies can be used with a C++ engine without
retraining merely because the engine language changed.

## 5. Current architectural findings

### 5.1 `Economy` and `World` are god objects

`Economy.__init__` owns more than one hundred explicit fields and other fields
are first created by subsystems. `World` similarly combines state storage,
external-policy caches, FX settlement, records, and scheduling.

Most phase functions accept `econ: Any` and freely touch `econ._private_name`.
This hides dependencies from types, tests, and future parallel scheduling.

### 5.2 Tick correctness depends on call order, not phase contracts

The authoritative business order is a hand-written call list in
`economy.py`. A new subsystem is placed by editing that list and relying on
comments. `firm_full_pnl` even selects two materially different debt,
settlement, and housing orders inside one function.

### 5.3 Hard gates are late and mutation is not transactional

Most conservation checks run only after money, inventory, employment,
population, securities, and RNG state have already changed. If a phase or hard
gate raises, the world remains partially advanced. World trade preparation also
removes reserved export inventory before the later dealer gate.

### 5.4 Several facts have an authority plus mutable mirrors

Examples include:

- household financial balances and person-level ownership claims;
- household debt and mortgage shadow balances;
- ledger loans and `_loan_book`;
- bond lots and a separate face-value holding index;
- household/bank equity positions and person claims;
- `ExternalPolicy` and World policy caches;
- labor jobs, employer rosters, suspensions, and accounting stocks.

The current engine explicitly performs periodic full person-claim
reconciliation because those mirrors can drift. Native code must remove this as
a normal operating mechanism rather than make the rebuild faster.

### 5.5 Structural configuration is overly flat and only immutable by discipline

`Config` contains roughly 370 fields spanning every domain. It is mutable, and
its grouped views cache through `__dict__`. Presets, capability cascades,
policy registry entries, controller specifications, new-game whitelists, and
frontend descriptions repeat parts of the same schema.

Cross-domain fields such as energy-linked mortality legitimately appear in more
than one capability relationship. Today those relationships are handwritten in
independent maps, so completeness and consistency must be established by tests.
A generated declarative schema makes multiple prerequisites explicit and rejects
accidental duplicate entries instead of relying on dictionary structure.

### 5.6 Some release invariants are Python `assert`

At the baseline, a source scan finds 278 bare `assert` statements in
`macro_sim`, including 248 structural validations in `config/model.py`, six
behavioral preconditions, five housing checks, four matching checks, two
securities identities, and three World constructor checks. These disappear
under `python -O`. Trade-lot paths instead explicitly `raise AssertionError`;
those survive optimization but still need a typed domain-error contract.

Native config validation, phase preconditions, and hard invariants must be
non-disableable. Debug assertions are only appropriate after a runtime
precondition has already been checked.

### 5.7 Metrics mix observation with engine feedback

`reporting/metrics.py` performs broad reflective scans. Some output is merely UI
analytics, but committed CPI, GDP, inflation, housing, energy, and demographic
signals also feed future behavior. The native design must distinguish:

- causal sensors required for the next tick;
- accounting records required for invariants;
- policy-visible released observations;
- optional detailed analytics and frontend panels.

Causal sensors and invariant accounting are unconditional hot-path work.
Release/control-plane work follows its configured calendar, which may be daily;
optional detailed analytics and frontend panels remain cadence-bound.

### 5.8 Checkpoints serialize implementation rather than state schema

The `.msim` container is already engine neutral, but its Python state member is
a compressed pickle of the complete object graph and retained record history.
This is unsuitable for a native engine, untrusted files, schema evolution, or
bounded memory.

## 6. Target system architecture

```text
                                      ┌─────────────────────────────┐
 Godot desktop ── loopback protocol ─▶│ macro_sim_server (C++)      │
                                      └──────────────┬──────────────┘
                                                     ▼
                                      ┌─────────────────────────────┐
                                      │ macro_sim_control (C++20)   │
                                      │ schedule / seats / events   │
                                      │ releases / built-in actors  │
                                      └──────────────┬──────────────┘
                                                     │
 Python controllers / Gym / RL ── nanobind abi3 ─────┤
                                                     │
 C / future SDK ───────── stable C ABI ──────────────┤
                                                     ▼
                                      ┌─────────────────────────────┐
                                      │ macro_sim_core (C++20)      │
                                      │                             │
                                      │ EngineSession / WorldKernel │
                                      │ PhaseGraph + transactions   │
                                      │ typed domain stores         │
                                      │ deterministic RNG           │
                                      │ metrics / snapshot ports    │
                                      └─────────────────────────────┘
```

### 6.1 Layering

Dependencies only point downward:

1. **Applications**
   - `macro_sim_server`
   - command-line benchmark and replay tools
2. **Language adapters**
   - nanobind Python module
   - stable C ABI
   - `macro_sim_io` archive/protocol adapters; JSON/ZIP/checkpoint metadata live
     here and depend on core/control, never the reverse
3. **Controlled-session kernel**
   - scheduler, coordinator, adjustment costs, seats/occupants
   - event/replay chain and observation releases
   - remains Python through M10; receives a native implementation for the
     standalone worker in M11
4. **Engine session facade**
   - economic lifecycle, tick advance, declared shock scheduling, snapshots,
     schema-generated state export/import ports, and clone
5. **Economic schedulers**
   - `WorldPhaseGraph`
   - `EconomyPhaseGraph`
   - deterministic execution and barriers
6. **Domain services**
   - fiscal, banking, securities, labor, population, housing, energy, trade
7. **Canonical state stores**
   - entity stores, posting book, contract books, tick journals
8. **Primitives**
   - IDs, units, errors, RNG, hashing, serialization, stable reduction

No domain service may include an adapter header. No store may call a controller,
emit JSON, or know about a Godot panel.

### 6.2 Proposed repository layout

```text
native/
  CMakeLists.txt
  CMakePresets.json
  cmake/
  include/macro_sim/
    c_api/macro_sim.h
    contracts/
    control/
    core/
    engine/
    io/
    domains/
  src/
    contracts/
    control/
    core/
    engine/
    io/
    domains/
  bindings/python/
  apps/server/
  benchmarks/
  tests/
schemas/
  config/
  policy/
  external_policy/
  shock/
  metrics/
  observation/
  phase/
  rng/
  event/
  invariant/
  controller/
  desktop_protocol/
  checkpoint/
assets/i18n/
  en/
  zh_CN/
```

Generated C++ and Python contract files live in explicit generated directories
and contain a source-schema hash. They are checked in only if reproducible
generation and a CI stale-file check exist.

The Python package remains `macro_sim`. The native module should be an
implementation detail such as `macro_sim._native`; user code consumes a stable
Python facade, not nanobind-generated classes directly.

## 7. Core design rules

### 7.1 One canonical owner per fact

An index may mirror lookup structure, but only the owner's mutation API can
change both the primary value and its index. A cache is versioned and
rebuildable. Reconciliation detects corruption in validation builds; it does not
repair normal runtime state.

### 7.2 Persistent state and tick scratch are physically separate

Every domain separates:

- `PersistentState`: survives the tick;
- `OpeningSnapshot`: values whose economic semantics require tick-open data;
- `TickJournal`: flows accumulated during the tick;
- `CommandBuffer`: validated mutations not yet committed;
- `DerivedView`: cache or observation, never authoritative.

Resetting a tick clears contiguous journals rather than walking heterogeneous
objects and assigning dozens of fields.

### 7.3 Strong IDs and units

Public stable entity IDs are monotonic fixed-width values. Internal dense stores
use an index plus generation so deletion and compaction cannot create stale
references. An ID contains or is validated against its economy and entity kind.

`AccountId` is a tagged value:

```text
AccountId {
  AccountKind kind;
  EconomyId economy;
  EntityId owner;
  CurrencyId currency;
}
```

Magic values such as `"TSY"`, `"CB"`, `"CLEARING"`, and `"CBRES:3"` never
appear in hot paths.

Compile-time wrappers distinguish `Money`, `Quantity`, `Price`, `Rate`,
`PersonCount`, and `TickIndex`. They may initially store `double` or fixed-width
integers but cannot be accidentally interchanged.

### 7.4 Composition rather than one giant firm union

`FirmStore` keeps stable identity and common columns. Optional dense components
hold:

- production and productivity;
- inventory;
- capital;
- energy producer/consumer state;
- housing builder state;
- equity issuer state;
- income statement and balance-sheet inputs;
- tick journal.

This avoids a deep inheritance tree while preventing every firm from carrying
every sector's fields and branches.

### 7.5 Data-oriented layout

Hot iteration uses dense structure-of-arrays or tightly grouped components:

- contiguous alive entity index;
- compact numeric vectors;
- sparse side tables only for genuinely sparse contracts or holdings;
- sorted or deterministic adjacency lists;
- no hash-map iteration in an accepted ordering contract.

Dead persons and exited entities release slots through a generation-safe free
list. Stable serialized IDs do not change during compaction.

Physical slot order is not an economic ordering contract. Every order-sensitive
phase declares a stable `IterationOrderId`; population/social parity uses an
order-preserving alive view keyed by the current append/birth sequence (a
monotonic sequence that is never reused), even when dense slots compact or are
recycled. The same rule covers household, firm, bank, seller-array, and market
tie/self-fallback order. Swap-pop order is allowed only after a phase proves
order irrelevance. Phase traces record the iteration-order contract.

### 7.6 Central mutation paths

- Every financial mutation enters one `SettlementTransaction`.
- `PostingBook` is the canonical owner of deposit, Treasury, central-bank,
  dealer, and other cash-account balances.
- `ReserveBook` is the canonical owner of bank reserve positions. A payment
  that affects deposits and reserves commits both books atomically.
- Loan principal changes only through `LoanBook`.
- Interbank principal, accrued interest, lender, borrower, and maturity live
  only in `InterbankBook`; lender/borrower portfolios are indexes over it.
- OMO and other central-bank asset/liability contracts live in
  `CentralBankOperationBook`; they post cash/reserves through the same
  transaction rather than maintaining a second balance mirror.
- Recognized bank income and expense entries live in `BankPnlJournal`.
  `BankCapitalState` is the canonical loss-absorbing book-capital balance;
  `BankBalanceSheetView` is derived from the posting, reserve, loan, security,
  interbank, central-bank-operation, and capital books.
- Security ownership changes only through `SecurityBook`.
- Housing ownership changes only through `PropertyRegistry`.
- Employment changes only through `EmploymentBook`.
- Household membership changes only through `HouseholdMembership`.
- Cross-border inventory is held through `ReservationBook`.

Each API emits domain events and updates all mandatory indexes atomically.

## 8. State ownership map

| Economic fact | Native canonical owner | Derived/index consumers |
|---|---|---|
| structural rules | immutable `Ruleset` | every phase |
| capabilities | immutable `CapabilitySet` | phase enable predicates |
| domestic policy | `PolicyState` per economy | immutable boundary snapshot |
| external policy | `ExternalPolicyState` per economy | World boundary snapshot |
| deposits and cash accounts | `PostingBook` | balance views, metrics |
| reserves | `ReserveBook`, atomically coordinated with `PostingBook` | RTGS, OMO, interbank |
| loan principal and lender | `LoanBook` | bank portfolio, debt service |
| interbank principal and accrued interest | `InterbankBook` | lender/borrower indexes, maturity view |
| central-bank operations and claims | `CentralBankOperationBook` | OMO portfolio and counterparty views |
| bank income and expense entries | `BankPnlJournal` | period P&L statement |
| bank loss-absorbing book capital | `BankCapitalState` | derived regulatory/balance-sheet views |
| mortgages and collateral | `MortgageBook` referencing `LoanId` and `DwellingId` | LTV and foreclosure views |
| government bonds | `SecurityBook<BondContract>` | issuer and holder indexes |
| firm and bank equity | `SecurityBook<EquityContract>` | valuation and owner views |
| beneficial ownership allocation | generic `OwnerId` and ownership lots in the relevant book | household/person summaries |
| household topology | `HouseholdMembership` | consumption and UI views |
| persons and relationships | `PersonStore` / `RelationshipStore` | lifecycle and labor |
| jobs and rosters | `EmploymentBook` | labor accounts and firm views |
| dwellings and title | `PropertyRegistry` | listings, rental, collateral |
| leases | `RentalBook` | household and dwelling views |
| firms and physical stocks | component stores | markets and statements |
| FX rates | `RateVector` | trade, capital, migration |
| external principal/arrears | `ExternalPositionBook` | NFA and factor income |
| peg reserve cash balance | anchor-economy `PostingBook` account referenced by `PegState` | reserve/coverage view |
| peg anchor, pressure, integrity, account reference, and exit state | `PegState` per pegger | FX regime view |
| shock realization/lifecycle | materialized `ShockTape` plus `ShockEngine` announced/active/realized indexes and internal event chain | immutable phase overlays |
| causal macro sensors | `SensorStore` | next-tick behavior |
| public releases | `ReleaseStore` | controllers and UI |
| optional analytics history | append-only `HistorySink` | frontend and diagnostics |

### 8.1 Household and person financial ownership

The current two-ledger repair loop is replaced by one transaction:

1. a financial contract is owned by one or more explicit ownership lots;
2. household liquidity is represented by account ownership rather than a
   separately mutable person claim mirror;
3. a marriage, household move, death, or inheritance executes ownership
   transfers through the same book as trading;
4. household and person totals are projections from those lots;
5. a validation scan may prove projection equality but never rewrite it.

If a policy intentionally treats a household account as jointly owned, the
ownership rule is an explicit contract attribute, not an inferred repair.

### 8.2 Money representation

The migration starts with IEEE-754 `double` because the model currently uses
continuous money, prices, quantities, interest, and taxes over a wide dynamic
range. Converting to cents or arbitrary decimal during the port would change
behavior and obscure whether a difference is architectural or economic.

The following constraints apply:

- all postings are finite and validated;
- a transaction balances before commit;
- deterministic pairwise or compensated reductions are used where totals
  affect behavior;
- one explicit residual policy absorbs representational roundoff when a
  division cannot close exactly;
- no subsystem privately adjusts a conservation residual;
- tolerance is a typed ruleset value and diagnostics report both raw and
  tracked representational drift;
- a later ADR may evaluate fixed-point money after native semantic parity.

## 9. Transaction and failure model

Full copy-on-write of hundreds of thousands of entities every tick would waste
the performance gained from C++. Direct unjournaled mutation would preserve the
current failure hazard. The compromise is phase commit plus a tick undo journal.

For each phase:

1. read only declared stores and opening snapshots;
2. compute thread-local or shard-local commands;
3. stable-merge commands by a collision-free total ordering key;
4. validate cumulative effects of the full batch against balances, inventory,
   capacity, and transaction balance rather than validating each command only
   against opening state;
5. reserve all destination/store capacity and append inverse values or
   tombstones to the tick arena before mutation;
6. apply through no-allocation/no-fail store mutation primitives;
7. run phase invariants.

At the final closed-economy or World-scope hard gate:

- success discards the undo arena and publishes records/releases;
- failure applies inverse operations in reverse phase order and returns a typed
  error with the first failed invariant and trace digest.

`WorldTransaction` owns every economy's tick undo journal plus boundary policy
activation, `ShockEngine` lifecycle and overlays, dealer, reservation, FX,
external-position, external-policy-transition, clock, ID/free-list allocator,
and event-sequence journals. Peg adoption/exit/anchor changes may swap or seed
reserve-ledger positions, and annual dealer-loss mutualization may post cash;
these are boundary transactions, not mere snapshot replacement. Local economy
gates may reject early, but no economy publishes or increments its date until
the World coordinator has accepted all local and global gates. A failed
boundary restores the policy versions, shock sets, clocks, allocator state, and
event head as well as the economic books.

Ordinary counter-based draws have no mutable stream cursor to roll back. Their
sample address is derived from seed, stream, tick, entity, event kind, and draw
index. The exceptional named global-sequence counters described in section
17.1 are part of the phase/tick journal, so a failed phase cannot consume them.

External side effects are forbidden inside a tick. Files, sockets, UI events,
and history flushes occur only after commit.

Accepted post-commit output enters a deterministic idempotent outbox keyed by
delivery-lineage/session/boundary/sequence/sink. A disk, socket, or history-sink
failure leaves the simulation committed and retries delivery; it never reports
the accepted tick as economically rolled back.

### 9.1 Error model

Internal C++ uses a typed result/error model for expected domain failures and
exceptions only for construction bugs or resource failures. Across the C ABI:

- no C++ exception escapes;
- every call returns a stable status code;
- a session exposes a bounded diagnostic record;
- caller-owned and engine-owned buffers are unambiguous;
- a rejected tick leaves economic state at its immediately prior committed
  boundary. Multi-tick calls are tick-atomic rather than call-atomic: accepted
  ticks before a later rejection remain committed, and the typed result reports
  requested/completed ticks, last committed boundary, failure phase, and
  retrievable receipts. A `ControlledSession` remains at the failed boundary
  tick/economic digest but may commit only the specified audit/lifecycle
  `failed_at_execution` and refund transition from section 14.2.

## 10. Economy phase graph

The port must preserve the current causal ordering before attempting to improve it.
Each native phase descriptor declares:

- stable phase ID and schema version;
- dependency phase IDs;
- state read set;
- state write set;
- opening-snapshot requirements;
- enable predicate;
- command ordering key;
- local and barrier invariants;
- whether deterministic static sharding is permitted.

### 10.1 Current semantic mapping

There is exactly one boundary latch. `B0 ControlBoundaryLatch`, invoked by the
standalone or World coordinator, atomically revalidates and activates the whole
due domestic/external policy set, applies administrative cost/refund semantics,
advances `ShockEngine` lifecycle once, binds immutable shock overlays, and
captures the first snapshot epoch. No economy phase commits policy or realizes
a shock again.

| Barrier | Native phase group | Current work that must be preserved |
|---|---|---|
| B0 | `ControlBoundaryLatch` | due policy transaction; external-policy ledger transitions; shock announcement/activation/expiry and one-shot realization; boundary snapshot |
| E0 | `OpenBooks` | fiscal/tick journal reset; national accounts open; bank P&L reset |
| E1 | `OpenFinancialSystem` | policy rate; deposit competition; reserve intraday reset; OMO |
| E2 | `OpenRealEconomy` | public-capital lag; technology; bond maturity |
| E3 | `PopulationBoundary` | births/deaths/social events; household transitions; estates; indexes |
| E4 | `PlanAndFinance` | expectations and journals; firm planning; Gibrat shock; credit |
| E5 | `ProduceAndTradeDomestic` | labor; energy; production; causal sector-output accumulation; family transfers; goods; capital goods |
| W0 | `ExternalSettlementSeam` | World trade/capital/migration/FX uses all economies at the same seam |
| E6 | `SettleDomestic` | firm and household debt; housing; fiscal/firm settlement |
| E7 | `CloseInstitutions` | firm entry/exit; sector switch; equity; interbank; bank runs/failure; finalize bank P&L; bank entry; bond issuance |
| E8 | `ValidateAndMeasure` | local ledger, reserve, securities, housing, claims, and labor gates; provisional accounts/metrics |
| E9 | `StageLocalCommit` | after local/global gates: journaled sensors, lags, and local/world record buffers; no publication or date increment |

The current full-P&L ruleset orders firm debt, household debt, housing, then
settlement. The legacy ruleset orders settlement, combined debt, then housing.
These become two explicit pipeline definitions with separate contract hashes.
They must not remain a hidden branch inside one phase.

### 10.2 Required barrier semantics

- Planning reads one coherent declared pre-plan snapshot.
- Labor, energy, and production consume current plans.
- Export inventory is reserved before domestic buyers can consume it.
- Cross-border flows settle before domestic P&L and metrics close.
- Cross-border cash uses opening FX rates; rate movement follows the dealer
  flow gate.
- Current-tick tax, tariff, remittance, factor-income, and housing flows enter
  the same tick's national accounts.
- Lags are committed only after the tick is accepted.
- Releases are published only after all invariants pass.
- A read declaration names a snapshot epoch, not merely "opening state":
  `TickOpen` contains the accepted prior boundary plus B0 effects and pre-flow
  FX/external positions; `PostPopulationPrePlan` contains maturity,
  demographic, household, and estate transitions visible to planning; and
  `PreDealer` contains the domestic production/trade seam. A phase cannot read
  a field from an undeclared epoch.
- The next natural date/demographic tick is staged before E3 and is visible to
  age, birth, death, and every later phase, matching the current calendar
  semantics. `W.CommitBoundary` publishes that staged date and increments the
  external `economy.t`/`world.t` counters once; rollback restores both staged
  and published clocks.

### 10.3 World BSP graph

```text
B0 ControlBoundaryLatch (exactly once)
  -> atomically revalidate/activate the whole due domestic+external policy set
  -> apply peg/dealer-loss boundary ledger transitions
  -> advance shock lifecycle and bind immutable overlays
  -> reserve cross-border resources
  -> [parallel by economy] E0..E5
  -> W.DealerSettlement
       trade
       factor interest/cash/accrual/arrears on opening positions
       aggregate migrant-stock routing, remittances, and taxes
       peg defense
       external principal roll-forward excluding current interest/reserve moves
       dealer flow gate
       FX price search/update
       revaluation and provisional World record
  -> [parallel by economy] E6..E8
  -> W.ValidateGlobal
  -> [parallel by economy] E9
  -> W.CommitBoundary
       increment every economy date and the World date exactly once
       discard all undo journals atomically
  -> W.Publish
       append accepted history
       publish controller releases/events in deterministic order
```

The central dealer remains a deterministic barrier. Economy work on either side
may run concurrently only after static read/write analysis proves isolation.
For an uncoupled economy, the same coordinator invokes B0, E0 through E9,
commits its date exactly once, and then publishes accepted output. In a World,
E9 is forbidden before `W.ValidateGlobal`, and no engine-derived post-tick
history, release, or event is emitted before `W.CommitBoundary`. Boundary
releases, contexts, and canonical ingress described in section 14.2 occur
before the engine transaction and are not misclassified as post-tick output.

Current trade timing is preserved explicitly: World preparation reserves export
inventory and creates importer offers; domestic goods consumes those offers in
E5; actual cross-border cash/dealer settlement occurs only after every economy
has reached the seam.

Trade preparation becomes a real reservation transaction. A rejected World tick
automatically releases every lot; no phase directly subtracts inventory as a
side effect of "preparation."

## 11. Complete module disposition

This matrix is the coverage checklist. A milestone cannot claim parity while a
row assigned to it is silently delegated to Python inside a native tick.

| Current area | Current responsibility | Native target | Migration milestone |
|---|---|---|---|
| `config/model.py`, `schema.py`, `loader.py` | structural rules and overlays | generated immutable `Ruleset`, validation, preset loader | M0-M1 |
| `core/policy.py` | live domestic policy | generated `PolicyState`, typed boundary transaction | M1, completed economically in M5 |
| `core/policy_registry.py` | lever schema/ownership/validation | single policy schema generating Python/C++/JSON metadata | M0-M1 |
| `core/policy_control_specs.py` | adjustment controls | generated controller-facing lever contract | M0, M10 |
| `core/policy_explanations.py` | human-facing economics text | locale assets keyed by policy ID; never hot-path C++ | M0/UI follow-up |
| `core/external_policy.py` | tariffs, controls, migration, sanctions, FX regime | per-economy `ExternalPolicyState`; immutable World snapshot | M1, M9 |
| `core/ledger.py` | deposits, loans, securities offset, reserve overlay | typed posting, account, reserve, and loan books | M2 |
| `core/state.py` | incomplete facade | removed; replaced by domain stores and `EngineSession` | M1-M2 |
| `domain/agents.py` | household/firm/bank mutable unions | identity stores plus hot/cold components and journals | M2-M4 |
| `behavior/planning.py` | expectations and behavioral equations | pure typed functions with explicit inputs/results | M3 |
| `markets/matching.py` | order/trade protocols | deterministic reusable market kernel | M3 |
| `systems/planning.py` | plan orchestration | `PlanningPhase` | M4 |
| `systems/production.py` | real production | `ProductionPhase` | M4 |
| `systems/technology.py` | TFP and learning | `TechnologyPhase` and named shock stream | M4 |
| `systems/goods.py` | household goods market | `GoodsMarketPhase` with explicit import port | M4 |
| `systems/capital_goods.py` | investment goods | `CapitalGoodsPhase` | M4 |
| `systems/family.py` | family transfers | ownership/membership-aware transfer phase | M7 |
| `systems/switching.py` | firm sector switching | firm lifecycle command phase | M6 |
| `systems/settlement.py` | fiscal and firm cash settlement | balanced settlement transaction | M4-M5 |
| `systems/firm_accounting.py` | income statements | typed firm journal and statement projection | M4 |
| `systems/firm_balance_sheet.py` | replacement-value statements | derived valuation view | M4-M6 |
| `systems/firm_demographics.py` | firm entry/exit | generation-safe firm lifecycle phase | M6 |
| `systems/credit.py` | origination and debt service | `CreditService`, `LoanBook`, loss commands | M5 |
| `systems/banking.py` | bank P&L, RTGS, interbank, runs, failure, entry | split settlement, prudential, market, resolution, and lifecycle services | M5-M6 |
| `systems/central_bank.py` | rate, OMO, reserves | central-bank phase over typed books | M5 |
| `systems/securities.py` | government bonds | bond contracts, holder/maturity indexes | M6 |
| `systems/equity.py` | firm/bank equity | equity book and batched order generation/clearing | M6 |
| `systems/valuation.py` | portfolio valuation | pure valuation service; no banking back-import | M3, M6 |
| `systems/energy.py` | producers, intermediate/household energy, SPR | energy components and market/fiscal phases | M8 |
| `systems/deprivation.py` | deprivation sensor | causal sensor computed from committed energy/consumption | M8 |
| `systems/labor.py` | spot labor option | deterministic labor market kernel | M4 |
| `labor/persistent.py` | jobs, rosters, suspension, second jobs | `EmploymentBook` and persistent labor phase | M7 |
| `labor/accounting.py` | E/U/S/JG stocks and flows | incremental labor accounts and hard gate | M7 |
| `demographics/agents.py` | person state | `PersonStore` with alive dense view and archive | M7 |
| `demographics/rates.py` | vital rates | pure hazard functions | M3, M7 |
| `demographics/kernel.py` | births/deaths | statically sharded population phase | M7 |
| `demographics/relationships.py`, `social.py`, `union.py` | kinship, marriage, divorce, unions | indexed relationship/union stores and event phases | M7 |
| `demographics/lifecycle*.py` | leaving home and household lifecycle | membership transactions | M7 |
| `demographics/inheritance.py`, `estate.py`, `marriage_economics.py` | property and estate rules | financial ownership/estate service in M7; dwelling integration in M8 | M7-M8 |
| `demographics/economic_state.py`, `economic_bridge.py` | person/household financial mirror and integration | decomposed ownership books; bridge deleted | M7 |
| `demographics/macro_signal.py`, `stratification.py` | causal feedback and strata | typed sensor and classification phases | M7 |
| `demographics/leslie.py`, `multistate.py` | cohort/oracle models | retain Python oracle unless needed in live engine | Python validation |
| `demographics/validation.py`, `phase*.py`, visualization | validation harness | retain Python, consume native snapshots/traces | M0 onward |
| `housing/registry.py` | dwelling title and stock | `PropertyRegistry` | M8 |
| `housing/market.py` | resale listings and trades | deterministic property market | M8 |
| `housing/mortgage.py` | secured debt shadow and foreclosure | `MortgageBook` referencing canonical loan/collateral | M8 |
| `housing/rental.py` | leases and rent | `RentalBook` and rental phase | M8 |
| `housing/construction.py` | builders and new dwellings | builder component and mint commands | M8 |
| `housing/affordability.py` | housing sensor | causal housing metric | M8 |
| `shocks/spec.py`, `registry.py` | shock schema/channels | generated shock schema and stable channel IDs | M0-M1 |
| `shocks/engine.py`, `stochastic.py` | tape, lifecycle, and optional generation | materialized `ShockTape` plus deterministic `ShockEngine`; optional pre-run generator uses counter RNG | M1, channel parity by M9 |
| `shocks/scenarios.py` | packaged crises | data assets validated against shock schema | M9 |
| `economy.py` | construction, state bus, schedule | thin `EconomyKernel` plus explicit phase graph | assembled M4-M9 |
| `world/fx.py` | rates and dealer accounts | `RateVector` and typed dealer accounts | M9 |
| `world/trade.py` | sourcing, reservation, import/export settlement | reservation book and trade phase | M9 |
| `world/capital.py` | positions, factor income, arrears, peg | external position and peg services | M9 |
| `world/migration.py` | aggregate migrant stocks, best-host routing, remittances, and taxes | aggregate route/state service; no person/household move in parity | M9 |
| `world/country.py` | genesis country profiles and relative overlays | maintained data presets targeting generated `NewGameSpec` fields | M0-M1 |
| `world/world.py` | World state and BSP | `WorldKernel` and `WorldPhaseGraph` | M9 |
| `reporting/national_accounts.py` | flow accounting | incremental native accounting journals | M4 onward |
| `reporting/metrics.py` | causal and optional broad metrics | split sensors, core metrics, analytics collectors | M4, complete M10 |
| `reporting/collectors.py` | record collection | bounded columnar history sink | M10 |
| `reporting/diagnostics.py` | analysis | retain Python over public probe API | M10 |
| `checkpoint.py` | `.msim` plus pickle state | engine and controlled-session native members in the existing container | M10-M11 |
| `controllers/api.py`, `protocol.py` | transport-neutral facade and canonical contracts | generated/shared protocol plus Python and C++ adapters | M10-M11 |
| `controllers/coordinator.py`, `transaction.py`, `costs.py` | policy validation, staging, costs, execution | Python over native engine in M10; native `macro_sim_control` for shipping in M11 | M10-M11 |
| `controllers/scheduler.py`, `session.py` | calendars, triggers, boundary state machine | Python composite in M10; native controlled-session state machine in M11 | M10-M11 |
| `controllers/events.py`, `replay.py`, `observation.py` | hash chain, replay, releases/revisions | Python parity first; native event/release kernel for standalone worker | M10-M11 |
| `controllers/occupants.py` | human queue, random, heuristic, RL occupants | Python custom occupants remain; shipping built-ins and model references port in M11 | M10-M11 |
| `controllers/gym_adapter.py` | SMDP Gym interface and whole-session pickle reset | explicit composite engine/controller/objective genesis snapshot | M10 |
| `rl/*` training | PPO, buffer, experiments, statistics | retain Python/PyTorch | M10 |
| `rl/model.py`, `artifact.py` | portable deployment model | retain Python; add strict C++ inference loader for native server | M11 |
| `diagnostics/*` | deep probes and empirical reports | retain Python; replace private access with typed probe snapshots | M10-M11 |
| `desktop/new_game.py` | latest config and profile mapping | generated config facade; may remain Python until server cutover | M10-M11 |
| `desktop/runtime.py`, `server.py` | snapshot assembly and NDJSON worker | native-backed Python worker, then `macro_sim_server` | M10-M11 |
| `desktop/godot/scripts/simulation_client.gd` | loopback client and framing | retain Godot; implement version/token/request/delta protocol | M11 |
| `desktop/godot/scripts/main.gd`, `economic_map.gd`, `metric_chart.gd` | gameplay presentation and charts | retain Godot; consume versioned snapshots only | continuous, M11 E2E |
| `desktop/godot/scripts/start_menu.gd` | new-game editor | retain Godot; consume generated `NewGameSpec` metadata | M10-M11 |
| `desktop/godot/scripts/localization.gd`, `desktop/godot/i18n/*` | locale loading and catalogs | retain as data/presentation; add generated key checks | continuous |
| `desktop/godot/tests/*`, `scripts/run_godot_prototype.sh`, `scripts/desktop_smoke.py` | frontend and launcher acceptance | retain and extend to packaged native worker | M11 |
| `configs/base.yaml`, `configs/calibrations/*.yaml`, `configs/runs/*.yaml`, `configs/versions/*.yaml` | maintained presets, calibrations, and run manifests | validated data targeting generated current contracts; explicit rebaseline history | M0 onward |
| `macro_sim/data/locales/**/*` | localized runtime text | retained locale assets, validated for key completeness and kept outside engine contracts | continuous |
| `macro_sim/rl/artifacts/*.msrl` | built-in deployable policies | retained, hash-pinned assets; Python/native inference compatibility corpus | M10-M11 |
| `desktop/godot/project.godot`, `desktop/godot/scenes/main.tscn` | Godot project and primary scene graph | retained; protocol-version and packaged-worker acceptance | M11 |
| `pyproject.toml`, package entry points, launcher/package metadata, and future Godot export presets | build, install, launch, and export contract | migrate deliberately to native wheel/server packaging with installed-artifact tests | M1, M11 |
| `visualization/*`, `experiments/*` | plots and batch orchestration | retain Python | continuous |

### 11.1 Dependency cycles to remove

Current function-local imports conceal cycles:

- banking ↔ securities;
- mortgage ↔ credit ↔ banking;
- World writes private import/export offers that goods discovers by `getattr`;
- metrics discovers subsystem state through private reflection.

The native dependency direction is repaired with explicit ports:

- `PortfolioValuation`;
- `FundingCapacity`;
- `CreditLossSink`;
- `CollateralRegistry`;
- `ImportOfferBook` / `ExportReservationBook`;
- subsystem `MetricFragment` producers.

High-level phases wire these ports. Domain libraries do not import one another
in both directions.

### 11.2 Grouped-row manifest

For avoidance of doubt, wildcard/grouped rows in the matrix cover these current
modules. Package `__init__.py` files are export surfaces, not independent
economic phases.

- Configuration: `config/model.py`, `config/schema.py`, `config/loader.py`.
- Controller transaction core: `controllers/api.py`,
  `controllers/coordinator.py`, `controllers/costs.py`,
  `controllers/transaction.py`, and `controllers/protocol.py`.
- Controller time/occupants: `controllers/scheduler.py`,
  `controllers/session.py`, and `controllers/occupants.py`.
- Controller information/replay: `controllers/observation.py`,
  `controllers/events.py`, `controllers/replay.py`, and
  `controllers/gym_adapter.py`.
- Demographic social/topology: `demographics/relationships.py`,
  `demographics/social.py`, `demographics/union.py`,
  `demographics/lifecycle.py`, and
  `demographics/lifecycle_households.py`.
- Demographic property/feedback: `demographics/inheritance.py`,
  `demographics/estate.py`, `demographics/marriage_economics.py`,
  `demographics/macro_signal.py`, and `demographics/stratification.py`.
- Demographic oracle/tools: `demographics/leslie.py`,
  `demographics/multistate.py`, `demographics/validation.py`,
  `demographics/phase0.py`, `demographics/phase1_acceptance.py`, and
  `demographics/visualization.py`.
- RL environment/contract: `rl/codec.py`, `rl/envs.py`,
  `rl/vector_env.py`, and the controller Gym adapter.
- RL training: `rl/algorithm.py`, `rl/network.py`, `rl/buffer.py`,
  `rl/trainer.py`, and `rl/metrics.py`.
- RL evaluation/deployment: `rl/baselines.py`, `rl/experiment.py`,
  `rl/model.py`, `rl/artifact.py`, and `rl/cli.py`.
- Shock package: `shocks/spec.py`, `shocks/registry.py`,
  `shocks/engine.py`, `shocks/stochastic.py`, and `shocks/scenarios.py`.
- Diagnostics contracts/data: `diagnostics/models.py`,
  `diagnostics/registry.py`, `diagnostics/observed.py`, and
  `diagnostics/empirical.py`.
- Diagnostics execution: `diagnostics/probes.py`,
  `diagnostics/world_probes.py`, `diagnostics/static_audit.py`,
  `diagnostics/scenarios.py`, `diagnostics/runner.py`,
  `diagnostics/analysis.py`, `diagnostics/cli.py`, and
  `diagnostics/empirical_cli.py`.
- Desktop: `desktop/new_game.py`, `desktop/runtime.py`, and
  `desktop/server.py`.
- Visualization/experiments: `visualization/artifacts.py`,
  `visualization/specs.py`, `visualization/render.py`,
  `visualization/compare_versions.py`, and `experiments/runlog.py`.

## 12. Contract and schema architecture

The current model repeats field knowledge across `Config`, presets, policy
registries, controller specs, new-game code, explanations, metrics, and Godot.
The native migration creates one declarative source for each contract family.

### 12.1 Schema families

| Schema | Required metadata |
|---|---|
| config | stable ID, English name, type, unit, default, range, domain, capability dependency, genesis/runtime class |
| policy | stable ID; type/unit/default/range; `requires`, `enabled_if`, aliases and `shadowed_by`; IMMEDIATE/NEW_CONTRACTS/STATE_TRANSITION semantics with handler ID and read point; owner and decision group; regular/emergency lag and emergency eligibility; minimum hold; `control_scale`, `max_step`, administrative weight, and cost class |
| external policy | the complete policy-lever contract above plus directionality, target cardinality, external validation, transition handler, and World joint constraints |
| shock | kind/channel ID, magnitude min/max, one-shot flag, allowed targets/sectors, capability requirements, emergency seats, start/duration/ramps, announcement, visibility/roles, source/calibration/correlation/tags |
| metric | stable ID, type, unit, stock/flow/rate, nominal/real, cadence, causal/public/analytic class |
| observation | release field, source metric, delay, revision rule, seat visibility, normalization |
| phase | stable ID, dependencies, read/write sets, barriers, enable predicate, ordering and sharding contract |
| RNG draw | stable draw-kind ID, owning phase, distribution algorithm/version, entity/global addressing rule |
| event | stable event type, causal phase, required payload, visibility, replay/idempotency semantics |
| invariant | stable ID, owning barrier, required stores, severity, residual type, tolerance/diagnostic fields |
| checkpoint | field/table ID, required/default/deprecated status and migration rule |
| controller/run | stable seat and decision-group IDs, calendars/windows, trigger thresholds/persistence/hysteresis/cooldown/expiry, administrative capacity, cost/refund specs, occupant kind/config, `ShockAuthority` principal/seat grants and allowed kinds/targets/timing, objective/time normalization, lifecycle phases, replay/checkpoint compatibility |
| desktop protocol | versioned command, response, error, snapshot, page, delta, entity-detail, save-slot, launcher-handshake, compatibility, and full-resync contracts |

Code generation produces:

- immutable C++ structs and validators;
- Python dataclasses/enums and validators;
- canonical JSON Schema and contract hashes;
- CLI/frontend machine metadata;
- locale keys, but not translated prose;
- test vectors containing valid, boundary, and invalid values.

No handwritten consumer may duplicate a range or enum. CI regenerates into a
temporary directory and fails if checked-in output is stale.

### 12.2 Configuration layers

The 370-field flat config becomes:

```text
NewGameSpec
  GenesisConfig       initial people, firms, banks, dwellings, profiles
  StructuralRules     behavioral equations and structural parameters
  CapabilitySet       whether a mechanism exists
  InitialPolicy       controller-adjustable starting values
  WorldRules          coupling and dealer structure
  RuntimeOptions      threads, validation tier, history and snapshot cadence
```

`StructuralRules` and `CapabilitySet` are immutable after construction.
`PolicyState` changes only through a policy transaction. `RuntimeOptions` may
alter execution and observability but never economic results.

Historical `v124`-style constructors are not native types. Maintained scenario
presets are named data documents that target the current schema and are upgraded
explicitly. The game always uses the current engine; no frontend model-version
selector returns.

### 12.3 Localization

Source code, schema identifiers, comments, errors intended for developers, and
commit subjects remain English. Human-facing titles, policy economics
explanations, profile descriptions, tooltips, and format strings live in
packaged catalogs keyed by canonical locale ID. `zh_CN` remains the canonical
ID because both current loaders use it; `zh-CN` is accepted only as an input
alias normalized before lookup. During migration the existing
`macro_sim/data/locales/zh_CN/` and `desktop/godot/i18n/{en,zh_CN}.json`
catalogs are consolidated/generated without changing runtime keys.

Runtime protocol values use stable IDs. Godot maps them to locale data; it never
hashes or branches on translated strings.

M10-M11 moves current player-facing labels, titles, statuses, and prose out of
`desktop/runtime.py` and Godot scripts. Server snapshots contain stable IDs and
raw typed values only. CI rejects unapproved human-facing literals, missing
catalog keys, and packaged projects that omit `project.godot`, `main.tscn`, or
the required catalogs.

## 13. Engine APIs

### 13.1 C++ facade

The public C++ facade is deliberately coarse:

```cpp
class EngineSession {
public:
    static Result<EngineSession> create(
        const NewGameSpec&, Seed, const RuntimeOptions&);

    Result<AdvanceResult> advance_ticks(std::uint32_t ticks);
    Result<ShockScheduleResult> schedule_shock(const ShockSpec&);

    Result<SnapshotLease> snapshot(const SnapshotSpec&) const;
    Result<SnapshotLease> probe(const ProbeSpec&) const;
    Result<EngineSession> clone() const;
};

class ControlledSession {
public:
    static Result<ControlledSession> create(
        EngineSession, const ControllerRunSpec&);

    Result<DecisionResult> advance_until_decision(const AdvanceLimit&);
    Result<ProposalResult> submit_policy_proposal(
        const ProposalIngressRequest&);
    Result<ProposalResult> submit_human_proposal(
        const ProposalIngressRequest&);
    Result<void> timeout_context(const TimeoutContextRequest&);
    Result<PolicyDecisionResult> cancel_pending(
        const CancelPendingRequest&);
    Result<void> assign_seat(const SeatAssignmentRequest&);
    Result<ShockScheduleResult> schedule_shock(
        const ControlledShockScheduleRequest&);
    Result<PolicySchemaView> policy_schema(const AccessScope&) const;
    Result<DecisionContextView> decision_context(
        ContextId, const AccessScope&) const;
    Result<PendingDecisionList> pending(const AccessScope&) const;
    Result<ShockBulletinView> shock_bulletins(const AccessScope&) const;
    Result<SnapshotLease> released_snapshot(
        const SnapshotSpec&, const AccessScope&) const;
    Result<SnapshotLease> frontend_snapshot(
        const SnapshotSpec&, const AccessScope&) const;
    Result<ControlledSession> clone() const;
};

class HybridControlledBridge {
public:
    static Result<HybridControlledBridge> create(
        EngineSession, CanonicalControllerEnvelope);
    Result<ControllerUpdateReceipt> update_controller(
        const ControllerEnvelopeTransition&);
    Result<PreparedBoundaryLease> prepare_boundary(
        const SealedControlBatch&);
    Result<AdvanceResult> commit_boundary(
        PreparedBoundaryLease&&, CanonicalControllerEnvelope next);
    Result<void> abort_boundary(PreparedBoundaryLease&&);
    Result<ShockScheduleResult> schedule_shock(
        const ControlledShockScheduleRequest&,
        CanonicalControllerEnvelope next);
    Result<SnapshotLease> engine_snapshot(
        const SnapshotSpec&, const AccessScope&) const;
    Result<SnapshotLease> probe(
        const ProbeSpec&, const DiagnosticAccess&) const;
    ControllerEnvelopeView controller_envelope() const;
    Result<HybridControlledBridge> clone() const;
};

class CheckpointArchive {
public:
    static Result<ByteBuffer> save(const EngineSession&);
    static Result<ByteBuffer> save_hybrid(
        const HybridControlledBridge&, OptionalObjectiveEnvelope);
    static Result<ByteBuffer> save(const ControlledSession&);
    static Result<EngineSession> load_engine(
        ByteSpan, const LoadOptions&);
    static Result<LoadedHybridComposite> load_hybrid(
        ByteSpan, const LoadOptions&);
    static Result<ControlledSession> load_controlled(
        ByteSpan, const LoadOptions&);
};
```

There is no supported API to set an endogenous balance, population outcome,
firm inventory, or macro result. Policies and declared shocks are the only
gameplay mutation surfaces. Test-only fixtures build state through a separate
library that is not linked into release applications.

Controlled mutation request envelopes carry the authenticated principal/actor,
server-derived seat/access scope, operation/idempotency ID, and canonical
payload. The server constructs them after authentication; actor/seat claims
inside an untrusted proposal body are ignored. This applies to automatic/human
proposal ingress, timeout, cancel, seat assignment, and controlled shock
scheduling so event/replay principals cannot disappear at the native boundary.

`schedule_shock` is legal for an engine-only session only at a committed
boundary and is a trusted host/scenario API that validates time, schema,
capability, topology, and atomicity but has no controller actor. A controlled
session may accept it in any boundary phase, but
current-boundary announcement/start is legal only at `BOUNDARY_START` before
release/trigger prelude; a request accepted in `AWAITING_HUMAN` or
`READY_TO_COMMIT` must announce/start no earlier than the next boundary. It
validates an authenticated run-spec `ShockAuthority`, unique shock ID,
channel/capability/topology
constraints, and rejects a backdated start or announcement without changing
schedule, lifecycle sets, event cursor, or digest. Accepted live scheduling is
a canonical controller input event containing the full normalized `ShockSpec`,
actor, authority, request/idempotency ID, and boundary; replay injects it, while
announce/start/end/realize remain derived shock events. This full request lives
only in the privileged access-controlled audit/replay chain and checkpoint; no
gameplay query or frontend snapshot exposes it. The public derived-transition
mirror follows section 14.4 visibility rules. Ordinary policy seats
cannot bypass the coordinator unless the run schema explicitly grants that
authority. The same operation exists in the C ABI, Python binding, and desktop
server.

`HybridControlledBridge` is the coarse M10 bridge from the Python coordinator.
The sealed batch contains due domestic/external action IDs and targets, expected
policy versions, cost/admin settlement references, and canonical input-event
references—not precomputed ledger mutations. `prepare_boundary` revalidates,
derives transition side effects, acquires exclusive handle access, and runs
B0/the economic tick through the ordinary in-place `WorldTransaction`/undo
journal. The prepared lease exposes only an immutable result preview; no other
engine query or mutation is permitted, so the logical public composite remains
at its prior boundary without copying every store.

Python then builds, allocates, serializes, and validates the complete next
controller/release/event/outbox envelope off to the side. Native code then
validates its schema/hash and cross-state facts against the prepared preview:
boundary, decision/effective versions, pending/cost/admin/refund state,
release/outbox cursors, event sequence, and event head. `commit_boundary`
performs only no-fail discard of the undo journal plus swaps of the small
controller/publication roots; publication starts afterward. An exception
before commit reverses the journal and aborts the lease. If Python's object
cache fails after commit, the stored
envelope is authoritative and reconstructs it before any next call. No Python
callback occurs inside commit. This permits lag-zero and World-wide due-set
parity without a half-advanced M10 composite before `macro_sim_control` becomes
native in M11. `advance_ticks` is only the no-new-decision convenience path.

The hybrid archive validates and atomically stores engine state, canonical
Python controller envelope, and optional Gym objective/horizon envelope. A
fresh load returns those neutral members without constructing a partially
advanced Python object. M11 `ControlledSession` consumes the same schemas.
Fault injection at every prepare, Python-build, commit, cache-rebuild, and
publish ordinal proves that no controller/economic half-state is observable.

The bridge consumes its `EngineSession`; M10 code receives no mutable backdoor.
It exposes scoped engine snapshots/probes, controller-envelope access, archive
operations, and an authorized shock-scheduling transaction that cross-validates
and swaps the updated envelope with the engine shock schedule. An outstanding
`PreparedBoundaryLease` exclusively locks the bridge: scheduling, snapshot,
archive, clone, and envelope mutation reject until commit/abort, and a lease
generation mismatch fails closed. Corrupt/stale envelope fixtures exercise
every cross-state field above.

Controller-only state never lives solely in a Python cache.
`update_controller` is an operation-keyed atomic envelope transaction with
expected-prior-hash, generated-schema validation, monotonic phase/event/release
cursors, input/derived hash-chain checks, and engine policy-version/boundary
cross-checks. Context opening, human proposal/timeout/cancel ingress, seat
assignment, prelude release state, and `failed_at_execution`/refund after an
aborted economic prepare must update the bridge before the API acknowledges
them. Same key+payload returns the stored receipt; a stale hash or mismatched
payload rejects. `prepare_boundary`, query, and `save_hybrid` read only the
bridge-owned envelope and reject a Python expected-hash mismatch, so an
`AWAITING_HUMAN` checkpoint cannot serialize stale controller state. The Python
object graph is a reconstructable cache, never the commit authority.

In M10 the Python service derives role-filtered `ReleaseSnapshot` and
`FrontendSnapshot` from the scoped engine snapshot plus authoritative envelope;
cross-seat negative tests remain mandatory. M11 moves the same operation behind
native `ControlledSession` without widening fields.

### 13.2 Stable C ABI

The long-term ABI exposes separate engine-only and controlled-session opaque
handles with versioned byte/struct contracts:

```c
typedef struct msim_engine msim_engine;
typedef struct msim_hybrid_controlled msim_hybrid_controlled;
typedef struct msim_controlled_session msim_controlled_session;
typedef struct msim_prepared_boundary msim_prepared_boundary;
typedef struct msim_snapshot_lease msim_snapshot_lease;
typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    const uint8_t *data;
    uint64_t size;
} msim_bytes_view;

MSIM_API msim_status MSIM_CALL msim_engine_create(
    const msim_create_request *request,
    msim_engine **out_engine);
MSIM_API msim_status MSIM_CALL msim_engine_load(
    const msim_load_request *request,
    msim_engine **out_engine);
MSIM_API msim_status MSIM_CALL msim_engine_advance(
    msim_engine *engine,
    const msim_advance_request *request,
    msim_owned_buffer *out_result);
MSIM_API msim_status MSIM_CALL msim_hybrid_prepare_boundary(
    msim_hybrid_controlled *session,
    const msim_bytes_view *sealed_control_batch,
    msim_prepared_boundary **out_prepared,
    msim_owned_buffer *out_preview);
MSIM_API msim_status MSIM_CALL msim_hybrid_commit_boundary(
    msim_hybrid_controlled *session,
    msim_prepared_boundary **prepared,
    const msim_bytes_view *next_controller_envelope,
    msim_owned_buffer *out_result);
MSIM_API void MSIM_CALL msim_prepared_boundary_abort(
    msim_prepared_boundary **prepared);
MSIM_API msim_status MSIM_CALL msim_engine_schedule_shock(
    msim_engine *engine,
    const msim_bytes_view *canonical_shock,
    msim_owned_buffer *out_result);
MSIM_API msim_status MSIM_CALL msim_controlled_submit(
    msim_controlled_session *session,
    const msim_bytes_view *canonical_proposal,
    msim_owned_buffer *out_result);
MSIM_API msim_status MSIM_CALL msim_controlled_save(
    const msim_controlled_session *session,
    msim_owned_buffer *out_checkpoint);
MSIM_API void MSIM_CALL msim_buffer_free(msim_owned_buffer *buffer);
MSIM_API void MSIM_CALL msim_engine_destroy(msim_engine **engine);
```

The excerpt shows the representation rules rather than replacing the generated
normative header. That header also exposes controlled create/load/advance/
schedule-shock, human-submit, timeout, cancel, seat-assign, role-scoped
schema/context/pending/bulletin queries, released/frontend snapshot acquisition,
archive save/load, clone, and pointer-to-handle destroy; engine archive
save/load/clone and snapshot/probe acquisition; hybrid create/prepare/commit/
abort, atomic controller-envelope update, authorized shock scheduling, scoped
snapshot/probe, archive, and clone; and `msim_snapshot_data` plus
pointer-to-lease release.
Every lifecycle has a
C-only installed-library smoke test. `ProbeSnapshot` is never exposed through
the gameplay server; only an explicitly privileged diagnostics client can ask
the engine-only API for it.

Rules:

- the public header defines `MSIM_API` visibility and `MSIM_CALL` as the
  platform C calling convention; exported symbols use C linkage and a version
  script/export list;
- no STL type, exception, reference, template, allocator, or internal pointer
  crosses the ABI;
- public scalars are fixed-width integers; every struct begins with
  `struct_size` and `abi_version`, has declared 8-byte maximum alignment and
  zero-required reserved fields, and is covered by compile-time layout tests;
- canonical byte payloads are little-endian; native structs are never serialized
  by dumping memory;
- `msim_status` is a fixed `int32_t` enum. Null is allowed only where explicitly
  stated; `data == NULL` is valid only with `size == 0`; all output pointers are
  initialized to null/zero on failure;
- the library exposes ABI, engine, schema, and capability versions;
- output buffer ownership is paired with the same library's free function;
  freeing a null/zero buffer is a no-op and clears the struct;
- destroy takes a pointer-to-handle, is a no-op for null, and clears the handle,
  so repeated cleanup of the cleared variable is safe;
- create/load failures are retrievable through a bounded thread-local
  `msim_last_error`; live-handle failures also update that handle's diagnostic;
- one mutable call at a time is permitted per handle and callbacks/re-entrancy
  are forbidden; independent handles are concurrent;
- ABI major changes receive a new SONAME/DLL ABI major; symbols are additive
  within a major and older struct sizes remain accepted when required fields
  are present.

Every mutating request carries an operation ID. Canonical result bytes and a
bounded receipt slot are allocated before the no-fail commit. Repeating the
same ID+payload returns the stored receipt without advancing; ID reuse with a
different payload rejects. Status distinguishes `rejected_no_commit`,
`partial_progress`, and `committed_result_delivery_failed`. In the last case
the caller retrieves the persisted receipt with `msim_result_get(operation_id)`.
Nanobind conversion/allocation failure raises an exception containing that
operation ID and follows the same recovery path. A caller is never told only
“failed” after state committed with no way to learn the accepted boundary.
Unacknowledged receipts are never evicted; a bounded full cache applies
backpressure until `msim_result_ack`, and receipt/ack state is checkpointed.

Snapshots use explicit leases. A snapshot call creates a reference-counted,
immutable buffer generation; advancing or destroying the session does not
invalidate an outstanding lease. The lease owns the memory until closed, the
Python array uses the lease as its base object, and the server copies or frames
from the same immutable generation. Per-session outstanding lease count/bytes
are bounded and excess acquisition returns a typed resource error. No borrowed
pointer into mutable SoA storage crosses a GIL-released advance.

### 13.3 Python binding

`macro_sim._native` wraps the engine, hybrid, and controlled C++ facades with
nanobind:

- construction from generated Python contract objects;
- `advance_ticks()` and `advance_until_decision()` release the GIL;
- bulk observations, masks, metrics, and probes are contiguous read-only NumPy
  arrays or bounded Python metadata;
- no callback into Python occurs for a person, firm, market order, or tick;
- `EngineSession.clone()` clones only economic state; a
  `NativeControlledSession`/Python composite snapshot also captures
  scheduler/coordinator/release/event/seat state, and the Gym adapter separately
  resets its objective evaluator;
- exceptions are translated from stable native error categories with full trace
  IDs but bounded payloads.

The stable user-facing Python classes select a backend and normalize return
objects. Tests must not import binding-generated implementation classes
directly.

### 13.4 Batch and vector interface

RL needs a batch API in addition to a convenient scalar facade. The following
is the Python Gym-owned composite, not an economic `EngineSession` API; it owns
in M10 each Python `ControlledSimulationSession` backed by a native
`HybridControlledBridge`/`EngineSession`, plus objective evaluator, horizon,
termination, and truncation state. M11 substitutes native
`ControlledSession` without changing this outer contract:

```text
GymControlledBatch.reset(seeds)
GymControlledBatch.advance_until_decision(actions?)
  -> observations[num_envs, observation_dim]
  -> action_masks[num_envs, action_dim, 3]
  -> rewards[num_envs]
  -> elapsed_ticks[num_envs]  # current playable daily ruleset: one tick/day
  -> terminated[num_envs]
  -> truncated[num_envs]
```

Initially each persistent Python worker owns one native session, matching the
current multiprocessing design. A later in-process batch may own multiple
single-threaded sessions. The engine and PyTorch thread pools must not be
enabled simultaneously without an explicit oversubscription policy.

The current synchronous vector contract remains homogeneous and
fixed-horizon: if one slot terminates/truncates, all slots must do so at that
boundary, then the complete batch resets and reseeds. Asynchronous per-slot
reset is a versioned trainer/seed/checkpoint change, not an optimization.

## 14. Controller, policy, shock, and observation semantics

### 14.1 Controller time remains semi-Markov

The C++ port does not change the established relationship:

- the current playable/NewGame daily ruleset advances one natural day per
  engine tick;
- a controller action occurs at a server-issued decision boundary;
- one Gym `step(action)` advances to the next decision boundary, which may span
  many engine days;
- current codec field IDs `boundary_tick` and `elapsed_ticks` remain unchanged,
  because they are part of deployed `.msrl` contract hashes; in the current
  playable ruleset one tick is one natural day and UI adapters may label it as
  such;
- continuation discount remains `gamma ** elapsed_ticks`;
- GAE trace decay remains `lambda ** elapsed_ticks`;
- an `ObjectiveSpec` declared `per_tick` is multiplied by `elapsed_ticks` to
  form the undiscounted interval reward before PPO/evaluation reward scaling;
  only continuation is discounted, and all objective time-normalization modes
  must match the Python contract;
- true termination bootstraps zero, while a time-limit truncation bootstraps
  from its terminal observation and still cuts the trace before reset;
- the policy adjustment cost and implementation lag remain part of the same
  policy transaction semantics.

Changing these feature IDs requires a new observation/artifact schema and an
explicit model migration or retraining; they must not be silently renamed.
The deployed fiscal-v1 101-feature base vector does not encode decision-group
identity or the pure-context advisory action mask as critic features. A
multi-group task therefore requires a new codec/artifact contract rather than
reusing fiscal-v1 weights.
Internal source retains `TickIndex` as a technical counter, while player-facing
text uses dates/days. The top-bar reference counter is a UI concern.
Legacy/pre-v13 and diagnostic fixtures with abstract periods or
`periods_per_year = 12` retain tick/period semantics in the compatibility
oracle; they must not be relabeled as daily calendar fixtures.

### 14.2 Policy transaction

The normative order in `docs/controllers_v26.md` remains binding. At
`ControlBoundary(t)`:

1. publish releases due at `t`, evaluate persisted/hysteretic triggers from
   accepted records through `t-1` plus public-role shock schedule/metrics as of
   boundary `t`, and open regular or server-authorized emergency contexts with
   role-scoped observations; operational/confidential disclosure alone cannot
   open a context and leak the shock's existence;
2. collect all due seats/economies without mutating economic state; a human
   pause remains inside this boundary and consumes no tick or RNG address;
3. decode absolute targets to stable policy IDs, validate policy versions,
   ownership, capability, range, projected timeline, hold, lag, capacity, cost,
   pending conflicts, and joint constraints, then enqueue decisions;
4. revalidate the complete due set and seal the conservative non-conflicting
   subset whose `effective_tick == t`, including lag-zero decisions, without
   mutating policy or ledgers;
5. invoke B0 exactly once to activate that sealed set and its
   domestic/external transition side effects, then run tick `t`; only a
   successful commit
   publishes engine-derived records, shock/forced-transition events, and the
   next date.

The shipped contract has exactly five seats and eleven decision groups. It
supports all registered built-ins—`NullOccupant`, `ScheduledOccupant`,
`HeuristicOccupant`, `RandomFuzzOccupant`, `HumanQueueOccupant`, and
`RLOccupant`—through the same coordinator.

Behaviorally binding details are preserved:

- a multi-lever proposal uses the maximum applicable regular/emergency
  implementation lag, and eligibility/max-step are evaluated against each
  lever's projected effective value rather than only the current value;
- an exact projected target is `accepted_noop`: it changes no version,
  cooldown, capacity reservation, adjustment cost, or effective event;
- one pending action per canonical lever is the default; explicit cancel and
  atomic supersession have versioned lifecycle events and declared refunds,
  while a context expiry rejects before capacity/cost reservation and charges
  nothing; failed execution follows its own declared refund rule;
- stale touched/prerequisite versions and duplicate idempotency keys are handled
  exactly; unrelated versions do not stale a proposal;
- the whole World due set is revalidated atomically. Parity uses the
  intersection of all maximum-cardinality valid subsets; after 4,096 search
  attempts it uses the maintained pairwise-conservative fallback. This may
  reject more than one minimal conflict set but never executes an ambiguous
  decision;
- emergency authority is issued only by a trigger with persistence, hysteresis,
  cooldown, expiry, and authorized seats. A client cannot self-declare it;
- administrative capacity reservation/refund and the Gym adjustment-cost
  lifecycle remain separate typed accounts;
- peg breaks and other engine-forced transitions update the relevant policy
  version and emit `forced_system_transition`;
- replay injects only canonical input events; derived contexts, decisions,
  effectiveness, shocks, and forced transitions are regenerated and compared
  against the hash chain.

Prelude releases, opened contexts, and committed human/timeout/cancel ingress
can survive an `AWAITING_HUMAN` checkpoint; proposal submission retains its
current semantic idempotency. The native protocol additionally gives
timeout/cancel a persisted operation key and payload/result cache: the same
key+payload returns the original result, while key reuse with a different
payload rejects. The v3 compatibility adapter never automatically retries its
legacy non-idempotent command shape. If economic execution
fails, the `WorldTransaction` restores due policy values/versions, pending
status, reserved capacity/cost, shock lifecycle, derived effective events, and
economic state; the controller then atomically records
`failed_at_execution`/refund against the already committed ingress. No date or
economic record advances. Thus “failed advance leaves the prior boundary”
refers to economic state, while the controlled audit stream may record the
failed attempt.

The domestic monetary regime belongs here, not to external policy:
`monetary_regime` is `exogenous`, `taylor`, or `manual`; `manual` requires a
non-null `manual_policy_rate`, and the other regimes require it to be null.

### 14.3 External policy

All economies first prepare and validate external policy. World installs its
boundary view only if the complete set and its ledger-mutating transition plan
are valid. Peg adoption/exit/anchor changes can swap or seed reserve-ledger
positions, and annual dealer-loss mutualization can post cash; all are inside
the same rollback scope.

The current semantics remain:

- a sanction effect can remain symmetric while ownership of each imposition is
  unilateral and independently removable;
- a peg does not require anchor consent;
- the state model stores per-pegger reserves, pressure, and integrity, including
  exited/broken history, while parity keeps the maintained limit of at most one
  active pegger; relaxing it later is a versioned economic-model change;
- peg cycles/chains remain forbidden according to the maintained policy
  contract;
- external `fx_regime` remains the distinct `float` or `peg` choice, with anchor
  and reserve constraints validated at the World boundary.

### 14.4 Shock boundary

Shocks use declared channels, never arbitrary state pointers. `ShockTape` is a
fully materialized immutable input. `ShockEngine` owns deterministic lifecycle
state and does not resample a tape during a run.

Each `ShockSpec` preserves the current complete contract:

- `shock_id` and registered kind/channel;
- affected economy IDs and optional sectors;
- start tick, finite/permanent duration, ramp-in, and ramp-out;
- magnitude;
- announcement tick;
- public/operational/confidential/oracle visibility and permitted roles;
- source, calibration note, correlation group, tags, and schema version.

The registered `ShockDefinition` also preserves magnitude bounds, one-shot
status, allowed sectors, capability requirements, and emergency seats. A
one-shot has duration absent/one, has no ramps, and realizes once. Continuous
composition remains strictly positive and bounded at 64 after multiplicative
stacking.

The engine also preserves announced/active/realized sets and its complete
ordered, hash-chained internal shock event stream. The public
controller/frontend derived-transition mirror includes only public transitions;
operational/confidential details reach only
authorized seats through role-filtered observations and bulletins.
Announcement and visibility are therefore enforcement metadata, not optional
UI text.

A stochastic scenario generator may use the native counter RNG to materialize a
complete tape before session creation, recording its seed and provenance. Once
bound, the generated tape is indistinguishable from any other concrete tape.
Python-generated tapes can therefore drive native differential tests exactly.

Phases receive an immutable current overlay. Stacking and expiry rules are
defined in the channel schema. A shock cannot bypass posting, ownership,
population, or resource invariants; it changes a valid model input or emits a
valid domain event.

### 14.5 Observation layers

Native state access is divided into:

1. `SensorSnapshot`: causal same-engine data needed next tick;
2. `AccountingSnapshot`: accepted flow/stock identities;
3. `ReleaseSnapshot`: delayed/revised, role-filtered controller information;
4. `FrontendSnapshot`: player-visible aggregates and paged entity detail;
5. `ProbeSnapshot`: explicit diagnostic data, unavailable to gameplay policy.

This prevents a native binding from accidentally turning complete state into an
RL observation or recreating a removed privileged gameplay mode.

## 15. RL continuity

### 15.1 Training

The following Python code remains authoritative:

- Gym/SMDP wrapper behavior;
- `ContextCodec` and `DirectionalActionCodec` Python facade;
- masked categorical PPO;
- rollout buffer, GAE, optimizer checkpoint, seed schedule;
- paired held-out evaluation and bootstrap superiority gates.

The environment factory constructs a native-backed controlled session instead
of a Python `World`. Episode reset restores one explicit composite genesis:

- native engine state;
- controller scheduler/coordinator, pending decisions, releases, events, seats,
  and occupants;
- objective-evaluator state owned by the Gym task.

It does not assume that cloning an `EngineSession` alone resets the controller.
Because current trainer checkpoints are episode-aligned and do not claim to
persist in-flight worker worlds, this replacement does not invalidate optimizer
checkpoint semantics.

Golden SMDP tests cover every `ObjectiveSpec` time-normalization mode, including
the undiscounted `per_tick * elapsed_ticks` interval reward, reward scaling,
`gamma ** elapsed_ticks`, `lambda ** elapsed_ticks`, and termination versus
time-limit truncation bootstrap.

### 15.2 Deployment artifact

Migration phase one keeps Python `NumpyMLPPolicy`. A policy proposal produced by
that model enters the same native policy transaction as a human action.

For the standalone native server, implement a strict `.msrl` v1 loader:

- verify outer member set, sizes, hashes, schema, shapes, dtypes, and finiteness;
- load the context/action contract generated from the same source schema;
- support the manifest's arbitrary dense-layer count, float32/float64 dtype,
  input mean/scale, input clipping, `tanh`/`relu`, action dimension, temperature,
  and deterministic flag;
- implement masking, stable softmax, and deterministic argmax;
- compare C++ and Python normalized inputs, logits, probabilities, masks,
  and deterministic action codes against golden fixtures.

Native M11 advertises the explicit capability
`msrl_v1_deterministic_inference`. The v1 format permits
`deterministic=False` and stores only a seed, but does not version NumPy's
generator/choice algorithm (the shipped fiscal artifact itself is
deterministic). Python therefore remains authoritative for stochastic v1 and
the native loader rejects that mode with a typed capability error. Native
stochastic inference requires a v2 manifest that names the categorical sampler,
RNG algorithm/version, and
serialized state; once implemented, its state is part of the controlled
checkpoint and golden vectors. This preserves the deployed deterministic
fiscal artifact without falsely claiming that unversioned NumPy sampling is a
portable v1 contract.

Masks and decoded legal action IDs must be exact. The M0 tolerance registry
sets separate absolute/relative limits for float32 and float64 normalized
inputs, logits, and probabilities. Deterministic argmax breaks an exact tie by
the lowest stable action code. Cross-language action equality is required when
the winning-logit margin exceeds its dtype tolerance; golden action fixtures
avoid accidental near ties, while dedicated near-tie fixtures prove the stable
tie rule and fail closed if implementations disagree about whether the margin
is resolved. No test may accept a different mask merely because logits are
close.

The fixed MLP does not justify ONNX Runtime or a native PyTorch dependency.
If NPZ parsing later proves disproportionate, an artifact v2 may add a raw
little-endian weight member. It must have a new explicit schema and cannot
silently reinterpret v1.

### 15.3 GPU position

A GPU is not required for the engine migration. The policy network is tiny and
the simulation dominates training. On Apple Silicon, MPS may still be benchmarked
for PPO updates, but CPU simulation throughput and worker scheduling matter
first.

Branch-heavy agent interactions, sparse contracts, deterministic market
ordering, and frequent barriers make a GPU port of the engine a poor first
investment. A future GPU or Metal experiment must be justified by a measured
native hotspot, not by population size alone.

## 16. Desktop integration

### 16.1 Staged transport

1. Existing Python desktop worker switches its `World` implementation to
   `NativeSession`; Godot messages remain unchanged.
2. `macro_sim_server` implements the same versioned protocol while linking
   `macro_sim_core`.
3. The launcher starts the native worker and removes the Python runtime from the
   packaged desktop application.
4. GDExtension remains an optional later adapter if measured IPC or deployment
   constraints justify its added ABI and crash coupling.

The process boundary preserves crash isolation, lets Python and native workers
coexist during migration, and prevents Godot release cadence from becoming the
core ABI.

### 16.2 Protocol hardening

The current loopback NDJSON protocol should add:

- binding only to loopback in product builds;
- an OS-assigned port rather than fixed `47821`;
- a per-launch 256-bit capability token;
- protocol version, request ID, connection/launcher ID, and sequence on every
  request; a non-null session ID is additionally required after creation, while
  `hello`/`new_session` use the authenticated pre-session connection;
- response version and request-ID verification in Godot;
- request and response size limits plus a bounded receive buffer;
- one mutable client owner per session;
- idempotency rules for retryable commands;
- explicit graceful shutdown and worker-crash messages;
- paged entity details and snapshot deltas instead of resending every
  household, firm, and history row after every batch.

The schema family defines, at minimum, `hello`, `new_session`, `advance`,
`submit_policy`, `submit_human_policy`, `timeout_context`, `cancel_policy`,
`assign_seat`, `restore_seat`, `schedule_shock`, role-scoped `policy_schema`,
`decision_context`, `pending_decisions`, and `shock_bulletins`, `snapshot`,
`entity_page`, `entity_detail`, `save_slot`, `load_slot`, `close_session`, and
`shutdown` commands; typed success/error responses; full snapshot, delta,
page/cursor, and entity-detail payloads; and worker-ready/launcher-failure
messages. Every response correlates to one request ID.

During stage 1, a versioned adapter retains current v3 names and shapes:
`new_game`, `resolve_context`, `trigger_shock`, and `get_schema` map to the new
typed operations. Removing those aliases requires an explicit protocol-major
Godot/server migration and dual-version end-to-end fixtures; “messages remain
unchanged” is not used to smuggle in a breaking rename.

A delta declares base and result snapshot IDs. Unknown bases, sequence gaps,
schema/locale changes, reconnects, or cache-epoch changes force an explicit
full-resync response; clients never guess whether a partial cache is valid.
During compatibility rollout the server can provide a versioned full-snapshot
representation until the client advertises the matching delta/page contract.

The launcher passes the OS-selected port and one-time token through the
M11-ADR-selected per-platform bootstrap channel—for example a launcher-brokered
local socket/named pipe or user-only one-shot bootstrap file—waits for a
versioned readiness handshake, and never places the token in process arguments
or scrapes stdout. Packaged macOS/Linux/Windows tests prove ACLs, cleanup,
worker/launcher crash handling, and absence of secret leakage; an inherited
descriptor is not assumed portable until Godot packaging proves it. Save/load
commands accept a validated logical slot ID under the application-owned
sandboxed save directory; neither Godot nor an untrusted protocol client can
supply an arbitrary filesystem path.

Protocol JSON is an adapter representation. Event/checkpoint hashes use a
specified canonical encoding rather than assuming Python and a C++ JSON library
print floating-point values identically.

## 17. Randomness, numerics, and determinism

### 17.1 Random engine

Use a documented counter-based generator, initially Philox4x32-10, with golden
vectors. A draw address is conceptually:

```text
RngAddress {
  root_seed,
  ruleset_rng_version,
  economy_id,
  phase_id,
  tick_index,
  entity_id,
  draw_kind,
  draw_index
}
```

Schema generation assigns numeric `phase_id` and `draw_kind`; runtime string
hashing is not part of the sequence.

Consequences:

- person hazards, firm shocks, and planning noise can run in any static shard;
- changing the thread count does not change a draw;
- one entity consuming another optional draw does not shift every later entity;
- a failed phase needs no mutable PRNG cursor rollback;
- new draw kinds require a contract version, not a free seed offset.

Entity births/entries first count results, allocate stable IDs by prefix sum and
defined order, then address any new-entity draws by those IDs.

The engine implements and tests its own bounded-integer, uniform-real,
Bernoulli, shuffle, normal/lognormal, Poisson, and weighted-choice algorithms.
It does not use `std::*_distribution` as a portable replay contract because the
distribution algorithms are implementation defined.

Global processes that genuinely require a sequence use an explicit named
counter stored in the checkpoint. The sequence name, counter, and algorithm
version are visible in a debug trace.

### 17.2 Determinism tiers

| Tier | Contract |
|---|---|
| D1 same native build | same config, seed, actions, and any supported worker count produce an exact state/event digest; a phase that has not proved thread-count invariance runs single-threaded |
| D2 supported native platforms | schema/IDs, integer operations, and non-float-driven ordering/events are exact; floating fields use typed tolerances, while float-threshold-driven economic events use declared value/sign/window criteria unless a portable math contract proves exactness |
| D3 Python vs C++ migration | randomness-disabled or fully materialized realization/action/shock tapes preserve phase events, conservation, signs/regimes, and declared numeric tolerances; ordinary endogenous stochastic runs belong to D4 |
| D4 stochastic economics | seed panels preserve distributional moments, failure frequencies, and policy/shock response envelopes |

Native save/fresh-process/load continuation must pass D1 exactly. A release may
only advertise cross-platform replay for the subset actually proven by D2.

### 17.3 Floating-point profile

The deterministic build:

- requires IEEE-754 binary64;
- uses round-to-nearest;
- disables fast-math and unsafe reassociation;
- disables implicit FMA contraction where it would alter the declared reduction;
- partitions each parallel phase into fixed logical blocks independent of
  worker count;
- stable-merges commands by a total versioned key and rejects key collisions;
- assigns each reduction site one versioned algorithm and fixed tree
  (pairwise, compensated, or another named implementation), never a runtime
  choice;
- treats NaN and Infinity as domain errors at mutation boundaries.

Platform `libm` transcendental results are not assumed bit-identical. A
distribution/threshold site either uses a checked-in deterministic
approximation with golden vectors or is covered by the narrowed D2/D4 contract.
The floating-point environment is checked at session creation and unsupported
rounding/denormal modes fail closed.

A separate `fast` build is not allowed to create save games or comparable
research results unless it receives a distinct engine profile and contract hash.

## 18. Performance design

### 18.1 Complexity repairs required before scale claims

| Current behavior | Current risk | Native design |
|---|---|---|
| daily population loops include all historical dead people | `O(all historical persons)` and ever-growing cost | compact alive dense view; cold death archive and stable ID indirection |
| marriage candidates scan the opposite pool and relationship updates rescan people | measured near-quadratic growth | indexed exact argmin/query preserving the current age-gap/wealth-assortativity/stable-ID total order; bounded sampling is only a separately versioned and recalibrated post-parity model change |
| divorce/orphan handling searches all persons | burst-time quadratic tail | child and kinship adjacency indexes |
| persistent labor repeatedly rebuilds rosters and wage totals | large-firm near-quadratic behavior | authoritative roster with incremental headcount/FTE/wage bill |
| preferential matching rebuilds seller weights after trades | worst case `O((buyers+sellers)*sellers)` | exact dynamic prefix-sum tree: preserve constant weights, swap-pop active-slot order, and self-hit fallback; `O(F)` build and `O(log F)` draw/deletion |
| optional/deferred `PriceSortedMatch` rebuilds/shuffles/sorts per buyer (not the current round-1 default) | repeated `O(F log F)` when selected | index price tiers/live membership, but preserve buyer-addressed equal-price permutations, buyer-local self-skip, and separate randomized unavailable-seller trace; `O(F log F + required visits/permutations)` |
| firm equity intents traverse a bounded watchlist (playable default `W=15`) | `O(F + H·W)` plus claim callbacks and avoidable constants | indexed sparse holdings/watchlist CSR, batched intent generation and per-asset clearing |
| bank equity intents scan every alive bank | `O(HB)` plus claim callbacks | preserve the all-bank opportunity set; batch/vectorize intent generation and per-bank clearing, with sparse storage only if it still represents every alive bank |
| person claims normalize household × bank mirrors | repeated scans and drift repair | canonical ownership lots and incremental indexes |
| metrics repeat full scans and sorts | multiple `O(H log H)` per tick | fused scan, reusable scratch/order statistics; expensive analytics by cadence |
| each importer re-sorts each exporter's firms | repeated World sorting | reuse only semantically identical quote indexes; preserve importer order, live inventory/shared shock cap, and source-list equal-price ties in `_ship_exports` |
| dense capital and migration routes | `O(N²)` even when stored state is sparse | sparse storage may remove zero edges, but exact complete candidate sets/flow equations and best-host search remain; route pruning is a versioned model change |
| full transaction objects retained then re-aggregated | allocation and bandwidth | aggregate buyer/seller journals by default; optional detailed trade trace |
| records and event arrays grow forever | memory linear in simulation length | fixed in-memory rings plus streamed history |

### 18.2 Concrete data structures

- `PostingBook`: dense cash balance, settlement-node, and flags arrays; account
  lookup leaves the transfer hot path. Loan principal lives only in `LoanBook`;
  reserve positions live only in `ReserveBook`.
- `PersonStore`: dense alive slots, stable-ID-to-slot table, compact archive.
- `HouseholdMembership`: flat member CSR rebuilt once at the population barrier.
- `HouseholdProfile`: one SoA snapshot only for structural/membership attributes
  whose declared epoch is stable across the tick. Planning uses its declared
  opening financial values, while post-labor/post-settlement claims and metrics
  read canonical live stores or a separately declared closing epoch; no stale
  financial/employment snapshot is reused.
- `EmploymentBook`: per-firm dense roster plus incrementally maintained active
  count, FTE, and wage bill.
- `SecurityBook`: lot pool with holder, issuer, maturity, and bank indexes; every
  mutation updates one version.
- `OrderArena`: count/prefix-sum construction and stable asset partitions.
- `WorldEdgeStore`: ordered active bilateral edges, with a dense mode chosen
  only below a benchmarked country-count threshold.
- preallocated tick arena and metric scratch; no allocation in steady hot loops
  unless entities or contracts actually enter.

### 18.3 Parallel boundaries

High-value safe candidates:

- independent economies on either side of the World dealer barrier;
- firm planning and production;
- person survival/fertility hazards;
- household economic profile construction;
- order-intent generation;
- local metric fragments and invariant scans.

Each uses static ranges, shard-local command buffers, and a stable merge tree.

Shared cash limits, inventories, rosters, order books, IDs, and matching cannot
be made safe by adding `parallel_for`. They require:

```text
parallel intent generation
  -> deterministic global match/allocation
  -> balanced batched posting
  -> deterministic commit
```

RTGS, goods, labor matching, and bank resolution stay single-threaded until
their semantics have this explicit form.

Desktop mode may assign workers to economies and heavy phases. RL mode defaults
to one native thread per environment and uses environment-level process
parallelism, avoiding oversubscription with PyTorch/BLAS.

### 18.4 Metric and history tiers

| Tier | Cadence | Contents |
|---|---|---|
| invariant | every tick | conservation totals, stock-flow identities, finite/nonnegative gates |
| causal | every tick | only values consumed by a later engine phase |
| release | release calendar | policy-visible official series and revisions |
| frontend | end of requested batch or visible-panel cadence | dashboard aggregates and deltas |
| analytic | configured sampling | exact distribution tails, detailed firm/household panels, debug traces |

Exact Gini/top/bottom calculations share one sorted scratch or selection pass.
They do not independently sort the same population.

In-memory history is a configurable ring. Full history is an append-only
columnar stream with chunk hashes and atomic manifest updates. A save stores the
ring and stream cursor, not ten years of duplicate frontend dictionaries.

### 18.5 Acceptance performance targets

Targets are measured on release builds with all declared invariants enabled.
They are budgets, not assumptions; failure blocks cutover and triggers profiling
or scope review.

| Gate | Reference scenario | Target |
|---|---|---|
| P0 first vertical slice | matched M4 V1 fixture of 5,000 basic household agents and 750 firms (no M7 PersonStore dependency) | native median day ≤20% of matched Python median (≥5x); absolute p95 budget frozen from M0 raw data |
| P1 parity speed | one full-feature 10k-person, about 5k-household, 750-firm, 8-bank economy | native p95 ≤75 ms/day single-thread and native median ≤10% of matched Python median |
| P2 historical anchor | 5,000-household v12.4-equivalent fixture | p95 ≤25 ms/day, versus historical Python ≈253 ms/day |
| P3 desktop small | current default three-country game, 60-day batch, normal frontend snapshot | batch+snapshot p95 ≤750 ms and snapshot component p95 ≤100 ms |
| P4 scale shape | matched 10k/20k/50k/100k-person economies | log-log time slope ≤1.08, 100k/10k p95 ratio ≤12, and post-warmup RSS p95 <4 GiB |
| P5 RL | eight default fiscal-v1 native environments | ≥3,200 engine days/second aggregate, exceeding 10x the recorded ≈311 days/second |
| P6 World qualification | same 16-economy ×10k-person World at one and 16 physical workers on the M0-pinned host | efficiency `T1 / (16 * T16) ≥70%` and central barrier <10% of `T16` |
| P7 longevity | 10 simulated years with fixed history ring | `RSS_year10 ≤ 1.05 * RSS_year2 + 64 MiB`, excluding the explicitly measured streamed-output file |

P0 binds M4. P1/P2 become measurable only after full domestic/headless parity
at M10; P1, P2, P3, P5, and P7 are mandatory before native-default cutover.
P4 is mandatory before advertising a supported 100k-person economy. P6 is a
separate research/large-World qualification before advertising 16-country
parallel scale and does not block the first desktop cutover. M0 records the
exact CPU/OS/compiler, physical-core count, affinity, and frequency policy for
each reference host; P6 never substitutes SMT threads for physical workers.

P4 uses a 30-day warmup and a 365-day measured window at every size and fits the
declared slope to all four medians. P7 compares fixed measurement windows in
years 2 and 10. Marriage stress at 400/800/1,600/3,200 persons must have no
doubling ratio above 2.6. Benchmarks always report median, p95, and p99;
averages may not hide marriage days, death bursts, bank crises, large rosters,
or country-matrix tails.

### 18.6 Benchmark suite

Microbenchmarks:

- same-bank and cross-bank posting;
- reserve settlement and transaction commit/rollback;
- sampled, preferential, and price-sorted matching;
- firm and bank equity intent/clear;
- claim/ownership identity;
- ordinary population day, marriage day, and death burst;
- large employer hire/separate/recall;
- causal metrics and analytic distribution metrics;
- trade sourcing and reservation;
- capital/migration matrices at `N=2..256`;
- checkpoint encode/decode and snapshot delta.

Macrobenchmarks:

- persons `1k / 10k / 100k`;
- households `250 / 500 / 1k / 5k`;
- economies `1 / 2 / 4 / 8 / 16 / 64`;
- normal day and registered crisis scenarios;
- controller interval and complete RL episode;
- desktop `advance(60)` plus visible snapshot.

Every result records commit, compiler, flags, CPU, threads, schema/ruleset hash,
seed, entity/event/transaction counts, allocation count, and invariant status.
Construction and steady-state advance are reported separately.

## 19. Checkpoint and cloning

The `.msim` ZIP container remains useful for a human-readable header and atomic
save-slot management. Native state uses a new member and engine identifier, for
example:

```text
save.msim
  header.json
  manifest.json
  state/cpp-soa-v1.fb
  controller/session-v1.fb
  artifacts/<sha256>.msrl
  events/controller/<chunk-sha256>.bin
  events/shock/<chunk-sha256>.bin
  history/manifest.json
  history/chunks/<chunk-sha256>.bin
```

`cpp-soa-v1` uses a versioned FlatBuffers schema or an equivalent approved
schema-generated format. The decision is confirmed by an M1 ADR and prototype,
but handwritten raw struct dumps are forbidden.

The native state member includes:

- schema, engine, ruleset, policy, metric, RNG, and controller contract hashes;
- the complete canonical `NewGameSpec`, immutable `Ruleset`, `CapabilitySet`,
  World/pipeline definitions, and their hashes, so a fresh process can
  reconstruct rather than merely recognize the session;
- tick/date and economy/world IDs;
- all canonical entity/store columns and active contracts;
- logical next-ID counters, slot generations, and semantically ordered
  free-list state (or its specified deterministic reconstruction);
- current domestic/external policy values, versions, and pending transition
  state;
- pending policy and shock schedules;
- counter-based RNG global counters, if any;
- causal sensor histories;
- complete shock tape plus current tick, announced/active/realized indexes,
  shock event cursor, event prefix, and head hash;
- economic/history/shock-output outbox entries with stable idempotency keys and
  per-sink acknowledgement cursors;
- mutating operation IDs/payload hashes, committed or partial result receipts,
  and caller acknowledgement state.

The controlled-session member is separately schema-defined; M10 stores it as
the hybrid bridge's canonical Python envelope and M11 maps the same schema into
native `ControlledSession`. It includes:

- the complete canonical `ControllerRunSpec`: calendars, trigger definitions,
  adjustment-cost/refund/admin weights, seat and release specifications, and
  `ShockAuthority` principal/seat grants and allowed kinds/targets/timing, plus
  the objective contract when it is part of the saved composite;
- lifecycle phase exactly at `BOUNDARY_START`, `AWAITING_HUMAN`, or
  `READY_TO_COMMIT`, plus boundary tick/date and run mode;
- current/open/missing/collected decision contexts and recorded-human markers;
- proposals, decisions, pending effective actions, policy versions,
  last-effective times, transaction sequences, policy fingerprint, and engine
  policy-log cursors;
- proposal/context and idempotency indexes together with their canonical
  payloads;
- scheduler calendars, triggers, next-due state, administrative capacity, and
  any charged/refunded adjustment-cost state;
- release specifications, clocks, source-history windows, published vintages,
  revisions, access classes, and release cursors;
- seat assignments, assignment archive and sequence, occupant kind/config,
  queued human proposals, heuristic/random state, and RL artifact reference/hash
  plus supported inference RNG state;
- chunked controller/shock input and derived event streams, sequence/cursors,
  replay classes, and head hashes;
- durable controller/release/audit outbox entries with stable idempotency keys
  and per-sink acknowledgement cursors. Socket/UI delivery is
  session-ephemeral and resynchronizes from snapshot IDs after reconnect.

The save validator reconstructs and checks every redundant index above before a
session can continue. Mid-boundary checkpoints are first-class, not coerced to a
clean boundary. A Gym task adds its explicit objective-evaluator state to the
composite reset/checkpoint when training requires it.

A commit → audit-sink failure → save → fresh-process load fixture must deliver
each logical audit/history output exactly once after retry. Ephemeral UI/socket
frames may be duplicated or dropped physically but are never the durable event
record and always recover through full resync.

Built-in native occupants have schema-defined state. A deployed `.msrl` asset
is embedded as a content-addressed member rather than referenced by a
machine-local path. A custom Python occupant can participate in a neutral save
only through a registered `ExternalOccupantStateCodec(type_id, version)` that
exports bounded canonical bytes and restores explicitly; arbitrary live objects
and pickle are rejected with a typed unsupported-save error. This is an
intentional security contract, not silent loss of continuation.

It excludes:

- arbitrary Python objects or pickle;
- hash-table bucket layout;
- rebuildable indexes and caches;
- UI panel state;
- full unbounded analytic history;
- debug-only pointers and heap/arena allocator implementation state.

Event/history streams use immutable content-addressed chunks. Only the bounded
working tail/ring is resident; a portable `.msim` embeds every chunk required
for replay/continuation. Optional full analytic history is either explicitly
embedded or explicitly omitted in the manifest and is never an undeclared
machine-local dependency. Save size may grow with an embedded audit history,
but P7 measures resident state; save size and latency are separate benchmark
outputs.

Hashing is non-recursive. Canonical `manifest.json` lists every payload member's
name, length, and SHA-256 but excludes itself and `header.json`. Define
`header_without_root` as the canonical meaningful header fields and compute
`root = SHA-256(canonical(header_without_root) || canonical(manifest))`; the
stored canonical `header.json` adds that root. ZIP entries use lexical member
order, fixed timestamp/permissions/UTF-8 flags, no platform extra fields, and
declared compression.

Save writes a sibling temporary file, flushes and `fsync`s it, atomically
replaces the slot, then `fsync`s the parent directory where the platform
supports it; the platform-specific durability guarantee is documented and
tested. Load validates header, root, member names/sizes/hashes, schemas,
references, and invariants before returning a newly constructed
`EngineSession` or `ControlledSession`. It never mutates an existing session,
and unknown required fields fail closed.

The save preserves the originating `RuntimeOptions` as provenance but contains
no machine-local path. `LoadOptions` may override only proven non-economic host
choices such as supported worker count, output-sink location/cadence, snapshot
cadence, and a validation tier that still includes mandatory production
invariants. Tests prove every permitted override leaves the economic/event
digest unchanged; rules, capabilities, policy, RNG profile, and economic
pipeline cannot be overridden during load.

`EngineSession.clone()` uses immutable shared rules/genesis data and copies only
mutable engine-store buffers. `ControlledSession.clone()` additionally clones
the state enumerated above; Gym objective state remains an explicit outer
component. Copy-on-write may be introduced after measurement. Correctness
cannot depend on a COW implementation.

Delivery responsibility is the explicit exception: `clone()` preserves event
history/cursors but detaches durable sinks and pending delivery work. Attaching
a sink to the fork mints a new non-economic `delivery_lineage_id`, so divergent
clones cannot emit different payloads under one idempotency key. `LoadOptions`
distinguishes exclusive `resume_slot` from `fork`: resume holds the logical
save-slot lease and preserves its lineage/pending acknowledgements for crash
recovery; fork (and raw-byte load) detaches outputs and mints a lineage only
when a sink is attached. A second concurrent resume of the same slot fails.
Delivery lineage is excluded from economic/controller event digests.

Tests cover clone→diverge→attach-to-same-sink, exclusive crash resume, and two
fork loads of one `.msim`; logical output neither collides nor becomes the
other branch's responsibility.

No native migration code for Python pickle checkpoints is required. If a
one-time development conversion ever becomes useful, a trusted offline Python
tool may load a known local pickle and export a neutral fixture; shipping native
code still never reads it.

## 20. Toolchain and dependencies

### 20.1 Build

- C++20;
- CMake minimum 3.26;
- Ninja default local/CI generator;
- ccache through `CMAKE_CXX_COMPILER_LAUNCHER`;
- checked-in `CMakePresets.json` for debug, release, ASan/UBSan, TSan,
  coverage, and benchmark builds;
- developer-only `CMakeUserPresets.json` ignored by Git;
- scikit-build-core replaces Hatchling when the extension first lands;
- nanobind builds `macro_sim._native`;
- `wheel.py-api = "cp312"` and nanobind `STABLE_ABI` where validated.

The current developer environment has CMake, Ninja, and ccache alongside Apple
Clang 21 and Godot 4.7.1. M1 adds a reproducible bootstrap/check script; this
design-only branch does not pretend that the script already exists. Build
commands must use the project's `uv` Python 3.12, not macOS system Python 3.9.

### 20.2 Runtime/build dependency budget

Initial allowed dependencies:

| Dependency class | Purpose |
|---|---|
| nanobind | Python binding only |
| FlatBuffers, subject to M1 ADR | structured native checkpoint |
| small audited JSON library | protocol/config/checkpoint-metadata adapter only |
| small ZIP/deflate implementation | `.msim` and `.msrl` containers |
| audited SHA-256 implementation | artifact, event, and save integrity |
| Catch2 v3 | C++ unit/integration tests |
| Google Benchmark | repeatable microbenchmarks |

Do not initially add Boost, Eigen, ONNX Runtime, OpenMP, TBB, or a general RPC
framework. The fixed MLP needs no matrix framework, and an internal static
thread executor is sufficient until profiling proves otherwise.

Dependencies are pinned by immutable version/tag plus source hash. Source
distributions and offline wheel builds must contain or otherwise reproducibly
resolve required native sources. CI generates a license/SBOM report.

Before any event/save/artifact parser lands, the M1 ADR assigns a
`CanonicalEncodingVersion` and exact dependency names/versions/licenses.
Canonical input rejects duplicate object keys, nonfinite numbers, invalid UTF-8,
unknown required fields, and noncanonical integer/float encodings; Python/C++
golden vectors cover Unicode and endian boundaries. Hash contracts never rely
on an implementation's default JSON or ZIP formatting.

One existing Python packaging issue should be fixed with M1:
`macro_sim/rl/vector_env.py` directly requires `cloudpickle`, so the appropriate
RL/train extra must declare it directly rather than receive it only transitively.
Matplotlib should move to a visualization extra so a headless native runtime
does not install it unnecessarily.

### 20.3 Binary distribution

Use cibuildwheel to build and test installed wheels:

- macOS arm64 and x86_64; a desktop app may additionally use universal2;
- manylinux x86_64 and aarch64;
- Windows MSVC x64;
- CPython 3.12 and the newest supported CPython against the same `abi3` wheel;
- free-threaded Python explicitly unsupported until separately tested.

Wheel tests run outside the source tree and cover import, create, advance,
clone, save/load, artifact inference, and a small invariant fixture.

Desktop worker binaries are built separately for the Godot export platforms,
signed/notarized as required, and tested by launching the actual packaged
worker. Full Xcode may be needed for signing/universal packaging even though
Command Line Tools are sufficient for local core compilation.

### 20.4 Static and dynamic analysis

Required CI profiles:

- warnings-as-errors on project code;
- clang-format and clang-tidy;
- ASan + UBSan on macOS/Linux;
- a separate TSan job for scheduler/store races;
- coverage for core contracts and error paths;
- fuzz targets for C ABI bytes, protocol frames, `.msim`, `.msrl`, and
  canonical event parsing;
- dependency and license scanning.

## 21. Migration milestones

### 21.1 Operating rules

- `refactor/cpp-engine-v33` is the integration branch.
- Work uses short-lived topical sibling branches from the latest integration
  head, such as `refactor/cpp-m0-contracts-v33`; milestone names are gates/tags,
  not months-long branches.
- Before every PR (and at least weekly), update from current `dev`, test the
  synthetic merge, then enter the protected merge queue only while Python
  regression, native tests, schema-staleness, and applicable differential gates
  are green.
- Tag each accepted gate `cpp-v33-mN`. Prefer landing additive, default-off
  native infrastructure directly into `dev`; otherwise promote the integration
  branch back through a fully tested PR so M11 never becomes a mega-merge.
- Baseline fixtures remain pinned to the exact Python oracle commit. A semantic
  change requires a reviewed rebaseline manifest containing old/new commit,
  contract hashes, reason, commands, and before/after artifacts; regeneration
  is never silent.
- Python remains the default backend through M10.
- `shadow` creates two independent sessions from the same config/action/shock
  tape. Only the selected authority publishes output; shadow never dual-writes a
  common state.
- If migration exposes an economic bug, first write a Python reproducer and
  decide whether the baseline is wrong. Fix and document the model before
  teaching C++ a different result.
- Never ship a phase that calls C++ once per transfer, person, firm, or order.
- Every canonical store/domain slice introduced in M5-M9 lands with genesis,
  capability rejection, relevant policy and shock channels, phase wiring,
  invariant/trace coverage, rollback/fault injection, stable digest,
  checkpoint/load, clone/continuation, minimal probe, and a matched benchmark.
  M9/M10 close remaining coverage; they do not introduce these foundations for
  earlier stores.

### 21.2 Summary

| Milestone | Result | Native completeness |
|---|---|---|
| M0 | contracts, traces, baselines, benchmark corpus | no engine behavior |
| M1 | build, IDs/units/errors/RNG/schema, empty session, ABI/binding | native foundation |
| M2 | canonical stores, posting/loan/reserve transaction core | accounting primitives |
| M3 | pure behavior, valuation, shock reads, matching kernels | reusable algorithms |
| M4 | minimal closed real-economy vertical slice | first native tick |
| M5 | fiscal, credit, banks, central bank, settlement | monetary closed economy |
| M6 | bonds, equity, valuation, firm dynamics | financial/firm frontier |
| M7 | persons, households, estates, ownership, persistent labor | population frontier |
| M8 | energy and housing | domestic playable frontier |
| M9 | trade, FX, capital, migration, peg, sanctions, shocks | multi-country frontier |
| M10 | metrics, releases, controller, Gym, checkpoint, diagnostics adapters | full headless parity |
| M11 | native policy inference, native desktop worker, packaging, cutover | shipping native engine |

### M0 — Freeze observable contracts

Detailed execution sequence, artifact layout, commands, and package-level exit
gates are defined in
[`cpp_engine_m0_execution_plan_v33.md`](cpp_engine_m0_execution_plan_v33.md).

Deliver:

- machine-readable inventory of config, capabilities, policies, shocks, metrics,
  observations, phases, RNG draws, events, invariants, controller seats/run
  contracts, desktop protocol, and scenarios;
- sorted IDs and contract hashes pin the audited baseline: exactly 370
  dataclass fields from `dataclasses.fields(Config)` (excluding ClassVars and
  aliases); 102 policy levers (88 domestic, 14 external; 88 immediate,
  9 new-contract-only, 5 state-transition); five seats
  (`central_bank`, `energy`, `external_affairs`, `regulator`, `treasury`);
  decision groups `monetary_stance`, `liquidity_operations`, `fiscal_stance`,
  `tax_and_transfers`, `debt_management`, `macroprudential`,
  `structural_law`, `trade_and_migration`, `fx_operations`,
  `energy_operations`, and `energy_structure`; default shock kinds
  `productivity`, `labor_availability`, `energy_capacity`,
  `household_demand`, `import_capacity`, `export_capacity`, `credit_supply`,
  and `capital_destruction`; and the deployed fiscal-v1
  101-feature/one-lever/three-direction action contract;
- compatibility aliases
  `firm_capital_haircut -> regulatory_firm_capital_haircut`,
  `firm_inventory_haircut -> regulatory_firm_inventory_haircut`,
  `land_convexity -> land_fee_stock_elasticity`, and
  `policy_rate_override -> manual_policy_rate`;
- Python phase trace with phase ID, tick, counts, posting digest, event digest,
  selected state columns, invariant results, and RNG metadata;
- deterministic fixtures with stochastic mechanisms disabled;
- fixed-seed stochastic fixtures and registered policy/shock tapes;
- reproducible Python micro/macro benchmark runner and JSON result format;
- tolerance registry by field and semantic type;
- current desktop and RL end-to-end trace fixtures;
- probe-disposition manifest mapping every maintained diagnostics
  probe/report to typed fields, snapshot epoch/cadence and privilege, or
  explicitly classifying it as Python-oracle-only during migration;
- machine-readable gate manifest with command, oracle/fixture hashes, platform,
  profile, thread counts, repetitions/seeds, tolerance/threshold, and artifact
  path for PR, nightly, milestone, and release classes;
- reconciled root/current architecture docs and generated module map, including
  obsolete closed-economy, v12.4/v23, empty-v20-World, and state-ownership
  claims listed in section 28.

Exit gate:

- full Python regression green;
- repeat runs create identical fixture artifacts;
- every row in the module disposition has an owner and milestone;
- benchmark results include hardware/compiler/Python/schema metadata;
- no fixture depends on object addresses or dictionary insertion accidents.

### M1 — Native foundation

Deliver:

- `native/` CMake project and presets;
- `macro_sim_core`, `macro_sim_c`, `_native`, CTest, and benchmark targets;
- strong IDs, unit wrappers, error taxonomy, buffers, arena primitives;
- deterministic schema generator and checked generated
  config/policy/external-policy/shock/metric/observation/phase/RNG/event/
  invariant/controller/checkpoint/protocol contract skeletons;
- Philox and all required portable sampling primitives with golden vectors;
- empty `EngineSession` lifecycle;
- C ABI and nanobind create/destroy/version smoke;
- wheel build on local macOS arm64 and CI smoke on Linux/Windows;
- initial `.github/workflows` native CI for macOS/Linux/Windows before claiming
  cross-platform RNG or ABI results;
- reproducible developer bootstrap/check script;
- ADR for checkpoint encoding after a FlatBuffers prototype.

Exit gate:

- clean configure/build/test from a fresh checkout;
- sanitizer-clean native tests;
- C-only linker smoke uses the installed ABI;
- wheel-installed Python can create/destroy a session without importing source;
- RNG vectors match on macOS/Linux/Windows;
- all config/policy invalid corpus cases fail identically in Python and C++.

### M2 — Canonical state and accounting

Deliver:

- identity/slot stores for households, firms, banks, accounts;
- the frozen M4 V0/V1 household/firm components and genesis builder;
- `PostingBook`, `ReserveBook`, and `LoanBook`;
- generic `OwnerId`/ownership-lot skeleton plus Treasury, central-bank, dealer,
  and bank institutional account identities needed by fiscal/settlement phases;
- balanced multi-leg transaction, undo journal, commit/rollback;
- `TickTransaction`/`WorldTransaction`, stable ID/free-list rollback, named-RNG
  counter journaling, and deterministic fault-injection ordinals;
- account lifecycle and typed settlement-node lookup;
- A4, A5, reserve, and loan ownership invariant registry;
- structured state digest and minimal native checkpoint round trip.

Exit gate:

- exact hand-authored posting fixtures;
- randomized transaction/model-based tests against a simple oracle;
- failed transaction and final gate restore the exact prior digest;
- no string lookup or allocation in steady transfer hot path;
- transfer microbenchmark meets the M2 budget established by M0;
- no Python call occurs inside native accounting.

This milestone does not replace Python `Ledger` in production. It proves the
root store that the first full native vertical slice will use.

### M3 — Pure equations and markets

Deliver:

- pure planning/expectation/price/wage/investment/credit-demand functions;
- valuation primitives;
- shock overlay read interface;
- deterministic sampled, preferential, and price-sorted matching;
- typed order, trade, allocation, and physical-stock commands;
- algorithmic fixes for repeated seller-weight rebuild and repeated sorting.

Exit gate:

- exact deterministic fixtures for every equation and market rule;
- property tests for feasibility, conservation, ordering, and no oversell;
- distribution tests for stochastic matching;
- matching output is invariant under supported thread counts;
- complexity benchmarks demonstrate declared asymptotic behavior.

### M4 — First complete native tick

Implement two closed-economy vertical tags entirely inside `macro_sim_core`:

- **V0 cash loop:** basic household/firm components and genesis, opening
  journals, planning, spot labor, production, one goods market, cash
  settlement, minimal accounts/sensors, invariants, tick commit, save/load.
- **V1 capital/fiscal:** add technology, physical capital and capital-goods
  market, basic tax/spending through the M2 Treasury account, firm statement,
  and lag commit.

Each starts with a deterministic maintained capability subset, explicit
rejection of unsupported flags, then adds only its registered stochastic and
shock channels.

Exit gate:

- one native `advance_ticks(n)` owns the complete state and calls no Python;
- phase-level deterministic differential fixtures pass exactly or by declared
  numeric tolerance;
- stochastic seed panels pass distribution envelopes;
- save/fresh-process/load continuation is exact;
- measured P0 passes for the frozen V1 household/firm manifest with no hidden
  quadratic path;
- a test-only differential harness drives independent Python/native sessions
  through the C ABI. This is not the production backend selector scheduled for
  M10, and only Python authority publishes output.

### M5 — Fiscal, credit, banks, and central bank

Deliver:

- complete domestic policy application for the migrated domains;
- household and firm fiscal flows;
- origination, repayment, write-off, and lender ownership;
- policy-rate regimes, reserves, RTGS, OMO, deposit competition;
- `CentralBankOperationBook`, `InterbankBook`, `BankPnlJournal`,
  `BankCapitalState`, runs, and non-equity failure resolution;
- explicit settlement ordering for full-P&L and maintained legacy fixtures.

Exit gate:

- A4/A5/reserve/interbank/loan/P&L gates pass every tick;
- deterministic crisis fixtures cover bank run, default, and the supported
  non-equity resolution path;
- policy-rate and fiscal impulse panels match semantic baselines;
- no banking/securities cycle exists in target headers;
- bank and posting benchmarks meet phase budgets.

### M6 — Securities, equity, and firm lifecycle

Deliver:

- bond-era Treasury/central-bank balance-sheet extensions over the M2 account
  identities and M5 operations;
- bond contracts, issuance, maturity, holder and maturity indexes;
- firm and bank equity ownership, market clearing, margin rules;
- equity-dependent bank resolution and bank entry;
- firm statements, valuation, sector switch, entry, and exit;
- generic M2 ownership lots applied first to household owners; M7 extends
  beneficial ownership to persons/estates without creating a mirror;
- sparse ownership/watchlist representation and batched claim changes.

Exit gate:

- outstanding face, holder, issuer, A5 net-financial-worth, equity, and cash
  identities pass;
- holder/maturity indexes stay consistent under fuzzed mutation sequences;
- firm/bank default, bank entry, and exit settle every contract exactly once;
- per-firm and bank-equity workloads lose household×asset full scans where the
  economic model does not require them;
- valuation is a one-way service dependency.

### M7 — Population, households, ownership, and persistent labor

Deliver as two independently gated slices:

- **V7a population/ownership:** person and household-membership stores, alive
  dense view/cold archive, births/deaths, basic lifecycle, estates,
  inheritance, and person beneficial ownership over the existing generic lots.
- **V7b social/labor:** relationship/union, marriage/divorce/guardianship/
  leaving-home and family transfers; persistent jobs, suspensions, second jobs,
  JG, participation, efficiency, labor accounting, and macro/stratification
  sensors.

Exit gate:

- population and household identities pass under long seed panels;
- death/marriage/divorce/estate fixtures move each migrated financial account,
  security, job, and contract exactly once;
- household/person projection equality is an invariant, with no periodic repair;
- employment stock/flow identity passes every tick;
- ordinary population cost scales with alive persons;
- exact marriage choices preserve the current total score/order and the
  400..3,200 stress doubling ratio remains at or below 2.6;
- death-before-marriage, compaction, and slot-reuse fixtures preserve the
  current greedy person iteration/match sequence;
- large-employer roster operations meet declared complexity.

### M8 — Energy and housing

Deliver as two independently gated tracks in dependency order:

1. **Energy:** firm components/intermediate market, household energy, SPR,
   fiscal flows, deprivation sensor, and their policy/shock channels.
2. **Housing:** property registry, resale, mortgage/collateral, rental,
   construction/builders, affordability feedback, and their policy/shock
   channels.

Exit gate:

- energy resource, cash, SPR, and deprivation paths match registered fixtures;
- each dwelling has one valid title and stock grows only through mint;
- mortgage principal has one authority and collateral references are valid;
- foreclosure, rent, construction, death/estate title transfer, and bank failure
  interaction panels pass;
- all currently playable domestic capabilities can run natively.

### M9 — World, external policy, and shocks

Deliver as three independently gated slices:

1. **Trade/FX:** rate vector, dealer accounts, private trade/remittance-only
   `fx_spread` bid/ask margins (factor/capital/official peg swaps stay at mid),
   iceberg `fx_friction`, `fx_trade_cap`, tariff/import-quota/export-subsidy
   policy, import/export-capacity shock channels, atomic external-policy
   boundary, trade sourcing/reservation/settlement, sanctions, and deterministic
   BSP seam.
2. **Capital/peg:** factor income on opening positions,
   `external_interest_settlement_fraction`, interest arrears, principal
   roll-forward, `capital_mobility`, `capital_adjust`, capital controls, capital
   flow/NFA, per-pegger reserve/pressure/defense,
   `fx_loss_mutualization`, dealer gates, FX search, and revaluation. Parity
   preserves the current mutualization cadence of every 365 ticks; a
   calendar-aware correction requires a versioned rebaseline.
3. **Aggregate migration:** preserve current aggregate migrant-stock dynamics,
   structural migration rate/max share/remittance share/wage smoothing,
   sanctions, immigration/emigration caps, guest-worker return, one best host
   route per origin, pro-rata remittances, inbound `remittance_tax`, and host
   `outward_remittance_tax`. Moving actual persons/households is a future
   versioned economic feature, not migration parity.

Every slice carries its policy/shock channels; M9 also closes the remaining
registered channels and packaged crisis scenarios.

Exit gate:

- single-economy World equals the corresponding closed native economy;
- dealer flow, reserve, current-account, and world NFA gates pass;
- failed trade/dealer tick releases every reservation and restores all economies;
- action/shock tapes preserve boundary timing;
- `N=2/4/8/16/64/256` complexity benchmarks identify the dense/sparse threshold;
- multi-country thread-count determinism passes;
- all current World gameplay mechanisms can run natively.

### M10 — Reporting, controllers, RL environment, and saves

Deliver:

- split invariant/causal/release/frontend/analytic metric pipeline;
- full maintained national accounts and public series;
- bounded history ring and streamed history sink;
- complete structured native checkpoint;
- generated observation/action codecs and contract hashes;
- Python controller/session facade backed by native state through
  `HybridControlledBridge` prepare/no-fail-commit and a canonical controller
  envelope, including lag-zero, due-set
  revalidation, versions, transition side effects, rollback, admin/cost/refund,
  and effective/forced events;
- `ControllerEnv` native clone/reset and vector batch;
- typed privileged probe API replacing diagnostic private-field access;
- privileged diagnostics adapters for maintained pre/post-step decompositions;
- Python desktop worker backed by native engine;
- stable-ID-only desktop snapshots and completed locale-catalog migration.

Exit gate:

- every maintained metric has source, unit, cadence, and parity rule;
- release delays/revisions and seat visibility match current contracts;
- controller event replay and checkpoint split-run are exact within native D1;
- Python coordinator → native B0 fixtures cover lag-zero domestic/external
  changes, whole-World failure, version/cost/refund state, and exact rollback;
- every hybrid prepare/controller-build/commit/cache-rebuild/publication fault
  ordinal exposes either the complete old or complete new composite, never a
  half-advanced state;
- current fiscal RL artifact can evaluate on a native environment;
- held-out baseline/heuristic comparisons run without information widening;
- ten-year memory gate P7 passes;
- P0 remains green and the now-complete full-feature P1/P2 gates pass;
- full headless module coverage has no Python economic phase;
- maintained diagnostics acceptance runs against native typed probes with no
  fallback access to private/native-layout fields.

### M11 — Native worker and production cutover

Deliver:

- strict native `.msrl` loader and MLP inference;
- native `macro_sim_control` scheduler, coordinator, administrative/cost
  accounting, release/event/replay, emergency triggers, five seats and eleven
  groups, occupant state, boundary lifecycle, and controlled checkpoint parity;
- hardened `macro_sim_server`;
- paged/delta desktop snapshots;
- Godot launcher and packaged worker for supported platforms;
- production binary/wheel pipeline, signing, SBOM, and release diagnostics;
- native backend as default; Python backend retained temporarily as oracle.

Exit gate:

- Python and C++ artifact logits/masks/actions pass golden vectors;
- complete new-game → play → policy → crisis → save → quit → load flow passes in
  packaged Godot builds;
- mandatory P0/P1/P2/P3/P5/P7 pass; P4/P6 pass before their corresponding
  100k-person/16-country scale claims;
- full native regression, fuzz, sanitizer, wheel, and end-to-end CI is green;
- no missing row remains in the module disposition;
- rollback to the previous product release remains possible at package level.

Only after a stabilization window may the Python economic engine be deleted.
Python controllers, RL training, diagnostics, experiments, and visualization
remain first-class supported clients.

## 22. Verification strategy

### 22.1 Contract tests

- schema generation reproducibility and stale-output detection;
- config/policy/shock/metric valid and invalid corpus;
- stable IDs and hashes;
- Python/C++ canonical field ordering and enum coverage;
- locale completeness without translated values entering engine contracts.

### 22.2 Exact primitive tests

- posting/rollback and all financial identities;
- entity ID lifecycle and stale handle rejection;
- market order feasibility and deterministic allocation;
- RNG/distribution golden vectors;
- serialization round trip and corruption rejection;
- controller policy transaction validation.

### 22.3 Phase differential traces

Each accepted phase emits a test-only compact record:

```text
phase_id
tick/economy
entity and contract counts
posting/event/physical-command digests
selected typed state columns
invariant residuals
RNG contract/version metadata
```

The harness stops at the first divergence and reports typed field differences.
Comparing only final GDP, unemployment, or a long-run digest is insufficient:
later cancellation can hide an earlier accounting error, while stochastic
chaos can make a harmless early floating difference look catastrophic.

### 22.4 Semantic and stochastic panels

- deterministic no-shock/no-random fixtures;
- fixed action and shock tapes over short windows;
- multi-seed distributions for births, deaths, firm entry/default, matching,
  unemployment, inflation, output, inequality, and crisis frequency;
- impulse responses for fiscal, monetary, prudential, housing, energy, trade,
  sanctions, peg, and external shocks;
- regime-transition timing and sign tests;
- model/economic review for any deliberately changed baseline.

M0's machine-readable statistical registry pins, before native results are
observed, the horizon, immutable seed set/count, pilot-based power calculation
(at least 80% power at the declared equivalence margin), field-level absolute
and relative tolerances, metric/event families, sign/regime rule, and allowed
event-timing window. Distributional parity uses two one-sided equivalence tests
or a confidence interval wholly contained in the declared margin—not failure
to reject a difference—with family-wise alpha 0.05 and Holm correction within
each registered family. The identical frozen panel may be rerun, but its seeds,
horizon, margins, transforms, and decision rule cannot change after a failure
without a reviewed rebaseline/waiver. Intentional drift requires a reviewed
manifest with
before/after raw artifacts and economic rationale.

### 22.5 Invariant suites

Run in native release acceptance, not only debug:

- double-entry and balanced posting;
- A4 nonnegative constraints and declared exceptions;
- A5 net financial worth;
- reserve conservation and RTGS;
- loan lender/borrower principal;
- bond/equity issuer-holder identities;
- bank capital/P&L and interbank pair equality;
- housing title/stock/collateral/lease integrity;
- population/household/relationship integrity;
- employment stocks, FTE, and named flows;
- goods/energy/inventory feasibility;
- dealer, current account, external positions, peg reserves, and world NFA.

### 22.6 Replay and persistence

- direct run equals save/fresh-process/load continuation exactly in D1;
- thread-count fixtures run in fresh processes at `1/2/4/8` workers; only
  platform-supported counts are advertised, and every supported count has the
  same exact D1 digest;
- clone produces the same next result and then isolates later mutation;
- controller event replay reconstructs decisions without model bytes;
- corrupted member, hash, size, reference, schema, or contract fails before
  session publication;
- checkpoint written during a simulated failure never replaces the prior slot.
- every deterministic transaction allocation/apply/validate/commit fault
  ordinal is injected at least once and restores digest, allocator, policy,
  shock, RNG-counter, event, and outbox state exactly.

### 22.7 Interface and security tests

- pure C ABI program and buffer-ownership tests;
- nanobind lifetime, GIL release, wrong dtype/shape, and exception tests;
- post-commit C-buffer serialization and Python-object conversion fault tests
  retrieve the same operation receipt without a second advance;
- multi-tick failure injected at every requested tick reports exact partial
  progress and retains precisely the earlier accepted tick prefix;
- protocol frame split/coalescing, bad UTF-8/JSON, oversize, stale/duplicate
  request, token/version mismatch, reconnect, and concurrent client tests;
- cross-seat and confidential-shock snapshot/query denial tests; caller input
  cannot forge an `AccessScope`;
- timeout/cancel retry after lost response and after save/load returns the
  original result for the same operation key, and rejects key/payload mismatch;
- `.msim`, `.msrl`, canonical event, and network parser fuzzing;
- wheel-installed and packaged-application tests.

### 22.8 Performance correctness

Every performance run also records invariant status and a semantic fingerprint.
An optimization cannot pass by skipping claims, metrics, releases, or a
capability included in the scenario. Validation tiers may reduce expensive
diagnostic scans only after incremental production invariants provide equivalent
coverage.

## 23. Backend selection and rollback

During migration:

```text
MACRO_SIM_BACKEND=python  # production authority
MACRO_SIM_BACKEND=native  # supported native subset or later full engine
MACRO_SIM_BACKEND=shadow  # Python authority plus isolated native comparison
```

This is a developer/runtime option, not a player-facing model selector.

Each native milestone can be disabled at the session boundary. Rollback means
starting a new Python session from the same genesis/action/shock tape; it does
not mean copying a half-advanced Python object graph into native state or vice
versa.

Once native becomes default, saves declare their engine format and only load in
a compatible native engine. Product rollback therefore ships the previous
binary alongside compatible saves rather than promising cross-engine state
conversion.

## 24. Engineering risks and mitigations

| Risk | Mitigation |
|---|---|
| scope expands into a permanent rewrite | vertical milestones, one runnable slice by M4, explicit exit gates |
| Python changes while native is in progress | generated shared contracts, integrate `dev` at milestones, phase fixtures |
| apparent parity failure from RNG/float differences | D1-D4 tiers, deterministic fixtures first, stochastic panels later |
| native code reproduces Python's duplicated state | unique-owner map and mutation API review required before porting a domain |
| transaction journal erases speed gains | benchmark per-phase command/undo arenas; no whole-world copy |
| threading changes economics | static shards, counter RNG, stable merge, thread-count tests |
| Python/C++ boundary becomes chatty | session/batch calls only; bulk arrays; no per-agent callbacks |
| RL gets privileged observations | release snapshot and generated codec are the only policy inputs |
| desktop snapshots dominate | delta, paging, cadence, separate visible/debug snapshots |
| history consumes all memory | rings and streamed columnar chunks |
| native parser/memory safety defects | bounds-first load, sanitizers, fuzzing, process isolation |
| wheel/platform fragmentation | C ABI core, abi3 binding, cibuildwheel and installed-wheel matrix |
| dependency supply-chain growth | minimal pinned dependencies, hashes, SBOM, offline build |
| performance goal is guessed rather than measured | M0 baselines and per-milestone budgets; no cutover on projection alone |

## 25. Immediate implementation backlog

The first implementation work after this design should be split into small,
reviewable commits:

1. Check in the complete schema inventory/ID hashes and the gate manifest,
   tolerance/statistical registry, rebaseline format, and duplicate/
   unknown-reference validators. Freeze the exact M4 V0/V1
   capability/store/phase/metric manifest before component-store design.
2. Implement the deterministic schema generator and checked C++/Python/JSON
   outputs for config, policy/external policy, shocks, metrics, observations,
   phases, RNG, events, invariants, controller/run, checkpoint, and desktop
   protocol; CI regenerates and compares bytes.
3. Add canonical trace/event encoding with Python/C++ golden vectors, then add
   `PhaseTrace` keyed only by generated phase IDs.
4. Add `benchmarks/python_baseline.py`, exact scenario manifests, raw JSON, and
   fixtures for full-playable, historical, RL, World, marriage, roster,
   history, desktop, and frozen V0/V1 cases.
5. Add `.github/workflows` plus reproducible bootstrap; only then add `native/`
   CMake presets, C++20 core/C ABI/CTest/benchmark targets, warnings and
   sanitizer profiles.
6. Implement strong IDs, units, status/errors, owned buffers, immutable
   snapshot leases, engine/controlled handle lifecycles, and installed C-only
   ABI smoke.
7. Implement Philox and every distribution primitive; run golden vectors on
   macOS/Linux/Windows CI before claiming portability.
8. Build the minimal nanobind module and prove installed pure-Python contents;
   only then switch to scikit-build-core and add wheel CI.
9. Select/pin the JSON/canonical-encoding, ZIP/deflate, SHA-256, NPZ/NPY, and
   checkpoint dependencies through M1 ADR prototypes and corruption vectors.
10. Implement account/entity/component identity stores, stable allocation,
    generic owner lots, and the V0/V1 genesis/capability rejection path.
11. Implement no-fail balanced transactions plus `PostingBook`, `ReserveBook`,
    and `LoanBook`; add cumulative-batch validation and a randomized simple
    oracle.
12. Add `TickTransaction`/`WorldTransaction`, every deterministic fault
    ordinal, invariant registry, stable digest, minimal checkpoint/load/clone,
    and fresh-process continuation.
13. Implement V0's phase graph/tick loop, probes, traces, persistence, and
    matched fixtures; then tag its gate.
14. Add V1 capital/basic fiscal through institutional accounts, relevant
    policy/shock inputs, and measured P0.
15. Add the test-only C-ABI differential shadow harness and only afterward the
    stable backend facade; it must never dual-write one state.
16. Add the benchmark dashboard after matched native V1 results exist, showing
    scenario, phase, entity/transaction counts, memory, and invariant status.

The first native PR must not contain translated economic phases. Its purpose is
to make every later port reproducible, packageable, measurable, and rejectable
when wrong.

## 26. Definition of complete C++ engine

The migration is complete only when:

- every gameplay module in section 11 is native or explicitly classified as an
  external Python client;
- no Python economic phase runs inside a native tick;
- all current capabilities, policies, shocks, controller seats, releases,
  scenarios, and frontend data needed for play are connected;
- hard invariants run in production acceptance;
- native replay/save continuation is exact at D1;
- cross-engine semantic and stochastic gates are approved;
- controller/Gym/RL semantics and current artifact deployment work;
- packaged Godot end-to-end flows pass on supported platforms;
- applicable performance and memory gates pass;
- source, schemas, build, wheels, server, dependencies, and save format are
  documented;
- Python remains available only where it is the better outer tool, not because
  a core module was forgotten.

## 27. Deferred ADRs with deadlines

These choices require prototypes, but none permits implementation to proceed
without a recorded decision:

| ADR | Decide by | Evidence required |
|---|---|---|
| FlatBuffers versus another generated native save schema | end of M1 | encode/load size/time, evolution test, corruption handling |
| canonical byte encoding plus exact JSON, ZIP/deflate, SHA-256, and NPZ/NPY implementations/licenses | before the first parser lands, no later than M1 | Python/C++ golden bytes; duplicate-key, nonfinite, Unicode, endianness and corruption corpus; offline build/SBOM |
| exact residual/rounding policy for `double` money | end of M2 | posting and long-run drift corpus |
| dense versus sparse World edge threshold | end of M9 | `N=2..256` trade/capital/migration benchmarks |
| copy versus COW session clone | end of M10 | reset throughput, memory, fault isolation |
| native internal executor design | before first parallel phase | static-shard determinism and oversubscription benchmark |
| eventual fixed-point money experiment | after M10 parity | range, speed, behavioral drift, serialization impact |
| optional GDExtension adapter | after native server ships | measured IPC/packaging need and crash-domain analysis |
| cross-platform launcher bootstrap transport | before M11 packaging | packaged macOS/Linux/Windows ACL, cleanup, crash, and secret-leak tests |

## 28. Audit notes to fix alongside migration

- `world/world.py` still contains introductory text for an earlier empty
  coupling barrier despite implementing trade, capital, migration, pegs, and
  shocks.
- some capital-policy ownership comments predate per-economy
  `ExternalPolicy`.
- the old performance note that every household bond valuation always scans all
  lots is stale; the current code has a version/rate/tick cache. The benchmark
  must measure current code rather than repeat that note.
- `SimulationState` is not the real runtime facade and should not become the C++
  target by name alone.
- `Policy` means controller-adjustable exogenous policy state, not the only
  mutable state in a simulation.
- direct `cloudpickle` use must have a direct optional dependency.
- all runtime-critical Python `assert` gates should be converted to explicit
  validation even before the corresponding native module lands.
- root `README.md`, `docs/README.md`, `docs/design/README.md`,
  `docs/design/current/developer-brief.md`, and
  `docs/design/current/module-map.md` describe obsolete closed-economy/v12.4/
  v23 scope or omit current packages. M0 reconciles them against the generated
  module manifest and CI rejects future drift.

## 29. Primary references

Repository evidence:

The source/doc audit was performed at `dev@c0adcf1`; M0 replaces this prose pin
with generated contract hashes and reviewed rebaseline manifests.

- `macro_sim/economy.py`
- `macro_sim/world/world.py`
- `macro_sim/core/ledger.py`
- `macro_sim/domain/agents.py`
- `macro_sim/demographics/economic_bridge.py`
- `macro_sim/reporting/metrics.py`
- `macro_sim/controllers/gym_adapter.py`
- `macro_sim/rl/artifact.py`
- `macro_sim/rl/model.py`
- `docs/design/current/performance.md`
- `docs/design/core/01-accounting-axioms.md`
- `docs/design/core/02-behavioral-axioms.md`
- `docs/checkpoint_design.md`
- `docs/policy_module_v25.md`
- `docs/controllers_v26.md`
- `docs/shocks_v27.md`
- `docs/rl_training_v26.md`
- `docs/frontend_v29.md`
- `docs/start_menu_design_v31.md`
- `docs/diagnostics/OPEN_ECONOMY_PORTRAITS.md`

External implementation references:

- [nanobind packaging](https://nanobind.readthedocs.io/en/latest/packaging.html)
- [scikit-build-core](https://scikit-build-core.readthedocs.io/en/stable/)
- [cibuildwheel](https://cibuildwheel.pypa.io/en/latest/)
- [CMake presets](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html)
- [Godot GDExtension overview](https://docs.godotengine.org/en/latest/engine_details/engine_api/gdextension/what_is_gdextension.html)
- [Random123 counter-based RNG documentation](https://www.thesalmons.org/john/random123/releases/latest/docs/CBRNG.html)
- [FlatBuffers format internals](https://flatbuffers.dev/internals/)
