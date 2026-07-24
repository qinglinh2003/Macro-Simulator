# C++ Engine M3 Execution Plan (V33)

Status: executable plan  
Branch: `refactor/cpp-m3-v33`  
Frozen base: `m2-canonical-accounting-v33`  
Base commit: `86e5448a1b700ce0b587bdc5550ffb1f6c219e7d`  
Scope: reusable pure algorithms; no production Python phase is replaced in M3

## 1. Outcome

M3 builds the deterministic economic algorithm layer that M4 will compose into
the first complete native tick. It ports state-free planning, valuation, vital
rate, shock-read, and physical-market rules into `macro_sim_core`, and repairs
the two known matching hot paths before they become part of the native state
machine.

M3 is accepted only when:

1. every supported equation is a pure typed function with explicit inputs and
   output;
2. stochastic functions receive an explicit draw or named Philox stream;
3. shock reads are identity-preserving, target-aware, deterministic, and do not
   mutate a schedule;
4. all market output is represented by typed trades, allocations, and physical
   stock commands;
5. matching never oversells, self-trades, exceeds a buyer budget, or creates
   physical quantity;
6. the three matching protocols have deterministic fixtures and stochastic
   distribution evidence;
7. matching output is unchanged for every advertised worker count;
8. preferential selection does not rebuild all seller weights after each
   trade, and price-sorted selection sorts only once per clearing;
9. complexity measurements satisfy the frozen ratio envelopes;
10. M0-M2 evidence remains immutable and the existing Python suite stays green.

M3 does not attach these algorithms to `EngineSession::advance_ticks`, mutate
the M2 root, or publish native simulation output. That authority begins with the
M4 vertical slice.

## 2. Frozen inputs

M3 consumes, but never rewrites:

- tag `m2-canonical-accounting-v33`;
- all files under `schemas/m0`, `schemas/m1`, and `schemas/m2`;
- `schemas/m0/manifests/m4_v0_v1.yaml`;
- `macro_sim/behavior/planning.py`;
- `macro_sim/markets/matching.py`;
- `macro_sim/systems/valuation.py`;
- `macro_sim/systems/securities.py::bond_price`;
- `macro_sim/demographics/rates.py`;
- `macro_sim/shocks/{spec,registry,engine}.py`;
- M2 typed IDs, quantities, Philox streams, and accounting contracts.

Python remains the semantic oracle. Native/Python bit identity is required for
closed-form deterministic fixtures where both languages use the same operation
order. Otherwise the tolerance in `schemas/m3/equation_contract.json` applies.
Native replay with the same inputs and stream identity is exact.

## 3. Binding decisions

### 3.1 Pure behavior surface

The behavior library uses input and result records rather than agent objects.
It covers:

- demand and income expectation updates;
- linear and Cobb-Douglas production and inverse labor demand;
- capital service cost, capital service unit cost, and operating unit cost;
- inventory target and production planning;
- wage and price planning with an explicit Calvo draw;
- investment user cost and accelerator/Tobin-q investment planning;
- firm credit request, debt-service headroom, credit grant, and debt service;
- household consumption, contractual debt-service reservation, equity demand,
  and subsistence credit demand.

`diversify_mpc` is a genesis population draw and is deferred to M4 genesis. It
is not a per-tick equation. Invalid structural inputs return `Status`; economic
clamps that are part of the Python rule remain part of the result.

### 3.2 Valuation and vital rates

The valuation library covers floor-safe price return, discount-rate composition,
residual-income value, and fixed-coupon bond price. The vital-rate library
covers Gompertz-Makeham mortality integral, survival, normalized fertility,
and life expectancy. These are pure functions reused by M7; M3 does not build
the demographic state transition.

### 3.3 Shock overlay reads

M3 introduces an immutable `ShockOverlay` compiled from already validated
continuous shock entries. An entry contains:

- stable shock ID;
- channel;
- economy scope or broadcast;
- optional canonical sector scope;
- start, duration, and ramp parameters;
- magnitude.

The overlay provides `intensity_at` and `factor` only. Factors compose in stable
shock-ID order as `product(1 - magnitude * intensity)`, default to exactly
`1.0`, apply `consumption` scope to `necessity` and `luxury`, and reject a
non-finite or non-positive result. Scheduling, announcement visibility, event
hashes, one-shot capital destruction, and capability validation remain stateful
M8 work.

### 3.4 Typed physical market contract

The market kernel consumes:

- `BuyOrder {order_id, buyer_account, demand, budget}`;
- `SellOffer {offer_id, seller_account, stock, price, attractiveness}`;
- `MarketConfig {protocol, sample_size, beta, price_elasticity, rng key,
  counter, worker_count}`.

It returns:

- `Trade` records with quantity, quote, and money value;
- buyer `Allocation` totals and remainders;
- seller `PhysicalStockCommand` deltas and sold totals;
- aggregate diagnostics and algorithm counters.

