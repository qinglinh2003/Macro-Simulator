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
| Contracts | `1b0d2be256765ba82e296a12c5d016d1f181e7b4396abaac758c6eb182948014` |
| Activation fixtures | `3645ae23f5fb0c632dc56f435683ec2e3fb1683fee3791b37d3f326b87c053a8` |
| Scenarios | `fb73c66468d93a58bdff55a56a2e7eebf75eae2b54aa08c16429e25d04195bd5` |
| Materiality | `66482a1fd0012dd99997ce4a3fafd1a7cdf4ee39c8fccd7261547dfe14cf3055` |
| Failure taxonomy | `054bbeca2be2780c7926122b3a05c2b0b2bb081bed4bae89deaf707c1ac716d8` |
| P0 root | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |

The acceptance gate is `tests/test_policy_causality_p0.py`, run together with the
existing Policy Registry and source-inventory gates. The combined focused suite passed
13 tests. The source-inventory count was refreshed from 370 to 368 after confirming that
the previously retired `symmetric_k` and `k_replacement_floor` fields were the exact two
field removals and that every remaining field is classified exactly once.

### P0 amendments discovered in P1 and P2

P1 showed that the P0 Registry still named legacy Python read locations. The audit now
replaces those strings with the first verified native C++ read point, or with an
explicit native route defect. P2 then corrected `peg_anchor` from an invalid isolated
change to the atomic `(fx_regime=peg, peg_anchor=<economy>)` transition required by the
native boundary. These are evidence and treatment-contract corrections, not changes to
the economic engine.

| Identity | Previous | Amended |
|---|---|---|
| Registry | `06d7196502c818bd19c9381b73419ff6947512edbe3b518dd227bce27d1632b8` | `e7719fec39b8e8bad451bb5cb70329a4516bd41fa165032eafef318a3643c81d` |
| Contracts | `cefbe666a42980c3caf69c247ef2fd47acad7aa152f894d9e788878f3a3da543` | `1b0d2be256765ba82e296a12c5d016d1f181e7b4396abaac758c6eb182948014` |
| P0 root | `41e248e00a04d871d285e2072c09209426e03041e08229e87dff4df252e81a87` | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |

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
| P1 route-contract root | `385d738195f2260a57694c12293c1a267bf0fd3cc4221ffb47b489d5d5932906` |
| Native smoke evidence | `820395e76f277519fc5e2369b7e1478c36ac185db8ed2db221a68d23811e3383` |
| P1 acceptance root | `8d930386225337a1e5af100da92764d373d768356bb236160f4a095769c64d00` |

The accepted rerun produced a 159,914,059-byte checkpoint and completed the audit smoke
in 24.40 seconds on the acceptance machine. All twelve boundary, rejection, no-op,
checkpoint, replay, and value-coverage checks passed.

Regression acceptance includes 18 focused Policy tests and all 74 native CTest targets.
The configured interpreter initially resolved two binding tests through an editable
install from another worktree; both passed when rerun against this worktree with isolated
module paths. The other 72 CTest targets passed in the original eight-worker run.

## P2 milestone acceptance evidence

