# C++ Engine M8 Execution Plan

Status: implemented and accepted locally

Base: accepted M7 integration head

Target engine version: `0.8.0-m8`

## 1. Outcome

M8 moves the remaining domestic energy and housing capabilities into the
native engine without narrowing the current playable model. Delivery is split
into two independently gated tracks in dependency order:

- V8a: energy producers, intermediate and household energy demand, rationing,
  strategic reserves, fiscal flows, deprivation, and policy/shock channels;
- V8b: dwellings, resale, mortgages and collateral, rent, construction,
  affordability, fiscal flows, and policy/shock channels.

M8 extends the accepted M7 session in one native call per simulated day. It
does not call Python inside a tick and does not cross the language boundary per
person, household, firm, dwelling, order, loan, or tenancy.

## 2. Source authority

The migration preserves the maintained behavior represented by:

- `macro_sim/systems/energy.py`;
- `macro_sim/systems/deprivation.py`;
- `macro_sim/housing/registry.py`;
- `macro_sim/housing/market.py`;
- `macro_sim/housing/mortgage.py`;
- `macro_sim/housing/rental.py`;
- `macro_sim/housing/construction.py`;
- `macro_sim/housing/affordability.py`;
- the current policy registry and shock-channel contracts;
- the current death, estate, household lifecycle, firm failure, bank failure,
  fiscal, loan, and national-accounting integrations.

Historical configuration labels are not an engine boundary. Native contracts
are derived from the latest maintained implementation, tests, policy schema,
and playable capability set.

## 3. M7 extension boundary

M8 first adds a public `M7TickExtension` and
`advance_m7_ticks_extended(...)`. The extension receives typed M4-M7 runtime
and scratch references at six boundaries:

1. `prepare_tick`, after M7 has copied opening population and labor state;
2. `before_labor`, after real-economy planning and before persistent matching;
3. `after_labor`, after persistent labor has staged effective labor but before
   production and goods clearing;
4. `close_day`, after base financial closure and M7 lifecycle staging;
5. `validate`, after M4-M7 validation and before any canonical mutation;
6. `commit`, after M7 canonical commit.

The M7 extension remains optional and preserves the current public M7 behavior
when absent. Nested commit callbacks are no-fail and execute only prevalidated
commands. Any fallible energy, housing, accounting, ownership, collateral, or
index work completes before the first canonical mutation.

## 4. V8a energy domain

### 4.1 Canonical stores

`EnergyRuntime` owns:

- energy-producer components keyed by stable `FirmId`;
- downstream energy-input inventory and weighted-average cost components;
- current energy-market price and slow reference-price state;
- strategic reserve quantity and weighted-average cost;
- household and industry demand, allocation, spending, and unmet-demand
  vectors;
- deprivation anchors and sticky household/person deprivation state;
- deterministic event counters and the latest typed energy metrics.

Energy firms remain canonical firms in the M4-M7 economy. `FirmSector` and
sector indexes distinguish consumption, capital, energy, and later builder
firms so that existing sector loops cannot silently treat every firm as a
consumption producer.

### 4.2 Daily phases

The V8a phase order is:

1. apply validated policy and materialized shock inputs;
2. compute capacity-constrained energy supply after labor assignment;
3. form household necessity and downstream intermediate demand;
4. add strategic-reserve buy or sell orders within target and flow limits;
5. clear the energy market under the selected rationing rule;
6. settle firm revenue, household subsidy, excise, and reserve cash flows;
7. update physical inventories and weighted-average costs;
8. expose energy input to downstream production;
9. update price, unmet demand, firm expectations, and deprivation sensors;
10. validate physical-resource, cash, inventory, and fiscal conservation.

Supported rationing rules are market, proportional, household first, and
industry first. A price cap changes the effective transaction price and any
enabled producer compensation without creating energy or cash. Household
demand is deposit-capped. Strategic-reserve sales cannot exceed stock and
purchases cannot exceed the configured target or public cash.

### 4.3 Policy and shock boundary

The native policy block covers current energy taxes, subsidies, price cap,
compensation, reserve target and flow, necessity demand, and rationing choices.
The native exogenous-input block accepts materialized capacity, productivity,
labor-availability, supply, demand, and price-reference shocks. M9 will own the
world-level shock tape and scenario scheduler; M8 owns the domestic typed
application points and their rollback semantics.

### 4.4 Deprivation

Deprivation is an observation-only causal sensor. Anchors are established only
after their configured burn-in. Household consumption and energy coverage are
projected to current members by stable membership, and boundary classification
is sticky. The sensor may publish mortality and welfare multipliers for a
later day but cannot alter a phase that has already committed.

## 5. V8b housing domain

### 5.1 Property authority

`PropertyRegistry` is the sole authority for dwellings and title. Every
dwelling has:

- stable `DwellingId`;
- exactly one owner, which may be a household, firm, bank, estate, or public
  authority;
