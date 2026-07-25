# C++ Engine M7 Execution Plan

Status: implementation baseline

Base: accepted M6 integration head

Target engine version: `0.7.0-m7`

## 1. Outcome

M7 moves the population frontier into the native engine without reducing the
feature set of the current playable model. The milestone is split into two
independently gated slices:

- V7a: persons, household membership, beneficial ownership, death, birth,
  estates, and inheritance;
- V7b: relationships, unions, household lifecycle, family transfers,
  persistent jobs, suspensions, second jobs, participation, job guarantee,
  labor accounting, and population/labor sensors.

Python remains the authority for later domains. M7 extends the accepted M6
session in one native call per simulated day; it never crosses the language
boundary per person, household, job, or transfer.

## 2. Source authority

The migration must preserve the maintained behavior represented by:

- `macro_sim/demographics/agents.py`;
- `macro_sim/demographics/kernel.py`;
- `macro_sim/demographics/rates.py`;
- `macro_sim/demographics/relationships.py`;
- `macro_sim/demographics/social.py`;
- `macro_sim/demographics/union.py`;
- `macro_sim/demographics/lifecycle_households.py`;
- `macro_sim/demographics/estate.py`;
- `macro_sim/demographics/inheritance.py`;
- `macro_sim/demographics/marriage_economics.py`;
- `macro_sim/demographics/economic_state.py`;
- `macro_sim/demographics/macro_signal.py`;
- `macro_sim/demographics/stratification.py`;
- `macro_sim/labor/persistent.py`;
- `macro_sim/labor/accounting.py`;
- `macro_sim/systems/family.py`.

The native design replaces the Python bridge and duplicated financial mirrors
with references to the canonical M2-M6 accounts, securities, loans, jobs, and
ownership lots.

## 3. V7a canonical stores

### 3.1 Person store

`PersonStore` uses stable `PersonId` values, a dense alive view, and a cold
archive. A person record contains:

- stable identity and sex;
- birth day and current completed age;
- alive flag and death day;
- mother, father, partner, and guardian references;
- current household reference;
- union and lifecycle timestamps;
- permanent efficiency and participation state;
- canonical financial owner reference.

Removal is two-stage. Death removes the ID from the alive dense view
immediately, while the archived record remains addressable for lineage,
checkpoint, diagnostics, and replay. Slot reuse must not alter stable IDs.

### 3.2 Household membership

`HouseholdMembershipBook` is the sole authority for person-to-household
membership. It maintains:

- one current household per alive person;
- ordered member rows per household;
- adult, dependent, and guardian indexes;
- household projection counts and labor-supply weights.

Membership changes are staged commands committed atomically with financial
transfers. There is no periodic reconciliation or repair pass.

### 3.3 Beneficial ownership

Persons become beneficial owners over the existing generic ownership lots.
Household operating accounts remain settlement accounts, while
`BeneficialOwnershipBook` records each member's claim on:

- household cash;
- security lots;
- debt responsibility;
- later property and mortgage interests.

For every household and asset class, person claims must sum to the canonical
household position within the accounting tolerance.

### 3.4 Population and estates

V7a provides deterministic daily phases for:

1. age/calendar roll-forward;
2. mortality hazards;
3. estate suspense creation;
4. job and relationship detachment;
5. heir selection;
6. cash, security, loan, and beneficial-lot transfer;
7. estate tax and residual public transfer;
8. births and new membership.

Death settlement is exactly once. Every migrated account, security lot, loan
responsibility, job, relationship, and estate record carries an explicit
resolved state or terminal event ID.

## 4. V7b social and labor stores

### 4.1 Relationship and union book

`RelationshipBook` stores symmetric partner links, parent-child links,
guardianship, marriage contracts, and union history. It supports:

- marriage;
- divorce;
- widowhood;
- guardianship repair;
- leaving home;
- household merge and split.

Candidate generation uses indexed age/sex/eligibility buckets. Exact matching
preserves the current score, stable tie ordering, greedy person iteration, and
match sequence. Approximate matching is not the default.

### 4.2 Employment book

`EmploymentBook` is the sole authority for persistent private employment. It
contains:

- primary and optional second job per person;
- firm rosters ordered by hire day and stable person ID;
- suspension and recall rights;
- wage, hours, efficiency, and hire anniversary;
- vacancy age and smoothed target per firm;
- indexed person and firm lookup.

Daily labor phases preserve the maintained ordering:

1. death and age exits;
2. churn and participation exits;
3. demand-gap layoffs;
4. cash-crunch suspensions or layoffs;
5. recalls;
6. frictional hiring;
7. job-ladder and second-job matching;
8. wage review and settlement;
9. job guarantee and stock/flow accounting.

Large-employer roster mutations must be indexed or swap/erase bounded. The
engine must not scan every person for every firm.

### 4.3 Labor accounting

`LaborAccounts` records the E/U/S/JG/OLF partition, private FTE and heads,
vacancies, underemployment, second jobs, and cumulative named flows.

Hard invariants run every day:

- `E + U + S + JG == labor_supply`;
- alive working-age persons partition exactly once;
- private FTE does not exceed employed capacity;
- roster, person-job, and suspension indexes agree;
- stock changes equal named head and FTE flows;
- firm roster effective labor equals the real-economy labor input.

### 4.4 Sensors

M7 publishes typed population and labor sensors for later phases:

- population, births, deaths, and natural growth;
- age structure and dependency ratio;
- household count and mean size;
- participation, employment, unemployment, suspension, and job guarantee;
- vacancies, underemployment, hires, separations, and job-to-job moves;
- labor efficiency and wage distribution;
- wealth strata and household/person projection error.

Sensors read committed state and never feed a same-day phase retroactively.

## 5. Genesis

M7 genesis extends `M6SimulationSpec` with a population specification:

- initial person count;
- start calendar day;
- age and sex distribution parameters;
- working, retirement, fertility, and maximum ages;
- household matching profile;
- relationship and union capability flags;
- persistent labor capability flags;
- vital-rate and labor-rule blocks.

Households are formed by the genesis matching algorithm. The person count is
the user-facing scale; household count is derived. M6 household financial
components are mapped onto generated households deterministically, and the
mapping is included in the genesis digest.

Invalid capability combinations are rejected before allocation. Examples
include second jobs without fractional hours, social dynamics without
relationships, and estates without beneficial ownership.

## 6. Phase integration and rollback

M7 is an `M6TickExtension`. All M7 work is staged in reusable scratch storage.
Persistent state is changed only after:

- M4-M6 validation succeeds;
- V7a and V7b invariants succeed;
- accounting and ownership transactions commit;
- optional fault injection has not fired.

An error restores the exact opening M4-M7 runtime, tick, RNG counters, indexes,
and event counters. Fault-injection tests cover every new commit boundary.

## 7. Determinism

M7 uses counter-based streams keyed by stable IDs and event ordinals for:

- mortality;
- fertility;
- sex at birth;
- marriage and divorce;
- leaving home;
- churn and participation;
- search contacts and job ladder;
- efficiency draws.

Thread count, dense compaction, and unrelated entity insertion must not change
an entity's draw. Stable digests include persistent records and RNG counters,
but exclude capacities and scratch addresses.

## 8. Checkpoint and public boundaries

The M7 checkpoint embeds the exact M6 checkpoint and adds versioned M7 state,
indexes that cannot be derived unambiguously, event counters, and SHA-256
integrity. Load rejects corruption, truncation, trailing bytes, unsupported
versions, and invalid cross-domain references.

The C ABI and Python binding expose:

- M7 capability discovery;
- genesis, policy/rules update, and multi-day advance;
- population and labor metrics;
- paged person, household-membership, relationship, estate, and job views;
- stable digest and checkpoint save/load.

Bindings release the GIL during genesis, advance, checkpoint, and restore.
Paged views have explicit total count, offset, capacity, and written count.

## 9. Performance design

Ordinary daily cost must scale with alive persons, active jobs, and changed
relationships:

- no household-by-person ownership scans;
- no firm-by-person hiring scans;
- no per-person account or security full scans;
- mortality and participation use dense alive views;
- heirs use lineage indexes;
- rosters use firm indexes;
- search uses reusable candidate buckets;
- scratch capacity remains stable during a no-topology benchmark panel.

The M7 benchmark has three gates:

1. alive population doubling;
2. large-employer roster mutation;
3. exact marriage matching at 400, 800, 1,600, and 3,200 candidates.

The 400-to-3,200 exact-matching stress ratio must remain at or below 2.6 after
normalizing by candidate count. Absolute and allocation budgets are frozen
from local and hosted-runner calibration before promotion.

## 10. Acceptance corpus

V7a tests include:

- genesis identity and projection equality;
- birth and death ordering;
- death before marriage;
- cash, security, debt, and ownership inheritance;
- spouse, child, parent, and public residual heir fixtures;
- estate tax and exactly-once settlement;
- archive compaction and stable ID continuation;
- checkpoint corruption and fresh-process continuation;
- long seed population panels.

V7b tests include:

- marriage, divorce, widowhood, guardianship, and leaving-home fixtures;
- exact matching order and stress scaling;
- primary job, second job, suspension, recall, timeout, churn, layoff, and
  bankruptcy separation;
- participation, efficiency, job guarantee, and wage anniversary;
- E/U/S/JG/OLF stock and flow equality on every day;
- large-employer roster complexity;
- deterministic replay and fault rollback.

Every test uses the current engine contracts and contains no language-specific
player-facing text.

## 11. Packaging and CI

M7 updates:

- CMake debug, release, sanitizer, and benchmark presets;
- installed C consumer smoke;
- wheel and source-distribution smoke;
- macOS, Linux, and Windows release jobs;
- macOS and Linux ASan/UBSan jobs;
- M6 compatibility performance gate;
- M7 population, labor, and matching performance gates.

The branch may be fast-forwarded into the V33 integration branch only when the
same pushed commit passes all required jobs. The development branch remains
untouched.

## 12. Commit sequence

1. freeze this execution plan and V7a contracts;
2. add stable person and membership stores;
3. add beneficial ownership and estate transactions;
4. integrate V7a genesis, phases, metrics, digest, and checkpoint;
5. pass and commit the V7a acceptance gate;
6. add relationship and exact-matching stores;
7. add employment, roster, suspension, and second-job stores;
8. integrate V7b phases and labor accounting;
9. add C ABI, Python binding, package, and artifact boundaries;
10. freeze and pass performance budgets;
11. publish the M7 acceptance record;
12. push, pass cross-platform CI, fast-forward, tag, and continue to M8.
