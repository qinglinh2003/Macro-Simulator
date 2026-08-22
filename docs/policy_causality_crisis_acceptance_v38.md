# Policy causality, crisis, and acceptance plan v38

Status: proposed execution protocol  
Date: 2026-08-22  
Scope: the current native engine, all 102 registered Policy levers, the free-policy
desktop path, Controller experiments, and Shock Engine v27

## 1. Objective

This audit must answer five different questions without conflating them:

1. Is every registered Policy lever routed to the current native engine?
2. Does each lever activate its declared economic mechanism at the correct time?
3. Does the mechanism produce economically coherent effects in ordinary states?
4. Do crisis-response policies work in independently specified crises, with visible
   costs and trade-offs?
5. Are policy combinations, timing, information, and institutional constraints
   represented without changing the underlying economic result by accident?

The audit is complete only when every lever has a frozen causal contract and a final
disposition. A completed experiment may conclude that a lever is ineffective, harmful,
redundant, or unsupported. Completion does not mean forcing every intervention to look
beneficial.

The preferred resolution order for a failed player-facing lever is:

1. repair a missing route, transition handler, or observable;
2. use the correct activation state;
3. correct the mechanism or its accounting;
4. merge or remove a redundant lever;
5. hide a technical or expert-only lever from ordinary play;
6. recalibrate the magnitude only after the channel is economically valid.

This programme does not select one optimal national welfare function, balance a
political game layer, or certify historical fidelity by default. It estimates causal
response surfaces and freezes evidence that later game modes, human players, and RL
objectives may use.

Related engine contracts are:

- [`policy_module_v25.md`](policy_module_v25.md);
- [`controllers_v26.md`](controllers_v26.md);
- [`controller_levers_v26.md`](controller_levers_v26.md);
- [`controller_observations_v26.md`](controller_observations_v26.md);
- [`shocks_v27.md`](shocks_v27.md);
- [`config_causality_audit_v37.md`](config_causality_audit_v37.md);
- [`frontend_free_policy_v34.md`](frontend_free_policy_v34.md).

## 2. Boundaries and definitions

### 2.1 Policy is not Config and a crisis is not an outcome override

Config defines genesis, technology, preferences, institutions, and other structural
conditions. Policy is authority-controlled runtime state. Shock inputs disturb a
registered economic channel. Outcomes such as unemployment, prices, bankruptcies,
poverty, and GDP must remain endogenous.

The audit must not create a crisis by directly setting an outcome to a crisis value.
For example, it may restrict credit supply and expose a leveraged banking system; it
must not set unemployment to 30 percent or overwrite bank capital merely to label the
result a financial crisis.

### 2.2 Four experiment objects

The protocol distinguishes four objects:

- **ordinary-state baseline**: a stable run used to measure normal operation and side
  effects;
- **activation fixture**: the smallest controlled state that makes one mechanism or
  constraint bind;
- **canonical crisis scenario**: a reusable, policy-independent economic failure path
  defined and accepted before any candidate response is evaluated;
- **historical replication**: a separately sourced attempt to match a named historical
  episode. Historical labels are not required for the causal audit and do not replace
  canonical scenario validation.

Activation fixtures may be tailored to a lever or mechanism family. Canonical crises
must not be tailored to make one policy succeed.

### 2.3 Two execution profiles

The economic and institutional questions use separate profiles.

**Economic-causality profile**

- Uses the free-policy protocol.
- Stages a complete atomic batch at a clean day boundary.
- Leaves the completed current day immutable.
- Commits the batch immediately before the next simulated day.
- Ignores meetings, authority, implementation lag, minimum hold, maximum step,
  administrative capacity, and generic adjustment cost.
- Retains type, domain, capability, linked-policy, transition, and world invariants.

This profile identifies what a policy value does to the economy.

**Institutional-delivery profile**

- Uses Controller decision contexts and released information.
- Applies authority, information access, meetings, implementation lag, emergency
  authority, minimum hold, maximum step, administrative capacity, and adjustment cost.
- Evaluates whether an institution can deliver the already-validated economic action.

This profile identifies whether a human, heuristic, or RL occupant can use the policy
under realistic procedural constraints. Institutional friction must never be used to
explain away a dead engine route.

## 3. Frozen audit surface

The current Registry contains 102 levers in 12 decision groups:

| Owner | Decision group | Count | Primary mechanism family |
|---|---|---:|---|
| Treasury | `fiscal_stance` | 7 | demand, public investment, benefits, job guarantee |
| Treasury | `tax_and_transfers` | 18 | tax bases, transfers, distribution, sector incentives |
| Treasury | `debt_management` | 3 | funding mix, coupon cohorts, maturity structure |
| Central bank | `monetary_stance` | 13 | policy rate, rule response, inflation measurement |
| Central bank | `liquidity_operations` | 6 | reserves, OMO, lender of last resort |
| Central bank | `fx_operations` | 5 | capital controls, settlement, peg and reserves |
| Regulator | `macroprudential` | 21 | bank, firm, margin, household, and mortgage credit |
| Regulator | `structural_law` | 7 | insolvency, resolution, foreclosure, eviction |
| External affairs | `trade_and_migration` | 9 | trade, sanctions, migration, remittances |
| Energy | `energy_operations` | 5 | reserves, rationing, caps, operational allocation |
| Energy | `energy_structure` | 1 | energy-firm ownership transition |
| Labor and social protection | `labor_and_welfare` | 7 | wages, employment support, welfare eligibility |

