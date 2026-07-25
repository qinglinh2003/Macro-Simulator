# C++ Engine Scale Baseline V33

Status: one-million-person M8 median target met; tail optimization continues

Date: 2026-07-25

Base commit: `a0c7a324d3cc79361bef7562e05bd42f5d461c16`

Branch: `perf/cpp-scale-v33`

## 1. Purpose

This survey establishes the first reproducible population-scale baseline for the
native engine after M9. It answers four questions:

1. How do daily latency, genesis latency, allocations, and peak resident memory
   scale with population?
2. How much overhead does the M9 `World` wrapper add around an otherwise identical
   M8 economy?
3. Which concrete code paths cause the observed superlinear behavior?
4. Is one million simulated persons at no more than one second per simulated day
   plausible without changing the economic model?

The median answer to the last question is now yes for the committed
static-population M8 acceptance scenario. Across days 31 through 60, 25 of 30 days
complete in less than one second. P95 is 1.054 seconds and the maximum is 1.190
seconds, so the tail target is close but not yet complete. This is not a claim
that dynamic, open-economy, or M9 workloads meet the same budget.

## 2. Test environment

- Machine: MacBook Pro, Apple M5, 10 CPU cores, 24 GiB unified memory
- Operating system: macOS 26.5.2
- Compiler: Apple Clang 21.0.0, arm64
- Build: `m9-release`, optimized, project warning gates enabled
- Build parallelism: 8 workers
- Measurement process: one configuration per process

The probe reports process peak RSS through `getrusage`. Genesis and simulated days
are timed with `std::chrono::steady_clock`. Heap allocation counts use the same
global allocation counter pattern as the existing milestone performance gates.

## 3. Probe scenario

`macro_sim_m9_scale_probe` creates the same domestic specification in both modes:

- `m8`: direct `EngineSession` execution
- `m9`: one economy inside `M9World`

The scenario is deliberately stable so that entity-scale cost is not confused
with population growth:

- 2.5 persons per household
- consumption and capital firms scale with population
- energy producers scale with population
- eight banks
- static population and household topology
- persistent labor and financial markets enabled
- twelve equity watchlist entries per household
- one portfolio review per household every 30 days, deterministically staggered
  across households
- housing stock enabled, with the active housing market disabled
- firm and bank entry dynamics disabled

The normal probe keeps beneficial ownership enabled. A diagnostic switch can
disable beneficial ownership and estates together. That switch exists only to
isolate a hotspot; it is not a proposal to remove either mechanism from the
product.

### 3.1 Performance acceptance population

All performance acceptance runs from this point forward use exactly 1,000,000
persons. Smaller scenarios may still be used for correctness, semantic, and unit
tests, but they are not performance evidence and cannot be used to claim an
optimization win.

The earlier smaller-population measurements below are retained only as historical
hotspot evidence from the initial survey.

### 3.2 First complete one-million-person M8 baseline

The first complete run followed the removal of quadratic account creation,
beneficial-asset insertion, securities genesis, and producer-opening transaction
paths. It kept beneficial ownership enabled and completed three validated days.

| Persons | Mode | Genesis | Day samples | Median day | Peak RSS | Max allocations/day |
| ---: | :---: | ---: | :--- | ---: | ---: | ---: |
| 1,000,000 | M8 | 8.10 s | 21.26 s, 30.99 s, 31.68 s | 30.99 s | 6.12 GiB | 26,860,085 |

The run produced root-state digest
`9c0bba0226b7c6784e82bfd330b3aae744fa60f59aaa5c287fd66970c3ebd0ce`.
The probe uses the root-state digest because the current full M8 digest first
materializes a checkpoint and the legacy checkpoint limit is 512 MiB. Full state
record and accounting validation still runs inside every measured day.

This baseline proves that the enabled model can now create and advance one
million persons on the target machine. It does not meet the interactive target.
The remaining gap is approximately 31 times at the median.

### 3.3 Current one-million-person optimization checkpoint

All accepted optimization measurements use exactly 1,000,000 persons with
beneficial ownership enabled. The original daily-review digest remains historical
evidence. The current deterministic digest changed intentionally when household
portfolio review moved to a realistic staggered 30-day cadence.

