# C++ Engine M9 Execution Plan

Status: accepted locally and on hosted CI

Base: accepted M8 integration head `a5e6eee`

Target engine version: `0.9.0-m9`

## 1. Outcome

M9 moves the complete maintained multi-country frontier into the native engine:

- deterministic world orchestration over independent M8 domestic economies;
- trade, foreign exchange, capital positions, pegs, sanctions, and aggregate
  migration;
- world-owned external policy and materialized shock boundaries;
- exact checkpoint continuation and public C/Python interfaces;
- explicit complexity and thread-count determinism gates through 256 countries.

One native call advances a whole World. Python is not called per country,
transfer, route, order, firm, household, or person.

## 2. Source authority

The maintained authority is:

- `macro_sim/world/fx.py`;
- `macro_sim/world/trade.py`;
- `macro_sim/world/capital.py`;
- `macro_sim/world/migration.py`;
- `macro_sim/world/world.py`;
- `macro_sim/core/external_policy.py`;
- `macro_sim/shocks/spec.py`, `engine.py`, `registry.py`, `scenarios.py`, and
  `stochastic.py`;
- current world, capital, migration, shock, controller-capability, national
  accounts, and diagnostic tests.

Historical model labels are not authority. M9 preserves the latest playable
mechanisms and current policy ownership semantics.

## 3. Delivery sequence

### V9a: World and Trade/FX

Deliver:

- stable economy and currency IDs;
- normalized log exchange-rate vector and triangular bilateral rates;
- dealer currency accounts, explicit spread revenue, and valuation;
- per-importer source choice, inventory reservation, iceberg loss, tariff,
  quota, export subsidy, and capacity shocks;
- symmetric sanctions with unilateral ownership;
- deterministic barrier, settlement, validation, and publication phases;
- single-country inert equivalence with M8.

### V9b: Capital and Peg

Deliver:

- opening external principal and debtor-creditor arrears;
- factor-income accrual, partial settlement, pro-rata cure, and roll-forward;
- capital mobility, adjustment, controls, NFA target, and flow;
- per-pegger anchor, reserves, pressure, intact state, defense, and release;
- private/dealer and official FX gates;
- annual dealer-loss mutualization at the maintained 365-tick cadence.

### V9c: Migration and Shocks

Deliver:

- aggregate origin stock and one best-host route per origin;
- persistent real-wage signal, immigration/emigration caps, return flow,
  remittances, and both tax sides;
- canonical shock specs, targets, tape, lifecycle, overlap composition, and
  event stream;
- all eight registered shock kinds and packaged crisis scenarios;
- deterministic materialization into existing domestic M8 application points
  and M9 world channels.

## 4. Native world state

`M9World` owns:

- one complete M8 economy state per country;
- dense vectors for rates, dealer inventory, country aggregates, policy, and
  migration stocks;
- dense matrices for capital principal, arrears, and current settlement across
  the qualified `N <= 256` World range;
- one world tick, event counter, shock engine, and stable digest;
- reusable phase scratch with capacities excluded from semantic digests.

All cross-country references use stable economy IDs. World vectors are stored
in ascending economy-ID order. The M9 benchmark found no crossover that
justifies a second edge representation inside the supported range, so `256` is
both the measured dense threshold and the initial maximum country count. A
later extension beyond 256 must add deterministic sparse edges sorted by
`(origin, destination)` and requalify checkpoints and complexity.

## 5. Phase graph and atomicity

The M9 daily phase order is:

1. validate and materialize due external policies and shocks;
2. snapshot opening rates, positions, inventory, and causal aggregates;
3. accrue opening-position factor income;
4. choose trade sources and reserve export inventory;
5. publish domestic exogenous inputs and advance every M8 economy;
6. settle realized trade, tariffs, subsidies, remittances, and factor income;
7. update capital targets, positions, arrears, pegs, and dealer state;
8. run aggregate migration and form next-day domestic labor inputs;
9. validate every domestic and world invariant;
10. commit the world boundary, emit events, and publish metrics.

Validation and fault injection happen before the first irreversible cross-world
mutation. No-fail commit code applies only prevalidated commands. A failed
prepare releases every reservation. A failed world tick exposes the complete
old state.