No row may be omitted because it looks technical, is non-numeric, or is expected to be
nonbinding in the product baseline.

The Shock Registry currently exposes eight causal channels:

- productivity;
- effective labor availability;
- physical energy capacity;
- desired household demand;
- import capacity;
- export capacity;
- bank loan-origination supply;
- one-shot physical capital destruction.

The existing oil embargo, global financial crisis, pandemic, and natural-disaster
builders are reduced-form and explicitly uncalibrated. They are inputs to the scenario
programme, not accepted crises by name.

## 4. Required policy contract

The audit generates one machine-readable contract for every lever. Each contract must
contain:

```yaml
lever: gov_consumption_share
registry_schema_version: 1
owner: treasury
decision_group: fiscal_stance
value_type: float
baseline_value: 0.20
treatment_values: [0.18, 0.22]
linked_actions: []
effective_semantics: immediate
first_native_read_point: <source symbol>
mechanism_proximal_metrics: [<metric ids>]
ordinary_state_scenarios: [BASE_NORMAL, BASE_SLACK]
activation_fixture: ACT_FISCAL_RESOURCE_SLACK
primary_crises: [CR_DEMAND_RECESSION]
secondary_crises: [CR_PANDEMIC, CR_CREDIT_CRUNCH]
safety_scenarios: [BASE_TIGHT, CR_SUPPLY_STAGFLATION]
expected_chain: [policy, public_demand, output, employment, fiscal_balance]
expected_signs:
  public_demand: positive
  fiscal_balance: negative
operating_horizon_days: [1, 365]
materiality_contract: <metric-specific thresholds>
tradeoff_metrics: [gov_debt_to_gdp, inflation]
guardrails: [accounting_identity, finite_values]
status: planned
```

Required final dispositions are:

- `accepted`;
- `accepted_activation_only`;
- `accepted_structural_long_horizon`;
- `accepted_expert_only`;
- `redundant_merge`;
- `engine_route_defect`;
- `mechanism_defect`;
- `observable_defect`;
- `unsupported_by_current_engine`;
- `remove_from_player_surface`.

No `pending`, `unknown`, or undocumented `N/A` remains at close-out.

## 5. Treatment design

### 5.1 Numeric levers

Each numeric lever receives, where valid:

1. a local decrease and increase around the product baseline;
2. an economically meaningful low and high dose;
3. the smallest dose that crosses a known binding threshold;
4. a reversal or withdrawal arm when hysteresis or stock effects are possible.

Rates and bounded shares should move in a scale appropriate to their domain. Zero
baselines use documented absolute doses. Integer values must cross an actual discrete
boundary. Registry minima and maxima are validation limits, not automatically sensible
experimental treatments.

### 5.2 Boolean, enum, nullable, set, and linked levers

- Boolean levers test both transitions.
- Enum levers test every valid transition, not only every value at genesis.
- Nullable levers test `null -> value`, `value -> value`, and `value -> null` when all
  are valid.
- Bilateral and set-valued levers test add, remove, repeated no-op, ownership, and
  symmetric or directional effect as declared by the Registry.
- Linked levers are changed in one atomic batch. Invalid partial batches are negative
  controls and must fail without partial mutation.

### 5.3 Cohort and state-transition semantics

The experiment must distinguish:

- immediate flow effects;
- new-contract-only effects;
- stock restatements;
- cohort replacement;
- persistent state transitions;
- world-level atomic transitions.

A new-contract policy passes only if old and new cohorts retain their correct terms.
A state transition passes only if related ownership, ledger, cache, and checkpoint
state changes atomically and survives replay.

## 6. Shared state and activation library

Every decision group receives reusable activation fixtures. These fixtures are not
claims of historical realism.