| Checkpoint | Median day | Peak RSS | Change from first baseline |
| :--- | ---: | ---: | ---: |
| First complete baseline | 30.99 s | 6.12 GiB | - |
| Linear beneficial validation and one close-day synchronization | 23.32 s | 5.86 GiB | -24.8% |
| Composite security-and-holder index | 17.21 s | 6.15 GiB | -44.5% |
| Shared beneficial derived indexes | 15.40 s | 7.06 GiB | -50.3% |
| Asset-row aggregation and no projection sort | 13.68 s | 7.54 GiB | -55.9% |
| Mutation-tracked incremental beneficial validation | 12.40 s | 7.78 GiB | -60.0% |
| Fast advance-entry validation | 10.27 s | 7.80 GiB | -66.9% |
| Monotonic sequential energy clearing | 10.05 s | 7.67 GiB | -67.6% |
| Stable equity-order bucketing | 9.47 s | 7.86 GiB | -69.4% |
| Compact incremental security-pair chains | 8.02 s | 8.06 GiB | -74.1% |
| Contiguous beneficial indexes and one synchronization boundary | 7.48 s | 7.83 GiB | -75.9% |
| Presence epochs and fingerprinted asset slots | 6.82 s | 7.23 GiB | -78.0% |
| Staggered review, change journal, and linear indexes, first cycle | 0.674 s | 6.88 GiB | -97.8% |
| Staggered review, second 30-day cycle | 0.760 s | 6.71 GiB | -97.5% |

The final first-cycle run used schema `m9-scale-probe-v3` and scenario
`static-population-staggered-portfolio-v2`. Genesis took 8.22 seconds. Across
days 1 through 30 the median was 0.674 seconds, p95 was 1.491 seconds, and the
maximum was 1.539 seconds. The deterministic root digest was
`5f23e4becd18f3e3d29595a0c12127682b0340c2cfcf0ef736e017e8cc7ad73f`.

The first cycle is a materialization ramp: each household cohort creates its
positions for the first time. At day 30 the economy contains 5,748,680 active
security lots and 15,392,650 active person-level beneficial lots.

The complete second-cycle run, days 31 through 60, has a 0.760-second median,
1.054-second p95, and 1.190-second maximum. Twenty-five of the thirty measured
days are below one second. Position materialization has not completely stopped:
the run ends with 6,093,687 security lots and 16,259,051 beneficial lots. The
tail result is therefore a real remaining workload rather than measurement
noise. Its digest is
`5b95c26e27d6015df5274f76888f876074e99007d8e84f17cafcb27bffc791d5`.
Genesis remains a one-time cost and is not part of daily latency acceptance.

The result comes from model-preserving algorithm and data-layout changes plus
one documented scheduling rule:

- Household portfolio decisions occur every 30 days rather than every day.
  Households are deterministically staggered, so one thirtieth reviews on each
  day. The watchlist size, order calculation, clearing, ownership, prices, and
  settlement mechanisms are unchanged.
- Security mutations publish a compact household-position change journal.
  Beneficial ownership updates only changed positions instead of rescanning all
  canonical security lots.
- Active holder and contract indexes use linear dense counting when identifiers
  are dense. Sparse inputs retain the comparison-sort fallback.
- Beneficial asset rows maintain active share totals incrementally. Daily
  validation checks dirty lots and verifies that each dirty active asset sums to
  one without rebuilding the complete reverse lot index.
- Daily security validation checks canonical records and accounting identities.
  Full index reconstruction and comparison remains at explicit state validation,
  checkpoint, and test boundaries.
- Inactive security lots are compacted at the daily close. `SecurityLotId` is
  therefore an internal transient identity across days; security identity,
  holder balances, cost basis, and public position semantics are preserved.
- Bond allocation is capped by the clearing holder's actual remaining units,
  preventing floating-point over-allocation at large scale.

The retained full 8-worker acceptance suite passes all 49 tests, including C and
Python bindings, checkpoint round trips, semantic panels, extension seams, and
fault-injection coverage. Further work should reduce the approximately 6.9 GiB
peak RSS and remove the remaining full tick-staging copies before treating M9
multi-economy or highly dynamic population workloads as complete.

## 4. Baseline with the current model enabled

All times are per process. Peak RSS is the maximum observed after genesis and
measured days.

