# C++ Engine Migration M0 Execution Plan v33

Status: executable plan  
Milestone: M0 — freeze observable contracts  
Oracle baseline: `dev@c0adcf1`  
Integration branch: `refactor/cpp-engine-v33`  
Plan branch: `refactor/cpp-m0-plan-v33`  
Parent design: [`cpp_engine_refactor_v33.md`](cpp_engine_refactor_v33.md)

## 1. Purpose

M0 turns the current Python simulation into a measured, reproducible oracle
before any economic behavior moves to C++. It freezes what the engine accepts,
does, emits, persists, and costs to run.

M0 does **not** implement native economic behavior. It may add observation,
inventory, trace, benchmark, and test hooks to Python, but those hooks must be
provably passive when disabled and must not change simulation results when
enabled.

This document is work package **M0-00**. M0 is complete only after work packages
M0-01 through M0-08 satisfy the exit gate in section 18.

## 2. Fixed boundary

### 2.1 In scope

- Inventory every externally meaningful configuration and runtime contract.
- Assign stable IDs and hashes to the audited Python baseline.
- Make phase order, randomness, events, invariants, and snapshot epochs
  inspectable.
- Freeze deterministic, fixed-seed, policy, shock, controller, RL, desktop,
  checkpoint, and World fixtures.
- Establish reproducible Python performance baselines.
- Define exact, tolerant, semantic, and statistical comparison rules before
  native results exist.
- Classify maintained diagnostic probes and every current Python module.
- Expose all M0 checks through a single machine-readable gate manifest.
- Reconcile current documentation with the generated inventory.

### 2.2 Out of scope

- Adding `native/`, CMake, nanobind, a C ABI, or native packaging.
- Choosing final cross-language checkpoint or canonical serialization
  dependencies.
- Replacing Python RNGs or changing seed derivation.
- Correcting economic behavior, changing defaults, or recalibrating results.
- Optimizing Python code unless a separate reviewed change is required to make
  a benchmark measurable. Such a change must happen outside M0 and requires a
  rebaseline.
- Changing desktop transport, Controller semantics, RL task semantics, policy
  availability, or shock effects.
- Supporting legacy saves. Save fixtures exist only to prove continuation from
  the M0 oracle into later migration milestones.

### 2.3 Change rule

An M0 pull request must be behavior-preserving. If a discovered defect must be
fixed, stop that work package, record the defect, fix it in a separate branch,
run the full Python suite, review the economic effect, update the oracle commit,
and then resume M0 through the rebaseline process.

## 3. Completion result

At M0 completion, a clean checkout can run one command and produce a report
that answers all of the following:

1. Which exact contracts and IDs define the current engine?
2. Which source symbol proves every inventory row?
3. Which phase first diverges when a later implementation changes?
4. Is a difference exact, numeric, semantic, event-timing, or statistical?
5. Which benchmark regressed, on which machine and configuration?
6. Which diagnostic, desktop, Controller, and RL paths are covered?
7. Which module migrates in which milestone, and who owns the decision?
8. Was a baseline intentionally changed, by whom, and with which evidence?

The command is:

```bash
uv run python scripts/cpp_migration/run_m0_gate.py --class milestone
```

The command does not exist at M0-00. M0-01 introduces it and each later work
package adds registered gates.

## 4. Repository layout

M0 introduces the following layout:

```text
schemas/
  m0/
    definitions/                 # JSON Schema for every checked M0 artifact
    inventory/                   # generated canonical contract inventories
    manifests/                   # reviewed source manifests
    hashes.lock.json             # sorted artifact IDs and SHA-256 hashes
tests/
  fixtures/
    m0/
      manifests/                 # fixture definitions and frozen seeds
      expected/                  # compact expected records and digests
      tapes/                     # policy, shock, realization, and action tapes
  migration/
    m0/                          # M0 unit, integration, determinism, and gate tests
scripts/
  cpp_migration/
    common.py                    # canonical JSON, hashing, metadata, errors
    generate_inventory.py
    export_phase_trace.py
    run_benchmarks.py
    compare_artifacts.py
    propose_rebaseline.py
    run_m0_gate.py
benchmarks/
  python_baseline.py             # stable public benchmark entry point
  scenarios/                     # exact benchmark inputs
  results/
    m0/
      reference/                 # reviewed compact raw JSON baselines
artifacts/
  migration/
    README.md                    # output location contract; generated files ignored
```

Rules:

- `schemas/m0/inventory/*.json` is generated and checked in.
- `schemas/m0/manifests/*` is reviewed source data and may be edited.
- `tests/fixtures/m0/expected/*` contains compact evidence, not full object
  dumps.
- Large traces, checkpoints, profiles, and repeated benchmark samples go under
  `artifacts/migration/` and are not committed.
- Reference benchmark JSON contains raw timing samples and metadata, but no
  profiler dump.
- M0 schemas describe migration evidence. They are not the generated
  Python/C++ engine schemas planned for M1.

## 5. Artifact conventions

### 5.1 Canonical M0 JSON

All generated checked artifacts use UTF-8 JSON with:

- keys sorted lexicographically;
- compact separators `,` and `:`;
- non-ASCII characters escaped;
- non-finite numbers rejected;
- a single trailing newline;
- lists sorted by stable ID unless their order is itself contractual.

The Python writer is logically equivalent to:

```python
json.dumps(
    value,
    allow_nan=False,
    ensure_ascii=True,
    separators=(",", ":"),
    sort_keys=True,
) + "\n"
```

This is the `m0-json-v1` evidence encoding. It is deliberately scoped to M0.
The final Python/C++ canonical event and checkpoint encoding remains an M1 ADR.

### 5.2 Stable identity

Every inventory row has:

- `id`: stable qualified identifier;
- `kind`: inventory family;
- `source_path`: repository-relative evidence path;
- `source_symbol`: importable symbol or named source block;
- `status`: `active`, `alias`, `derived`, `deprecated`, or `oracle_only`;
- `introduced_by`: current feature/version when known;
- `owner_milestone`: first native milestone responsible for it;
- `notes`: optional non-contract explanation.

IDs never depend on object addresses, `repr()` output, set iteration, or
dictionary insertion order. Human-facing translated text is excluded from
engine contract hashes.

### 5.3 Hash lock

`schemas/m0/hashes.lock.json` records:

- oracle commit;
- generator version;
- Python major/minor;
- artifact path;
- artifact schema ID;
- sorted ID count;
- SHA-256 of canonical bytes;
- aggregate SHA-256 over sorted `path + digest` pairs.

Counts are drift tripwires. Sorted IDs and hashes are authoritative.

### 5.4 Evidence quality

