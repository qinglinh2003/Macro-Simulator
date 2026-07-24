# C++ Engine M4 Execution Plan (V33)

Status: executable plan  
Branch: `refactor/cpp-m4-v33`  
Frozen base: `m3-pure-algorithms-v33`  
Base commit: `02a708cdf4077449ae37f221adf6ec6f33e0c353`  
Scope: first complete native tick inside the migration to the current playable
engine

## 1. Target correction

The migration target is not a historical `Config.v*` factory.

The authoritative product model is:

- `PLAYABLE_MODEL_ID == "current_playable_v1"`;
- `PLAYABLE_FEATURE_OVERRIDES` in `macro_sim/desktop/new_game.py`;
- `NewGameSpec.configs()` for normalized country configuration;
- `NewGameSpec.world` for open-economy configuration;
- the current policy, shock, controller, release, desktop, and RL contracts.

Historical factories such as `v124` remain useful only as low-cost regression
tripwires. They do not define native completeness. In particular, they cannot
be used as the full-playable, desktop, controller, shock, persistence, or
release oracle.

The M0 source manifest incorrectly labels several product-facing fixtures as
`v124`. M4 does not silently inherit that defect. It freezes a new
`current_engine_target` contract from the production builder and records the
old entries as superseded fixture metadata. The immutable historical M0
artifacts remain available for audit.

M4 is still a deliberately small vertical slice. That is an implementation
sequence, not a reduction in product scope. Every current playable module has a
native owner milestone:

| Current playable domain | Native owner |
|---|---|
| basic households, firms, labor, production, goods, capital | M4 |
| fiscal, credit, banks, central bank, settlement | M5 |
| bonds, equity, valuation, firm dynamics | M6 |
| persons, families, estates, ownership, persistent labor | M7 |
| energy and housing | M8 |
| trade, FX, international capital, migration, peg, sanctions, shocks | M9 |
| metrics, releases, controllers, Gym/RL, diagnostics adapters | M10 |
| native policy inference, desktop worker, packaging, cutover | M11 |

No production cutover is permitted before the full current playable contract
is covered.

## 2. Outcome

M4 delivers the first state-owning native daily tick. It composes the M2
canonical root and M3 algorithms into two closed-economy verticals:

- **V0 cash loop:** household and firm planning, spot labor, production,
  consumption-goods matching, cash settlement, firm distribution, metrics,
  invariants, and lag commit.
- **V1 capital and basic fiscal:** V0 plus Cobb-Douglas consumption firms,
  linear capital firms, accelerator investment, capital-goods matching,
  profit/income/consumption taxation, government goods purchases, Treasury
  settlement, capital accumulation, and a minimal firm income statement.

M4 is accepted only when:

1. `EngineSession::advance_ticks(n)` owns the complete native V0/V1 path and
   makes no Python call;
2. production code cannot confuse a historical factory with the current
   playable target;
3. unsupported current capabilities fail before genesis with stable,
   machine-readable reasons;
4. deterministic phase fixtures agree with an independent Python oracle;
5. fixed-seed stochastic panels satisfy the frozen envelopes;
6. a checkpoint restored in a fresh process continues exactly;
7. failed ticks restore all money, physical state, lags, metrics, RNG counters,
   and the tick number;
8. the steady tick reuses persistent scratch capacity and does not make a full
   state copy or compute a state digest;
9. the P0 V1 benchmark is at least five times faster than the matched Python
   oracle and has no hidden quadratic growth;
10. all M0-M3 regression, packaging, sanitizer, and cross-platform gates remain
    green.

## 3. M4 capability boundary

### 3.1 V0 supported surface

V0 supports:

- one closed economy and one currency;
- basic economic households, one labor unit per household;
- consumption firms with linear production;
- adaptive income and demand expectations;
- inventory-buffer production planning;
- Calvo wage and price updates from named Philox streams;
- sampled, preferential, or price-sorted consumption matching;
- optional rationed-demand observation;
- cash wages, goods purchases, profit, and equal household dividends;
- total money, output, price index, unemployment, and conservation drift.

V0 rejects capital firms, government, credit/banks as economic mechanisms,
securities, persons/demographics, persistent labor, housing, energy,
open-economy coupling, shocks, policy/controller mutation, and RL.

### 3.2 V1 supported surface

V1 adds:

- consumption and capital firm sectors;
- physical capital and Cobb-Douglas consumption production;
- accelerator and depreciation replacement investment demand;
- the capital-goods market and next-tick capital commitment;
- a Treasury account that may run negative;
- profit, income, consumption, and wealth tax rates;
- competitive government consumption and public investment;
- firm revenue, compensation, tax, dividend, and retained-earnings flows;
- aggregate capital, tax, spending, deficit, and firm-statement metrics.

V1 still rejects the M5-M10 mechanisms. A capability rejection means
"scheduled for another milestone", not "absent from the latest engine".

### 3.3 Ruleset provenance

The M4 ruleset contains only the fields consumed by V0/V1, but every field maps
to the current 370-field config inventory and current policy registry. Defaults
come from the daily production builder where the capability is active.
Historical preset names are not serialized into native state.

Rules, capabilities, vertical ID, contract hash, and RNG profile are immutable
for a session. Runtime policy mutation begins in the milestone that owns the
corresponding policy domain.

## 4. State and phase design

### 4.1 Persistent state

The M4 root adds only authoritative cross-tick columns:

- household account, expected and realized income, consumption plan and
  realization, labor sold;
- firm account, sector, technology, inventory, capital, productivity,
  expectation lags, posted wage/price/markup, and prior rationing state;
- Treasury identity for V1;
- tick, ruleset identity, vertical, named RNG counters, and last committed
  aggregate metrics.

Within-tick plans, orders, offers, trades, journals, and derived aggregates are
not persistent state.

### 4.2 Persistent tick scratch

`EngineSession` owns one `TickScratch` allocated after genesis. It contains:

- stable household and firm ID/account projections;
- reusable worker and firm permutation arrays;
- reusable labor assignments;
- reusable consumption and capital orders/offers/clearing buffers;
- a transfer command buffer;
- a typed component undo journal;
- phase aggregate accumulators.

Capacity is reserved from genesis counts and reused. Growth is allowed only
when entity counts exceed the recorded capacity; M4 itself has no entry/exit,
so a normal tick does not grow it.

### 4.3 Tick journal

M4 does not use `WorldTransaction` or a full checkpoint for daily rollback.

At tick open, it journals:

- every cross-tick household and firm column that a phase may mutate;
- the prior value of each touched account;
- named RNG counters;
- committed aggregate metrics and tick number.

After capacity reservation, application is no-fail. A validation or injected
fault restores the journal in reverse order. State digests are test and
checkpoint operations, never hot-path transaction machinery.

### 4.4 Phase order

The native phase IDs remain aligned with the current phase graph:

1. `open-books`
2. `open-real-economy`
3. `plan-and-finance`
4. spot labor
5. production
6. consumption-goods market
7. capital-goods market (V1)
8. `settle-domestic`
9. `validate-and-measure`
10. `stage-local-commit`

M4 stores phase summaries in a test-only trace sink. The sink is passive and
does not own simulation state.

## 5. Performance contract

Performance is an M4 exit condition.

### 5.1 Structural requirements

- no Python call inside `advance_ticks`;
- no per-agent virtual dispatch or string-key lookup;
- no full-state checkpoint, clone, digest, or JSON serialization per tick;
- no repeated seller-weight rebuild or repeated price sort;
- no `O(H * F)` labor scan;
- one stable pass over households and firms for planning and aggregates;
- direct indexed account access;
- scratch and journal capacities are reused after warm-up;
- result history is bounded to the requested output cadence.

### 5.2 P0 workload

The milestone workload is one V1 economy with:

- 5,000 basic economic households;
- 525 consumption firms;
- 225 capital firms;
- one settlement bank identity;
- 365 measured days after five warm-up days;
- seed 206.

The benchmark compares native V1 with the matched Python V1 subset, not with
`v124` and not with the full current playable engine.

Required:

- native median day no more than 20% of matched Python median day;
- native p95 day below the frozen absolute budget;
- 2x entity scaling ratio below 2.6 for the measured tick;
- scratch capacity unchanged after warm-up;
- zero checkpoint/digest calls from the tick path;
- allocations after warm-up either zero or explicitly attributed to a checked
  standard-library/math implementation with a bounded count.

The full current playable 60x product budget remains 16.7 ms/day. M4 records
progress toward it but does not claim full-product performance while most
domains still execute only in Python.