| Persons | Mode | Genesis | Median day | Slowest measured day | Peak RSS | Max allocations/day |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: |
| 2,000 | M8 | 8.5 ms | 22.17 ms | 22.48 ms | 32.5 MiB | 1,268 |
| 2,000 | M9 | 8.5 ms | 26.11 ms | 26.17 ms | 49.7 MiB | 43,155 |
| 10,000 | M8 | 202 ms | 129.96 ms | 285.80 ms | 158.3 MiB | 114,741 |
| 10,000 | M9 | 204 ms | 153.05 ms | 309.80 ms | 237.6 MiB | 226,605 |
| 20,000 | M8 | 834 ms | 287.17 ms | 912.87 ms | 317.2 MiB | 229,401 |
| 20,000 | M9 | 822 ms | 341.79 ms | 974.19 ms | 454.1 MiB | 452,924 |
| 50,000 | M8 | 5.63 s | 899.69 ms | 5.02 s | 695.2 MiB | 573,374 |
| 50,000 | M9 | 5.80 s | 1.05 s | 4.99 s | 1,084.2 MiB | 1,131,871 |

The slow measured day is not random noise. It is an ownership-index expansion
day. At 20,000 persons, the measured M8 sequence in nanoseconds was:

```text
912873167, 287173916, 287976500, 290574000,
283516959, 283940625, 283871916, 283069750
```

The stable days are already superlinear, and the expansion day is much worse.

## 5. Beneficial-ownership isolation

The diagnostic run disables beneficial ownership and estates while leaving the
rest of the scenario unchanged.

| Persons | Mode | Genesis | Median day | Slowest measured day | Peak RSS | Max allocations/day |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: |
| 20,000 | M8 | 819 ms | 81.58 ms | 84.13 ms | 161.9 MiB | 558 |
| 50,000 | M8 | 5.63 s | 222.62 ms | 239.48 ms | 414.6 MiB | 1,283 |
| 50,000 | M9 | 5.67 s | 264.72 ms | 275.41 ms | 662.2 MiB | 88,077 |
| 100,000 | M8 | 25.92 s | 509.37 ms | 519.10 ms | 825.9 MiB | 2,490 |
| 100,000 | M9 | 26.05 s | 596.08 ms | 608.95 ms | 1,244.8 MiB | 175,816 |

At 20,000 persons, beneficial ownership currently causes:

- 3.52 times the stable-day latency
- 10.85 times the slow-day latency
- 1.96 times the peak memory
- 411 times the maximum daily allocation count

At 50,000 persons, it causes:

- 4.04 times the stable-day latency
- 20.98 times the slow-day latency
- 1.68 times the peak memory
- 447 times the maximum daily allocation count

The disabled result is a diagnostic lower bound, not an acceptable product
configuration.

## 6. M9 `World` overhead

With beneficial ownership disabled, the M9 wrapper adds the following cost over
direct M8 execution:

| Persons | Day latency | Peak RSS | Allocations/day |
| ---: | ---: | ---: | ---: |
| 50,000 | 1.19 times | 1.60 times | 68.6 times |
| 100,000 | 1.17 times | 1.51 times | 70.6 times |

The source and allocation profile identify the direct cause:

```cpp
M9World staged = *this;
```

Every simulated day deep-copies the complete world, including each domestic
economy and its scratch state, before doing useful work. The copy preserves
atomic failure semantics, but its memory and allocation cost is not viable at the
target scale.

## 7. Profiled hotspots

### 7.1 Beneficial ownership: quadratic asset-index insertion

In the enabled 50,000-person profile, approximately 71% of CPU samples ended in:

```text
BeneficialOwnershipBook::AssetIndexRow vector insertion
```

`BeneficialOwnershipBook::create_lot` inserts a new row into a sorted vector for
each newly observed asset. A growing number of security positions therefore
causes repeated movement of the remaining vector. `synchronize_beneficial_claims`
also walks canonical positions and the ownership book more than once per day.

This combines:

- quadratic insertion behavior during asset expansion
- full ownership-book copies into M7 scratch
- full synchronization scans
- full projection validation scans

### 7.2 Genesis: one full-state transaction per energy producer

Genesis scales from 0.82 seconds at 20,000 persons to 5.63 seconds at 50,000 and
25.92 seconds at 100,000. This is close to quadratic.