| Fixture | Binding state | Groups primarily covered |
|---|---|---|
| `ACT_FISCAL_RESOURCE_SLACK` | unemployed labor and idle supply capacity | fiscal stance, labor and welfare |
| `ACT_TAX_BASES` | nonzero wage, profit, consumption, wealth, property, and energy tax bases | tax and transfers |
| `ACT_DEBT_ISSUANCE` | active deficit, bond demand, and multiple issuance cohorts | debt management, monetary liquidity |
| `ACT_TAYLOR_INTERIOR` | inflation and unemployment gaps with rate away from both clamps | monetary stance |
| `ACT_BANK_LIQUIDITY` | heterogeneous banks near reserve or funding constraints | liquidity operations, macroprudential |
| `ACT_BANK_SOLVENCY` | leveraged and exposed banks with loss-bearing assets | macroprudential, structural law |
| `ACT_HOUSEHOLD_CREDIT` | eligible borrowers near household-credit and bankruptcy constraints | macroprudential, structural law |
| `ACT_MORTGAGE_CREDIT` | active originations, arrears, collateral risk, and housing turnover | macroprudential, structural law, tax |
| `ACT_MARKET_MARGIN` | active capital-market positions near margin constraints | macroprudential |
| `ACT_TRADE_FLOWS` | nonzero bilateral imports and exports with spare and binding capacities | trade and migration |
| `ACT_MIGRATION_FLOWS` | nonzero bilateral migration and remittances | trade and migration |
| `ACT_PEG_PRESSURE` | a valid peg, owned reserves, and live rate or external-flow pressure | FX operations |
| `ACT_ENERGY_SHORTAGE` | energy stock, constrained capacity, unmet demand, and eligible users | energy operations, energy tax and transfers |
| `ACT_INSOLVENCY_ARREARS` | firms and households crossing persistence, foreclosure, or eviction boundaries | structural law |
| `ACT_OWNERSHIP_TRANSITION` | a live energy firm with all affected ledgers and pricing modes | energy structure |

Each fixture must state the smallest sufficient precondition, forbid direct outcome
overrides, and declare which measurements prove activation.

## 7. Canonical scenario library

### 7.1 Scenario construction rule

Every crisis follows:

```text
vulnerability build-up -> exogenous trigger -> endogenous propagation -> recovery or failure
```

A scenario manifest freezes:

- Config and initial Policy hashes;
- country profiles, world graph, and capabilities;
- population, institution densities, and seeds;
- pre-crisis duration and vulnerability targets;
- checkpoint immediately before the disclosed decision boundary;
- immutable shock tape and information visibility;
- crisis entry, severity, and exit rules;
- prohibited direct state modifications;
- primary, propagation, trade-off, and guardrail metrics;
- no-response acceptance results;
- data provenance and calibration caveats.

Vulnerability-building actions, if any, are completed before the common checkpoint and
are identical in every branch. A candidate response lever may not define the crisis in
the same experiment in which its efficacy is judged. Another economy's policy or a
pre-crisis policy path may be treated as part of the frozen environment, but it must be
declared as a scenario input and must not be counted as the response effect.

### 7.2 Initial library and readiness

| ID | Scenario | Native construction | Readiness |
|---|---|---|---|
| `CR_DEMAND_RECESSION` | demand contraction and unemployment | household-demand shock after stable burn-in | ready to calibrate |
| `CR_SUPPLY_STAGFLATION` | lower output with price pressure | sector productivity plus energy-capacity shock | ready to calibrate |
| `CR_ENERGY_EMBARGO` | energy and import shortage | oil-embargo template, then empirical retuning | ready to calibrate |
| `CR_CREDIT_CRUNCH` | credit contraction and balance-sheet recession | credit-supply, demand, and productivity legs | ready to calibrate |
| `CR_PANDEMIC` | labor, production, demand, credit, and trade interruption | pandemic template | ready to calibrate |
| `CR_NATURAL_DISASTER` | physical-capital loss and disrupted production | capital destruction plus sector disturbances | ready to calibrate |
| `CR_TRADE_INTERRUPTION` | import/export capacity loss | bilateral import and export capacity shocks | ready to calibrate |
| `CR_PEG_PRESSURE` | reserve drain and forced adjustment risk | peg vulnerability plus trade and live-rate pressure | conditional on a reliable endogenous pressure path |
| `CR_BANK_RUN` | deposit flight and liquidity contagion | vulnerable banks plus endogenous run mechanism | conditional; no direct withdrawal shock exists |
| `CR_HOUSING_BUST` | leveraged housing downturn and arrears | endogenous credit/price build-up followed by macro trigger | conditional on reproducible boom-bust formation |
| `CR_SOVEREIGN_STRESS` | refinancing stress or sovereign default loop | debt cohorts and funding demand | blocked if risk-premium/default transmission is absent |

`conditional` scenarios may not be used for final policy efficacy until their
propagation chain passes. `blocked` scenarios must produce an explicit engine-gap issue;
they must not be approximated by overwriting the desired outcome.

### 7.3 Structural non-crisis scenarios

Long-run and preventive policies also require:

- `STRUCT_HIGH_POVERTY`;
- `STRUCT_HIGH_INEQUALITY`;
- `STRUCT_LOW_PARTICIPATION`;
- `STRUCT_HOUSING_SHORTAGE`;
- `STRUCT_LOW_PRODUCTIVITY`;
- `STRUCT_ENERGY_DEPENDENCE`;
- `STRUCT_POPULATION_AGING`;
- `STRUCT_EXTERNAL_IMBALANCE`.

These are not relabeled as crises solely to make an intervention appear urgent.

## 8. Crisis validation before policy evaluation