## 6. Differential and stochastic evidence

The M4 oracle is a small independent Python implementation that imports no
native code. It consumes the same normalized M4 fixture document and emits a
phase trace.

Deterministic comparison includes:

- account balances;
- household expectations, income, spending, and labor;
- firm inventories, capital, expectations, postings, sales, costs, taxes,
  dividends, and lags;
- market allocations and stock commands;
- phase aggregates, metrics, and invariants;
- tick and named RNG counter state.

Exact comparison is required for IDs, enums, counters, ordering, integer
fields, and deterministic money transfers. The M0 tolerance registry applies
to documented floating-point reductions.

Fixed-seed panels cover Calvo changes, sampled seller choice, worker ordering,
and firm ordering. They compare aggregate distributions and replay exactness,
not Python's Mersenne Twister sequence.

## 7. Persistence and interfaces

The native checkpoint stores:

- M2 canonical books;
- M4 component columns;
- vertical, ruleset/capability hashes, and tick;
- named RNG counters;
- last committed metrics.

M2-only checkpoints retain their existing byte contract. M4 checkpoints use a
new required feature and never masquerade as M2 payloads.

M4 exposes:

- C++ `initialize_simulation`, `advance_tick`, and `advance_ticks`;
- a test-only C ABI for genesis, advance, summary, digest, save, and load;
- a nanobind batch adapter used by differential tests.

The Python production engine remains authoritative until the M10/M11 cutover.

## 8. Work packages

### M4-00 — Current-engine target correction

Deliver the current playable target contract, feature/milestone coverage
matrix, supersession record for stale M0 product-fixture labels, and this plan.

Exit:

- the contract is generated from `current_playable_v1`;
- every production override and World capability has one native owner;
- only F0 classifies `v124` as an intentional historical target;
- CI fails if the production builder changes without refreshing the contract.

### M4-01 — Tick state and scratch

Deliver M4 rules/capabilities, state columns, projections, `TickScratch`,
component journal, phase trace, and benchmark instrumentation.

Exit:

- rejected capabilities leave no root;
- scratch reuse and rollback tests pass;
- no full-state operation appears in a measured tick.

### M4-02 — V0 cash loop

Deliver planning, spot labor, production, goods matching, settlement,
distribution, metrics, invariants, and lag commit.

Exit:

- deterministic phase differential passes;
- seed panels and fault ordinals pass;
- direct and chunked `advance_ticks` are identical.

### M4-03 — V1 capital and basic fiscal

Deliver capital genesis, capital firms, investment, capital matching, tax and
spending, firm statements, public/physical capital commitment, and metrics.

Exit:

- V1 differential and accounting identities pass;
- V0 remains unchanged;
- unsupported M5-M10 capabilities remain explicit.

### M4-04 — Persistence and boundary adapters

Deliver M4 checkpoint/load/continuation, C ABI, nanobind adapter, and installed
consumer tests.

Exit:

- fresh-process continuation is exact;
- old M2 checkpoint tests remain byte-stable;
- all adapters batch work at tick granularity.

### M4-05 — Performance and complete acceptance

Deliver release benchmark artifacts, scaling/allocation counters, sanitizer
evidence, full Python regression, packaging, and cross-platform CI.

Exit:

- every performance gate in section 5 passes;
- all regression and portability gates pass;
- the branch is clean and source/contract locks are current.

### M4-06 — Freeze and promotion

Deliver annotated tag `m4-first-native-tick-v33` and fast-forward
`refactor/cpp-engine-v33`.

Exit:

- M4 branch, V33 branch, and tag peel to the same accepted commit;
- `dev` remains unchanged;
- remote CI is green on macOS, Linux, and Windows.

## 9. Explicit deferrals

M4 does not implement or claim parity for:

- credit, bank behavior, central-bank operations, RTGS, or interbank;
- bonds, equity, valuation, firm entry/exit, or resolution;
- persons, demographic events, families, estates, or persistent labor;
- energy or housing;
- World coupling, FX, trade, migration, peg, sanctions, or stateful shocks;
- releases, controller scheduling, Gym/RL, desktop cutover, or native policy
  inference.

These are all part of the current engine target and are owned by M5-M11. Their
absence from M4 is always reported as `unsupported`, never accepted as a
silent no-op and never used to redefine the latest engine.