P2 was accepted on 2026-08-22 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_defects`. This milestone validates mechanism activation and
ordinary-state safety; it does not claim crisis efficacy, empirical calibration, or
long-run welfare optimality, which remain P3-P7 work.

The frozen experiment used:

- four matched seeds (`4201`, `4213`, `4231`, `4253`);
- 100,000 initial persons per country and eight native engine workers per session;
- four concurrent independent seed jobs;
- a 7-day burn-in, 7-day ordinary-state window, and 7-day withdrawal window;
- activation windows of 30, 90, or 365 days according to the preregistered mechanism
  horizon;
- three ordinary experiment groups and 48 activation groups, yielding 204 native run
  records; and
- no legacy Python simulator. Python only built specifications, branched native
  checkpoints, and reduced maintained native metrics.

All treatments were applied at the intended next-day boundary, every tested withdrawal
restored the policy value, all recorded values were finite, and no treatment arm failed
at runtime. The final ledger covers all 102 Registry levers with no pending disposition:

| Final disposition | Count |
|---|---:|
| Accepted in ordinary and activation states | 45 |
| Accepted in the activation state | 31 |
| Accepted but below player-facing salience | 1 |
| Accepted structural, long-horizon mechanism | 1 |
| Native route defect | 3 |
| Mechanism defect | 3 |
| Observable/cohort-evidence defect | 11 |
| Unsupported by the current activation state | 7 |

The 78 accepted mechanisms include several corrections to false negatives from the
first pass. Taylor coefficients were retested inside an actual Taylor regime; job
guarantee, strategic-reserve, subsidy, SOE, migration, and capital-flow levers received
their missing binding conditions; origin-owned migration policies were applied to the
origin economy; and asymmetric constraints were tested on the binding side. In
particular, `margin_ltv=0` eliminated margin balances in active seeds,
`bankrupt_persist=1` generated firm-default exits in all four seeds,
`mortgage_ltv_cap=0` eliminated new mortgages in all four seeds, and
`mortgage_foreclosure_ltv=0.5` increased foreclosures in all four seeds.

The three mechanism defects are:

1. `bank_capital_constraint`: credit and capital were active, but disabling the gate
   changed no declared observable;
2. `mortgage_arrears_floor`: foreclosures were active, but doses spanning 0, 1, 1.5,
   4, 10, and 100 changed no declared observable; and
3. `deficit_u_cap`: government consumption and the unemployment multiplier were active,
   but binding-side doses changed no realized fiscal observable.

The eleven observable defects are `bond_coupon`, `bond_maturity`,
`mortgage_underwriting`, `mortgage_dsti_cap`, `mortgage_stress_rate_addon`,
`housing_in_wealth_tax`, `firm_credit_min_dscr`,
`regulatory_firm_capital_haircut`, `regulatory_firm_inventory_haircut`,
`land_fee_share`, and `land_fee_stock_elasticity`. Nine are new-contract mechanisms for
which aggregate outcomes cannot prove cohort separation; the remaining two move the
trajectory outside their declared proximal observables.

The seven unsupported rows are `lolr`, `bank_resolution_fund`, `margin_max`,
`housing_permits`, `household_bankruptcy`, `bank_migrate_on_failure`, and
`unified_bank_rwa`. Their required direct event or binding state did not occur in all
four controls, so P2 does not mislabel them as dead mechanisms. The three P1 route
defects remain `fiscal_uses_national_accounts_gdp`, `mortgage_risk_weight`, and
`mortgage_min_capital_ratio`.

P2 also records four validation-contract defects that are independent of causal
efficacy: the Registry/native legal domains disagree for `import_quota`,
`immigration_cap`, `margin_ltv`, and `margin_max`. Experiments used values accepted by
both layers; the player-facing domains still require repair before freeze.

The frozen P2 identities are:

| Component | SHA-256 |
|---|---|
| P0 root | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |
| Experiment manifest | `880233514e3cba3ba02e5890eaf342cc3970d962c3b01540f32012b64af2ea7d` |
| P2 evidence | `3b6b2b8743ad9656ab802ff72bb7620c62dd345a262d73669a7252fce04a25b1` |
| P2 acceptance | `0a112ee71733089ade75d7916dda6ccf9cfdc0ec64b40bcb5484c716a425949c` |

The focused P0/P1/P2 acceptance suite contains 22 tests and passes in isolation. The
eight-worker native CTest run passed 72 of 74 targets directly. The two remaining
Python-binding targets were initially redirected by an unrelated editable install from
another worktree; both passed when rerun concurrently with `-S` and explicit paths to
this source tree, its native module, and the dependency site-packages. P2 stops here:
no P3 scenario is accepted or used for a policy-efficacy claim.

## P3 milestone acceptance evidence

P3 was accepted on 2026-08-22 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_defects`. This status accepts the scenario-library audit and
its exclusion boundary; it does not accept every declared crisis. P4 must use only a
crisis that passed all five P3 gates.

The formal experiment used:

- eight matched seeds (`5101`, `5113`, `5129`, `5143`, `5159`, `5177`, `5193`,
  `5209`);
- 100,000 initial persons per country and eight native engine workers per session;
- four concurrent independent seed jobs;
- 11 ordinary or structural state environments and 10 runnable crisis environments;
- a matched no-response control plus mild, moderate, and severe shock tapes for every
  runnable crisis and seed;
- checkpoint replay for the moderate arm of seed `5101` in every runnable crisis; and
- 168 fresh native run records with zero cache hits and no legacy Python simulator.

All 11 state environments passed in all eight seeds: `BASE_NORMAL`, `BASE_SLACK`,
`BASE_TIGHT`, `STRUCT_HIGH_POVERTY`, `STRUCT_HIGH_INEQUALITY`,
`STRUCT_LOW_PARTICIPATION`, `STRUCT_HOUSING_SHORTAGE`, `STRUCT_LOW_PRODUCTIVITY`,
`STRUCT_ENERGY_DEPENDENCE`, `STRUCT_POPULATION_AGING`, and
`STRUCT_EXTERNAL_IMBALANCE`.

The crisis gate results are:

| Scenario | Entry | Propagation | Severity | Recovery | Integrity | P4 disposition |
|---|---:|---:|---:|---:|---:|---|
| `CR_DEMAND_RECESSION` | pass | pass | pass | pass | pass | accepted |
| `CR_SUPPLY_STAGFLATION` | pass | pass | fail | fail | fail | excluded |
| `CR_ENERGY_EMBARGO` | fail | pass | fail | pass | fail | excluded |
| `CR_CREDIT_CRUNCH` | pass | fail | fail | pass | pass | excluded |
| `CR_PANDEMIC` | pass | fail | fail | pass | fail | excluded |
| `CR_NATURAL_DISASTER` | pass | pass | pass | fail | fail | excluded |
| `CR_TRADE_INTERRUPTION` | pass | fail | fail | pass | fail | excluded |
| `CR_PEG_PRESSURE` | fail | pass | fail | fail | fail | excluded |
| `CR_BANK_RUN` | pass | fail | pass | pass | pass | excluded |
| `CR_HOUSING_BUST` | fail | pass | fail | fail | fail | excluded |
| `CR_SOVEREIGN_STRESS` | blocked | blocked | blocked | blocked | blocked | excluded |

Only `CR_DEMAND_RECESSION` is frozen for P4. It passed entry, propagation, recovery,
and integrity in all eight seeds; its primary real-output loss was strictly ordered in
seven seeds and in aggregate, with mean peak losses of 1,651.78, 2,020.52, and 3,561.12
for mild, moderate, and severe tapes.

The excluded scenarios expose specific defects rather than missing generic coverage:

1. supply stagflation has nearly flat and non-monotone real-output losses across
   severity and does not recover under the declared rule;