The no-response control arm validates a crisis before candidate responses are added.
Validation has five gates.

### 8.1 Entry gate

The predeclared crisis-entry rule must be met in at least six of eight matched seeds at
the 100,000-person stage. A failed seed is retained and reported; it is not silently
dropped. Deterministic scenarios should meet the rule in all seeds.

### 8.2 Path gate

The expected causal ordering must be visible. For a credit crisis, for example:

```text
credit headroom falls
-> originations fall
-> firm liquidity or investment weakens
-> defaults or layoffs rise
-> household demand falls
-> secondary losses increase
```

The scenario fails if only the injected input changes while the declared propagation
metrics remain flat.

### 8.3 Severity gate

Every scenario defines mild, moderate, and severe variants using control-arm outcomes,
not shock magnitude alone. Severity bands include peak damage, cumulative damage, and
duration. Adjacent bands must be ordered on the primary damage estimand across matched
seeds.

### 8.4 Recovery gate

Finite shocks must either recover, settle into a documented new regime, or cross a
declared failure boundary. Permanent unexplained collapse, numerical lock-up, and
instant costless recovery are failures.

### 8.5 Integrity gate

All scenarios preserve finite values, deterministic replay, checkpoint continuation,
stock-flow identities, money and real-stock accounting, valid entity references, and
the immutable shock-tape hash.

Once accepted, the scenario manifest and no-response envelope are frozen before any
policy result is inspected.

## 9. Policy-to-scenario matrix

Every lever is mapped many-to-many to scenarios with one of four roles:

- `primary`: the policy is intended to improve a predeclared target in this state;
- `secondary`: an important indirect effect is plausible and must be estimated;
- `safety`: improvement is not required, but material worsening must be measured;
- `not_applicable`: there is no implemented causal path, with a written reason.

A policy may have no crisis marked `primary` if it is structural, administrative, or
preventive. It must still have ordinary-state and activation coverage.

The matrix must be frozen before outcome results are opened. Adding a new crisis after
seeing a policy fail requires a protocol amendment that explains the missing economic
state and maps at least one mechanism family, rather than only the failed lever.

The initial family-level coverage map is:

| Decision group | Ordinary and structural coverage | Candidate crisis coverage |
|---|---|---|
| `fiscal_stance` | normal, slack, tight, high poverty | demand recession, credit crunch, pandemic |
| `tax_and_transfers` | tax-base fixture, poverty, inequality, energy dependence | recession safety, stagflation, energy embargo |
| `debt_management` | active issuance and long debt cohorts | credit crunch, peg pressure, sovereign stress when supported |
| `monetary_stance` | Taylor interior, normal, slack, tight | recession, stagflation, credit crunch, peg pressure |
| `liquidity_operations` | reserve and funding constraints | credit crunch, bank run when supported |
| `fx_operations` | live trade/capital flows and peg pressure | trade interruption, peg pressure |
| `macroprudential` | active bank, firm, household, margin, and mortgage credit | credit crunch, bank run, housing bust |
| `structural_law` | insolvency, arrears, foreclosure, and eviction fixtures | credit crunch, bank run, housing bust, disaster |
| `trade_and_migration` | live bilateral flows, remittances, external imbalance | trade interruption, pandemic, energy embargo |
| `energy_operations` | energy stock and shortage fixture | energy embargo, stagflation, disaster |
| `energy_structure` | long-run ownership and energy-dependence states | energy-emergency safety and recovery |
| `labor_and_welfare` | slack labor, poverty, participation, inequality | recession, pandemic, credit crunch |

This table guarantees family coverage; it does not automatically mark every member of
a group as `primary`. The 102-row lever matrix makes that narrower ruling.

## 10. Counterfactual experiment design

### 10.1 Paired branch procedure

For each seed:

1. Run the common genesis and vulnerability-building period.
2. Save and validate checkpoint `T0` before the intervention boundary.
3. Clone the checkpoint into control and treatment branches.
4. Reuse the identical future shock tape and exogenous random streams.
5. Stage the control no-op and treatment batch through the same protocol.
6. Advance through identical horizons and release schedules.
7. Compare branches by matched seed.

The control branch is never regenerated from genesis after the treatment result is
known. Common random numbers and the same checkpoint isolate the policy action.

### 10.2 Timing arms

Crisis-response policies receive predeclared timing arms where meaningful:

- anticipated: after announcement but before realization;
- immediate: first clean boundary after a public surprise;
- delayed: 7 days after realization;
- late: 30 days after realization;
- standing facility: already active before the crisis.

An event created inside day `t` cannot be observed and retroactively prevented inside
that same day. In free-policy experiments, an action staged after day `t` applies before
day `t+1`. Controller experiments additionally respect release and decision clocks.

### 10.3 Horizons

| Mechanism | Minimum windows |
|---|---|
| operational liquidity, FX, energy | 1, 7, 30, 90 days |
| demand, monetary, credit, labor | 30, 90, 365 days |
| tax, investment, housing, insolvency | 90 days, 1, 5 years |
| debt cohorts and structural ownership | 1, 5, 10 years |
| migration, pension, distribution | 1, 5, 20 years where computationally feasible |