## 6. Policy ownership

Each economy owns one `ExternalPolicyState`:

- tariff, import quota, and export subsidy;
- capital control and external-interest settlement fraction;
- sanctions imposed on other economies;
- immigration and emigration caps;
- inbound and outward remittance taxes and guest-worker return;
- FX regime, peg anchor, reserve scale, and defense parameters.

At a boundary the World validates the entire proposed policy vector, including
cross-country constraints, then commits it atomically. An economy can remove
only its own sanction claim. A sanction is effective while either side owns a
claim. A peg does not require anchor consent. P0 supports at most one pegger;
the anchor must float. The runtime layout is per-pegger so this restriction can
be relaxed without a checkpoint migration.

## 7. Trade and FX invariants

Every tick proves:

- every reserved source unit is sold once, returned once, or consumed once as
  iceberg loss;
- import delivered volume plus iceberg loss equals source withdrawal;
- gross import value decomposes into basic value, tariff, spread, and declared
  subsidy legs;
- dealer flow equals only declared spread revenue before revaluation;
- exchange rates remain finite, positive, normalized, and triangular;
- sanctions and quotas admit no forbidden volume;
- a failed barrier restores all source inventories and reservation indexes.

## 8. Capital and Peg invariants

Every tick proves:

- principal and arrears are finite and nonnegative in their contract currency;
- factor income is computed from opening principal only;
- cash paid plus new arrears equals due income plus cured arrears;
- creditor allocation is deterministic and pro-rata within tolerance;
- aggregate NFA, dealer inventory, official reserves, and valuation reconcile;
- reserve defense cannot spend more than available reserves;
- released peg pressure enters the float path exactly once.

## 9. Migration invariants

Migration remains aggregate for parity. It does not move native M7 persons or
households. Every tick proves:

- migrant stocks are finite, nonnegative, and bounded by origin/host policy;
- each origin selects at most one host in stable order;
- returns cannot exceed opening migrant stock;
- remittance collection, both tax legs, conversion, and payout conserve value;
- sanctions prohibit new routes and financial flows.

## 10. Shock contract

Shock IDs are unique and stable. Numeric specs contain kind, target, start,
duration, shape, magnitude, optional sector, and deterministic ramp timing.
Materialization is pure for `(spec, world tick, economy ID, sector ID)`.
Overlaps compose in canonical shock-ID order. Checkpoints store specs plus
lifecycle state, never callable objects or host-language state. Player-facing
visibility, source, and narrative metadata belong to the M10 release envelope
and do not enter the M9 economic state.

## 11. Performance design

The World uses bulk contiguous vectors and one barrier per day. It never scans
persons or firms to compute world routing inputs; M8 publishes maintained
country aggregates. Candidate trade and migration edges are pruned by
sanctions, capacity, and positive-flow tests.

Benchmarks cover `N=1/2/4/8/16/64/256`, active coupling, checkpoint
continuation, and thread counts. The measured all-dense decision through the
initial 256-country maximum becomes a checked contract. Threading is permitted only
between independent domestic prepares; reduction and commit order remain
stable.

## 12. Public boundaries and checkpoints

M9 adds:

- C++ `M9World` create, update, advance, probe, checkpoint, restore, and clone;
- opaque C handles with versioned structs and caller-owned paged buffers;
- Python `WorldSession` bindings for coarse calls only;
- typed metrics for rates, trade, current account, capital, reserves,
  migration, shocks, and per-country M8 summaries;
- a structured checksum-protected M9 checkpoint with exact split-run
  continuation.

## 13. Acceptance gates

M9 is accepted only when:

- all M8 gates remain green;
- single-country World is semantically equal to the corresponding M8 session;
- two- and multi-country trade, dealer, NFA, peg, migration, and shock panels
  pass;
- fault injection proves reservation release and whole-world rollback;
- checkpoint split-run and fresh-process continuation are exact;
- thread counts produce identical digests and events;
- `N=2/4/8/16/64/256` benchmarks qualify the dense representation and its
  supported-range limit;
- release and sanitizer CTest pass;
- isolated C, Python wheel, and source artifacts consume M9;
- the full Python regression passes with eight workers;
- macOS, Linux, and Windows CI are green before integration promotion.