The genesis profile is dominated by repeated
`SettlementTransaction::commit()` calls from energy-producer creation. Each
producer receives opening cash in its own transaction. Each commit performs
whole-state digest and invariant work, including:

- `OwnershipBook::validate_shares`
- root-state serialization for the digest
- SHA-256 calculation

The producer count grows with population, while each commit scans a state that
also grows with population.

### 7.3 Stable days: securities index lifecycle

After removing the ownership hotspot diagnostically, the stable-day profile is
dominated by:

- `SecurityBook::find_active_lot`
- `SecurityBook::units_held`
- `SecurityBook::rebuild_indexes`
- flat holder-index sorting
- equity-order sorting
- repeated `SecurityBook::transfer_units`

Security indexes are rebuilt and searched repeatedly during a batch of related
mutations. The mutation lifecycle needs one deterministic batch rebuild, not
repeated global rebuilds.

### 7.4 World staging and duplicate validation

M9 deep-copies the world at the start of each day, advances the already-staged
domestic engines, validates the complete world, and then moves the staged world
back. Domestic advancement already has its own scratch and validation protocol.
The current layering duplicates memory, allocation, and some validation work.

## 8. One-million-person projection

Direct M8 execution now demonstrates the median target rather than projecting it:

- 8.22 seconds for one-time genesis
- 0.760-second median across days 31 through 60
- 1.054-second p95 and 1.190-second maximum
- 25 of 30 second-cycle days below one second
- approximately 6.7 GiB peak RSS

The first-cycle p95 remains above one second while millions of direct positions
and person-level claims are materialized. Product startup can hide or explicitly
report this market-initialization phase, but the engine should continue reducing
it rather than treating it as free work.

M9 is still outside the claim. Its world-level transactional staging deep-copies
the domestic economy and can multiply the M8 memory footprint. One million
persons in one M9 economy therefore remains blocked on removing the world copy,
not on the domestic economic mechanisms measured here.

## 9. Optimization order

Completed work includes quadratic genesis removal, compact ownership indexes,
incremental synchronization and validation, stable order bucketing, linear
security-index construction, and staggered portfolio scheduling.

The next measured order is:

1. Remove the M9 daily world deep copy with a reusable atomic prepare/commit or
   undo-journal protocol.
2. Replace remaining full M6 and M7 tick-staging copies with chunked copy-on-write
   storage or mutation journals.
3. Reduce the approximately 15.4 million materialized beneficial lots through a
   compact household-equal-claim representation with explicit exception records.
4. Rebuild public security indexes no more than once per mutation phase.
5. Profile dynamic population, firm entry and exit, active housing, and
   multi-economy workloads at one million persons.
6. Add deterministic parallel phases only after their read/write sets and memory
   budgets are measured.

Complexity and memory-layout fixes continue to precede multithreading. Parallel
execution would otherwise multiply the remaining staging footprint.

## 10. Next acceptance gates

Each optimization must preserve:

- M4-M9 deterministic digests
- checkpoint round trips
- fault-injection atomicity
- accounting and ownership invariants
- C, C++, and Python binding contracts
- sanitizer cleanliness

The sole performance gate is one million persons. Each accepted optimization
must improve or preserve genesis time, daily latency, peak RSS, and allocation
count on that population while all required correctness gates remain green. The
target is no more than one second per normal M9 day.

## 11. Reproduction

Configure and build:

```bash
uv sync --group dev --group m1
uv run cmake --preset m9-release
uv run cmake --build --preset m9-release --parallel 8
```

Run the one-million-person first-cycle probe:

```bash
build/native/m9-release/native/macro_sim_m9_scale_probe \
  --mode m8 \
  --persons 1000000 \
  --warmup-days 0 \
  --days 30 \
  --beneficial-ownership enabled
```

Run the post-materialization steady-state probe:

```bash
build/native/m9-release/native/macro_sim_m9_scale_probe \
  --mode m8 \
  --persons 1000000 \
  --warmup-days 30 \
  --days 5 \
  --beneficial-ownership enabled
```

Run the one-million-person M9 acceptance probe once M9 memory staging is safe:

```bash
build/native/m9-release/native/macro_sim_m9_scale_probe \
  --mode m9 \
  --persons 1000000 \
  --warmup-days 0 \
  --days 3 \
  --beneficial-ownership enabled
```