Windows are relative to actual effectiveness, not proposal or announcement time.

### 10.4 Scale, seeds, and workers

| Stage | Population per country | Matched seeds | Purpose |
|---|---:|---:|---|
| route smoke | 100,000 | 1 | crash, exact silence, boundary correctness |
| single-lever confirmation | 100,000 | 4 | mechanism, sign, timing, dose response |
| crisis validation | 100,000 | 8 | entry rate, propagation, severity, recovery |
| crisis policy estimate | 100,000 | 8 | paired benefit, trade-offs, tails |
| rare-event stress | 1,000,000 | 16 or more | failures and low-rate events only |
| finite-size confirmation | 100,000 and 1,000,000 | 8 matched | selected representatives by mechanism family |

Full native runs use eight engine workers. Independent simulations run concurrently
only while the machine remains below the measured memory and CPU saturation point.
Python may orchestrate the native engine and analyze artifacts; the legacy Python
simulation is not an oracle or acceptance target.

## 11. Estimands

For outcome `Y`, treatment `p`, seed `s`, and window `h`, store:

- paired average treatment effect;
- absolute and relative effect;
- local elasticity or semi-elasticity where meaningful;
- area under the response curve;
- peak effect and time to peak;
- time to half-recovery and terminal effect;
- volatility and downside-tail effects;
- event-rate differences for default, bankruptcy, bank failure, foreclosure,
  migration, deprivation, and other maintained events;
- direct fiscal, central-bank, household, firm, bank, energy, and external balance-sheet
  costs;
- cross-country spillovers and displacement effects;
- interaction terms for policy combinations.

Time series use block-bootstrap uncertainty. Seed-level paired intervals are primary;
daily observations are not treated as independent samples. Multiple-outcome screening
reports false-discovery-adjusted support but cannot replace a predeclared primary
estimand.

## 12. Acceptance gates

### 12.1 Registry and routing

A lever passes when:

- its type, absolute domain, owner, group, capabilities, linked requirements, effective
  semantics, handler, and first native read point are known;
- its current value and effective event agree across native state, metrics, checkpoint,
  and frontend protocol;
- unsupported capabilities reject the action before partial mutation;
- it has an assigned activation fixture and scenario-matrix disposition.

### 12.2 Boundary and atomicity

A lever passes when:

- staging does not mutate the completed current day;
- the valid batch commits before the next day's first applicable read;
- a failed batch changes no lever, transition state, ledger, cache, or world view;
- exact no-op staging changes no policy version or economic trajectory;
- checkpoint and replay reproduce the same effective event and future path.

### 12.3 Mechanism activation

A lever passes when its activation fixture produces a deterministic change at the
declared first read point and a nontrivial difference in at least one
mechanism-proximal observable. Exact trajectory equality is a failure unless the
contract explicitly predicts nonbinding behavior in that state.

For new-contract and state-transition levers, passing additionally requires the correct
cohort or transition evidence; a changed aggregate alone is insufficient.

### 12.4 Economic coherence

Before execution, each contract declares expected sign, horizon, monotonicity or
threshold behavior, plausible magnitude band, and known ambiguous equilibrium effects.

Failure classes include:

- wrong sign without an explained regime transition;
- correct sign but implausibly weak or explosive;
- effect on the wrong clock;
- missing intermediary in the declared mechanism chain;
- a pure accounting or genesis artifact;
- improvement generated by violating a stock-flow identity;
- treatment effects dominated by unexplained finite-size noise.

### 12.5 Crisis efficacy

A `primary` crisis-policy pairing passes when:

1. the control crisis was frozen and accepted first;
2. the policy activates the intended mechanism;
3. the matched interval improves at least one predeclared primary-loss estimand in the
   expected direction;
4. the effect exceeds its metric-specific materiality floor;
5. all predeclared costs and trade-offs are reported;
6. no hard guardrail is breached;
7. the result is not created solely by one seed or by deleting the affected population,
   firms, banks, or market.

Failure to improve is a valid scientific result, but a player-facing lever advertised
for that crisis is not accepted until it is repaired, relabeled, narrowed, or removed.

### 12.6 Safety and side effects

Every lever must pass at least one normal-state safety run. Crisis policies also receive
an unnecessary-intervention arm. Record whether the policy:

- destabilizes a normal economy;
- shifts losses to another country, sector, cohort, or balance sheet;
- creates fiscal or financial dominance;
- suppresses a price while worsening quantity shortage;
- delays rather than reduces failures;
- improves the headline target by worsening poverty, inequality, or access;
- creates persistent dependence or exit problems after withdrawal.

No universal rule requires every side effect to be zero. The trade-off must be visible,
bounded, and consistent with the declared economic mechanism.

### 12.7 Gameplay salience

Wiring materiality and gameplay salience are separate.