2. the energy embargo does not produce the declared transaction-price entry response,
   and its unfilled-energy loss is explosively non-monotone across severity;
3. credit crunch never produces the declared firm-default propagation event;
4. pandemic never produces the declared poverty propagation response and has weak
   per-seed severity ordering;
5. natural disaster leaves its one-day capital-destruction shock reported as active at
   the terminal boundary, failing both recovery and integrity;
6. trade interruption produces the declared price-level propagation response in only
   two of eight seeds and has weak per-seed severity ordering;
7. peg pressure does not reliably move reserves or the exchange rate, and its primary
   loss is zero at every severity;
8. bank run never produces a bank-failure propagation event;
9. housing bust does not reliably move house prices or foreclosures, and its primary
   loss is identical at every severity; and
10. sovereign stress remains blocked because sovereign risk-premium/default
    transmission is absent.

Checkpoint replay is exact for demand recession, credit crunch, bank run, and natural
disaster. It is not exact for supply stagflation, energy embargo, pandemic, trade
interruption, peg pressure, or housing bust. Those replay defects are independent
integrity blockers even when another gate fails first. All captured series are finite,
all required accounting metrics are present, and all recorded accounting residuals
remain within their declared tolerances.

The formal pandemic run initially exposed a native lifecycle defect at seed `5159`:
a retired household could retain a nonzero deposit tail smaller than the accounting
tolerance, pass the tolerance check, and then fail the posting book's exact-zero close
contract. The commit path now transfers such tails through the rounding-residual
account before closing. A dedicated regression test passes, and the previously
deterministic 100,000-person, three-country, eight-worker severe-pandemic path now
completes. All eight formal pandemic seeds subsequently completed all four paths.

The frozen P3 identities are:

| Component | SHA-256 |
|---|---|
| Experiment source revision | `e096064df93af33c1e098106159eb7432cd20ce9` |
| P0 root | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |
| Scenario manifest | `6ca7fe558b659ea08738da080433b8dec1b27ae91cf148d8c266793429c50285` |
| P3 evidence | `0201ac50a650945f3d0077b492f4354a0f7c5b6cd4e947954c31e0ac8c8064b4` |
| P3 acceptance | `f7e8b218a8d989a31af8a89bc97c2b12fe0a5780953d2fd013c2ea0289721933` |

All 168 caches match the frozen source revision, population, and worker contract, and
the three report hashes reproduce from their canonical payloads. The focused P0-P3,
Registry, and source-inventory suite passes 33 tests. The eight-worker native CTest run
passes 72 of 74 targets directly. The remaining two targets were redirected by an
unrelated editable install from another worktree and both pass when rerun concurrently
with `-S` and explicit paths to this source tree, native module, and dependency
site-packages.

P3 stops here. No single-policy crisis efficacy experiment has been run, and no
excluded scenario may support a P4 efficacy claim until its earliest failed layer is
repaired and the full P3 gate is rerun.

## P4 milestone acceptance evidence

