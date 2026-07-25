# C++ Engine Scale Baseline V33

Status: one-million-person open multicountry M9 60-day target met

Date: 2026-07-26

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

The answer to the performance target is now yes for static-population M8 and for
closed, open, multicountry, and shock-active M9 acceptance scenarios. All 60
measured days complete in less than one second over the first two portfolio
cycles. The all-days result includes the documented household-portfolio
beneficial-ownership simplification below; before that change, the median met
the target but the tail did not. Dynamic population, active housing, and firm or
bank entry remain outside this claim.

## 2. Test environment

- Machine: MacBook Pro, Apple M5, 10 CPU cores, 24 GiB unified memory
- Operating system: macOS 26.5.2
- Compiler: Apple Clang 21.0.0, arm64
- Build: `m9-release`, optimized, project warning gates enabled
- Build and M9 runtime parallelism: up to 8 workers
- Measurement process: one configuration per process

The probe reports process peak RSS through `getrusage`. Genesis and simulated days
are timed with `std::chrono::steady_clock`. Heap allocation counts use the same
global allocation counter pattern as the existing milestone performance gates.

## 3. Probe scenario

`macro_sim_m9_scale_probe` creates the same aggregate domestic specification in
both modes:

- `m8`: direct `EngineSession` execution
- `m9`: one or more economies inside `M9World`

For multicountry runs, `--persons` is the exact total population rather than a
per-country count. Quotient and remainder distribution keeps the reported total
exact. The probe can enable trade, capital flows, migration, and one bounded
household-demand shock. Neighboring countries alternate between two modest
opening wage and price profiles, and each country has a distinct seed. The
shock reduces household demand by 10 percent for 30 days and ramps out over the
last 10 days.

The scenario is deliberately stable so that entity-scale cost is not confused
with population growth:

- 2.5 persons per household
- consumption and capital firms scale with population
- energy producers scale with population
- eight banks per economy
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
| Aggregate household portfolio claims, first cycle | 0.565 s | 4.82 GiB | -98.2% |
| Aggregate household portfolio claims, second cycle | 0.701 s | 5.05 GiB | -97.7% |
| M9 staged-world baseline, first cycle | 0.959 s | 6.61 GiB | -96.9% |
| M9 closed-single-country direct path, first cycle | 0.568 s | 5.36 GiB | -98.2% |
| M9 closed-single-country direct path, second cycle | 0.707 s | 5.59 GiB | -97.7% |
| M9 two-country open, serial, 60 days | 0.654 s | 4.68 GiB | -97.9% |
| M9 two-country open, 8-worker limit, 60 days | 0.394 s | 4.81 GiB | -98.7% |
| M9 eight-country open, 8 workers, 60 days | 0.199 s | 4.38 GiB | -99.4% |
| M9 eight-country open with shock, 8 workers, 60 days | 0.190 s | 4.20 GiB | -99.4% |

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

The pre-aggregation result comes from model-preserving algorithm and data-layout
changes plus one documented scheduling rule:

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

The final tail-latency checkpoint deliberately simplifies one game rule. A
household now has one beneficial claim set for its complete securities
portfolio, rather than a separate person-level claim set for every stock and
bond position. Estate valuation still uses the live market value of every
security in the portfolio, and the portfolio claim still transfers to heirs.
The model no longer preserves a distinct internal ownership history for each
security acquired by the same household. This changes the household-level legal
abstraction, but not security balances, market clearing, prices, household net
worth, or estate valuation. When a last-member estate merges into a household
that already has a portfolio, the inherited securities adopt the destination
household's existing internal portfolio-share schedule. A destination without a
portfolio keeps the inherited schedule.

The aggregate-portfolio probe uses schema `m9-scale-probe-v4` and scenario
`static-population-aggregate-portfolio-v3`. Genesis takes approximately 8.21
seconds. Across days 1 through 30, median daily latency is 0.565 seconds, p95 is
0.806 seconds, and the maximum is 0.870 seconds. Across days 31 through 60,
median daily latency is 0.701 seconds, p95 is 0.803 seconds, and the maximum is
0.843 seconds. All 60 measured days are below one second.