- Wiring requires a mechanism-proximal difference above numerical tolerance.
- Salience requires a recognizable strategic difference at a meaningful dose and
  horizon, together with at least one cost, delay, risk, or competing objective.

Each metric defines its own absolute just-noticeable floor and a scale-normalized floor.
As a default screen, the effect must exceed both numerical tolerance and either the
metric floor or 0.2 robust control standard deviations. This default may be replaced by
a preregistered empirical or design threshold; it may not be relaxed after results are
seen merely to pass a lever.

A policy with one dominant setting across ordinary states and all crises fails the
gameplay trade-off review even if its code path is correct.

### 12.8 Reproducibility, stability, and performance

All accepted runs must preserve:

- finite values and bounded rates;
- accounting and conservation invariants;
- deterministic checkpoint continuation and event hashes;
- valid entity references and world-level atomicity;
- identical results under accepted worker scheduling;
- recorded wall time, peak resident memory, and output volume.

A policy change that materially changes results only because of worker count or record
frequency is a defect.

## 13. Falsification and negative controls

Every family includes:

- exact no-op action;
- invalid linked action that must fail atomically;
- action in a nonbinding state;
- action in a binding activation fixture;
- pre-intervention trend comparison;
- policy withdrawal or reversal where meaningful;
- non-target economy and spillover measurement in world runs;
- crisis tape without policy and policy without crisis;
- placebo effectiveness date when the mechanism cannot yet read the value.

Scenario entry and exclusion are determined from the control arm. Treatment outcomes
must never decide which seeds count as crisis observations.

## 14. Policy combinations

Combinations begin only after every component passes routing and activation. Initial
packages are:

1. recession response: monetary easing, fiscal demand, benefits, and job guarantee;
2. anti-inflation: monetary tightening, fiscal stance, energy relief, and supply-side
   measures;
3. bank liquidity: OMO, reserve floor, lender of last resort, and deposit-related rules;
4. bank solvency: capital, leverage, exposure, migration-on-failure, and resolution;
5. housing cycle: mortgage underwriting, LTV/DSTI, capital, permits, and housing taxes;
6. energy emergency: strategic reserves, rationing, caps, compensation, subsidy, and
   windfall tax;
7. external crisis: peg, reserves, rates, capital controls, trade, and settlement;
8. poverty and employment: income tax, transfers, minimum wage, benefits, and public
   employment;
9. debt sustainability: fiscal stance, funding fraction, coupon, maturity, and monetary
   interaction.

Use full factorial designs for two or three components and preregistered fractional
factorials for larger packages. Report main effects, pairwise interactions, crowd-out,
redundancy, and whether the package violates a guardrail that no component violates
alone.

## 15. Institutional and Controller experiments

Institutional tests start only after the economic action passes the free-policy audit.
For the same checkpoint and crisis tape, compare:

- immediate unrestricted delivery;
- scheduled human-comparable Controller delivery;
- emergency delivery;
- delayed or missed meeting;
- heuristic occupant;
- random-walk safety occupant;
- RL occupant only after the action and observation contracts are frozen.

The decomposition is:

```text
total outcome gap
= economic policy effect
+ information delay
+ decision delay
+ implementation delay
+ action constraint
+ adjustment and administrative cost
+ occupant decision quality
```

Controller observations must use released vintages and role access. Oracle metrics may
evaluate outcomes but may not enter a human-comparable decision rule.

## 16. Execution phases and exit criteria

### P0 - Freeze inventory and contracts

- Generate the 102-row Registry ledger and hashes.
- Assign every lever an activation fixture, outcomes, horizons, and scenario roles.
- Freeze the metric materiality catalog and failure taxonomy.

Exit: no unowned, unmapped, or unclassified lever.

### P1 - Route, boundary, and transition verification

- Run one-seed 100,000-person smoke tests.
- Verify native read points, next-day atomicity, no-op behavior, linked rejection,
  checkpoint, and replay.

Exit: all levers pass routing or have explicit defects; no defect is mislabeled as a
small elasticity.

### P2 - Ordinary-state and activation experiments

- Run four matched seeds per lever.
- Estimate local and meaningful-dose effects.
- Validate thresholds, cohorts, withdrawal, safety, timing, and salience.

Exit: every lever has an accepted mechanism or a final repair/removal disposition.

### P3 - Build and validate the scenario library

- Calibrate no-response ordinary, structural, and crisis manifests.
- Validate entry, propagation, severity, recovery, and integrity.
- Freeze accepted scenario tapes and checkpoints.

Exit: no policy efficacy result uses an unaccepted crisis.

### P4 - Single-policy crisis evaluation

- Run the frozen Policy-to-Scenario matrix.
- Estimate timing, dose, primary benefit, trade-offs, tails, and spillovers.

Exit: every `primary`, `secondary`, and `safety` cell has evidence or an explicit
engine-gap disposition.

### P5 - Combination and robustness experiments

- Run the nine packages.
- Test interactions, alternative severity, alternative baselines, and withdrawal.