An inventory row is acceptable only when its source is mechanically extracted
or the row carries a manually reviewed evidence location. Prose documentation
alone is not evidence.

Unknown or duplicate references are hard failures. A known omission cannot be
represented as a silent empty list; it must be a tracked `unresolved` row with
an owner and deadline, and M0 cannot exit with such a row.

## 6. Inventory specification

### 6.1 Source map

| Family | Primary sources | Required corroboration |
|---|---|---|
| config | `macro_sim/config/model.py`, `schema.py`, `loader.py`, `configs/` | YAML loader and config-view tests |
| capabilities | Config mechanism flags, `macro_sim/desktop/new_game.py`, system guards | valid/invalid creation corpus |
| policy | `core/policy.py`, `policy_registry.py`, `policy_control_specs.py`, `external_policy.py` | `scripts/policy_inventory.py`, policy tests |
| shocks | `shocks/spec.py`, `registry.py`, `engine.py`, `scenarios.py` | shock tests and scenario files |
| metrics | `reporting/metrics.py`, `collectors.py`, `national_accounts.py` | observable and purity tests |
| observations | `controllers/observation.py`, `protocol.py`, RL codecs | observation, Gym, and deployment tests |
| phases | `economy.py`, `world/world.py`, Controller boundary code | phase trace and ordering tests |
| RNG | all `random.Random`, NumPy RNG, draw helpers, and seed offsets | repeated-run and tape tests |
| events | Controller events/session/coordinator/replay, shock and domain events | replay and protocol tests |
| invariants | ledger checks, validation methods, explicit assertions | negative corpus and fault tests |
| controller | seats, groups, schedules, costs, transactions, occupants | Controller hardening tests |
| desktop protocol | `macro_sim/desktop/server.py`, `runtime.py`, `new_game.py`, Godot client | desktop smoke and runtime tests |
| scenarios | version/run configs, shock scenarios, diagnostics, RL tasks | load and execution smoke |
| probes | diagnostics registry/probes/world probes/reporting diagnostics | probe-disposition checks |
| module disposition | every tracked Python, Godot, script, and data module | `git ls-files` coverage |
| M4 V0/V1 subset | design-selected capabilities, stores, phases, metrics | subset validator |

### 6.2 Config inventory

Extractor:

```bash
uv run python scripts/cpp_migration/generate_inventory.py --family config --check
```

Required data per field:

- qualified field ID;
- Python type annotation and normalized type class;
- default kind and canonical default;
- nullable, enum, range, and unit metadata where declared;
- loader aliases and compatibility transformations;
- structural, physics, capability, initial-condition, policy-seed, shock-seed,
  or runtime classification;
- version/profile overrides that reference the field;
- owner milestone.

Baseline tripwire:

- exactly 370 entries from `dataclasses.fields(Config)`;
- ClassVars, properties, derived views, and aliases excluded from that count;
- aliases listed separately and pointed at canonical IDs.

Acceptance:

- instantiating default `Config` and every checked profile succeeds;
- every serialized field resolves to one canonical field;
- every YAML key is known or explicitly declared metadata;
- every dataclass field has exactly one classification;
- normalized defaults round-trip without type loss.

### 6.3 Capability inventory

Capabilities are creation-time or mechanism switches, not policy levers.
Required data:

- capability ID and Config field;
- dependent capabilities;
- mutually exclusive capabilities;
- fields and profiles made valid or invalid;
- systems and phases enabled;
- failure code for invalid combinations;
- native owner milestone.

The inventory must distinguish absence of a mechanism from a policy regime.
For example, `monetary_regime` remains policy, while banking, bonds, housing,
and market-mechanism switches remain capabilities.

Acceptance uses a generated pairwise valid/invalid corpus plus manually listed
higher-order constraints from new-game validation.

### 6.4 Policy inventory

M0 refactors `scripts/policy_inventory.py` into an importable extractor while
preserving its executable compatibility entry point.

Required data:

- lever ID, seat, decision group, scope, value type, unit, default, range, and
  step;
- temporal semantics: immediate, new-contract-only, or state-transition;
- cadence, notice, implementation lag, cooldown, and emergency eligibility;
- capability and regime requirements;
- runtime read sites and effectiveness test IDs;
- legacy Config seed and aliases;
- external target cardinality where applicable;
- native owner milestone.

Baseline tripwires:

- 102 control specs and 102 levers;
- 88 domestic and 14 external;
- 88 immediate, 9 new-contract-only, and 5 state-transition;
- seats: `central_bank`, `energy`, `external_affairs`, `regulator`,
  `treasury`;
- decision groups:
  `monetary_stance`, `liquidity_operations`, `fiscal_stance`,
  `tax_and_transfers`, `debt_management`, `macroprudential`,
  `structural_law`, `trade_and_migration`, `fx_operations`,
  `energy_operations`, and `energy_structure`.

Frozen compatibility aliases:

| Alias | Canonical ID |
|---|---|
| `firm_capital_haircut` | `regulatory_firm_capital_haircut` |
| `firm_inventory_haircut` | `regulatory_firm_inventory_haircut` |
| `land_convexity` | `land_fee_stock_elasticity` |
| `policy_rate_override` | `manual_policy_rate` |

Acceptance:

- no unclassified Config, Policy, World, or reviewed institutional literal;
- every control spec resolves to one live field;
- every live field has at least one runtime read or an explicit state-machine
  transition;
- aliases cannot shadow canonical values;
- control specs, UI metadata, Controller actions, and explanations agree on
  identity and range;
- localized policy text is completeness-checked but excluded from contract
  hashes.

### 6.5 Shock inventory

Required data:

- shock kind, channel, target scope, unit, combination rule, and sign;
- onset, duration, recovery, persistence, and disclosure semantics;
- capability requirements;
- affected read sites and prohibited direct state writes;
- scenario references;
- serialization and replay fields.

Baseline default kinds:

- `productivity`
- `labor_availability`
- `energy_capacity`
- `household_demand`
- `import_capacity`
- `export_capacity`
- `credit_supply`
- `capital_destruction`

Acceptance:

- registry IDs equal engine-supported IDs;
- every scenario uses known kinds and valid targets;
- overlays revert without residual mutation;
- order-independent combination holds where declared;
- checkpoint/replay preserves active shocks exactly.

### 6.6 Metric inventory

Required data:

- metric ID, type, unit, stock/flow/rate class;
- source fields and formula symbol;
- snapshot epoch;
- publication cadence, lag, and revision behavior;
- economy or World scope;
- privilege: public, delayed public, Controller, diagnostic, or internal;
- aggregation and missing-value semantics;
- history retention requirement;
- native owner milestone.

Acceptance:

