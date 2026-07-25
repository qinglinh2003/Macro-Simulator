# C++ Engine Scale Baseline V33

Status: one-million-person M8 baseline established; optimization in progress

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

The answer to the last question is not yet yes. The survey found several specific,
removable implementation bottlenecks. It did not find evidence that the economic
mechanisms themselves impose the current limit.

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
validation still runs inside every measured day.

This baseline proves that the enabled model can now create and advance one
million persons on the target machine. It does not meet the interactive target.
The remaining gap is approximately 31 times at the median.

### 3.3 Current one-million-person optimization checkpoint

All accepted optimization measurements continue to use exactly 1,000,000
persons, beneficial ownership enabled, three measured days, and the same
scenario. The root-state digest remains
`9c0bba0226b7c6784e82bfd330b3aae744fa60f59aaa5c287fd66970c3ebd0ce`.

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

The latest acceptance run measured 10.05 s, 10.27 s, and 9.25 s. A second
profiled run measured a 9.76-second median. Genesis remained approximately
8.25 seconds. The optimization has therefore removed approximately 68% of
median daily latency without changing the deterministic result, but it is still
approximately ten times above the interactive target.

The additional lookup structures currently increase peak resident memory. This
is an explicit open issue, not an accepted final tradeoff. The next data-layout
work must share or remove redundant derived security indexes and release stale
scratch capacities while continuing to reduce daily latency.

Beneficial ownership now keeps canonical lots independently in runtime and tick
scratch, while immutable reverse indexes are shared until a mutation requires a
copy. Daily validation checks every touched lot and asset row. Checkpoint loads,
explicit state validation, and the acceptance suite still execute the complete
cross-index validation.

Normal single-day advancement now uses the existing fast M6 record validation at
its entry boundary. Explicit state validation and checkpoint boundaries retain
the full security-index check, and the per-day working-state validation remains
in place. Sequential energy rationing now carries a monotonic cursor over
price-ordered offers. Permanently exhausted offers are visited once rather than
once per buyer; buyer priority, offer priority, prices, fiscal flows, and the
resulting digest are unchanged.

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

The current enabled engine is already above one second on a normal M9 day at
50,000 persons and has approximately five-second ownership expansion days. It
cannot support one million persons at interactive speed in its present form.

Even the diagnostic lower bound reaches 596 ms per M9 day and 1.22 GiB peak RSS
at 100,000 persons. A simple linear projection gives approximately:

- 6 seconds per simulated day at one million persons
- 12.2 GiB peak RSS for the simulation process

The measured latency slope is slightly worse than linear, so these are optimistic
lower bounds. The current genesis slope would imply tens of minutes at one
million persons.

The one-million-person, one-second target therefore requires all of the primary
complexity fixes. Removing only the `World` copy or adding threads will not be
enough.

## 9. Optimization order

The recommended order is based on measured benefit and dependency risk:

1. Replace per-lot sorted-vector insertion with deterministic batch index
   construction, and make beneficial synchronization incremental.
2. Batch genesis transfers so that all energy producers share one transaction
   commit and one validation boundary.
3. Replace daily `M9World` deep copy with an atomic prepare/commit or undo-journal
   protocol that reuses domestic scratch state.
4. Batch securities mutations and rebuild holder/security indexes once per
   mutation phase.
5. Remove redundant whole-state validation and digest work from hot runtime paths
   while preserving explicit debug and acceptance checks.
6. Reprofile before changing data layout or adding deterministic multithreading.

Complexity and allocation fixes come before multithreading. Parallel execution
would otherwise multiply memory pressure and hide avoidable serial work.

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

Run the current one-million-person M8 acceptance probe:

```bash
build/native/m9-release/native/macro_sim_m9_scale_probe \
  --mode m8 \
  --persons 1000000 \
  --warmup-days 0 \
  --days 3 \
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