Exit: recommended packages have no hidden dominant component or unreported guardrail
failure.

### P6 - Finite-size and rare-event confirmation

- Select at least one representative from each of the 12 decision groups plus every
  rare-event mechanism.
- Repeat matched 100,000 and 1,000,000-person runs.
- Run million-person tail experiments only where scale materially changes the event.

Exit: signs, activation, accounting, and material conclusions survive scale, or the
finite-size dependency is explicitly part of the contract.

### P7 - Empirical and gameplay freeze

- Compare magnitude bands and crisis stylized facts against primary empirical sources
  where available.
- Separate empirical estimates from model-design priors.
- Freeze Registry ranges, recommended UI doses, policy explanations, scenario
  manifests, and regression thresholds.

Exit: every player-facing claim is traceable to engine evidence and every uncertainty
is labeled.

### P8 - Institutional delivery and occupant evaluation

- Apply Controller clocks, authority, information, costs, and occupants to frozen
  economic experiments.
- Attribute the outcome gap to delivery and decision components.

Exit: human, heuristic, and RL comparisons share the same causal environment and do not
receive hidden information or privileged actions.

## P0 milestone acceptance evidence

P0 was accepted on 2026-08-22 on branch `audit/policy-causality-v38`. This is a
contract and inventory milestone only. It does not claim that any policy has passed a
dynamic causal experiment.

The generated P0 ledger reports:

- 102 Registry levers and 102 causal contracts;
- 12 decision groups and 21 activation fixtures;
- 11 canonical crises with explicit readiness classifications and a complete scenario
  role for every lever;
- 108 declared materiality metrics, all present in the current native reporting source;
- 28 closed failure classes;
- zero unowned, unmapped, unclassified, or validation-error levers.

The frozen component hashes are:

| Component | SHA-256 |
|---|---|
| Registry | `e7719fec39b8e8bad451bb5cb70329a4516bd41fa165032eafef318a3643c81d` |
| Contracts | `81e99e0e029ecfcbc00ec30b14921e168312ae2371dc77f5dc02d3dc0cd3edcb` |
| Activation fixtures | `3645ae23f5fb0c632dc56f435683ec2e3fb1683fee3791b37d3f326b87c053a8` |
| Scenarios | `fb73c66468d93a58bdff55a56a2e7eebf75eae2b54aa08c16429e25d04195bd5` |
| Materiality | `66482a1fd0012dd99997ce4a3fafd1a7cdf4ee39c8fccd7261547dfe14cf3055` |
| Failure taxonomy | `054bbeca2be2780c7926122b3a05c2b0b2bb081bed4bae89deaf707c1ac716d8` |
| P0 root | `384aa82b14de97de39668327fae57abb6fe22f41b794070ef36ba4b23a3f6b63` |

The acceptance gate is `tests/test_policy_causality_p0.py`, run together with the
existing Policy Registry and source-inventory gates. The combined focused suite passed
13 tests. The source-inventory count was refreshed from 370 to 368 after confirming that
the previously retired `symmetric_k` and `k_replacement_floor` fields were the exact two
field removals and that every remaining field is classified exactly once.

### P0 read-point amendment discovered in P1

P1 showed that the P0 Registry still named legacy Python read locations. The audit now
replaces those strings with the first verified native C++ read point, or with an
explicit native route defect. This is an evidence correction, not a treatment or
scenario change.

| Identity | Previous | Amended |
|---|---|---|
| Registry | `06d7196502c818bd19c9381b73419ff6947512edbe3b518dd227bce27d1632b8` | `e7719fec39b8e8bad451bb5cb70329a4516bd41fa165032eafef318a3643c81d` |
| Contracts | `cefbe666a42980c3caf69c247ef2fd47acad7aa152f894d9e788878f3a3da543` | `81e99e0e029ecfcbc00ec30b14921e168312ae2371dc77f5dc02d3dc0cd3edcb` |
| P0 root | `41e248e00a04d871d285e2072c09209426e03041e08229e87dff4df252e81a87` | `384aa82b14de97de39668327fae57abb6fe22f41b794070ef36ba4b23a3f6b63` |

No P0 dynamic evidence is invalidated because P0 produced inventory and contract
evidence only; the first dynamic native run belongs to P1.

## P1 milestone acceptance evidence