- collectors do not mutate simulation state;
- each published desktop and observation field resolves to one metric ID;
- national-accounting identities list residual metrics and tolerances;
- housing, labor, population, firm, financial-market, energy, and external
  metrics are not omitted simply because an older Config profile did not
  enable them.

### 6.7 Observation inventory

Required data:

- observation schema/version and ordered feature ID;
- source metric/state field;
- transform, normalization, clipping, missing-value handling, and dtype;
- timing epoch, publication lag, scope, and privilege;
- feature bounds;
- consumers: human Controller, Gym task, deployed model, desktop, or replay.

Frozen deployed RL tripwire:

- task `fiscal_stabilization_v1`;
- 101 ordered features;
- one controlled lever;
- three directional actions.

Acceptance:

- feature ordering is explicit and hash-pinned;
- runtime bounds contain valid fixtures or violations are documented;
- artifact codec and environment produce identical feature vectors;
- unavailable public data is never filled from future or privileged state.

### 6.8 Phase inventory

The inventory names every observable boundary in Economy and World execution.
Initial stable phase families are:

- bootstrap/genesis (`B*`);
- economy phases (`E*`);
- World coordination (`W*`);
- dealer/settlement;
- validation;
- commit;
- publication.

The exact sorted phase IDs are generated from the current code audit in
M0-03. Phase IDs are explicit constants; they are never inferred from function
names at trace time.

Required data:

- phase ID and ordered predecessor/successor set;
- economy/World scope;
- source symbol;
- state slices read and written;
- RNG streams consumed;
- event and posting families emitted;
- invariants checked;
- snapshot epoch before and after;
- owner milestone.

Acceptance:

- one complete tick traverses the registered legal graph;
- conditional phases declare their capability guards;
- no unregistered phase can emit a posting or public event;
- trace instrumentation does not alter order or results.

### 6.9 RNG inventory

M0 preserves Python RNG behavior; it does not standardize it.

Required data:

- stream ID;
- constructor and algorithm;
- root seed source;
- current offset or derivation expression;
- owner object and lifetime;
- draw sites and distribution;
- phase;
- state/checkpoint behavior;
- whether a realization tape can replace the draw in a fixture;
- future native owner milestone.

The audit includes all fixed offsets currently embedded in `economy.py` and
other modules, all `random.Random` instances, all NumPy generators, module
globals, shuffles, sampling, and implicit library randomness.

Acceptance:

- a static scan allowlist accounts for every RNG constructor and draw helper;
- repeated fresh-process runs produce identical D1 artifacts;
- no fixture records unstable internal object representation;
- seed panels never change after native results are observed.

### 6.10 Event inventory

Required data:

- event ID and version;
- producer phase and source symbol;
- payload field schema and units;
- ordering key;
- public/privileged classification;
- replay and persistence behavior;
- consumer list;
- native owner milestone.

Acceptance:

- event encoding rejects unknown fields in strict fixtures;
- equal-tick ordering is explicit;
- direct runs and replays have the same event digest;
- cancellation, terminal, emergency, shock, policy, and publication events are
  covered.

### 6.11 Invariant inventory

Required data:

- invariant ID;
- phase and cadence;
- exact or tolerant residual;
- severity and failure code;
- state inputs;
- capability guard;
- test that demonstrates both pass and fail;
- native owner milestone.

The initial registry covers:

- balanced ledger and conservation;
- nonnegative and declared-exception constraints;
- net financial worth;
- reserves, RTGS, and interbank pairs;
- loan, bond, equity, and ownership identities;
- bank capital and P&L;
- housing title, stock, collateral, and lease integrity;
- population, household, relationship, and estate integrity;
- employment stocks, FTE, and flows;
- goods, energy, and inventory feasibility;
- dealer, current account, external position, peg reserve, and World NFA.

### 6.12 Controller and run-contract inventory

Required data:

- seat and decision group IDs;
- actor, occupant, and permission model;
- observation and decision epochs;
- proposal, validation, commit, cancel, terminal, and replay transitions;
- cadence, pause, deadline, emergency, and cost rules;
- action and transaction schemas;
- checkpointed state;
- Gym mapping.

Acceptance:

- the five seat IDs and eleven group IDs are exact;
- direct, human, scripted, heuristic, random-walk, and RL occupants use the
  same transaction boundary;
- pause/resume and terminal paths cannot apply an action twice;
- checkpoint restoration preserves release clocks and pending decisions.

### 6.13 Desktop protocol inventory

Required data:

- message ID and protocol version;
- request/response/event direction;
- payload schema;
- session-state precondition;
- synchronous/asynchronous behavior;
- error schema;
- Godot and Python handlers;
- privilege and snapshot epoch.

Acceptance covers:

- new game;
- natural-time and reference-tick advancement;
- pause/play/speed;
- policy proposal and commit;
- shock scheduling;
- snapshot/detail queries;
- Controller decision boundaries;
- save/load;
- return to main menu;
- clean worker termination.

### 6.14 Scenario inventory

Every checked config, country profile, diagnostic scenario, shock composition,
Controller task, RL task, and desktop smoke scenario receives:

- scenario ID and version;
- source files;
- config/profile hashes;
- seed or frozen seed set;
- capability set;
- duration and natural-time mapping;
- policy/shock/action tapes;
- expected gate classes;
- resource tier.

### 6.15 Probe-disposition inventory

Every maintained diagnostics registry entry, probe, report, and private-field
read is classified as one of:

- `typed_public`;
- `typed_privileged`;
- `derived_from_snapshot`;
- `python_oracle_only`;
- `retire`.

Each row records snapshot epoch, cadence, cost tier, required fields, current
source, future adapter, owner milestone, and acceptance test.

M0 cannot exit with an unclassified maintained probe.

### 6.16 Module disposition

The generator enumerates tracked files under:

- `macro_sim/`;
- `desktop/godot/`;
- `scripts/`;
- `configs/`;
- maintained data assets.

Each runtime module is assigned:

- role;
- canonical state ownership;
- migration action: keep, wrap, port, generate, adapter, oracle-only, or
  retire;
- target milestone;
- dependencies;
- test and benchmark coverage;
- responsible subsystem.

Test files are linked as evidence, not migrated as runtime modules.

### 6.17 Frozen M4 V0/V1 manifest

M0 freezes the first native vertical slice before C++ component design begins.
The manifest explicitly lists:

- supported and rejected capabilities;
- required Config and initial Policy fields;
- entities, stores, and institutional accounts;
- phase graph;
- transaction and posting families;
- metrics, events, invariants, RNG streams, and shock channels;
- V0-to-V1 additions;
- fixture and benchmark scenario IDs.

No M4 implementation may silently expand this manifest. Expansion requires a
reviewed manifest change and matched M0 evidence.

