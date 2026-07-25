# C++ Engine M8 Acceptance

Status: accepted locally on macOS arm64; hosted promotion pending

Engine version: `0.8.0-m8`

## Scope

M8 adds the native domestic energy and housing frontier on top of the accepted
M7 population and labor economy:

- canonical energy firms, downstream energy inputs, household necessity
  demand, rationing, price caps, subsidies, excise, and strategic reserves;
- deprivation and fuel-poverty sensors with explicit causal lag;
- a canonical dwelling registry with stable identity, title lineage, owner,
  occupant, and collateral indexes;
- deterministic resale and rental markets;
- canonical M5 mortgage origination, servicing, payoff, write-off, collateral,
  foreclosure, and lender-loss integration;
- builder firms, work in progress, labor and energy inputs, permits, land fees,
  dwelling completion, minting, and listing;
- affordability anchors and lagged leaving-home and fertility feedback;
- death, estate, firm-exit, and bank-resolution housing cleanup;
- exact M8 checkpoint continuation, corruption rejection, and state digest;
- complete C ABI and Python views for the new runtime;
- installed C package, wheel, source-distribution, semantic, and performance
  gates.

The Python product remains the compatibility authority for capabilities beyond
the M8 frontier.

## Correctness gates

The following gates passed on 2026-07-25:

- full Python regression with eight workers and work stealing: 1,586 passed,
  11 skipped, four existing Gymnasium warnings;
- release CTest: 44 of 44 passed in 5.27 seconds;
- ASan and UBSan CTest, excluding Python-binding tests: 31 of 31 passed in
  29.33 seconds;
- focused M8 C ABI smoke;
- fresh-process M8 checkpoint continuation and digest equality;
- deterministic M8 semantic panel;
- independent installed CMake consumer;
- isolated wheel install, initialization, advancement, snapshot, checkpoint,
  and continuation;
- source-distribution content and path-safety smoke;
- M4-M8 contract checks, source locks, current-target check, CJK scan, and
  `git diff --check`.

The complete eight-worker Python regression finished in 54 minutes. The four
warnings concern infinite Gymnasium Box observation bounds and predate M8.

## Findings resolved during implementation

- M7 now exposes one typed extension boundary instead of requiring M8 to fork
  or duplicate the M4-M7 daily pipeline.
- The extension closes before beneficial-ownership synchronization, so
  same-day M8 mortgage origination and write-off are reflected in canonical
  beneficial claims.
- M5 bank closing capital now follows the full opening-capital, net-income,
  resolution-flow, and distribution roll-forward.
- Housing state copies its property registry only when a title, occupancy, or
  collateral mutation is staged.
- Property occupancy and owner-occupancy metrics are maintained incrementally.
  A quiet housing day uses constant-time registry validation and does not scan
  the dwelling stock.
- Active-listing uniqueness validation uses stable sorting instead of a
  quadratic pairwise scan.
- Monthly sale and rental lookup uses reusable stock-sized masks instead of
  dwelling-by-listing scans.
- Lower-frontier session advances explicitly reject an M8 session, preventing
  accidental execution that would omit the energy and housing extension.

## Performance gate

All figures below use a release build on the local macOS arm64 host. Each row
contains 60 measured days after 11 warm-up days.

| Panel | Persons | Median day | p95 day | Maximum allocations per day |
|---|---:|---:|---:|---:|
| Quiet energy and housing | 500 | 3.29 ms | 3.79 ms | 1,069 |
| Quiet energy and housing | 2,000 | 23.30 ms | 29.47 ms | 2,071 |
| Energy only | 2,000 | 23.61 ms | 29.46 ms | 2,071 |
| Active weekly housing market | 500 | 3.29 ms | 3.78 ms | 4,119 |

The 2,000-person p95 was below the 120 ms platform budget. The normalized
500-to-2,000 entity scaling ratio was 1.77 against a maximum of 2.50.
Quiet housing cost 0.987 times the energy-only median in this run, against a
maximum overhead ratio of 1.20. The ratio below one is timing noise; the
important result is that static dwelling stock added no measurable daily scan
and no additional allocation. Scratch capacity remained stable.

These measurements are native engine latency. They are intentionally separate
from the 54-minute Python compatibility suite, whose wall time is dominated by
long tests that still execute the Python world.

## Atomicity and persistence

M8 stages energy and housing work through the M7 extension. Fallible work
finishes before canonical commit. Tests cover injected failures after energy
planning, after energy clearing, and before commit, as well as housing sale,
mortgage, rent, foreclosure, construction, lifecycle, and checkpoint failure
paths.

The M8 checkpoint embeds the exact M7 state and serializes all energy, property,
listing, mortgage, tenancy, builder, affordability, policy, input, and event
state under a versioned SHA-256 envelope. Restored sessions continue with
byte-identical deterministic digests.

## Public boundaries

The C ABI advertises `MACRO_SIM_CAPABILITY_M8_ENERGY_HOUSING` and exposes:

- default and custom M8 genesis;
- live energy and housing policy and exogenous-input updates;
- multi-day M8 advance and typed nested metrics;
- stable paged views for dwellings, listings, mortgages, tenancies, builders,
  and energy producers;
- digest and checkpoint save/load.

The Python extension exposes the complete M8 specification, policy, rules, and
input types; GIL-free genesis and advance; typed metric dictionaries; complete
M8 snapshots; and exact checkpoint continuation.

## Promotion rule

The M8 branch may be fast-forwarded into the V33 integration branch only after
the pushed M8 commit passes every required macOS, Linux, Windows, sanitizer,
performance, C package, wheel, and source-artifact job. The development branch
remains untouched.