The kernel never moves money. M4 converts accepted trades into one M2
transaction and applies stock commands inside the same tick transaction.

Inputs must be finite and nonnegative, prices must be positive for live offers,
IDs must be valid and unique within their domain, and `worker_count` must be one
of `1, 2, 4, 8`. Buyer ordering, sample selection, and tie breaking use named
Philox draws. The stable serial commit order is authoritative; worker count
controls only partitionable preparation, so output is identical across all
supported counts.

### 3.5 Matching algorithms

- **Sampled:** maintains a swap-pop live seller vector. Each attempt samples at
  most `m` live sellers and chooses the cheapest eligible sampled offer.
- **Preferential:** builds seller weights once and stores them in a Fenwick
  tree. Selection and exhausted-seller removal are `O(log S)`; self-trade
  exclusion is handled without rebuilding the tree.
- **Price sorted:** assigns deterministic Philox tie keys and stable-sorts the
  live sellers once by `(price, tie_key, offer_id)`. Every buyer walks the same
  ordered index while skipping exhausted and self offers.

The declared clearing bounds are:

```text
sampled:      O(B log B + T * min(m, S))
preferential: O(B log B + S + T log S)
price_sorted: O(B log B + S log S + T + skipped)
```

`B` is buyer count, `S` seller count, and `T` committed trade count.

## 4. Work packages

### M3-01 — Contracts and fixtures

Deliver this plan, gate manifest, equation inventory, market contract, exact
fixtures, stochastic envelopes, performance budgets, and predecessor locks.

Exit:

- every roadmap item maps to one implementation/test owner;
- M0-M2 tracked evidence differs by zero bytes from the M2 tag;
- source and commit-subject deltas contain no CJK text.

### M3-02 — Behavior, valuation, and vital-rate functions

Deliver typed headers and implementations with no Python, global mutable state,
agent object, allocation, or hidden RNG dependency.

Exit:

- exact fixtures cover normal, boundary, clamped, sticky, and invalid cases;
- randomized Python differential cases pass the numeric contract;
- all returned finite quantities satisfy their declared domain.

### M3-03 — Shock overlay

Deliver immutable entries, canonical target matching, ramp intensity, stable
multiplicative composition, and a batch read surface.

Exit:

- identity, broadcast, economy, sector alias, pulse, permanent, ramp, stacking,
  favorable, and invalid-composition fixtures pass;
- input order does not change factor results;
- reads do not allocate after overlay construction.

### M3-04 — Typed matching kernel

Deliver validation, the three protocols, typed output, deterministic Philox
stream use, Fenwick selection, one-time price sorting, and algorithm counters.

Exit:

- deterministic fixtures pass for every rule;
- properties prove budget, demand, stock, value, conservation, no-self-trade,
  and stable ordering;
- identical inputs produce byte-equivalent result fields for worker counts
  `1, 2, 4, 8`.

### M3-05 — Stochastic and differential evidence

Deliver native distribution tests plus a nanobind batch adapter used only by
tests and M4 development.

Exit:

- uniform sampled selection and configured preferential shares fit frozen
  statistical envelopes;
- price ties show no fixed seller advantage over the seed panel;
- Python and native deterministic equations and market invariants agree.

### M3-06 — Complexity and packaging

Deliver operation-count assertions, release timing benchmarks, installed-header
smokes, wheel/sdist smokes, and source-artifact checks.

Exit:

- doubling-ratio envelopes in `schemas/m3/performance_budget.json` pass;
- algorithm counters prove one price sort and one preferential weight build;
- macOS, Linux, and Windows build with warnings-as-errors;
- ASan/UBSan are clean on macOS and Linux.

### M3-07 — Freeze and promotion

Deliver final contract/source/vendor locks, full Python regression evidence, a
green cross-platform workflow, annotated tag `m3-pure-algorithms-v33`, and a
fast-forward of `refactor/cpp-engine-v33`.

Exit:

- all M3 gates pass from a clean checkout;
- `dev` remains unchanged;
- the M3 branch, V33 branch, and annotated tag peel to the same accepted commit.

## 5. Gate sequence

1. contract/predecessor/English-delta checks;
2. native debug build and tests;
3. native release build and tests;
4. ASan/UBSan build and tests;
5. Python differential and randomized properties;
6. distribution and thread-invariance panels;
7. complexity and timing benchmark;
8. installed CMake package, wheel, and source distribution smokes;
9. full Python suite;
10. final lock and clean-tree audit;
11. push, cross-platform CI, V33 fast-forward, tag, and remote verification.

## 6. Explicit deferrals to M4

M3 intentionally does not:

- add a native tick scheduler or phase barrier;
- read/write the M2 household and firm stores during an economic phase;
- convert a trade into an accounting transaction;
- implement labor matching, production settlement, fiscal settlement, or
  national accounts;
- expose a production backend selector;
- claim end-to-end speedup for a full simulation day.

Those are the acceptance boundary of M4 V0/V1.