P4 was accepted on 2026-08-22 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_defects`. This accepts completion and reproducibility of the
single-policy crisis ledger. It does not mean that every policy is effective, that an
accepted policy improves every objective, or that any package is ready for player
recommendation.

The formal experiment used only the P3-accepted moderate `CR_DEMAND_RECESSION` tape
and its frozen per-seed checkpoints. It used:

- eight matched seeds (`5101`, `5113`, `5129`, `5143`, `5159`, `5177`, `5193`,
  `5209`);
- 100,000 initial persons, eight native engine workers per session, and four concurrent
  independent seed jobs;
- 102 Policy-to-Scenario cells: 27 primary, 46 secondary, 28 safety, and one not
  applicable;
- 63 runnable cells, 118 preregistered dose arms, and 168 crisis timing arms;
- an ordinary no-policy control, crisis no-policy control, policy-only negative
  control, and policy-plus-crisis treatment for each applicable immediate arm; and
- 2,304 fresh native branches, with no legacy Python simulator and no runtime,
  action-boundary, checkpoint, shock-tape, missing-metric, non-finite, or accounting
  integrity error.

The complete ledger is:

| Final P4 disposition | Count |
|---|---:|
| Accepted primary crisis efficacy | 4 |
| Primary effect present but no supported crisis benefit | 7 |
| Primary policy nonbinding in this crisis | 13 |
| Secondary effect detected | 20 |
| Secondary policy inactive in this crisis | 8 |
| Safety screen passed | 9 |
| Safety concern | 2 |
| Blocked by a frozen P2 defect | 24 |
| Blocked by the single-country scenario topology | 14 |
| Not applicable | 1 |

Four primary policies passed at least one preregistered paired benefit gate. The
reported effects below are difference-in-differences interactions relative to both the
ordinary policy-only path and the crisis no-policy path, not raw before-and-after
changes:

| Lever and tested arm | Supported primary benefit | Seed support | One-sided paired bound |
|---|---|---:|---:|
| `benefit_income_floor=0.20`, immediate | poverty rate lower by 0.387 percentage points | 8/8 | at least 0.354 percentage points |
| `pension_replacement=0.40`, immediate | poverty rate lower by 0.215 percentage points | 8/8 | at least 0.192 percentage points |
| `manual_policy_rate=0.001` with manual regime, immediate | unemployment lower by 0.0757 percentage points | 6/8 | at least 0.0175 percentage points |
| `gov_investment_share=0.02`, immediate | poverty rate lower by 0.0410 percentage points | 7/8 | at least 0.00730 percentage points |

These are partial efficacy findings, not unconditional endorsements. The meaningful
`benefit_income_floor` arm also increased unemployment by 1.55 percentage points in
all eight seeds, while the `pension_replacement` arm increased unemployment by 1.77
percentage points in all eight seeds. The accepted manual-rate and government-
investment arms passed only one of their three primary outcome gates. P5 must preserve
these adverse or uncertain outcomes as explicit package guardrails rather than hiding
them behind an aggregate score.

Two safety-role policies failed their screen. `energy_price_cap=0.10` reduced real
output by about 6.17 million units and raised unemployment by about 54.0 percentage
points in all eight seeds. `energy_rationing=household_first` reduced real output by
about 892,000 units and raised unemployment by about 1.35 percentage points in all
eight seeds; the `industry_first` arm also raised unemployment by about 0.330
percentage points in all eight seeds. These results apply to the accepted demand-
recession environment. They do not substitute for the excluded energy-crisis
validation that P3 still requires.

The seven primary policies with a detectable response but no supported benefit are
`gov_deficit_target`, `deficit_u_ref`, `benefit_replacement`, `min_wage`,
`inflation_target`, `monetary_regime`, and `r_neutral`. Thirteen other primary rows
were nonbinding at their preregistered doses in this crisis. This is a scenario-specific
finding, not evidence that those mechanisms are globally silent.

The 24 P2 defects remain upstream blockers. The 14 external policies remain blocked
because the only P3-accepted crisis contains one economy and therefore cannot identify
counterparty, exchange-rate, migration, remittance, sanction, or trade spillovers.
P4 does not manufacture evidence for those cells from an invalid topology.

The frozen P4 identities are:

| Component | SHA-256 |
|---|---|
| Experiment source revision | `4dbcefa5c0b0ee6e90c7f8923d3d1cbe319f5dfe` |
| Native `m11-release` extension | `2654ba58b61b4147f86bb7eea079d0cdd05b104d81cab4b9c7baf8e8000b9cd1` |
| P0 root | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |
| P4 manifest | `321339ec4e1eb0a12d1d67f22db816fe58167d10097197ad44455577e5456561` |
| P4 evidence | `9a4aba45036517eecb1e613b5a9436cc72b311ead65e37692021f74aa143abbd` |
| P4 acceptance | `38f3702aa2e45c8de274b15416a52e17b9d33bff2b390a8b5cc3ec3f546a8df2` |

A complete cache replay hit all 2,304 branches and reproduced the same acceptance
hash. The focused P0-P4 suite passes 33 tests with eight workers. The eight-worker
native CTest run passes 72 of 74 targets directly. The remaining two targets are
redirected by an unrelated editable install from the `config-audit` worktree; both
pass when rerun concurrently with `-S` and explicit paths to this source tree, its
`m11-release` native module, and this worktree's dependency site-packages.

P4 stops here. No policy package, alternative crisis severity, finite-size claim, or
P5 interaction result is accepted by this milestone.

## P5 milestone acceptance evidence

P5 was accepted on 2026-08-23 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_defects`. This accepts the completeness, integrity, and
reproducibility of the nine-package ledger. It does not recommend either executed
package, validate any package blocked by upstream evidence, or repair any P2 or P3
defect.

The frozen ledger contains nine preregistered packages. Only `recession_response` and
`poverty_and_employment` were eligible because they use the P3-accepted
`CR_DEMAND_RECESSION` scenario and only P4 arms with frozen evidence. The other seven
packages remain blocked by their required P3 scenarios; bank liquidity, bank
solvency, housing cycle, and debt sustainability also retain explicit P2 component
blockers. P5 did not substitute a different scenario or silently remove a broken
component to make any package executable.

Each runnable package used a five-factor, 16-run regular Resolution IV fractional
factorial design. Main effects are estimable, while the reported two-factor terms
remain alias groups except for one preregistered pair per package that was rerun as a
complete 2-by-2 follow-up. For every package and seed the experiment also ran the
moderate crisis control, five component ablations, mild and severe control/treatment
pairs, a withdrawal arm, and an accepted alternative initial-state control/treatment
pair. This produced 33 branches per package and seed, or 528 formal branches in total.

The formal run used:

- eight matched seeds (`5101`, `5113`, `5129`, `5143`, `5159`, `5177`, `5193`,
  `5209`);
- 100,000 initial persons, eight native engine workers per session, and four concurrent
  independent seed jobs;
- exact P3 crisis checkpoints and mild, moderate, and severe shock tapes;
- exact P3 `BASE_SLACK` and `STRUCT_HIGH_POVERTY` state checkpoints for alternative-
  baseline evaluation; and
- 528 fresh native branches with no legacy Python simulator and no runtime,
  action-boundary, checkpoint, shock-tape, missing-metric, non-finite, or accounting
  integrity error.

Both runnable packages received `package_guardrail_failure`; no package was accepted
for recommendation:

| Package | Supported outcome | Material harm or guardrail failure | Other robustness evidence |
|---|---|---|---|
| `recession_response` | mean poverty lower by 0.366 percentage points; cumulative real output higher by about 68,804 | mean unemployment higher by 1.30 percentage points; debt/GDP higher by 0.502 percentage points; deficit/GDP higher by 2.91 percentage points | severe-crisis output becomes harmful; alternative-state and withdrawal screens fail fiscal guardrails |
| `poverty_and_employment` | mean income Gini lower by 0.0789 | mean poverty higher by 0.314 percentage points; unemployment higher by 9.55 percentage points; debt/GDP higher by 1.25 percentage points; deficit/GDP higher by 9.52 percentage points; inflation higher by 0.0857 percentage points; cumulative real output lower by about 1.09 million | the Gini benefit repeats at all three severities, but alternative-state and withdrawal screens retain primary or guardrail harms |