## 7. Python PhaseTrace

### 7.1 API

M0-03 adds an optional trace sink accepted by Economy and World construction or
run orchestration. The default is `None`.

The sink receives immutable records at registered phase boundaries. It cannot
call back into the engine or retain mutable engine objects. Trace projection
copies only registered scalar columns, typed ID lists, and precomputed digests.

### 7.2 Record

Each `phase-trace-v1` record contains:

```text
schema_version
run_id
scenario_id
tick
calendar_date
economy_id
phase_id
phase_ordinal
snapshot_epoch
entity_counts
contract_counts
posting_digest
event_digest
physical_command_digest
selected_state
invariant_results
rng_metadata
terminal_status
```

`run_id` is a stable fixture identifier, not a random UUID.

### 7.3 Digest projection

Posting and event digests use canonical semantic projections:

- stable typed IDs, not Python object IDs;
- declared units and normalized numeric values;
- explicit equal-tick ordering;
- sorted unordered collections;
- aliases resolved to canonical IDs;
- no localized labels or log strings.

Selected state columns are registered in the fixture manifest. A fixture
cannot request arbitrary recursive object serialization.

### 7.4 Snapshot epochs

M0 names at least:

- tick-open;
- post-policy;
- post-shock-read;
- post-market/phase;
- pre-validation;
- post-validation;
- committed;
- published.

Each metric, observation, event, and probe declares one of these epochs.

### 7.5 Passive-instrumentation proof

For each deterministic fixture:

1. Run with no trace sink.
2. Run with an in-memory trace sink.
3. Run with the JSON-lines sink.
4. Compare final semantic digest, event digest, checkpoint bytes where
   applicable, and next-step continuation.

All four results must match. Repeating the JSON-lines run in a fresh process
must produce byte-identical output.

## 8. Fixtures and tapes

### 8.1 Fixture tiers

| Tier | Purpose | Initial cases |
|---|---|---|
| F0 | existing refactor tripwires | v1, v2, v93, v124; 80 days |
| F1 | deterministic native V0 seed | cash loop, randomness disabled |
| F2 | deterministic native V1 seed | capital and basic fiscal |
| F3 | full playable oracle | latest profile, one economy |
| F4 | World oracle | one, two, and three economies |
| F5 | policy semantics | domestic/external, immediate/contract/transition |
| F6 | shock semantics | each default kind and compositions |
| F7 | Controller lifecycle | scripted/human pause, emergency, replay, save |
| F8 | RL contract | `fiscal_stabilization_v1` reset/step/terminal/artifact |
| F9 | desktop flow | new game through save/load and main-menu return |
| F10 | persistence | direct versus fresh-process continuation |
| F11 | stochastic panels | births, deaths, matching, entry/default, crises |

F0 remains a low-cost tripwire and is not relabeled as an economic acceptance
suite.

### 8.2 Deterministic fixtures

Deterministic fixtures disable endogenous stochastic mechanisms where
supported and materialize realization tapes where disabling would change the
economic path being tested.

Each manifest pins:

- full normalized Config hash;
- initial Policy/external Policy hash;
- calendar start and duration;
- capabilities;
- entity genesis hash;
- realization, policy, shock, and action tape hashes;
- trace projection;
- expected phase/event/invariant IDs;
- exact and tolerant output sets.

### 8.3 Fixed-seed fixtures

Fixed-seed fixtures pin a frozen ordered seed list. Seed zero is not treated as
special. Each seed runs in a fresh process where global state contamination is
possible.

The fixture records both the root seed and current derived stream metadata.

### 8.4 Policy tapes

Policy tapes contain:

- natural decision date and reference tick;
- seat, group, lever, target economy/counterparty;
- proposed and accepted value;
- transaction ID;
- declared lag/cooldown;
- expected effective date/window;
- expected event IDs.

At least one tape covers every semantic type and every seat. Exhaustive lever
effectiveness remains in policy tests; fixture tapes are representative
cross-system paths.

### 8.5 Shock tapes

Shock tapes cover:

- each of the eight default kinds;
- overlapping additive/multiplicative composition;
- onset, active interval, recovery, and expiry;
- targeted and World scope;
- disclosure timing;
- checkpoint during an active shock;
- policy plus shock interaction.

### 8.6 Action and realization tapes

Controller/RL actions use the same canonical action records. Endogenous
realizations may be taped only through registered RNG stream IDs and typed
draw results.

No fixture may monkey-patch arbitrary engine functions.

## 9. Python benchmark baseline

### 9.1 Runner contract

Public entry point:

```bash
uv run python benchmarks/python_baseline.py \
  --scenario small_closed_daily \
  --output artifacts/migration/benchmarks/small_closed_daily.json
```

The runner:

- starts measurement after explicit setup/warmup;
- uses `time.perf_counter_ns`;
- records every raw sample;
- runs repetitions in fresh processes for macro cases;
- separates genesis, advance, snapshot, save, and load timing;
- records peak RSS when supported;
- never prints timing as the only result;
- validates scenario and output schemas;
- fails if invariants fail.

### 9.2 Result schema

`python-benchmark-result-v1` includes:

- result and scenario schema versions;
- repository commit and dirty flag;
- aggregate M0 contract hash;
- UTC timestamp;
- OS/version/architecture;
- CPU brand, physical/logical cores, and memory;
- power-mode metadata when observable;
- Python implementation/version;
- dependency lock hash;
- command, environment allowlist, process and thread counts;
- scenario/config/policy/shock/action hashes;
- warmup and repetition counts;
- raw nanosecond samples;
- median, p95, p99, minimum, maximum, and robust spread;
- workload counters;
- semantic result digest;
- error/invariant status.

Unknown hardware metadata is explicit `null`, never guessed.

### 9.3 Scenario matrix

| ID | Shape | Primary use | Gate |
|---|---|---|---|
| `tiny_refactor_v124` | 80 households, 12 firms, 80 days | harness smoke | PR |
| `small_closed_daily` | 100 people, about 20 firms, 2 banks, 1 year | developer baseline | PR |
| `medium_closed_daily` | 500 people, about 100 firms, 8 banks, 1 year | phase cost | nightly |
| `large_closed_daily` | 1,000 people, about 200 firms, 8 banks, 1 year | scaling | nightly |
| `full_playable_10k` | 10,000 people, 750 firms, 8 banks, 1 year | desktop target | milestone |
| `m4_v0_cash_loop` | frozen V0 manifest | P0 denominator | milestone |
| `m4_v1_capital_fiscal` | 5,000 basic household agents, 750 firms | P0 denominator | milestone |
| `world_three_country` | three playable economies | coordination cost | nightly |
| `rl_fiscal_v1_episode` | one complete deployed task episode | training throughput | nightly |
| `desktop_e2e` | worker plus snapshot/action flow | client latency | milestone |
| `checkpoint_full` | full playable save/load | persistence budget | milestone |
| `marriage_400_3200` | 400, 800, 1,600, 3,200 candidates | complexity curve | nightly |
| `employer_roster_scale` | controlled roster sizes | labor hot path | nightly |
| `history_ten_year` | fixed metrics/history profile | retention cost | nightly |
| `world_scale_2_256` | 2, 4, 8, 16, 64, 256 economies | topology curve | manual |

