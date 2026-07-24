# C++ Engine M5 Acceptance (V33)

Status: accepted locally
Branch: `refactor/cpp-m5-v33`
Base: `49fcd45f8d2289e6ee1b47a52f588505e2b8d88e`
Date: 2026-07-24

## 1. Product target

M5 extends the accepted M4 native vertical with the monetary closed-economy
domains owned by the current complete playable engine. It does not target or
depend on a historical model preset.

Python remains an independent behavioral oracle. It is not called by the
native tick. Production cutover remains forbidden until M11 accepts every
domain in the current-engine ownership map.

## 2. Accepted M5 surface

M5 adds:

- live fiscal policy, including deficit targeting, allowances, wage floors,
  income support, and job-guarantee controls;
- exogenous, Taylor, and manual monetary regimes with exact manual-rate
  validation;
- multiple commercial banks, deterministic customer assignment, relationship
  lock-in, deposit competition, and credit search;
- household and firm credit, lender ownership, principal repayment, interest,
  prudential limits, and deterministic write-off fixtures;
- canonical reserve, RTGS, interbank, central-bank-operation, bank-P&L, and
  bank-capital books;
- reserve operations, lender-of-last-resort support, bank runs, and
  non-equity resolution;
- maintained legacy and realized bank-P&L scheduling paths;
- atomic M5 tick rollback and deterministic M5 checkpoints;
- C++, append-only C ABI, and Python public interfaces;
- isolated wheel, source-artifact, and installed C SDK coverage.

Securities, equity ownership, firm lifecycle, and equity-aware resolution
remain assigned to M6. M5 introduces no banking-header dependency on those
domains.

## 3. Canonical ownership and atomicity

Financial state is owned once:

- postings own deposits and institutional cash;
- the reserve book owns settlement positions and reserve stock;
- the loan book owns commercial credit;
- the interbank book owns overnight bank claims;
- the central-bank-operation book owns reserve absorption and
  lender-of-last-resort claims;
- the P&L journal and capital state own the realized bank close.

M5 uses the M4 projected-tick extension seam. A phase failure restores the M5
runtime, publishes none of the projected books, and leaves the tick and
canonical root digest unchanged.

The tick validates money net of loan principal, reserve stock, loan ownership,
interbank and central-bank contracts, finite values, P&L identities, and bank
capital roll-forwards before commit.

## 4. Public and persistence contracts

The accepted public boundary includes:

- `EngineSession` M5 initialization, policy updates, stepping, snapshots,
  checkpointing, and restoration;
- append-only C ABI capability, M5 specification, policy-default, update,
  advance, digest, and checkpoint functions;
- Python M5 policy, rules, specification, monetary regime, stepping, and
  inspection interfaces;
- checkpoint magic `MSM5CP01`, schema version 1, SHA-256 integrity, semantic
  validation, and a 256 MiB input cap.

Same-process and fresh-process continuations are exact. Corrupt checkpoints are
rejected before state publication.

## 5. Local validation evidence

The final local validation set includes:

- M5 debug build: 21 of 21 CTest cases passed;
- M5 release build: 21 of 21 CTest cases passed;
- M5 AddressSanitizer and UndefinedBehaviorSanitizer build: 14 of 14 CTest
  cases passed;
- monetary, fiscal, credit, RTGS, interbank, crisis, resolution, legacy-P&L,
  realized-P&L, and bank-assignment fixtures passed;
- public semantic panel: 10 of 10 checks passed;
- exact fresh-process checkpoint continuation passed at tick 29;
- isolated wheel smoke passed;
- source-distribution offline-input smoke passed;
- installed C-only consumer smoke passed;
- complete current Python engine regression: 1,586 passed and 11 skipped.

The Python suite emitted four existing Gymnasium warnings about unbounded Box
observation limits. It emitted no failures.

## 6. Performance evidence

Release P0 workload:

- 2,000 households;
- 300 firms;
- 16 banks;
- six warm-up days and 120 measured days;
- fixed seed 505;
- active credit origination and settlement.

Latest local gate result:

- native median tick: 310,709 ns;
- native p95 tick: 358,167 ns;
- 2x entity scaling ratio: 1.48694;
- maximum steady-state allocations per day: 1;
- scratch-capacity signature unchanged;
- credit and settlement sinks both exercised.

All values pass the M5 budget: 2 ms p95, at most two allocations per day, and
at most 2.6x latency for the doubled entity workload.

This is evidence for the migrated M5 vertical, not yet a speed claim for the
complete engine. M6-M11 still own substantial current-engine domains.

## 7. Acceptance decision

M5 is accepted locally as a deterministic, recoverable, packageable, and
performant monetary closed economy. It is ready for cross-platform CI and,
after all macOS, Linux, Windows, ASan, and UBSan jobs pass on one commit, a
fast-forward into `refactor/cpp-engine-v33`.

The acceptance tag is `m5-monetary-closed-economy-v33`.