- quality, size, location, age, occupancy, and market-state attributes;
- at most one active collateral reference;
- a complete mint and title-transfer event lineage.

Housing stock grows only through an explicit validated mint command. Sale,
inheritance, foreclosure, firm or bank failure, and estate settlement transfer
existing title; they never manufacture or duplicate a dwelling.

### 5.2 Resale market

The deterministic property market supports monthly listing and matching,
posted asks, forced-sale discounts, ask decay, buyer reservation prices,
search limits, liquidity buffers, transfer duty, cash purchases, and mortgage
financing. Stable order and stable IDs resolve all ties.

A sale is one atomic command bundle:

1. validate title, listing, buyer eligibility, and occupancy;
2. underwrite and originate any canonical loan;
3. transfer deposits, taxes, fees, and proceeds;
4. transfer title and collateral;
5. update occupancy, beneficial claims, and market records.

Partial sales are impossible. A failed bundle leaves state, indexes, counters,
and cash unchanged.

### 5.3 Mortgage and collateral

The M5 canonical loan ledger is the only authority for principal, rate,
amortization, arrears, write-off, and lender exposure. `MortgageBook` is a
secured-loan projection containing borrower household, lender bank,
collateral dwelling, underwriting data, and lifecycle state.

Underwriting enforces loan-to-value, debt-service-to-income stress, bank risk
weight, capital, liquidity, and borrower constraints. Foreclosure validates
arrears and distress, writes off the canonical loan exactly once, records the
bank loss, transfers title to the lender, clears occupancy when required, and
creates one forced listing. Bank failure preserves or transfers valid
collateral references rather than orphaning them.

### 5.4 Rental market

`RentalBook` owns persistent tenancy records, daily rent obligations, arrears,
eviction state, and monthly matching indexes. Rent settlement is deposit
capped and produces named paid and unpaid flows. Eviction, owner occupation,
sale, death, household closure, and dwelling destruction terminate or transfer
a tenancy exactly once.

Imputed owner-occupier rent is a metric only. It never posts cash or ledger
entries.

### 5.5 Construction

Builder firms are canonical firms with builder components and work-in-progress
records. Construction validates permits, land and public fees, labor, capital
goods, energy inputs, cash, completion, and the final mint command. A completed
dwelling is minted once, titled to the builder, and listed or retained
according to the maintained rule. Builder failure resolves work in progress
without creating unearned stock.

### 5.6 Affordability and lifecycle integration

Affordability publishes price-to-income, rent burden, ownership, vacancy,
construction, and distress measures after the configured burn-in and anchor.
It may emit next-day leaving-home and fertility multipliers, never same-day
retroactive effects.

Death and estate settlement transfer title and secured liabilities through
the M7 estate command. Marriage, divorce, household merge or split, and leaving
home update occupancy and beneficial claims without duplicating title.
Household retirement is rejected while unresolved housing commands remain.

## 6. Accounting and invariants

Every V8 tick validates:

- energy source equals industry, household, reserve, and residual uses;
- all energy quantities, inventories, capacities, and prices are finite and
  nonnegative;
- energy firm, household, Treasury, tax, subsidy, and reserve cash flows
  conserve through the canonical transaction;
- every dwelling has one valid title and every title index resolves back to
  the same dwelling;
- stock changes equal validated mint commands net of explicit destruction;
- every occupied dwelling and tenancy references live compatible entities;
- each active mortgage references one canonical live loan, one borrower, one
  lender, and one collateral dwelling;
- canonical loan principal equals the secured projection within accounting
  tolerance;
- sale, rent, tax, construction, foreclosure, and estate flows conserve cash;
- no retired entity remains in an active listing, tenancy, collateral, or
  ownership index.

Invariant failures identify the domain, stable entity ID, tick, and expected
relationship. No reconciliation or repair pass is permitted in production.

## 7. Genesis

`M8SimulationSpec` extends `M7SimulationSpec` with energy and housing blocks.
Genesis deterministically:

- creates energy and builder firms in the canonical firm set;
- initializes capacity, input inventories, strategic reserves, and price
  anchors;
- mints the configured initial dwelling stock;
- assigns exactly one title per dwelling;
- forms owner occupancy, rental supply, tenancy, and initial mortgages;
- establishes collateral and beneficial ownership projections;
- rejects impossible capability combinations before allocation.

Person count remains the user-facing population scale. Household formation is
owned by M7, while firm and dwelling counts are derived from the selected
profile and configured ratios unless explicitly overridden.

## 8. Atomicity and determinism

M8 stages all mutable state in reusable scratch storage and uses the nested M7
prepare, validate, and no-fail commit protocol. Fault injection covers energy
clearing, fiscal settlement, sale, mortgage origination, rent, foreclosure,
construction mint, title transfer, lifecycle interaction, validation, and
publication boundaries.