At the end of the first cycle, 5,748,680 active security lots map to 2,000,000
active beneficial lots rather than 15,392,650. Peak RSS falls from 6.88 GiB to
4.82 GiB. At the end of the second cycle, 6,093,687 security lots still map to
2,000,000 beneficial lots. Peak RSS falls from 6.71 GiB to 5.05 GiB. Root-state
digests remain
`5f23e4becd18f3e3d29595a0c12127682b0340c2cfcf0ef736e017e8cc7ad73f`
for day 30 and
`5b95c26e27d6015df5274f76888f876074e99007d8e84f17cafcb27bffc791d5`
for day 60, matching the per-security-claim runs.

The retained full 8-worker acceptance suite passes all 49 tests, including C and
Python bindings, checkpoint round trips, semantic panels, extension seams, and
fault-injection coverage. Further work should reduce the approximately 5.05 GiB
day-60 peak RSS and remove the remaining full tick-staging copies before
treating M9 multi-economy or highly dynamic population workloads as complete.

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

## 8. One-million-person results

Direct M8 execution now demonstrates the complete 60-day target rather than
projecting it:

- approximately 8.21 seconds for one-time genesis
- 0.565-second median, 0.806-second p95, and 0.870-second maximum on days 1-30
- 0.701-second median, 0.803-second p95, and 0.843-second maximum on days 31-60
- all 60 measured days below one second
- 4.82 GiB peak RSS at day 30 and 5.05 GiB at day 60

The measured M9 baseline confirms the cost. In the same one-country closed-world
scenario, days 1 through 30 have a 0.959-second median, 1.454-second p95, and
1.460-second maximum, with 6.61 GiB peak RSS. The world wrapper is therefore the
remaining reason that the latest container misses the tail target.

For one country with trade disabled, no shocks, and no fault injection, M9 can
use the already-transactional M8 prepare/validate/commit path directly. No
cross-country state can change in this configuration, so copying and validating
the complete M9 world adds no rollback protection. At this earlier checkpoint,
multicountry, shock, and fault-injection advances retained the original
staged-world transaction; Section 8.1 records the later multicountry result.

After the direct path, the closed single-country M9 result is:

- approximately 8.30 seconds for one-time genesis
- 0.568-second median, 0.838-second p95, and 0.870-second maximum on days 1-30
- 0.707-second median, 0.803-second p95, and 0.853-second maximum on days 31-60
- all 60 measured days below one second
- 5.36 GiB peak RSS at day 30 and 5.59 GiB at day 60

The day-30 M9 digest remains `6935004978910860284` before and after the direct
path. The day-60 digest is `15096525921303579400`. A dedicated equivalence test
also compares the direct path with the staged path using an inactive future
shock and requires identical domestic checkpoints, world metrics, and digests.

### 8.1 Open multicountry result

The original exact one-million-person two-country open baseline took 3.318
seconds at the median over its first three days, peaked at 3.382 seconds, and
used 3.29 GiB. It deep-copied the complete world and then repeated full root
audits and state hashing during post-domestic trade settlement.

Normal multicountry advancement now moves the current world into its staging
object instead of deep-copying it. This changes the default failure contract:
if an unexpected internal error occurs, the partially advanced staged world is
restored rather than the complete pre-day world. Callers that need strong
rollback can set `require_world_rollback`; explicit M9 fault injection and
per-country override paths retain deep-copy rollback automatically.

Each successful M8 domestic advance already validates its staged projection.
The M9 close therefore validates exchange rates, external contracts, shock
lifecycle state, pegs, and migration routes without rescanning every domestic
record. Explicit `M9World::validate` calls remain complete.

Trade settlement uses an explicit locally validated transaction commit. It
still checks command references, account status, overdrafts, reserve movement,
and posting and reserve conservation, and it retains mutation undo. It omits
the root-wide ownership audit and before/after SHA digests because the domestic
root was just audited and M9 controls the subsequent firm and posting
mutations. The default `SettlementTransaction::commit` contract remains a full
audit with both digests.