Country population is the primary scale input. Household and firm counts are
derived through the same creation rules used by the desktop unless the
scenario is explicitly a synthetic microbenchmark.

### 9.4 Measurement policy

- PR benchmarks are smoke and schema gates, not performance blockers.
- M0 records raw baselines before setting absolute native budgets.
- Later performance comparisons use matched semantic result digests.
- Wall-clock thresholds are only enforced on a pinned reference runner.
- Developer machines report data without causing portability failures.
- A faster result with a different semantic digest is invalid.
- Profilers may explain a result but are not the recorded benchmark.

### 9.5 Initial reference capture

M0-05 captures the first reviewed reference on the current Apple Silicon
development machine and records detected metadata. The plan does not hard-code
the machine as “M5” or infer details from product marketing.

At least three full runner invocations are performed for each milestone case.
The checked result preserves raw samples from the selected healthy run and
links the other two artifact digests in the review record.

## 10. Comparison and tolerance registry

### 10.1 Comparison classes

| Class | Meaning | Examples |
|---|---|---|
| exact bytes | canonical artifact must match | IDs, schemas, deterministic tapes |
| exact semantic | normalized values/events match | integer counts, typed IDs |
| absolute/relative numeric | finite tolerance | accounting residuals, rates |
| event window | same event within a time window | default, regime transition |
| sign/regime | economic direction/state preserved | impulse response |
| distributional equivalence | frozen seed-panel equivalence | births, matching, crises |
| performance | matched workload/time relation | phase or full-tick speed |

### 10.2 Tolerance record

Each `tolerance-v1` row contains:

- field or metric pattern;
- unit and transform;
- comparison class;
- absolute and relative tolerance;
- zero and near-zero rule;
- NaN/infinity policy;
- applicable fixture/scenario IDs;
- snapshot epoch;
- rationale and evidence;
- owner and review date.

There is no global epsilon fallback. An unregistered numeric comparison fails
with `unknown_tolerance`.

### 10.3 Statistical record

Each statistical panel pins:

- metric/event family;
- immutable ordered seed set;
- horizon and burn-in;
- transform and aggregation;
- equivalence margin;
- pilot source and power calculation;
- decision procedure;
- event-time window if relevant;
- family grouping for multiple-testing correction.

Rules:

- power is at least 80% at the declared equivalence margin;
- family-wise alpha is 0.05 with Holm correction;
- distributional parity uses two one-sided equivalence tests or a confidence
  interval wholly inside the margin;
- failure to reject a difference is not parity;
- the identical frozen panel may be rerun;
- seeds, horizon, margin, transform, and decision rule cannot change after a
  native failure without rebaseline review.

### 10.4 Semantic impulse panels

Before native output exists, M0 freezes short policy and shock impulse panels
for:

- fiscal;
- monetary;
- prudential and banking;
- housing;
- energy;
- trade and sanctions;
- peg/FX;
- migration and external capital;
- productivity, demand, supply, credit, and destruction shocks.

Each panel declares expected sign, regime, peak window, recovery window, and
identity constraints. It does not require identical noisy trajectories.

## 11. Gate manifest and runner

### 11.1 Gate record

Every gate has:

- `id`;
- `class`: PR, nightly, milestone, or release;
- command and working directory;
- dependency gate IDs;
- fixture/oracle/contract hashes;
- platform/profile constraints;
- process/thread counts;
- repetitions and seeds;
- timeout;
- tolerance, statistical, or performance threshold reference;
- expected artifact paths;
- owner;
- failure classification.

### 11.2 Gate classes

**PR**

- schema validation;
- inventory regeneration and byte comparison;
- duplicate/unknown-reference checks;
- hash lock;
- F0 tripwires;
- selected trace determinism;
- selected policy/shock/controller/desktop contract tests;
- benchmark runner smoke.

**Nightly**

- full Python test suite;
- all deterministic and fixed-seed short fixtures;
- World, Controller, RL, desktop, and checkpoint traces;
- medium/large and complexity benchmarks;
- statistical pilot/health checks.

**Milestone**

- full M0 contract regeneration;
- all fixture tiers;
- full statistical panels;
- full playable and M4 V0/V1 benchmark references;
- module/probe/document coverage;
- fresh-checkout reproducibility;
- three-run artifact repeatability audit.

**Release**

- milestone gates on supported reference platforms;
- reviewed waiver and rebaseline audit;
- artifact provenance and clean-tree verification.

### 11.3 Runner behavior

The runner:

- resolves a dependency DAG;
- rejects cycles and unknown references;
- validates the oracle and current commit policy;
- records stdout/stderr and structured result per gate;
- stops dependent gates after failure but continues independent evidence;
- emits one canonical summary;
- returns nonzero on any required failure;
- never mutates checked baselines.

## 12. Rebaseline process

Checked expected artifacts cannot be overwritten by the normal generator or
gate runner.

The only preparation command is:

```bash
uv run python scripts/cpp_migration/propose_rebaseline.py \
  --reason-file /path/to/reason.md \
  --output artifacts/migration/rebaseline/proposal
```

It produces:

- old/new oracle commit;
- generator and contract hashes;
- changed IDs and counts;
- before/after canonical artifact digests;
- metric/event/trace differences;
- raw benchmark references where relevant;
- economic rationale supplied by the author;
- affected gates and milestones;
- proposed checked-file patch list.

It does not edit checked expected files. Applying a rebaseline is a separate
reviewed commit. A reviewer must be able to distinguish:

- intentional model change;
- instrumentation/schema-only change;
- platform measurement refresh;
- defect correction.

Waivers are scoped, dated, owned, and cannot suppress unknown contract IDs or
invariant failures.

## 13. Documentation reconciliation

M0-07 reconciles or replaces stale claims in:

- root `README.md`;
- `docs/README.md`;
- `docs/design/README.md`;
- `docs/design/current/developer-brief.md`;
- `docs/design/current/module-map.md`;
- current World introductions and stale inline architecture comments.

Generated module-disposition data is the source for the module map. Human prose
may explain the map but cannot maintain a conflicting module list.

The update must remove or qualify:

- obsolete closed-economy descriptions;
- v12.4/v23 as the current product boundary;
- claims that World is an empty v20 shell;
- obsolete state-ownership descriptions.

## 14. Work packages

Each package uses a short-lived branch from the latest
`refactor/cpp-engine-v33`, one focused review, and a fast-forward or reviewed
merge back into that integration branch.

### M0-00 — Execution plan

Branch:

```text
refactor/cpp-m0-plan-v33
```

Changes:

- add this document;
- link it from the parent design and documentation index.

Acceptance:

```bash
git diff --check
python - <<'PY'
from pathlib import Path
for path in (
    Path("docs/cpp_engine_m0_execution_plan_v33.md"),
    Path("docs/cpp_engine_refactor_v33.md"),
    Path("docs/README.md"),
):
    assert path.is_file(), path
PY
```

### M0-01 — Evidence framework and governance

Suggested branch:

```text
refactor/cpp-m0-framework-v33
```

Dependencies: M0-00.

Create:

- `schemas/m0/definitions/*.schema.json`;
- empty reviewed manifest skeletons;
- `scripts/cpp_migration/common.py`;
- gate DAG/manifest loader;
- canonical JSON and SHA-256 helpers;
- rebaseline proposal schema and no-overwrite guard;
- `tests/migration/m0/test_canonical_artifacts.py`;
- `tests/migration/m0/test_gate_manifest.py`;
- `tests/migration/m0/test_rebaseline_guard.py`.

Decisions frozen:

- `m0-json-v1`;
- stable ID grammar;
- repository-relative evidence paths;
- artifact schema versioning;
- generated-versus-reviewed ownership;
- gate classes.

Acceptance:

```bash
uv run pytest -q \
  tests/migration/m0/test_canonical_artifacts.py \
  tests/migration/m0/test_gate_manifest.py \
  tests/migration/m0/test_rebaseline_guard.py
uv run python scripts/cpp_migration/run_m0_gate.py --class pr --list
git diff --check
```

Failure/rollback:

- no simulation runtime module is changed;
- framework can be reverted without baseline updates.

Review size target: 500–900 changed lines excluding JSON Schema boilerplate.

### M0-02 — Complete inventory and hash lock

Suggested branch:

```text
refactor/cpp-m0-inventory-v33
```

Dependencies: M0-01.

Create or change:

- importable policy inventory library;
- `generate_inventory.py`;
- all inventory JSON and reviewed source manifests from section 6;
- alias, duplicate, unknown-reference, evidence-path, and coverage validators;
- frozen M4 V0/V1 manifest;
- `hashes.lock.json`;
- focused inventory tests.

Implementation order:

1. Config and aliases.
2. Capabilities.
3. Policy and external policy.
4. Shocks.
5. Metrics and observations.
6. Controller, desktop protocol, and scenarios.
7. Phases, RNG, events, and invariants as source-level inventories; runtime
   trace wiring follows in M0-03.
8. Probes, modules, and M4 V0/V1 subset.

Acceptance:

```bash
uv run python scripts/cpp_migration/generate_inventory.py --write
uv run python scripts/cpp_migration/generate_inventory.py --check
uv run pytest -q \
  tests/test_policy_inventory.py \
  tests/test_policy_registry.py \
  tests/test_external_policy.py \
  tests/test_shocks_v27.py \
  tests/test_controller_specs_hardening.py \
  tests/test_controller_observation.py \
  tests/test_desktop_new_game.py \
  tests/migration/m0
git diff --exit-code -- schemas/m0/inventory schemas/m0/hashes.lock.json
```

Hard acceptance:

- 370 Config field tripwire;
- 102 policy IDs with the frozen partitions;
- five seats and eleven decision groups;
- eight default shock kinds;
- 101/one/three fiscal-v1 contract;
- four compatibility aliases;
- zero duplicate, unknown, unclassified, or missing-evidence rows;
- every module and maintained probe has an owner milestone.

Failure/rollback:

- mismatches are investigated against source;
- expected counts are not edited merely to make the gate pass.

Review size target: one commit per inventory family group if the generated
diff exceeds 2,000 lines.

### M0-03 — Phase, event, invariant, and RNG tracing

Suggested branch:

```text
refactor/cpp-m0-trace-v33
```

Dependencies: M0-02.

Create or change:

- explicit stable phase constants;
- optional Economy/World trace sink;
- canonical semantic posting/event/physical-command projections;
- invariant result projection;
- RNG metadata projection;
- JSON-lines trace writer and comparator;
- passive-instrumentation and first-divergence tests.

Runtime constraints:

- default path performs no trace projection;
- instrumentation cannot draw RNG, sort live mutable collections in place, or
  retain live engine objects;
- trace errors fail the test harness but do not partially commit a tick;
- no per-transfer disk I/O.

Acceptance:

```bash
uv run pytest -q \
  tests/test_conservation.py \
  tests/test_world_container.py \
  tests/test_controller_phase_replay_hardening.py \
  tests/migration/m0/test_phase_registry.py \
  tests/migration/m0/test_phase_trace.py \
  tests/migration/m0/test_trace_is_passive.py \
  tests/migration/m0/test_rng_inventory.py
uv run python scripts/cpp_migration/export_phase_trace.py \
  --fixture refactor_v124 \
  --repeat 3 \
  --require-byte-identical
```

Hard acceptance:

- all registered legal paths traverse declared phase graphs;
- enabled/disabled trace results are semantically identical;
- three fresh-process traces are byte-identical;
- static scan finds no unregistered RNG source;
- first-divergence reporting identifies phase and typed field.

Review size target: separate registry/projection commit from Economy/World
wiring commit.

### M0-04 — Deterministic fixtures and tapes

Suggested branch:

```text
refactor/cpp-m0-fixtures-v33
```

Dependencies: M0-03.

Create:

- F0–F10 manifests and compact expected artifacts;
- V0/V1 deterministic genesis and phase traces;
- policy, shock, Controller/RL action, and realization tapes;
- fresh-process fixture launcher;
- fixture schema and determinism tests.

Reuse:

- current v1/v2/v93/v124 tripwires;
- existing policy effectiveness, shock, Controller replay, checkpoint, RL
  deployment, and desktop runtime fixtures.

Acceptance:

```bash
uv run pytest -q \
  tests/test_refactor_golden_baseline.py \
  tests/test_policy_effectiveness.py \
  tests/test_shocks_v27.py \
  tests/test_checkpoint.py \
  tests/test_controller_terminal_human_replay.py \
  tests/test_rl_model_deployment.py \
  tests/test_desktop_runtime.py \
  tests/migration/m0/test_fixture_manifests.py \
  tests/migration/m0/test_fixture_determinism.py
uv run python scripts/cpp_migration/run_m0_gate.py \
  --class nightly \
  --only fixtures
```