Every listed material benefit or harm occurred in all eight matched seeds. These are
paired treatment-minus-control estimates at the preregistered statistic, not raw
before-and-after movements. The inflation guardrail is a signed upper-side screen; it
does not claim that lower inflation is always welfare-improving.

Component ablation shows that `benefit_income_floor` alone accounts for at least 100%
of each package's supported benefit under the preregistered dominance rule. The other
components therefore do not establish an indispensable package contribution. The
isolated `manual_policy_rate` by `gov_consumption_share` interaction is zero on every
declared package outcome. The isolated `tax_income_rate` by `benefit_income_floor`
interaction is materially adverse: it raises poverty by about 0.152 percentage
points, unemployment by 2.55 percentage points, deficit/GDP by 1.54 percentage
points, debt/GDP by 0.114 percentage points, and inflation by 0.0242 percentage
points, while reducing cumulative real output by about 406,000. This interaction is
not a recommendation.

The complete package disposition ledger is:

| Final P5 disposition | Count |
|---|---:|
| Package guardrail failure | 2 |
| Blocked by frozen P3 scenario evidence | 7 |
| Recommended package | 0 |

The frozen P5 identities are:

| Component | SHA-256 |
|---|---|
| Experiment source revision | `3c53b41b98fbae9a36ba9cb5506139668bc77aed` |
| Native `m11-release` extension | `2654ba58b61b4147f86bb7eea079d0cdd05b104d81cab4b9c7baf8e8000b9cd1` |
| P0 root | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |
| P2 acceptance | `0a112ee71733089ade75d7916dda6ccf9cfdc0ec64b40bcb5484c716a425949c` |
| P3 acceptance | `f7e8b218a8d989a31af8a89bc97c2b12fe0a5780953d2fd013c2ea0289721933` |
| P4 acceptance | `38f3702aa2e45c8de274b15416a52e17b9d33bff2b390a8b5cc3ec3f546a8df2` |
| P5 manifest | `37fef202cd9045cf7100e93465733a460f2fe87daa2e57f1e92f7039f23ed4f2` |
| P5 evidence | `3fcca4d0c9092f12ca3f0326d6b5487e18c717244cb8647270b934e3b1b4b543` |
| P5 acceptance | `26839f8523bbb508bf426b28cdc4afebf4688e1a220856e18eb48a5c56fb79c1` |

A complete replay hit all 528 cached branches, executed no new simulation branch,
and reproduced the same P5 acceptance hash. The focused P0-P5 suite passes 39 tests
with eight workers. The eight-worker native CTest run passes 72 of 74 targets
directly. The remaining two targets are redirected by an unrelated editable install
from the `config-audit` worktree; both pass when rerun concurrently with `-S` and
explicit paths to this source tree, its `m11-release` native module, and this
worktree's dependency site-packages.

P5 stops here. The two rejected packages and seven blocked packages remain explicit
inputs to future repair or redesign work.

## P6 milestone acceptance evidence