Transaction workspace reservation no longer computes a state digest merely to
grow scratch storage, and undo vectors reserve for actual mutations rather than
for every account, reserve position, and loan in the root.

With those serial changes, the exact one-million-person, two-country open run
over 60 days records:

- 4.72 seconds for one-time genesis
- 0.654-second median, 0.805-second p95, and 0.863-second maximum
- all 60 measured days below one second
- 4.68 GiB peak RSS
- deterministic digest `8685033631341402429`

The independent domestic economies then advance in parallel after deterministic
trade reservation. Workers only mutate their assigned economy and result slot;
all world clearing and commit order remains deterministic. A one-worker and an
eight-worker run are required to produce identical checkpoints and digests.
The two-country run can use only two workers and improves to:

- 0.394-second median, 0.502-second p95, and 0.594-second maximum
- 4.81 GiB peak RSS
- the same digest `8685033631341402429`

The full eight-worker result uses eight countries and exactly 1,000,000 total
persons:

| Scenario | Genesis | Median day | P95 day | Maximum day | Peak RSS | Digest |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| Open, no shock | 1.70 s | 0.199 s | 0.238 s | 0.249 s | 4.38 GiB | `8891068046243627764` |
| Open, 30-day demand shock | 1.66 s | 0.190 s | 0.233 s | 0.249 s | 4.20 GiB | `9292730278626412201` |

Both eight-country scenarios complete all 60 days below one second. The shock
case is slightly faster because lower demand reduces realized market work; it
is evidence that the shock path remains inside the budget, not that shocks are
generally performance-positive.

### 8.2 Numerical stability corrections

Large multicountry batches exposed two false rejections rather than economic
imbalances:

- Thousands of balanced reserve postings left a roughly
  `5e-15` aggregation residual. The reserve check now uses the greater of the
  root accounting tolerance and a scale-aware floating-point error bound.
- Fiscal settlement produced `-8.67e-19` after subtractive cancellation. M4 now
  treats negative values whose magnitude is below the existing economic epsilon
  as zero; materially negative and all non-finite transfers remain invalid.

These changes do not add money, remove money, or relax the final root
invariants. They align intermediate command validation with the precision
already used by the economic model.

## 9. Optimization order

Completed work includes quadratic genesis removal, compact ownership indexes,
incremental synchronization and validation, stable order bucketing, linear
security-index construction, staggered portfolio scheduling, aggregate
household portfolio claims, copy-free normal M9 staging, locally audited trade
settlement, and deterministic country-level parallelism.

The next measured order is:

1. Replace remaining full M6 and M7 tick-staging copies with chunked copy-on-write
   storage or mutation journals.
2. Rebuild public security indexes no more than once per mutation phase.
3. Profile dynamic population, firm entry and exit, active housing, and
   multi-economy workloads at one million persons.
4. Reduce the approximately 4.2-4.8 GiB day-60 peak RSS and bound history
   retention for long game sessions.
5. Extend deterministic parallelism inside a single large country only after
   phase read/write sets and memory-bandwidth limits are measured.

Country-level parallelism is now active because economies have disjoint domestic
state. Parallelism inside one economy still follows complexity and memory-layout
work so it does not multiply avoidable staging or synchronization.

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
target is no more than one second per M9 day. Closed, open multicountry, and
bounded shock-active static-population scenarios now meet it; new dynamic
workloads must pass independently before entering the claim.

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

Run the one-million-person eight-country open acceptance probe:

```bash
build/native/m9-release/native/macro_sim_m9_scale_probe \
  --mode m9 \
  --persons 1000000 \
  --economies 8 \
  --workers 8 \
  --world-mode open \
  --shocks none \
  --warmup-days 0 \
  --days 60 \
  --beneficial-ownership enabled
```

Run the same acceptance with the bounded demand shock:

```bash
build/native/m9-release/native/macro_sim_m9_scale_probe \
  --mode m9 \
  --persons 1000000 \
  --economies 8 \
  --workers 8 \
  --world-mode open \
  --shocks active \
  --warmup-days 0 \
  --days 60 \
  --beneficial-ownership enabled
```