P1 was accepted on 2026-08-22 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_defects`. The formal smoke used one seed (`3801`), three
economies, 100,000 initial persons per economy, and eight native engine workers.

The generated route ledger reports:

- all 102 Registry levers have generated native storage routes;
- 99 levers have a verified first native economic read point;
- all 102 values can be projected as non-noops and become effective in one atomic
  next-day batch;
- invalid partial manual-rate and peg batches reject without mutation;
- the completed day remains immutable while a boundary is prepared;
- exact no-op replay leaves both policy generation and the economic trajectory
  unchanged;
- checkpoint restore and continuation are exact after preserving the native
  `PersonStore` live-order state.

The three explicit route defects are:

1. `fiscal_uses_national_accounts_gdp` is stored and checkpointed, but no fiscal
   mechanism reads it;
2. `mortgage_risk_weight` is stored and range-validated, but bank risk-weighted assets
   never read it;
3. `mortgage_min_capital_ratio` is stored and range-validated, but mortgage capital
   gating never reads it.

These rows are defects, not weak elasticities, and must be repaired or given a final
non-player disposition before P2 can accept their mechanisms.

The frozen P1 identities are:

| Component | SHA-256 |
|---|---|
| Native control contract | `b871cbf679516a6012658e715ab0b3e099d31076e387fa70bd69b8edaaae23a4` |
| Route ledger | `e1eb003349328505e77eee6b556824bba67959bf8e806231b4cb9bc9ce52948a` |
| P1 route-contract root | `d13edcc1b2e50d2a3865fd93aa2560e5f6dc8c2430ec5a6848b991dac5f02a4a` |
| Native smoke evidence | `820395e76f277519fc5e2369b7e1478c36ac185db8ed2db221a68d23811e3383` |
| P1 acceptance root | `90c73d1ba38c3a166f1f78aefd09f8ba48978ae56d5618c60afacaa30b7f46bc` |

The accepted run produced a 159,914,059-byte checkpoint and completed the audit smoke
in 24.96 seconds on the acceptance machine. All twelve boundary, rejection, no-op,
checkpoint, replay, and value-coverage checks passed. P2 ordinary-state and activation
effect experiments have not started.

Regression acceptance includes 18 focused Policy tests and all 74 native CTest targets.
The configured interpreter initially resolved two binding tests through an editable
install from another worktree; both passed when rerun against this worktree with isolated
module paths. The other 72 CTest targets passed in the original eight-worker run.

## 17. Artifacts and provenance

Generated results live under `artifacts/policy-audit/` and are not committed. Source
code, schemas, contracts, manifests, regression thresholds, tests, and this protocol
are committed.

Each run records:

- Git commit and dirty-tree digest;
- native build identifier and compiler settings;
- Policy Registry, Config schema, metric schema, and observation schema hashes;
- Config, initial Policy, world graph, and country-profile hashes;
- shock tape, checkpoint, and event-chain hashes;
- population, firm/bank densities, seeds, horizon, and worker count;
- staged action, accepted effective action, and actual first read boundary;
- daily or declared-frequency metric chunks;
- wall time, peak resident memory, warnings, and termination reason.

Required generated reports are:

1. `policy_inventory.json` and `.md`;
2. `p1_route_ledger.json` and `.md`;
3. `policy_contracts.json` and `.md`;
4. `activation_fixture_catalog.json` and `.md`;
5. `scenario_catalog.json` and `.md`;
6. `policy_scenario_matrix.json` and `.md`;
7. `single_policy_evidence.json` and `.md`;
8. `crisis_evidence.json` and `.md`;
9. `combination_evidence.json` and `.md`;
10. `scale_confirmation.json` and `.md`;
11. `final_acceptance.json` and `.md`.

The final report must separate `experiment completed` from `lever accepted`. Counts of
executed jobs, passing mechanisms, accepted player levers, known engine gaps, and
blocked scenarios are reported independently.

## 18. Stop, repair, and amendment rules

Stop a family before expensive runs when:

- the action never reaches the native read point;
- the activation fixture does not bind;
- the crisis fails its no-response validation;
- an invariant, replay, or checkpoint gate fails;
- the primary observable is missing or semantically wrong;
- worker count or output cadence changes the economic result.

Repair the earliest failed layer, rerun its local gate, and invalidate downstream
evidence produced by the defective build.

Protocol amendments must record the reason, affected contracts and scenarios, old and
new hashes, and which evidence is invalidated. Treatment levels, crisis definitions,
primary outcomes, materiality floors, and seed inclusion rules may not be changed after
results are inspected without such an amendment.

## 19. Definition of complete acceptance

The full audit is accepted only when:

1. all 102 levers have final contracts and dispositions;
2. every retained player-facing lever has a valid native route and activation result;
3. every canonical crisis used for efficacy has passed independent no-response
   validation;
4. every matrix cell required by its role has reproducible evidence;
5. all retained levers expose a meaningful strategic effect or are explicitly labeled
   activation-only, long-horizon, or expert-only;
6. costs, delays, trade-offs, spillovers, and withdrawal effects are visible;
7. no accepted conclusion depends on direct outcome manipulation, future leakage,
   treatment-dependent seed selection, legacy Python simulation output, or a broken
   invariant;
8. representative conclusions survive finite-size confirmation;
9. the final generated report contains no undocumented pending item;
10. the desktop free-policy path and Controller path agree on the economic effect of
    the same effective Policy state, after accounting for delivery timing and costs.

This definition permits an honest conclusion that a policy or crisis is not supported
by the current engine. It does not permit a silent control, an unvalidated crisis label,
or a favorable result constructed specifically for one lever.