Hard acceptance:

- every fixture references known contract IDs and hashes;
- deterministic artifacts repeat byte-for-byte in fresh processes;
- direct and save/fresh-process/load continuations match;
- tape timing uses natural dates plus reference ticks;
- no fixture uses object addresses or accidental container order.

Review size target: group by fixture tier; do not check in large checkpoint
files.

### M0-05 — Python benchmark corpus

Suggested branch:

```text
refactor/cpp-m0-benchmarks-v33
```

Dependencies: M0-02 for schemas; M0-04 for matched fixtures.

Create:

- `benchmarks/python_baseline.py`;
- runner implementation and schemas;
- scenario matrix from section 9;
- workload counters and semantic digest hooks;
- compact reviewed reference results;
- benchmark smoke and metadata tests.

Acceptance:

```bash
uv run pytest -q tests/migration/m0/test_benchmark_runner.py
uv run python benchmarks/python_baseline.py \
  --scenario tiny_refactor_v124 \
  --repeat 3 \
  --output artifacts/migration/benchmarks/tiny.json
uv run python scripts/cpp_migration/run_m0_gate.py \
  --class pr \
  --only benchmark-smoke
```

Reference capture:

```bash
uv run python scripts/cpp_migration/run_benchmarks.py \
  --suite m0-reference \
  --output artifacts/migration/benchmarks/reference
```

Hard acceptance:

- result schema contains raw samples and complete detectable metadata;
- benchmark and fixture semantic digests match;
- setup/genesis is separated from steady advancement;
- M4 V0/V1 Python denominators are captured;
- absolute native budgets are not fabricated from a single sample.

Review size target: runner separately from large scenario/reference-data diff.

### M0-06 — Tolerances and semantic/statistical panels

Suggested branch:

```text
refactor/cpp-m0-acceptance-v33
```

Dependencies: M0-04 and M0-05.

Create:

- tolerance and statistical registries;
- exact/numeric/event-window/semantic/statistical comparators;
- impulse-panel manifests and Python oracle results;
- pilot, power, and Holm-family validation;
- invalid comparison corpus.

Acceptance:

```bash
uv run pytest -q \
  tests/migration/m0/test_tolerance_registry.py \
  tests/migration/m0/test_artifact_comparator.py \
  tests/migration/m0/test_statistical_registry.py \
  tests/migration/m0/test_semantic_panels.py
uv run python scripts/cpp_migration/compare_artifacts.py \
  --self-test schemas/m0/manifests/comparator_cases.yaml
```

Hard acceptance:

- every compared numeric field resolves to a declared rule;
- equivalence margins and seed panels are frozen before native output;
- at least 80% power and Holm family definitions validate;
- intentionally corrupted fixtures fail for the expected reason;
- no pass-by-rerun or fallback epsilon exists.

Review size target: exact/numeric comparator before statistical tooling.

### M0-07 — Diagnostics, end-to-end traces, and docs

Suggested branch:

```text
refactor/cpp-m0-clients-docs-v33
```

Dependencies: M0-03 through M0-06.

Create or change:

- probe-disposition completion and validation;
- current desktop full-flow trace;
- current Controller human/scripted/RL traces;
- deployed RL artifact contract fixture;
- module map generation;
- documentation reconciliation from section 13.

Acceptance:

```bash
uv run pytest -q \
  tests/test_v23_diagnostics.py \
  tests/test_world_diagnostics.py \
  tests/test_controller_longrun.py \
  tests/test_rl_envs.py \
  tests/test_rl_model_deployment.py \
  tests/test_desktop_runtime.py \
  tests/migration/m0/test_probe_disposition.py \
  tests/migration/m0/test_module_disposition.py \
  tests/migration/m0/test_client_traces.py
uv run python scripts/desktop_smoke.py
uv run python scripts/cpp_migration/generate_inventory.py --check
```

Hard acceptance:

- no maintained probe or runtime module is unclassified;
- desktop and RL traces reference only registered protocol/observation IDs;
- generated module map matches tracked source;
- current docs contain no known stale architecture claims listed in section 13.

Review size target: evidence/client fixtures separate from prose reconciliation.

### M0-08 — Milestone gate and freeze

Suggested branch:

```text
refactor/cpp-m0-freeze-v33
```

Dependencies: all prior M0 packages.

Changes:

- finalize gate DAG and classes;
- capture reviewed milestone artifacts;
- execute full clean-checkout audit;
- close all unresolved inventory/probe/module rows;
- record final oracle, hashes, environment, and test totals;
- tag the M0 contract set in the integration branch.

Required run:

```bash
uv sync --extra rl --extra train --extra dev
uv run python scripts/cpp_migration/generate_inventory.py --check
uv run python scripts/cpp_migration/run_m0_gate.py --class milestone
uv run pytest -q -n 6
git diff --check
git status --short
```

Repeatability audit:

```bash
for m0_run in 1 2 3; do
  uv run python scripts/cpp_migration/run_m0_gate.py \
    --class milestone \
    --artifact-root "artifacts/migration/m0-run-${m0_run}"
done
uv run python scripts/cpp_migration/compare_artifacts.py \
  --repeatability \
  artifacts/migration/m0-run-1 \
  artifacts/migration/m0-run-2 \
  artifacts/migration/m0-run-3
```

The shell loop is an operator example. The checked gate implementation must
offer a platform-neutral repeat option for CI.

Hard acceptance:

- full Python regression is green;
- deterministic checked artifacts are identical across all three runs;
- statistical and benchmark artifacts contain complete provenance;
- all inventory rows and cross-references validate;
- no unresolved probe/module/contract rows remain;
- rebaseline history is empty or fully reviewed;
- working tree is clean after a check-only run.

## 15. Dependency graph and execution order

```text
M0-00 plan
  |
M0-01 framework
  |
M0-02 inventory + M4 manifest
  |\
  | +------------------+
  v                    v
M0-03 trace          M0-05 benchmark scaffolding
  |                    ^
M0-04 fixtures --------+
  |
M0-06 acceptance rules
  |
M0-07 clients, probes, modules, docs
  |
M0-08 full freeze
```

Only M0-05 scaffolding may begin after M0-02; checked matched reference results
wait for M0-04.

## 16. Branch and commit policy

For every package:

1. Update `refactor/cpp-engine-v33` from its reviewed predecessor.
2. Create the exact topical branch listed in section 14.
3. Keep generated changes separate from generator logic when that improves
   review.
4. Use English commit subjects and English source comments.
5. Never merge unrelated worktrees or branches into the M0 branch.
6. Run package acceptance before integration.
7. Merge into `refactor/cpp-engine-v33`.
8. Do not merge the C++ integration branch into `dev` until the requested
   milestone review.

