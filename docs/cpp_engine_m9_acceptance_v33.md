# C++ Engine M9 Acceptance

Status: accepted locally and on hosted CI; V33 promotion pending

Engine version: `0.9.0-m9`

## Scope

M9 adds the native multi-country frontier on top of complete M8 domestic
economies:

- one atomic World boundary over stable country and currency IDs;
- normalized triangular foreign-exchange rates and country dealer accounts;
- realized trade with inventory reservation, iceberg loss, tariffs, import
  quotas, export subsidies, and symmetric effects for unilaterally owned
  sanctions;
- opening-position factor income, arrears, capital flow, NFA, dealer
  revaluation, peg reserves, pressure, defense, and release;
- aggregate migration, returns, remittances, and both remittance tax legs;
- eight native shock channels, deterministic overlap, lifecycle events, ramps,
  capital-destruction one-shots, and packaged crisis scenarios;
- whole-World rollback, exact checkpoints, stable digests, and per-economy M8
  checkpoints;
- complete C and coarse Python World interfaces;
- installed C package, wheel, source-distribution, semantic, and performance
  gates through 256 countries.

Python is not called per country, route, transfer, order, firm, household, or
person during native World advancement.

## Correctness gates

The following local gates passed on 2026-07-25:

- full Python compatibility regression with eight workers and work stealing:
  1,586 passed, 11 skipped, and four existing Gymnasium warnings in 3,113.31
  seconds;
- release CTest: 49 of 49 passed;
- ASan and UBSan CTest, excluding Python-binding tests: 33 of 33 passed;
- single-country World continuation is byte-identical to standalone M8;
- multi-country trade, FX, tariff, sanction, capital, peg, migration,
  remittance, and shock panels;
- all eight shock channels reach their native economic seams;
- reservation, domestic-phase, and pre-commit fault injection restore the
  byte-identical complete old World;
- exact split-run and fresh-process checkpoint continuation;
- identical checkpoints, digests, and lifecycle events for requested worker
  counts one and eight;
- isolated M9 C ABI smoke and independent installed CMake consumer;
- isolated wheel install, World advancement, snapshot, checkpoint, and
  continuation;
- source-distribution content and path-safety smoke;
- M4-M9 contract checks, source locks, current-target check, CJK scan, and
  `git diff --check`.

Hosted workflow `30155395605` passed release, performance, installed C package,
wheel, and source-artifact gates on macOS, Linux, and Windows, plus sanitizer
gates on macOS and Linux.

## Findings resolved during implementation

- M4 now accepts validated sector productivity, labor-availability, household
  demand, and external-goods inputs without introducing World ownership into
  the domestic engine.
- Productivity shocks affect both linear productivity and Cobb-Douglas total
  factor productivity.
- Imported goods enter the ordinary importer goods market. Importing
  households pay their domestic dealer, realized fills drive external
  settlement, and unfilled source inventory is restored.
- Tariffs, export subsidies, factor income, capital flow, remittances, and peg
  intervention use actual domestic accounts rather than metric-only mirrors.
- Capital destruction is a one-time physical mutation at the opening World
  boundary and is checkpointed through its realized lifecycle event.
- Shock timing rejects tick overflow and overflowing ramp combinations.
- The supported country range uses one measured dense representation through
  256 countries. A future expansion beyond 256 must introduce and requalify a
  deterministic sparse representation.

## Performance gate

The table below uses a release build on the local macOS arm64 host. Each panel
advances seven fully coupled days and includes active trade and migration. The
measurement ran concurrently with the Python compatibility suite, so it is a
conservative local result.

| Countries | Median World day | p95 World day | Maximum allocations per country-day |
|---:|---:|---:|---:|
| 2 | 0.108 ms | 0.119 ms | 367.00 |
| 4 | 0.148 ms | 0.153 ms | 350.75 |
| 8 | 0.219 ms | 0.231 ms | 341.25 |
| 16 | 0.401 ms | 1.007 ms | 335.81 |
| 64 | 2.257 ms | 3.820 ms | 332.19 |
| 256 | 8.665 ms | 13.103 ms | 331.21 |

The 256-country p95 is below the 30 ms platform budget. Normalized
64-to-256 scaling is 0.960 against a maximum of 2.00. The allocation gate
reports 331.21 allocations per country-day at N=256 against a maximum of 400.

These figures measure one small domestic specification per country and do not
constitute a 100,000-person claim. They do show that the World coupling layer
can remain below one 60x frame interval even at the supported 256-country
boundary. Entity-scale P4 and parallel P6 claims remain gated separately.

## Atomicity and persistence

`M9World::advance_one` stages a complete World copy, reserves external
inventory, advances every domestic M8 economy, settles realized external
flows, validates all country and cross-country invariants, and swaps only after
success. Fault tests compare the exact serialized World before and after
failures at each cross-country barrier.

The versioned SHA-256 checkpoint contains every M8 economy, World rules,
external policies, rate and dealer state, external positions and arrears, peg
state, migration stocks, shock specs, lifecycle state, event cursor, and World
tick. Restored sessions continue with byte-identical checkpoints.

## Parallelism boundary

M9 accepts a worker-count request and proves that one and eight produce
identical semantic state. The current implementation intentionally executes
domestic economies serially; it does not claim an M9 threading speedup. This
keeps the first World cutover deterministic and leaves P6 as a measured,
separately gated optimization after the complete native phase graph is stable.

## Public boundaries

The C ABI exposes versioned opaque World handles, genesis, policy and shock
updates, advancement, typed metrics, paged lifecycle events, checkpoints, and
per-economy checkpoints. Caller-owned buffers and explicit required sizes keep
allocation ownership outside the ABI.

The Python extension exposes complete M9 specifications and rules, external
policies, shocks and crisis factories, coarse GIL-free World advancement,
snapshots, lifecycle events, and exact checkpoint continuation. Python remains
a client and compatibility oracle rather than an economic hot-path runtime.

## Promotion rule

The M9 branch may be fast-forwarded into the V33 integration branch only after
the pushed M9 commit passes every required macOS, Linux, Windows, sanitizer,
performance, C package, wheel, and source-artifact job, and the exact full
Python regression passes with eight workers and work stealing. The development
branch remains untouched.