Random streams are counter based and keyed by stable entity IDs and event
ordinals. Thread count, dense compaction, allocation capacity, unrelated entity
insertion, and checkpoint continuation cannot alter results. Stable digests
include canonical records and event/RNG counters while excluding addresses and
scratch capacity.

## 9. Checkpoint and public boundaries

The M8 checkpoint embeds the exact M7 checkpoint and adds versioned energy,
property, mortgage, rental, construction, affordability, policy, input, index,
and counter state with SHA-256 integrity. Load rejects corruption, truncation,
trailing bytes, unsupported versions, duplicate title, invalid collateral,
orphan tenancy, and cross-domain reference errors.

The C ABI and Python binding expose:

- M8 capability discovery, genesis rules, live policy/input update, and
  multi-day advance;
- energy, deprivation, housing, mortgage, rental, and construction metrics;
- paged stable-ID views of producers, inventories, dwellings, listings,
  mortgages, tenancies, and builders;
- stable digest and checkpoint save/load.

Bindings release the GIL for M8 genesis and advance. Snapshot conversion keeps
the GIL while materializing Python objects. No public view leaks dense indexes
or native addresses.

## 10. Performance design

Ordinary daily work scales with active producers, demanding households,
downstream firms, active listings, buyers, mortgages, tenancies, and builders:

- no household-by-dwelling or firm-by-dwelling scans;
- no dwelling-by-loan collateral scans;
- no bank-by-mortgage underwriting scans;
- no person scan for household energy or housing aggregation;
- owner, occupant, listing, collateral, tenancy, and firm-sector indexes are
  maintained incrementally;
- monthly work is gated by cadence and active sets;
- matching uses bounded search and reusable sorted/indexed buffers;
- static coefficients and reserve capacity are prepared outside hot loops;
- unchanged topology performs no steady-state heap allocation.

V8 performance gates cover:

1. energy daily scaling at doubled households and firms;
2. constrained-supply rationing at doubled active orders;
3. housing quiet-day cost with large inactive stock;
4. monthly resale matching at doubled listings and buyers;
5. mortgage/rental servicing at doubled active contracts;
6. construction and title-index mutation;
7. M7 compatibility budgets and full-feature native day P1 trajectory.

Hosted budgets are frozen from release-runner calibration before promotion.
Any superlinear gate requires an explicit algorithm review rather than a wider
threshold.

## 11. Acceptance corpus

V8a acceptance includes:

- capacity-constrained production and intermediate inventory;
- household deposit cap and necessity demand;
- all rationing rules and deterministic ties;
- excise, subsidy, cap, compensation, and reserve buy/sell flows;
- strategic-reserve target, flow, stock, and average-cost bounds;
- price and unmet-demand expectation feedback;
- deprivation burn-in, sticky boundary, membership projection, and lag;
- resource and cash conservation under materialized shocks;
- checkpoint continuation, fault rollback, and long seed panels.

V8b acceptance includes:

- one-title and mint-only stock invariants;
- cash and mortgage sale bundles;
- underwriting limit and bank-capacity rejection;
- canonical principal, floating rate, amortization, and payoff;
- foreclosure, write-off, bank loss, title transfer, and forced listing;
- daily rent, arrears, eviction, vacancy, and monthly matching;
- construction inputs, fees, completion, mint, listing, and builder failure;
- property and transfer taxes;
- affordability burn-in and causal feedback;
- death, estate, marriage, divorce, leaving-home, firm exit, and bank failure
  interaction panels;
- checkpoint corruption, deterministic replay, and every fault boundary.

The full M4-M7 native acceptance suite and complete Python oracle regression
remain required. Full Python regression uses eight workers with work stealing.

## 12. Packaging and CI

M8 updates:

- CMake debug, release, sanitizer, fuzz, and benchmark presets;
- installed C consumer smoke;
- wheel and source-distribution smoke;
- macOS, Linux, and Windows release jobs;
- macOS and Linux ASan/UBSan jobs;
- M7 compatibility performance gates;
- V8a energy and V8b housing performance gates.

The branch may be fast-forwarded into the V33 integration branch only when the
same pushed commit passes every required hosted job. The development branch
remains untouched.

## 13. Commit sequence

1. freeze this execution plan;
2. add and test the nested M7 extension boundary;
3. add energy stores, sector indexes, specifications, and genesis;
4. integrate production, demand, clearing, settlement, reserve, and
   deprivation phases;
5. pass and commit the V8a acceptance and performance gates;
6. add property authority, title indexes, specifications, and genesis;
7. integrate resale, mortgage, collateral, rental, and fiscal flows;
8. integrate construction, affordability, lifecycle, firm, and bank failure;
9. pass and commit the V8b acceptance and performance gates;
10. add checkpoint, digest, C ABI, binding, package, and artifact boundaries;
11. run the complete native and eight-worker Python regressions;
12. publish the M8 acceptance record;
13. push, pass cross-platform CI, fast-forward, tag, and continue to M9.