P6 was accepted on 2026-08-24 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_defects`. This status accepts a complete and reproducible P6
ledger, including its withheld claims and defects. It does not assert that every
planned million-person cell completed, repair the newly observed accounting defect,
or promote any P6 representative into a policy recommendation.

The frozen design covers one representative from each of the 12 P4 decision groups,
plus `mortgage_foreclosure_ltv` and `rental_eviction_arrears` as additional rare-event
mechanisms. Each runnable record is a matched control/treatment pair. The formal run
used:

- 100,000 and 1,000,000 initial persons;
- eight matched seeds (`5101`, `5113`, `5129`, `5143`, `5159`, `5177`, `5193`,
  `5209`);
- eight native engine workers per session and four concurrent independent records at
  each population size; and
- native in-memory cloning at one million persons, because the M8 serialized
  checkpoint ceiling does not admit a world of that size.

The frozen matrix planned 224 paired records, or 448 native branch paths. It completed
192 paired records and 384 branch paths. The remaining 32 paired records and 64 branch
paths are not missing evidence hidden by the reducer: they are explicitly classified
as `scale_execution_blocked`, and P6 makes no million-person effect claim for them.
The disposition ledger is:

| P6 representative disposition | Count |
|---|---:|
| Finite-size confirmed | 7 |
| Finite-size dependency | 3 |
| Scale execution blocked | 4 |

The seven effects confirmed across both frozen population sizes are
`benefit_income_floor`, `tax_income_rate`, `energy_price_cap`,
`manual_policy_rate`, `bond_finance_frac`, `omo`, and `bank_min_capital`. In each
case the declared proximal effect preserved its sign, passed the frozen materiality
gate, and had at least six of eight supporting seeds at both scales. This is a
mechanism-and-scale result, not an economic-welfare endorsement. For example,
`energy_price_cap` reliably lowers the transaction price and raises unfilled energy
demand; P6 does not reinterpret the latter as a benefit.

Three representatives are explicitly scale-dependent:

| Lever | Observed scale dependence |
|---|---|
| `gov_investment_share` | The action activated in 8/8 seeds at both sizes, but the declared public-capital and fixed-capital-formation contrasts were nonzero at 100,000 persons and exactly zero at one million; neither scale gate passed. |
| `bankrupt_persist` | Firm default and exit effects were material and sign-stable at both sizes, but the declared fixture-activation metrics were silent in all 16 seed-size cells; it therefore fails the complete mechanism gate. |
| `soe_efirm` | Energy transaction price preserved the expected sign in 8/8 seeds at both sizes, but the production contrast changed sign and had only 4/8 supporting seeds at 100,000 and 3/8 at one million. |

The four scale-execution blockers retain their valid 100,000-person evidence but no
one-million-person conclusion:

| Lever | Evidence boundary |
|---|---|
| `tariff` | Direct observation: four concurrent one-million-person records remained CPU-active and produced no record after more than 12 wall-clock hours. Its 100,000-person reference record took 47.245 seconds. |
| `fx_regime` | Conservative projection: it uses the same three-economy topology as `tariff`, and its 100,000-person reference record was slower at 49.252 seconds. |
| `mortgage_foreclosure_ltv` | Conservative projection: its 100,000-person reference record already took 280.881 seconds, more than five times the directly blocked tariff reference. |
| `rental_eviction_arrears` | Conservative projection: its 100,000-person reference record already took 159.594 seconds, more than three times the directly blocked tariff reference. |

Only the tariff limit is a direct one-million-person observation. The other three are
deliberately conservative projections from the directly observed blocker and the
frozen 100,000-person timings. They must not be cited as completed one-million-person
runs. This boundary prevents an unbounded audit from being mistaken for stronger
causal evidence and records a concrete native performance backlog for later work.

P6 also inventories all 13 count-first rare-event mechanisms from the runtime
contract. Four were eligible under P2: `bank_min_capital`,
`mortgage_foreclosure_ltv`, `bankrupt_persist`, and
`rental_eviction_arrears`. The latter two housing mechanisms inherit their explicit
scale-execution blockers. `bank_min_capital` is finite-size confirmed, while
`bankrupt_persist` retains the scale-dependent classification above. The other nine
mechanisms keep their frozen P2 blocker rather than receiving manufactured scale
evidence. Neither of the two completed rare-event comparisons materially changed
event incidence or per-person frequency, so the preregistered extra-seed long-tail
gate did not open and P6 executed zero tail records.

One underlying accounting-integrity defect remains explicit. In the
`mortgage_foreclosure_ltv` treatment at 100,000 persons and seed `5159`, maximum M4
conservation drift was `0.00011181086301803589`, above the frozen `0.0001` absolute
limit; the matched control passed, the action was applied, and no runtime error
occurred. The report contains both the seed-level defect entry and the representative
prerequisite entry for this same finding. P6 records but does not repair it, in line
with the milestone boundary. Integrity limits at one million persons scale from the
frozen 100,000-person absolute limits so that the allowed residual per person remains
constant; this avoids making the larger experiment fail merely because it contains
ten times as many agents.

The frozen P6 identities are:

| Component | SHA-256 |
|---|---|
| Experiment source revision | `3e4fcd1d9d26c32f0c7c1ada86e2e388873ca317` |
| Native `m11-release` extension | `2654ba58b61b4147f86bb7eea079d0cdd05b104d81cab4b9c7baf8e8000b9cd1` |
| P0 root | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |
| P2 acceptance | `0a112ee71733089ade75d7916dda6ccf9cfdc0ec64b40bcb5484c716a425949c` |
| P3 acceptance | `f7e8b218a8d989a31af8a89bc97c2b12fe0a5780953d2fd013c2ea0289721933` |
| P4 acceptance | `38f3702aa2e45c8de274b15416a52e17b9d33bff2b390a8b5cc3ec3f546a8df2` |
| P5 acceptance | `26839f8523bbb508bf426b28cdc4afebf4688e1a220856e18eb48a5c56fb79c1` |
| P6 manifest | `64c9af0a62ce6ac5384821d0ce9258b2dcfc404c9f942ae603f03b2f935319e7` |
| P6 evidence | `f8338da45aeda7fe1a6656b1a6dfcd85d5a15502a2c114e48595be83d0595e77` |
| P6 acceptance | `2558901f5fd9192b8b12ade4fb499dd2de64d8b36f4a929ceeebb4cf43c4a5fb` |

A complete replay hit all 192 available cached paired records, executed no new native
branch, and reproduced the same P6 acceptance hash. The focused P0-P6 suite passes 49
tests with eight workers. The eight-worker native CTest run passes 72 of 74 targets
directly. The remaining two targets are redirected by the unrelated editable install
from the `config-audit` worktree; both pass when rerun concurrently with `-S` and
explicit paths to this source tree, its `m11-release` native module, and this
worktree's dependency site-packages.

P6 stops here. P7 production acceptance, UI truthfulness, governance, and release
packaging have not started.

## P7 milestone acceptance evidence

P7 was accepted on 2026-08-24 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_defects`. This milestone freezes evidence boundaries and
player-facing policy provenance; it does not repair a P1-P6 defect, convert a tested
dose into an empirical optimum, or assert that every policy has a validated welfare
benefit.

P7 is a deterministic reducer over the frozen P0-P6 artifacts. It executed no native
or legacy Python simulation and performed no network fetch during acceptance. Its
reviewed source catalog contains 11 entries: ten original research or official
historical sources and one explicitly labelled research synthesis. Empirical
estimates, official historical references, evidence syntheses, and model-design
priors are stored as different claim bases and are never treated as interchangeable.