Suggested commit pattern:

```text
docs: define M0 execution plan
test: add M0 evidence artifact framework
test: freeze M0 contract inventory
test: add Python phase trace oracle
test: freeze migration fixtures and tapes
perf: record Python M0 benchmark corpus
test: define migration acceptance registry
docs: reconcile M0 client and module contracts
test: freeze M0 migration oracle
```

Generated artifacts include a header field identifying the generator; commit
messages do not claim generated data was manually authored.

## 17. Verification strategy

### 17.1 Test layers

1. Schema and manifest unit tests.
2. Source extraction and reference-integrity tests.
3. Passive instrumentation tests.
4. Deterministic fixture and replay tests.
5. Semantic and statistical acceptance tests.
6. Benchmark validity tests.
7. Existing subsystem regression tests.
8. Full Python regression.
9. Fresh-checkout and repeated-artifact audit.

### 17.2 Failure classification

The runner classifies failures as:

- `schema`;
- `inventory_drift`;
- `unknown_reference`;
- `oracle_mismatch`;
- `trace_divergence`;
- `invariant`;
- `semantic`;
- `statistical`;
- `performance`;
- `nondeterminism`;
- `environment`;
- `timeout`;
- `tool_error`.

This classification is part of the report contract. A timeout cannot be
reported as a performance regression, and missing optional hardware metadata
cannot be reported as a semantic failure.

### 17.3 Clean-checkout proof

M0-08 must be run from a new temporary worktree at the frozen commit with no
untracked source files. Inputs outside the repository are prohibited except:

- the package cache used by `uv`;
- operating-system metadata;
- an explicitly chosen artifact output directory.

The proof records the exact bootstrap and gate commands.

## 18. M0 exit checklist

### Contracts

- [ ] 370 Config dataclass-field tripwire passes.
- [ ] 102 policy/control-spec IDs and all partitions pass.
- [ ] Five seats and eleven decision groups pass.
- [ ] Eight default shock kinds pass.
- [ ] Fiscal-v1 101-feature/one-lever/three-action contract passes.
- [ ] Four compatibility aliases resolve uniquely.
- [ ] Config, capabilities, policy, shocks, metrics, observations, phases, RNG,
      events, invariants, Controller, desktop protocol, scenarios, probes,
      modules, and M4 V0/V1 are complete.
- [ ] Sorted IDs and aggregate hashes are frozen.

### Trace and replay

- [ ] PhaseTrace covers Economy and World legal paths.
- [ ] Trace-enabled and trace-disabled runs are identical.
- [ ] Repeated fresh-process deterministic traces are byte-identical.
- [ ] Direct and save/fresh-process/load continuation match.
- [ ] First divergence reports phase, field, and comparison rule.

### Fixtures and acceptance

- [ ] F0 through F10 are checked and F11 seed panels are frozen.
- [ ] Policy, shock, action, and realization tapes validate.
- [ ] Every compared numeric field has a tolerance rule.
- [ ] Statistical panels meet power and multiple-testing rules.
- [ ] Semantic impulse expectations are frozen before native output.

### Performance

- [ ] Benchmark runner validates its own result schema.
- [ ] Raw samples and complete detectable environment metadata are recorded.
- [ ] Full playable and M4 V0/V1 Python baselines exist.
- [ ] Semantic digests match benchmark workloads.
- [ ] No unsupported absolute threshold is claimed.

### Coverage and governance

- [ ] Every maintained probe has a disposition.
- [ ] Every runtime module has an action and owner milestone.
- [ ] Gate manifest has no cycle or unknown reference.
- [ ] Rebaseline cannot silently overwrite expected files.
- [ ] Stale architecture documentation is reconciled.
- [ ] Full Python regression is green.
- [ ] Three milestone runs pass repeatability audit.
- [ ] Check-only execution leaves a clean tree.

## 19. Known risks and controls

| Risk | M0 control |
|---|---|
| inventory duplicates existing handwritten lists | one generated canonical inventory; old scripts become adapters |
| trace hook changes timing or RNG order | disabled fast path and enabled/disabled semantic proof |
| full-state dumps become brittle | registered compact projections and semantic digests |
| hashes freeze accidental Python details | qualified IDs and canonical semantic projections |
| benchmarks are noisy | raw samples, fresh processes, metadata, reference-runner-only thresholds |
| tests bless existing bugs forever | tripwire versus economic acceptance labels; separate defect/rebaseline workflow |
| statistical margins are chosen after seeing C++ | freeze panels, margins, seeds, power, and correction in M0 |
| desktop/RL are deferred and later break | M0 current-client end-to-end traces |
| old diagnostics keep reaching private state | complete probe disposition with snapshot epoch and privilege |
| M4 scope expands during implementation | frozen V0/V1 manifest with explicit rejection set |
| generated files hide review changes | generator and generated artifact commits are separable |

## 20. First implementation batch

After M0-00 is merged, begin M0-01 with the following ordered tasks:

1. Add `m0-json-v1` canonical writer and tests.
2. Add artifact schemas and stable ID grammar.
3. Add hash-lock generation and no-overwrite behavior.
4. Add gate-manifest schema, DAG validation, and `--list`.
5. Add rebaseline-proposal schema and dry-run command.
6. Register only the framework self-tests in the initial PR gate.

Do not begin inventory extraction in M0-01. Keeping the framework independent
allows M0-02 review to focus on whether the extracted economic contract is
complete rather than on serialization plumbing.

M0-01 is ready to merge when its acceptance commands pass from a clean
worktree and it changes no simulation result or runtime default.

## 21. Decision log for implementation

The following decisions are settled by this plan:

- M0 is Python-oracle work and contains no native economic engine.
- Checked M0 artifacts use `m0-json-v1`; final cross-language encoding is
  deferred.
- Generated inventories, reviewed manifests, compact expected fixtures, and
  large transient artifacts have separate locations.
- Stable IDs and hashes, not counts alone, define the baseline.
- Natural dates are authoritative in user-facing and event fixtures; ticks are
  retained as reference and engine sequence fields.
- Current Policy, Controller, Shock, RL, desktop, diagnostics, and World
  functionality are all in scope.
- Benchmark validity requires matching semantic output.
- Rebaseline is proposal-first and cannot silently overwrite evidence.
- M4 V0/V1 scope is frozen during M0, before native state-store design.

Open implementation details that do not block M0-00:

- the exact final list of phase IDs after source extraction;
- whether process RSS collection needs a small optional platform adapter;
- the final reference-runner identity;
- which statistical panels need additional pilot seeds to reach 80% power.

Each open item has an owning work package and cannot remain open at M0 exit.