The frozen player-facing ledger covers all 102 Registry levers. Every row binds the
legal Registry domain, reference baseline, tested P2 doses, complete four-field
economic explanation, mechanism and trade-off metrics, P2/P4/P6 dispositions,
empirical source identifiers where available, a permitted claim scope, and an
explicit uncertainty label. The resulting UI boundary is:

| Player-facing surface | Count |
|---|---:|
| Complete policy explanations | 102 |
| Tested UI presets available | 78 |
| Presets withheld because of an upstream defect | 24 |
| Crisis manifests in the ledger | 11 |
| Crises accepted for policy-efficacy claims | 1 |

Registry domains remain runtime invariants rather than empirically calibrated safe or
optimal ranges. Available UI presets are the frozen P2 meaningful dose, or the last
available tested dose when no meaningful arm exists. They are labelled as general,
binding-state-only, expert-only, or long-horizon according to the P2 disposition. The
24 rejected P2 mechanisms receive no recommended preset and may display only their
economic definition and explicit implementation defect. Only
`CR_DEMAND_RECESSION` may support a scenario-specific efficacy statement; all other
scenario rows state that efficacy claims are not accepted.

P7 makes ten scoped comparisons between frozen model evidence and reviewed empirical
or historical references:

| Comparison | Frozen disposition |
|---|---|
| Government spending and output | Direction and monotonicity conflict |
| Income tax and output | Direction conflict |
| Benefits, consumption, and poverty | Scope mismatch and missing primary outcome |
| Minimum wage and employment | Qualitative tension with dose and outcome mismatch |
| Manual policy rate in recession | Model direction only; no empirical magnitude crosswalk |
| Open-market operations | Missing comparable long-yield outcome |
| Bank capital and new credit | Qualitative direction only; magnitude is non-monotone |
| Mortgage LTV and originations | Qualitative direction match at non-comparable extreme doses |
| Tariffs and imports | Direction and magnitude conflict |
| Demand-recession stylized facts | Partial match with a major horizon mismatch |

Four of those rows are elevated as explicit P7 findings. First, the short P2 spending
ratios change sign across dose: government consumption is negative at both frozen
doses, while public investment changes from negative locally to positive at the
meaningful dose. Second, the meaningful income-tax cut lowers both tax revenue and
real output, opposite the conventional expansionary direction. Third, OMO changes
reserves and flows but exposes neither a comparable long-term sovereign yield nor a
duration-adjusted purchase dose. Fourth, a 5 percent tariff raises model imports by
about 2.09 percent and a 25 percent tariff lowers them by only about 1.19 percent,
which conflicts with the direction and scale of the reviewed official tariff
evidence.

The accepted demand-recession path has the correct output-loss and unemployment
ordering, with a mean peak output loss of about 4.14 percent and a mean peak
unemployment increase of about 1.40 percentage points across the eight P3 seeds. Its
mean persistent recovery is only 28.25 days. P7 therefore treats the severe 2007-09
U.S. recession as a historical reference, not as a calibration target, and records a
substantial horizon and propagation mismatch.

The frozen P7 identities are:

| Component | SHA-256 |
|---|---|
| Reducer source revision | `c9b71435f009f938b70ae8d0084c76a5688fe5c6` |
| P0 root | `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6` |
| Policy explanation catalog | `922cf801970c974a57933bf4680108c1d79eecc7641411c2b7a3d597dc58d297` |
| P7 manifest | `5f5ef3ca606580c81d55d9c015c34d553df8547f54ed6283f5849899015e930e` |
| P7 evidence | `ad3e8e05f7d5f5cfe5a21453fda33e27230f4789f684287a791c45ddaaee09ae` |
| P7 acceptance | `c0107cee11076a681aa2f35363950beb9690b78f2adec46375bd3427209540af` |
| Generated JSON artifact | `a80c4f5f3f0a4d3c03217f0ebb8ae078bbe6b98db72096c0431c4b6787f74972` |
| Generated Markdown artifact | `6823e14d76209faab2cce32a89c2c993702c719de1b842c43d6df65b134376bc` |

Two consecutive formal reductions reproduced the same JSON and Markdown artifact
hashes and the same P7 acceptance hash. The focused P0-P7 suite passes 58 tests with
eight workers. The eight-worker native CTest run passes 72 of 74 targets directly.
The remaining two targets are redirected by the unrelated editable install from the
`config-audit` worktree; both pass when rerun concurrently with `-S` and explicit paths
to this source tree, its `m11-release` native module, and this worktree's dependency
site-packages.

P7 stopped at this boundary. P8 institutional-delivery and Controller-occupant
evaluation subsequently started and is recorded below.

## P8 milestone acceptance evidence

P8 was accepted on 2026-08-26 on branch `audit/policy-causality-v38` with status
`accepted_with_explicit_limitations`. It validates one representative institutional
delivery experiment and a common native occupant benchmark; it does not claim that
all occupants are competent, that the shipped RL artifact is native-trained, or that
the representative policy is welfare improving.

The delivery experiment reuses the frozen P3 `CR_DEMAND_RECESSION` checkpoint and
shock tape and the P4 meaningful `benefit_income_floor=0.20` action. Eight matched
100,000-person seeds each execute eight native paths, for 64 paths in total. Every
native session uses eight workers. The economic engine is C++; Python is restricted
to Controller institutional state, orchestration, and reduction. The legacy Python
economic simulator is not used.

The delivery paths and first effective policy boundaries are:

| Path | Effective boundary | Interpretation |
|---|---:|---|
| Crisis control | None | Frozen crisis without the policy action |
| Free immediate | 31 | Unrestricted economic-causality reference |
| Precommitted regular | 37 | Decision at boundary 30 plus seven-day implementation lag |
| Emergency | 32 | Public crisis disclosure at boundary 31 plus one-day emergency lag |
| Scheduled regular | 98 | First ordinary meeting at boundary 91 plus seven-day lag |
| Delayed regular | 128 | Delayed meeting at boundary 121 plus seven-day lag |
| Missed meeting | None | No action delivered |
| Recorded human ingress | 98 | Same released context and action as scheduled regular delivery |

All six preregistered delivery gates pass: effective boundaries match the Registry
contract, the human transport path has exact economic parity with the scheduled path,
no future or oracle value enters a decision, the free-policy paths exactly reproduce
the P4 result over the shared P8 metric projection, every branch reaches its expected
policy state, and all native integrity checks pass. The 112 Controller contexts carry
112 fixed-schema `oracle_daily_output` shells marked `access_denied`; exposed oracle
values, future releases, and future bulletins are all zero.

P8 found and repaired one real bridge defect before acceptance. Native shocks already
changed C++ economic state, but `ControlledSimulationSession` only sent legacy
ShockEngine trigger metrics to `DecisionScheduler`. A native demand crisis therefore
could not open an emergency Controller context. The native observation adapter now
projects disclosed native shock severities into the scheduler trigger contract, and a
regression test proves that the disclosure opens the expected emergency context. The
repair changes institutional delivery only; the frozen shock tape and P3/P4 economic
paths remain unchanged.

The first provisional P8 information audit also treated an `access_denied` oracle
schema shell as if it were an exposed value. That failed report was not accepted. P8
schema v2 separates denied oracle field identities from exposed oracle releases and
invalidates every provisional v1 P8 cache. No P0-P7 evidence is invalidated.

The paired delivery decomposition exposes a material policy trade-off. Relative to
the crisis control, immediate `benefit_income_floor=0.20` lowers the mean poverty rate
by `0.00386648` (about 0.387 percentage points; 8/8 seeds) and raises mean
unemployment by `0.0154510` (about 1.545 percentage points; 8/8 seeds). It also raises
the mean government-deficit-to-GDP ratio by `0.0165775` and increases cumulative real
output by `47,893` on average, although the output interval crosses zero and one seed
is negative. These are model responses under the frozen demand-recession scenario,
not empirical welfare weights.

Institutional timing is economically visible. The seven-day regular implementation
lag erodes the poverty improvement by about `0.000310915`; waiting from the
precommitted boundary to the ordinary meeting erodes it by another `0.00292268`; an
additional delayed meeting erodes another `0.000495228`. The recorded-human transport
gap is exactly zero for every outcome and every seed because it intentionally submits
the same frozen action; this proves ingress and timing parity, not human decision
quality. Ordinary Controller delivery reserves `1.25` administrative units and incurs
`1.17` adjustment cost; emergency delivery reserves the same administration and
incurs `1.755` adjustment cost.

The occupant benchmark evaluates heuristic, recorded-human hold, no-action, random,
and the shipped RL policy on the same eight-seed native
`fiscal_stabilization_v1` environment with released human-comparable observations.
The shipped artifact's action and observation vector contracts match, but its training
environment hash belongs to the pre-native backend and does not match the current
native environment. P8 therefore classifies it as an
`explicit_cross_backend_transfer_probe` and forbids an RL superiority claim. The
random occupant has the best mean discounted return in this small benchmark, while
the heuristic, hold, no-action, and transferred RL policies tie; no ranking is
promoted to a player-facing claim because the environment contract mismatch and lack
of participant data are explicit limitations.

The frozen P8 identities are:

| Component | SHA-256 |
|---|---|
| Experiment source revision | `25e7e68ff5b1791ad0310867d434bee4812a3a22` |
| P8 manifest | `3ddc6684b14fd40ff0bbc7533fc5020b4b0df3fa066e0c9a45deeaca6abbbc08` |
| P8 evidence | `d97a3ae98803f7a13c26a2e0a23ec3203549265a12a0d1a0c55293d17cf9b41d` |
| P8 acceptance | `49da53cbf12e9b4723494ae072a9dac81e97bebe81c0f7d4d27b712a923d3cf3` |
| Generated JSON artifact | `8de58cd32d922558c697640624e9191c76a4abddfa68bdfae506cd555ebe5eb6` |
| Generated Markdown artifact | `af9abfc5e1a29ea6faf9c5b9a1e29f232e89e7f5da5166fb04a2b105b82e25d4` |

Two consecutive formal reductions reused all eight frozen seed caches and reproduced
the same P8 acceptance hash. The focused P0-P8 suite passes 62 tests with eight
workers, and the P8/native-shock focused suite passes five tests. The eight-worker
native CTest run passes 72 of 74 targets directly. Its two failures are build-directory
commands pinned to the unrelated `config-audit` worktree's editable virtual
environment; both smoke programs pass when rerun concurrently with this worktree's
Python executable and explicit current source/native paths.

P8 stops here. The remaining work is not another audit milestone: it is repair of the
explicit P1-P7 engine defects, native retraining or formal migration of the RL policy,
and genuine participant studies if human decision-quality claims are desired.

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
11. `empirical_and_gameplay_freeze.json` and `.md`;
12. `final_acceptance.json` and `.md`.

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
