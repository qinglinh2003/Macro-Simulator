# Config causality and calibration audit v37

Status: P0-P3 complete; every executable Config field has a reviewed contract, all module and package screens are complete, and P4 million-person confirmation is in progress
Scope: the latest native C++ engine, not a historical Python model  
Branch: `audit/config-causality-v37`

## 1. Objective

This audit establishes that every player-relevant immutable Config input has a
real, directionally plausible, measurable effect in the native economic engine.
It precedes the Policy audit so that genesis conditions, institutional
capabilities, structural assumptions, live policy levers, shocks, and numerical
controls are not mixed into one experiment.

The final deliverable is not merely a sensitivity table. It is a causal contract
for every Config field:

1. the field reaches the native engine;
2. the field changes the mechanism stated in its economic definition;
3. the primary effect has the expected sign and a plausible magnitude;
4. important spillovers and trade-offs are observable;
5. the effect is robust across seeds, horizons, and large populations;
6. the field is either meaningful to players or deliberately hidden as an
   implementation control.

## 2. Meaning of "all modules enabled"

The playable baseline enables every completed, mutually compatible economic
module. It does not enable every boolean in the repository.

Some booleans select alternative model formulations, activate stress-only
mechanisms, or control diagnostics. Enabling all of them simultaneously would
not represent a neutral economy and can make causal attribution impossible.

The current baseline requires the following module families:

| Module family | Required baseline capabilities |
|---|---|
| Firms and accounts | full P&L, priced balance sheets, capital-service pricing |
| Firm dynamics | entry, exit, subscale exit, capital-firm entry |
| Banking and credit | banks, realized P&L, household credit, relationship lending |
| Interbank and runs | interbank market and bank-run mechanism |
| Securities | government bonds, firm equity, equity finance |
| Public sector | government and national accounts |
| Demography | fertility, mortality, household lifecycle, family transfers |
| Labor | persistent matching, fractional hours, second jobs, suspensions, search friction, relationship wages, job ladder, efficiency, participation |
| Housing | registry, resale, mortgages, underwriting, rental, construction |
| Energy | producers, household energy use, deprivation gauges |
| Distribution | consumption strata and sector switching |
| Open economy | trade, capital flows, and migration |

The static gate currently passes for all required module families and for all
three built-in country profiles.

The following examples are intentionally not part of the all-on baseline:

- `consumption_rationed_signal`: a stress experiment. Genesis stockouts can
  otherwise become a persistent demand shock.
- `symmetric_k`: an alternative capital formulation, not an additive module.
- `deposit_interest_arrears`: a contract treatment that needs its own banking
  stress scenario before becoming a baseline choice.
- `couple`: an internal world coupling state derived from open-economy
  capabilities, not a player-facing switch.

Every such exception must have an explicit disposition and activation test.

## 3. Canonical Config surface

The canonical M0 inventory contains 455 immutable inputs:

| Declaring type | Fields |
|---|---:|
| `Config` | 370 |
| `LifecycleHouseholdConfig` | 4 |
| `RelationshipConfig` | 12 |
| `SocialDynamicsConfig` | 35 |
| `World` | 34 |

The audit first separates these fields by ownership:

| Ownership | Meaning | Dynamic test |
|---|---|---|
| Gameplay structure / physics | immutable economic mechanism or behavior | causal treatment |
| Policy seed | initial value of a runtime Policy lever | excluded; tested in Policy audit |
| Shock | exogenous intervention definition | excluded; tested in Shock audit |
| Scale | population or institution count | scale-invariance and density test |
| Genesis transient | opening balance, price, stock, or expectation | convergence and washout test |
| Numerical / observability | tolerance, reconciliation, history, run control | invariance and reliability test |

The adjudicated P0 inventory reports:

| Disposition | Fields |
|---|---:|
| Native route confirmed | 209 |
| Native route missing or incomplete | 82 |
| Policy-owned; defer to Policy audit | 108 |
| Shock-owned; defer to Shock audit | 4 |
| Numerical or observability invariance | 20 |
| Deliberately fixed in the native engine | 12 |
| Superseded compatibility names | 16 |
| Derived values | 2 |
| Run control | 1 |
| Planned removal | 1 |

The 82 missing or incomplete routes are real implementation work; they are not
allowed to enter a dynamic run and be reported as small elasticities. The other
non-routed fields have been marked as exactly one of:

- `real_gap`: missing or incomplete native implementation;
- `native_fixed`: the latest engine deliberately fixes the behavior;
- `derived`: computed from other inputs and invalid as an independent treatment;
- `superseded`: retained compatibility name replaced by a canonical field;
- `run_control`: duration, seed, clock, or diagnostics rather than economics;
- `remove`: obsolete surface that should leave Config.

## 4. Economic module catalog

Dynamic treatments are organized into the following modules. This list is also
the reporting order, so effects are judged against mechanism-specific outcomes
before broad macro spillovers.

| Module | Primary outcomes | Important spillovers |
|---|---|---|
| Scale and genesis | per-capita output, price/wage normalization, convergence half-life | memory, throughput, finite-size variance |
| Production and technology | real output, productivity, capital stock, utilization | wages, prices, employment, investment |
| Firms and industrial dynamics | entry, exit, concentration, firm size and profitability | employment, output volatility, credit losses |
| Consumption, prices and expectations | consumption, inventories, markups, CPI and inflation | output gap, employment, household welfare |
| Labor market | participation, employment, unemployment, hours, vacancies and flows | wages, production, poverty, fiscal balance |
| Demography and households | births, deaths, age structure, household size and dependency | labor supply, consumption, housing demand |
| Distribution and welfare | poverty, income and wealth Gini, deciles, savings | consumption, labor participation, fiscal cost |
| Government and public sector | tax receipts, spending, deficit, debt, public capital | output, employment, inflation, distribution |
| Banking and credit | lending, deposits, spreads, arrears, capital and bank failures | investment, consumption, bankruptcies |
| Securities and capital markets | issuance, prices, returns, turnover and leverage | investment, wealth, financial fragility |
| Housing | prices, transactions, tenure, rent burden, mortgages, construction | wealth, consumption, fertility, credit risk |
| Energy | price, output, inventory, deprivation and reserves | CPI, production costs, poverty, mortality |
| Open economy | trade, current account, FX, capital flows, migration and remittances | output, wages, inflation, reserves |
| Numerics and observability | identities, deterministic replay, tolerance failures | no material economic effect expected |

## 5. Causal experiment design

### 5.1 Unit of intervention

One experiment changes exactly one immutable Config treatment before genesis.
The control and treatment share:

- the same engine commit and build;
- the same country profile and all non-treatment Config values;
- the same seed;
- the same population and institution densities;
- the same start date, horizon, world graph, policies, and shocks;
- the same worker count and reporting schedule.

This paired-counterfactual design removes most Monte Carlo noise. No-shock runs
measure endogenous transmission. A field that only operates under a particular
state receives a second, predeclared activation scenario.

### 5.2 Treatment levels

- Boolean: `false` versus `true`.
- Category: baseline versus every valid alternative.
- Positive numeric: central difference near the baseline, normally `-10%` and
  `+10%`, plus economically meaningful low/high levels.
- Bounded share or probability: symmetric movement in log-odds space where
  possible, so 0.01 and 0.99 are not treated as ordinary interior values.
- Zero baseline: a documented absolute step based on the field's unit.
- Count: coordinated density-preserving changes, not a lone count that changes
  the meaning of population scale.

Invalid or economically impossible combinations are rejected before simulation.

### 5.3 Scale and horizons

Small toy economies are not accepted as causal evidence.

| Stage | Population per country | Seeds | Horizons | Purpose |
|---|---:|---:|---|---|
| Wiring smoke | 100,000 | 1 | 90 days | crash, route and exact-no-effect detection |
| Screening | 100,000 | 4 | 1 and 5 years | effect sign, timing and broad magnitude |
| Confirmation | 1,000,000 | 8 | 1, 5 and 20 years | confidence interval and finite-size robustness |
| Rare-event stress | 1,000,000 | 16+ | scenario-specific | failures, tail risk and activation-only mechanisms |

The native engine uses eight workers for all full runs. Concurrency across runs
is limited so independent simulations do not oversubscribe the machine.

### 5.4 Estimands

For outcome `Y`, treatment `x`, seed `s`, and horizon window `h`, the audit stores:

- paired average treatment effect: mean of `Y_treatment - Y_control` by seed;
- relative effect for positive level variables;
- local elasticity: `d log(Y) / d log(x)` where defined;
- semi-elasticity for rates and bounded outcomes;
- for directionally heterogeneous market mechanisms, the paired absolute
  relative effect and the share of seed pairs above the predeclared materiality
  floor; this prevents opposite but material path responses from cancelling in
  a signed average;
- cumulative effect and area under the response curve;
- peak effect, time to peak, time to half-decay, and terminal effect;
- volatility and downside-tail effects;
- event-rate differences for bankruptcy, default, bank failure, migration, and
  demographic transitions.

Paired seed-block confidence intervals are the default. Time-series uncertainty
uses block bootstrap windows rather than treating every day as independent.
Screening across many field-outcome pairs reports false-discovery-adjusted
significance as supporting evidence, never as the sole gameplay criterion.

### 5.5 Causal decomposition

For important fields the audit records a mechanism chain, for example:

`productivity -> unit cost -> price/wage -> demand -> employment -> welfare`

The decomposition combines:

1. temporal ordering of maintained native metrics;
2. accounting decompositions such as GDP expenditure and income identities;
3. stock-flow decompositions for bank, firm, government, household, housing,
   energy, and external balance sheets;
4. sequential ablations of explicitly competing channels;
5. factorial interaction terms for joint treatments.

The report must distinguish a direct mechanism effect from equilibrium feedback.

## 6. Combination packages

Commonly co-moving Config treatments are tested only after their components pass
single-factor validation. Each package uses a fractional or full factorial design
that includes the single treatments and their interaction terms.

Initial packages:

1. Productive capacity: productivity, capital share, depreciation, investment
   adjustment, public-capital productivity, and TFP law.
2. Labor institutions: matching friction, search intensity, participation,
   wage adjustment, job ladder, second jobs, and suspension rules.
3. Credit architecture: bank competition, leverage dispersion, relationship
   lending, amortization, interbank, household credit, and bank runs.
4. Housing and family formation: supply response, transaction friction,
   mortgage availability, rent adjustment, leaving-home elasticity, and
   fertility-housing coupling.
5. Energy dependence: household energy need, production capacity, downstream
   intensity, inventories, hoarding, and deprivation transmission.
6. Firm dynamism: entry hurdle, entry rate, exit hazard, startup balance sheet,
   sector switching, and retooling loss.
7. Open economy: trade capacity, FX adjustment and friction, capital mobility,
   migration, remittances, and wage smoothing.

Policy values are held fixed in this phase. Tax-benefit, monetary, regulatory,
foreign-policy, and energy-policy packages belong to the subsequent Policy audit.

## 7. Acceptance criteria

### 7.1 Wiring

A gameplay field passes wiring when a nontrivial treatment changes its native
contract or genesis state and produces a deterministic difference in at least
one mechanism-proximal observable under its activation scenario.

A byte-identical or numerically identical trajectory is a failure unless the
field is classified as scale, genesis washout, numerical invariance, derived, or
superseded.

### 7.2 Economic realism

Each field has a predeclared expected direction, operating horizon, monotonicity
expectation, and plausible magnitude band. Empirical bands must cite primary
sources or explicitly state that they are model-design priors.

Failure classes:

- wrong sign;
- correct sign but implausibly weak;
- correct sign but explosively strong;
- effect arrives on the wrong clock;
- mechanism works but violates an accounting identity;
- only a genesis artifact is visible;
- sign changes without an economically explained regime transition.

### 7.3 Gameplay salience

Player-facing Config fields should create a recognizable strategic difference
without guaranteeing one dominant choice. A field is salient when at least one
primary outcome moves materially while at least one trade-off, cost, risk, or
time delay remains visible.

Silent player fields are not automatically amplified. The preferred resolution
order is:

1. fix a missing route or broken observable;
2. use a correct activation scenario;
3. merge or remove redundant fields;
4. hide expert/numerical controls from ordinary setup;
5. recalibrate magnitude only when the underlying economic channel is valid.

### 7.4 Stability and invariants

All accepted treatments must preserve finite values, deterministic replay,
conservation gates, accounting identities, valid entity references, and bounded
failure rates. Numerical controls must not materially alter economic outcomes
inside their certified operating range.

## 8. Findings to date

### 8.1 Product contract and routing

The native product baseline comparison now projects every one of the 209
currently routed Config fields into the exact C++ new-game contract at 100,000
persons per country:

| Native baseline relationship | Fields |
|---|---:|
| Exact semantic value | 189 |
| Representative-agent density scaling | 7 |
| Experiment scale override | 7 |
| Experiment seed override | 1 |
| Computed or unit-encoded value | 5 |

Two unexplained product drifts were found and repaired:

- `theta_equity` was 0.30 in Config but 0.25 in the native product;
- `marriage_assortativity` was 1.0 in Config but 0.25 in the native product.

`energy_hh_share` is not a drift: Config expresses an expenditure share while
the native rule stores physical need, so the bridge must apply
`share * wage / energy_price`. The experiment overlay previously skipped this
conversion and now preserves it.

The opening firm money, inventory, capital, expected demand, energy-producer
cash, and builder demand seed are density-scaled after product overrides. The
first experiment overlay wrote unscaled treatment values into an already scaled
contract. The corrected overlay preserves the native control multiplier. For
example, a +/-20% `K_firm0` treatment now changes actual opening capital by
exactly +/-20%.

### 8.2 Structural defects found by dynamic experiments

1. `a` reaches `linear_productivity`, but the playable product uses
   Cobb-Douglas consumption firms and therefore reads Hicks-neutral `A` instead.
   `a` is now classified as a compatibility field for the retired cash-loop
   vertical rather than a second player-facing productivity control.
2. Both dividend implementations had a large-population rounding defect. The
   securities path and the no-equity M4 fallback reconstructed a final payment
   from algebraic totals rather than the clearing account's actual remaining
   balance. At 100,000 households this could fail the sufficient-funds gate.
   Both paths now distribute a bounded real remainder and have native
   large-population regressions.
3. `necessity_share0` now reaches C++ genesis and changes the number of
   necessity firms, but a 0.50 to 0.80 treatment still produces an identical
   economic trajectory under equal tax rates. The native goods market lacks
   the old two-stage Engel mechanism (necessities first, discretionary goods
   second). This is a genuine mechanism-salience failure, not a route failure.
4. `lambda_I` is dormant while desired capital is below installed capital; the
   baseline initially remains on replacement investment. It is assigned a
   predeclared positive-capital-gap activation scenario rather than being
   reported as silent.
5. Lowering capital-goods productivity was rejected as an activation for
   `capital_rationed_signal`: it created a bottleneck that producers could not
   respond to, so disabling the expectations signal changed cumulative
   investment by only about 0.0000007%. Halving opening consumption-firm
   capital instead creates funded investment orders and unmet demand while
   retaining supply response. Under this common activation, disabling the
   signal lowers 90-day cumulative investment by 2.66%.

### 8.3 Production and technology early screen

The current early screen uses 100,000 persons, four paired seeds, 90 days,
eight native workers, and a 22-day burn-in. It is a timing and wiring screen,
not the final empirical calibration.

| Config | Observed causal response | Current decision |
|---|---|---|
| `alpha`, 0.25 / 0.35 | real GDP per capita about -31.7% / +40.1%; capital moves in the expected direction | live but probably too sensitive; inspect factor-income and price channels before calibration |
| `capital_firm_entry=false` | capital-firm count is lower, but the birth flow is unresolved over 90 days | extend to one and five years; do not infer from broad RNG divergence |
| `capital_market=false` | equity market capitalization and primary issuance fall 100% | direct capability effect passes; quantify real spillovers separately |
| `A`, -20% / +20% | real GDP per capita about -23.1% / +16.6%; price level moves oppositely | direction passes; asymmetry and magnitude require medium-run calibration |
| `a_K`, -20% / +20% | capital output about -8.2% / +5.9%; investment about -12.8% / +8.1% | direction passes, upper investment interval remains wide |
| `delta_K`, -20% / +20% | capital about +0.22% / -0.20%; investment about -12.0% / +13.7% | replacement and stock legs both pass |
| `K_firm0`, -20% / +20% | post-burn-in capital about -18.8% / +19.9% after correcting density scaling | genesis effect passes; multi-year washout remains to be measured |
| `tfp_drift_rate`, 0.6% / 2.4% annual | 90-day output effect is small and its interval crosses zero | inconclusive at this horizon; use the predeclared five-year trend estimand |
| `v`, -20% / +20% | investment about -27.6% / +154%; strong threshold asymmetry | live but highly nonlinear; map the capital-gap response surface |
| `lambda_issue`, 0.1 / 0.3 | first-window issuance about -87.7 / +38.7 per day; 90-day cumulative issuance -2,369 / +1,027, then convergence | valid adjustment-speed control; judge the expected direction on the first-window flow and report cumulative reversal and half-life as trade-offs |
| `capital_rationed_signal=false`, positive-capital-gap activation | cumulative investment -2.66%; paired 95% level interval -51,572 to -25,911 capital units; first difference day 7 | conditional mechanism passes; keep it out of a neutral no-gap screen |
| `lambda_I`, -20% / +20%, positive-capital-gap activation | cumulative investment -4.59% / +2.02%; low arm interval resolves, high arm interval crosses zero; response peaks in the first week | mechanism passes but is asymmetric and seed-sensitive; map the response surface before calibration |

The screen does not treat every changed metric as evidence. Capability switches
can alter conditional random-number consumption even before their event fires.
Acceptance therefore requires a predeclared mechanism-proximal metric and a
paired interval that resolves the expected effect. Small seed blocks use
Student's t intervals, and direction checks report `pass`, `fail`, or
`inconclusive` when the interval crosses zero.

### 8.4 Production and technology one-year screen

The one-year batch completed 72 native runs without a stability failure. It
uses the same 100,000-person, four-seed paired design and a 90-day burn-in.

- Moving `alpha` from 0.30 to 0.25 / 0.35 changes post-burn-in real GDP per
  capita by about -26.5% / +36.3%. The mechanism is live, but this response is
  too strong to accept without decomposing factor income, labor demand, prices,
  and the Cobb-Douglas normalization.
- Disabling capital-firm entry reduces one-year capital-firm births by 3.5 on
  average, with a paired 95% interval of -5.55 to -1.45, and reduces the mean
  capital-firm stock by 0.35%. The rare event channel is now resolved.
- Disabling capital markets removes equity capitalization and issuance and
  lowers post-burn-in real GDP per capita by about 10.1%. The direct ablation
  passes; the real-side magnitude still needs an equity-finance decomposition.
- A +/-20% change in `A` moves real GDP per capita by about -18.7% / +12.4%
  and the price level by +22.8% / -14.8%. Both directions pass, with material
  asymmetry.
- A +/-20% change in `a_K` moves capital output by about -10.2% / +6.5% and
  investment by -10.3% / +6.8%. Both arms resolve at one year.
- A -20% / +20% change in `delta_K` moves installed capital by +0.65% / -0.64%
  and investment by -7.16% / +1.78%. The signs pass but replacement investment
  is strongly asymmetric.
- A -20% / +20% opening-capital treatment still leaves aggregate capital about
  -17.8% / +17.5% apart after burn-in. Neither arm reaches half-decay in one
  year, so `K_firm0` remains a persistent-path initial condition rather than a
  demonstrated washout.
- A -20% / +20% change in `v` moves installed capital by -2.26% / +1.92%, but
  investment by -51.6% / +1.33%. The upper investment interval crosses zero;
  the control lies close to an accelerator threshold.
- `lambda_issue=0.1` lowers first-window primary issuance as expected. The 0.3
  arm raises early issuance but its one-year cumulative effect reverses and is
  imprecise. This confirms an adjustment-speed interpretation; a permanent
  positive cumulative sign would be an invalid acceptance criterion.

Expected-direction metrics are now automatically included in each contract's
primary time-path set, even when they are not part of the broad module metric
catalog. Washout checks require an observed half-decay; a merely smaller
terminal difference is reported as inconclusive.

### 8.5 Five-year trend and initial-condition screen

The targeted five-year batch completed 20 additional native runs, covering
36,500 simulated days without a stability failure.

- Reducing annual `tfp_drift_rate` from 1.2% to 0.6% lowers fifth-year real GDP
  per capita by about 4.1%; increasing it to 2.4% raises fifth-year real GDP per
  capita by about 9.4%. The paired direction resolves in both arms. The price
  level moves oppositely, by about +3.0% / -3.7% at the endpoint.
- The GDP response is larger than the mechanically accumulated TFP difference,
  indicating amplification through production, prices, labor, and capital. It
  is a live growth-rate parameter, not an undetectable annual drift, but the
  amplification must be decomposed before empirical calibration.
- A -20% / +20% `K_firm0` treatment reaches capital half-decay on day 1,593 /
  1,354 respectively. Fifth-year aggregate capital remains about -9.3% / +8.2%
  from control. Opening capital therefore changes a four-year-plus development
  path; it should be presented as a meaningful initial endowment rather than a
  harmless transient.
- Fifth-year real GDP per capita no longer differs precisely under either
  opening-capital arm even though the physical stock remains different. The
  long-run stock and flow implications must therefore be reported separately.

### 8.6 Firms and industrial dynamics screen

All 21 mapped causal or genesis fields in this module now have reviewed
contracts: 14 neutral-baseline contracts and seven conditional contracts. The
one-year neutral batch completed 104 native runs; the conditional screens added
72 runs. A final four-seed, 90-day closure for the two previously omitted
fields added 20 native runs. No run failed a native stability gate.

One invalid dependency closure was repaired before measurement. Disabling
`firm_dynamics` while founder-owned per-firm equity remained enabled violated
the Config contract. The shared capability cascade now closes per-firm equity
and its dependants explicitly. Effects of this master switch are consequently
reported as a capability package, not as a pure birth/death coefficient.

Current findings:

- Disabling firm dynamics removes 100% of observed births and exits and lowers
  post-burn-in real output by about 11%. The real effect includes the required
  founder-equity dependency closure.
- Disabling `firm_subscale_exit` removes all roughly 555 first-year exits. A
  half hazard lowers exits by about 27.2%, a double hazard raises them by 11.2%,
  a 90-day grace period raises exits by 18.8%, and a 365-day grace period lowers
  them by 98.2%. This is the dominant incumbent-exit mechanism and is highly
  salient.
- `subscale_viability_workers` changes neither total exits at 0.05 nor at 2.0,
  despite the baseline being 0.5. The same field also enters the capital-firm
  spin-off threshold and causes tiny capital-firm-count changes. This overloaded
  meaning should be split or recalibrated; its named viability channel is
  currently silent.
- Lowering the consumption-entry hurdle to zero raises first-year births by
  2.25 on average with a resolved interval; doubling the hurdle lowers births
  by 1.75 but the interval narrowly crosses zero. `entry_beta` has the expected
  average signs but remains imprecise with only about five baseline births per
  year.
- `entry_max=1/6` is exactly silent in the neutral economy because desired daily
  entry never reaches even one. Under a shared high-entry-pressure activation,
  it lowers/raises 90-day births by about 63%/61%; both intervals resolve. It is
  a valid conditional safety cap, not a neutral-economy growth control.
- Capital-entry hazard has the expected sign: halving it reduces the mean
  capital-firm stock by about 0.19%, while the upper arm remains imprecise.
  `k_entry_demand` is not monotonic over the tested ranges. The maintained
  metrics combine consumption- and capital-firm births, so a sector-specific
  capital-birth observable is needed before causal diagnosis is complete.
- Turning off the full cash-basis firm P&L changes trajectories, but the
  one-year cumulative interest and profit intervals both cross zero. The
  accounting channel is live but not yet gameplay-salient under normal credit
  conditions.
- `w_firm0` and `mu_firm0` violate their documented genesis-washout role. A
  +/-20% opening wage leaves the mean wage about -20.1%/+19.8% after burn-in;
  the high-wage arm lowers real output by about 8.1%. A 0.15/0.25 opening markup
  leaves average markup about -17.1%/+16.1%, with the largest difference at the
  end of year one. These behave as persistent nominal and pricing anchors, not
  temporary initial quotes.
- Opening expected energy demand does decay, although its lower arm rebounds
  after first crossing half-decay. Washout acceptance now requires both an
  observed half-decay and a terminal effect no larger than half the peak.
- `rho` was already wired into firm settlement but lacked a direct maintained
  observable. The engine now publishes `metric.source.m4.dividends_paid` and
  persists it through checkpoints. Relative to the 0.5 control, lowering the
  payout ratio to 0.1 cuts cumulative 90-day dividends by about 60.3%, while
  raising it to 0.9 increases them by about 60.5%. Both four-seed intervals
  exclude zero, so the retained-earnings versus shareholder-distribution
  channel is no longer hidden behind indirect household outcomes.

The neutral baseline produces no sector switches at all. Conditional tests
therefore isolate each switching input with a shared return-differential setup:

- `switch_hazard` and `switch_retool_loss` pass their direct event and destroyed-
  capital metrics;
- disabling the `sector_switching` master capability removes all 927.5 mean
  switch events and all 1.325 million mean capital units destroyed by retooling
  over the activated 90-day screen; both effects are -100%, with four-seed
  intervals excluding zero;
- lowering `switch_return_gap` to zero raises 90-day switches by about 812 on
  average, while 0.10 remains imprecise relative to the 0.50 control;
- shortening `switch_pressure_days` from the default 60 to 2/10 days raises
  switches by about 1,840/581. The original 30/120-day probe was exactly silent
  because return leadership reset before eligibility;
- `shell_exit_ticks=180/548`, under isolated idle-firm activation, changes
  two-year exits by about +249/-319, and the first differences occur on the
  declared threshold days.

The switching machinery is functional, but the default 50% return gap plus a
60-day uninterrupted pressure requirement effectively disables it. That is a
calibration and gameplay-salience failure even though stress activation passes.

### 8.7 Consumption, inventories, and prices screen

All 12 routed causal fields owned by this module now have reviewed contracts:
nine neutral-baseline contracts and three conditional contracts. The core
one-year batches completed 108 native runs at 100,000 persons; range and price-
proxy probes added 40 runs. All runs passed the native stability gates.

Before measurement, explicit module ownership was added for short mathematical
names and cross-module fields. Token fallthrough had incorrectly assigned, for
example, `delta` to consumption instead of labor and `lambda_p` to consumption
instead of securities. This did not change native routing, but it prevented
fields from being reviewed against the wrong economic outcomes.

Current findings:

- Moving the expected-income propensity `alpha1` from 0.95 to 0.90 / 0.99
  changes post-burn-in real household consumption by about -5.88% / +1.60%.
  Both intervals resolve, but the asymmetry means this is a strong behavioral
  assumption rather than a cosmetic household preference.
- The baseline wealth propensity `alpha2=5.5e-5` is weak over the ordinary
  half/double range: consumption moves only about -0.25% / +0.22%, with both
  intervals crossing zero. At `5e-4`, consumption rises 2.86% and the savings
  rate falls about 2.96 percentage points. The mechanism is live, but a useful
  player range must be materially wider than a local calibration interval and
  must expose the savings trade-off.
- Halving/doubling markup adjustment `eta` changes average markups about
  -18.4% / +37.2%. This is exceptionally strong and asymmetric. `eta` also
  controls energy-producer markup adjustment, so the current Config field is a
  cross-sector pricing regime rather than a consumption-only coefficient.
- `inventory_gap_close` and demand-learning speed `lambda_d` both have large,
  non-monotonic inventory effects. Their tested arms raise inventory-to-sales
  by roughly 40% to 174% relative to control. Faster permanent-income learning
  `lambda_y` changes consumption by +2.77% at the lower arm and -2.05% at the
  upper arm. These are adjustment-speed controls: a permanent level sign is not
  a valid contract, and the response surface needs calibration before exposure
  to ordinary players.
- Raising target inventory days `phi` from 14 to 17.5 raises inventory-to-sales
  about 72.2%, lowers real output about 3.73%, and raises unemployment about
  1.02 percentage points. Lowering it to 10.5 has a smaller and imprecise direct
  inventory effect but improves output and employment. `phi` also sets the
  energy-producer inventory target. The effect is salient, but probably too
  strong and too overloaded for one player-facing Config.
- A high Calvo repricing probability (`theta_price=0.0074`) raises post-burn-in
  inflation volatility about 588%; the lower arm remains inconclusive. The
  mechanism is live but highly nonlinear around the playable baseline.
- Markup ceilings and floors are valid conditional mechanisms. Under opening
  shortage pressure, `mu_max=0.20/0.22` changes average margins monotonically;
  under excess opening inventory, `mu_min=0.18/0.20` raises margins about
  5.0% / 9.9%. Both bounds also control energy producers, so they should be
  presented as economy-wide pricing institutions unless the fields are split.
- Enabling `consumption_rationed_signal` during a shared opening stockout raises
  inventory-to-sales about 70.1% and realized household consumption about
  0.31%, but lowers real output about 2.01%, lowers the price level about 0.87%,
  and raises unemployment about 1.48 percentage points. The signal is wired,
  but it over-amplifies stock rebuilding and remains a stress-only option rather
  than an all-on baseline capability.
- Increasing seller search from one offer to 2 / 8 offers changes the maintained
  household-spending-to-sector-sales price proxy by about -1.06% / -2.15%; only
  the eight-offer interval resolves. Samples of 2, 8, 16, and 64 raise native
  runtime by roughly 25%, 30%, 42%, and 166%, respectively, while measured price
  gains flatten. The ordinary range is therefore capped at eight. This proxy is
  not a true household unit value because the engine does not yet publish
  household goods quantity separately from total sector sales. A native
  household goods-quantity observable is required before final calibration.

Several fields are intentionally not credited with consumption causality.
`pref_attach_beta` and `pref_price_elasticity` remain among the 82 blocked native
routes, and `necessity_share0` reaches genesis but remains economically silent
because the native goods market has no two-stage necessity/discretionary Engel
allocation. These are implementation gaps, not small elasticities.

### 8.8 Labor-market screen

The labor inventory contains 26 Config fields. Twenty-one have native causal
routes and reviewed contracts: 15 neutral-baseline treatments and six
conditional treatments. Two fields (`suspension_quit_discount` and
`wage_indexation`) remain blocked native routes. The remaining three are
deliberate native invariants: persistent labor accounting, explicit matching,
and person-level efficiency.

`labor_accounting=false` cannot be treated as an ordinary all-module ablation.
The current energy, payroll, and household projections require persistent
person-job records, so disabling that vertical while retaining downstream
modules is not a coherent playable economy. It is now classified as a fixed
engine architecture choice rather than credited with a causal effect.

The final evidence set covers 180 native worlds at 100,000 persons. The core
neutral and conditional screens use four paired seeds, 90 days, a 22-day
burn-in, and eight workers. One-year paired runs resolve the wage-downward-
adjustment extremes. Every final run passed the native stability gates.

The experiments exposed and repaired a native labor-state defect. A suspended
employee could leave the labor force through the reservation-wage margin and
then be recalled despite no longer participating. Payroll subsequently
reported more household labor sold than participation capacity. Recall now
requires current participation, the M4 invariant identifies the precise
invalid projection, and a native regression preserves this rule.

Current findings:

- `efficiency_sigma` now owns a complete native route instead of silently
  leaving every person at efficiency one. Genesis residents and newborns draw
  deterministic mean-normalized lognormal efficiency, and the engine publishes
  its mean and standard deviation. At 100,000 persons, setting sigma to zero
  removes all dispersion; raising it from 0.35 to 0.70 raises the standard
  deviation by about 120.5%, while mean efficiency remains statistically
  unchanged near one. This also supplies the heterogeneity required by
  assortative marriage.
- Annual exogenous churn is strongly live. Moving `churn_annual` from 0.28 to
  0.14 / 0.42 changes 90-day churn separations by about -54.5% / +66.3%.
  Search intensity is also monotonic: 0.075 / 0.30 changes cumulative hires by
  about -1.76% / +5.22%. Removing matching friction raises hires by 13.1%.
- Fractional hours and second jobs currently form a dependency package.
  Disabling either removes all roughly 55,168 secondary labor-hours over the
  screen. The shared capability cascade now closes second jobs whenever the
  intensive margin is disabled, preventing invalid hybrid configurations.
- Suspensions are an active retention channel. Disabling them removes all
  roughly 2,632 suspension events. A one-day recall window lowers the average
  suspended stock by 78.9%, but increasing the timer from its 30-day baseline
  to 90 days is exactly silent over this screen. The upper threshold is above
  the duration of economically relevant suspensions and is not presently a
  useful ordinary player range.
- Demand-layoff speeds are highly salient. `lambda_fire=0.015/0.06` changes
  cumulative demand layoffs by about -68.4% / +112.6%, while
  `layoff_target_smooth=0.01/0.08` changes them by about -60.7% / +311%. These
  controls both govern firing adjustment and need a joint response surface
  before either is exposed as an independent gameplay choice.
- `layoff_band` is correctly conditional. It is unresolved in the neutral
  economy, where material contractions are rare. Under a predeclared hiring-
  boom-and-correction scenario, a 0.50 band lowers layoffs by 643.5 on average,
  or 86.1%, with a fully resolved paired interval. A zero band raises layoffs
  by 124.5 on average but remains seed-imprecise. The mechanism works as an
  employment-hysteresis buffer when the relevant state occurs.
- The baseline job ladder is effectively disabled by its 5% required wage
  premium: raising the threshold to 10% remains exactly silent. With a shared
  zero-premium activation, the baseline search intensity produces about 83,058
  job-to-job moves over 90 days. Disabling either the ladder or relationship
  wages removes all moves; moving ladder search intensity to 0.015 / 0.06
  changes moves by about -46.4% / +72.0%. The machinery is functional, but the
  default calibration suppresses an important labor-market flow.
- Raising the welfare-relative reservation markup from 1.0 to 2.5 lowers
  participation by 2.87 percentage points, creates about 65,351 welfare quits,
  lowers real output by 6.11%, and raises unemployment by 9.36 percentage
  points. A 0.5 markup is exactly silent because the reservation threshold no
  longer binds. Disabling endogenous participation under the same binding
  setup reverses these effects. This threshold is economically meaningful but
  too nonlinear to present without the outside option and wage distribution.
- Under the same binding reservation setup, lowering
  `welfare_quit_hazard` to 0.01 reduces welfare quits by 46.5%, raises
  participation by 1.56 percentage points, raises output by 4.26%, and lowers
  unemployment by 4.36 percentage points. Raising it to 0.08 nearly triples
  quits, lowers participation by 3.68 percentage points, lowers output by
  23.3%, and raises unemployment by 19.9 percentage points. The high arm is far
  too destructive for an ordinary calibration range.
- Wage adjustment is split between one live and one nearly silent control.
  Halving/doubling shortage adjustment `omega` changes mean wages by about
  -0.029% / +0.063%. Changing Calvo reset probability `theta_wage` to
  0.0055 / 0.022 changes post-burn-in wage volatility by about -48.6% / +106.8%.
  By contrast, the complete legal range of downward adjustment `delta=0/0.0099`
  moves one-year mean wages by only +0.031% / -0.011%; the upper interval still
  crosses zero. `delta` reaches the engine but is gameplay-negligible at its
  current scale and should be rescaled, combined with wage-reset timing, or
  hidden as an expert parameter.

The labor screen therefore distinguishes three different problems that a raw
"changed metric" count would hide: missing routes, functional mechanisms whose
default thresholds suppress all events, and live coefficients whose accepted
range is economically too weak or too destructive. Calibration must repair the
latter two without weakening the native state invariants.

### 8.9 Demography and household-lifecycle screen

The demography inventory currently has 14 executable Config contracts. The
core final screen covers 96 native worlds at 100,000 persons: four paired seeds,
365 days, and eight native workers. Age-threshold contracts use separate
lifecycle horizons because a one-year screen cannot identify the age at which a
child leaves home.

The screen found and repaired two causal-identification defects before crediting
any result. First, changing mortality also changed the stable genesis age
distribution, so lower mortality created an older opening population and could
raise near-term deaths. Experiments now freeze genesis vital rates and vary only
runtime hazards. Second, every native person previously had efficiency one,
making the marriage-assortativity coefficient mathematically silent. The new
person-efficiency route and observables separate this matching mechanism from
marriage incidence.

Current findings:

- Fertility and mortality are live with clean directions. Moving total
  fertility from 1.6 to 1.0 / 2.2 changes annual births by about -37.4% /
  +37.7%. Moving the mortality multiplier from 0.85 to 0.50 / 1.50 changes
  deaths by about -36.4% / +66.0%. Disabling the legacy demographics package
  removes both flows and now consistently disables its dependent marriage,
  divorce, and leaving-home capabilities.
- Marriage and divorce incidence respond almost proportionally to their annual
  hazards. Halving/doubling the marriage rate changes new marriages by about
  -50.0% / +101.5%; halving/doubling the divorce rate changes divorces by about
  -48.8% / +94.0%. Disabling either capability removes its corresponding event
  flow.
- `demographic_marriage_market_interval_days` is not an economic gameplay
  parameter. Moving the clearing cadence from 30 days to 14 / 90 days changes
  annual marriage incidence by only about +0.84% / +0.15%, with both intervals
  unresolved. Its hazard is already interval-adjusted, so this field is now
  treated as a numerical-cadence equivalence contract rather than a required
  nonzero causal effect.
- Assortative matching is strongly live without changing the number of
  marriages materially. Setting its weight from 1 to zero raises the mean
  absolute partner log-efficiency gap by about 893%; raising it to four lowers
  that gap by about 48.5%. Both four-seed intervals exclude zero. The mechanism
  changes who marries whom, not the aggregate marriage hazard.
- Leaving-home capabilities and rates are live under an eligible-cohort
  scenario. Disabling the capability removes all departures. Halving/doubling
  the late-age hazard changes departures by about -43.9% / +90.1%; the same
  treatment on the peak-age hazard changes them by about -49.6% / +83.2%.
- The minimum leaving age requires a long horizon but is highly salient: in a
  provisional ten-year 100,000-person run, moving the threshold from 21 to 18
  raises cumulative departures by about 558%, while moving it to 26 lowers them
  by about 95%. Multi-seed confirmation remains required.
- The endpoint of the peak leaving-age band is live but weak. The original
  ten-year design was invalid because no genesis child crossed the 30/35-year
  endpoints. In a corrected twenty-year eligible-cohort scenario with lower
  shared departure hazards, moving the endpoint from 30 to 26 / 35 changes
  cumulative departures by about -2.64% / +1.45%. These are single-seed
  mechanism checks, not confidence-qualified estimates; the field is unlikely
  to merit a prominent gameplay control at its current salience.

`demographic_lifecycle_consumption` remains a real semantic native gap. The
Python Config defines finite-life consumption budgeting, while its historical
native assignment only toggled household moves after marriage, divorce, and
leaving home. The audit now blocks this field instead of falsely crediting that
unrelated assignment as an implemented route.

### 8.10 Distribution and private household support screen

The distribution inventory contains only two executable economic Config
contracts: the family-transfer capability and its donor reserve buffer. Two
additional inputs, the `deprivation_gauges` switch and the `subsistence_share`
poverty-line standard, are observation-only. The
remaining seven fields are blocked until their intended native mechanisms are
implemented.

The family screen covers 16 native worlds at 100,000 persons: four paired
seeds, 365 days, and eight native workers. Its current findings are:

- Disabling `family_transfers` removes the private kin safety net exactly.
  Cumulative transfer value falls by 17,434.7 currency units and cumulative
  recipient-days by 54,649.3, both -100%, with four-seed confidence intervals
  excluding zero. The direct mechanism is therefore fully live.
- The macro effect is small at the current scale. Disabling the mechanism raises
  mean post-burn-in relative poverty by 0.047 percentage points (about 0.25%
  relative). Real household consumption falls by about 0.14%, but its
  confidence interval crosses zero; income-Gini changes are also unresolved.
  Private transfers currently insure individual liquidity shortfalls without
  materially moving aggregate demand or measured inequality.
- Lowering `family_transfer_buffer` from 1.5 to 1.0 raises cumulative transfer
  value by about 0.33% and recipient-days by about 0.68%, both resolved. Raising
  it to 3.0 lowers those measures by about 0.59% and 0.63%, but the four-seed
  intervals cross zero. The coefficient has the intended sign but is too weak
  and noisy to deserve a prominent gameplay control at its present scale.
- A separate 16-world measurement screen uses a shared zero-year measurement
  burn-in for identification over 90 days; it does not change the product
  calibration. Disabling `deprivation_gauges` removes an 18.6% below-
  subsistence reading and all related spell stocks. Real output, unemployment,
  and household consumption remain exactly bit-identical across all four paired
  seeds.
- `subsistence_share` had previously been mis-owned by the securities module
  because of the generic word "share." It is the external poverty-line anchor,
  not a portfolio parameter or behavioral input. Moving it from 0.50 to 0.25
  lowers the classified below-subsistence share by 5.72 percentage points;
  moving it to 0.75 raises it by 17.96 percentage points. The same three
  economic series remain exactly invariant. Both measurement controls belong
  in diagnostics or methodology settings rather than the economy setup screen.

Static review also found two false-positive native routes. `consumption_strata`
is defined by Config as a sequenced necessity/luxury goods market, but the
native member currently only gates sector switching and preserves a tax tag.
`necessity_share0` is defined as a fixed per-need-unit necessity quantity, while
the native member controls the fraction of consumption firms tagged as
necessity producers. Both are now blocked as semantic gaps instead of receiving
credit for unrelated effects. Together with missing MPC dispersion, MPC wealth
curvature, firm-share normalization, and stratum multipliers, this means the
full distribution-to-demand feedback loop is not yet native-complete.

### 8.11 Banking and credit screen

The banking inventory contains 26 executable causal Config contracts and one
genesis-only capitalization field. Nine additional fields are blocked by
semantic native gaps. The final causal screen covers 200 native worlds at
100,000 persons: four paired seeds, 365 days, and eight native workers. Eleven
contracts run against the neutral product baseline; fifteen conditional
contracts use shared capital, entry, deposit-migration, or run-pressure states.

Static review found three routes that had previously received false credit.
`bank_enabled` does not yet behave as the master credit capability promised by
Config: its bridge closes selected dependent features while settlement banks
and ordinary firm lending remain active. `monetary_direct_transmission` promises
investment user-cost, household debt-budget, and firm debt-service channels,
but native currently implements only the firm debt-service screen.
`bank_assignment="random"` is actually deterministic round-robin assignment;
the canonical `"by_size"` spelling was also incorrectly compared with
`"size"` in two native bridges. The spelling defect is fixed, while all three
fields remain blocked until their full semantics are implemented. The other
blocked fields are household interest arrears, the four investment-user-cost
parameters, and the market-information weight in run behavior.

Current causal findings are:

- Firm-loan amortization is clean and monotonic. Halving/doubling its daily
  rate changes cumulative principal repayment by about -39.9% / +65.9% and
  the post-burn-in loan stock by about +6.0% / -8.8%. Household amortization
  has the expected direct repayment effect (-6.4% / +12.4%); only the faster
  arm produces a resolved debt-stock reduction, about 2.2%, because household
  refinancing and liquidity constraints weaken the low-arm stock response.
- Credit competition is live but uneven. Disabling lender-rate competition
  raises cumulative loan interest by about 4.4%, while the aggregate
  origination effect is unresolved. Removing relationship lock-in first
  diverges after roughly two months but its one-year credit and interest
  effects remain seed-imprecise. Increasing lender search breadth from two to
  eight lowers cumulative interest by about 6.8%; reducing it from two to one
  is exactly silent. The lower search range should not be exposed as a
  meaningful player choice.
- Loan-spread dispersion is highly salient through borrower selection. Moving
  it from 4.47e-5 to zero / 1e-4 changes cumulative interest by about +38.4% /
  -50.1%. This is not a generic claim that volatility is beneficial: with
  active search and an unchanged mean, greater dispersion gives borrowers a
  lower tail from which to select.
- A 0.000134 daily deposit rate raises annual deposit interest by about 174,530
  currency units and lowers mean bank capital by about 34.7%. A shared positive
  carry scenario confirms that disabling realized bank P&L removes all deposit
  interest and drives the legacy payout path to roughly 99.6% lower mean bank
  capital. The accounting regime is therefore consequential and should not be
  presented as an innocuous numerical option.
- Deposit-offer dispersion activates account migration and approximately
  272 million currency units of cumulative interbank funding in this screen.
  With that shared reserve mismatch, disabling interbank settlement removes all
  funding; adding a 0.000134 base spread raises the realized interbank rate by
  about 50.7%; moving tightness from 0.00137 to zero / 0.005 changes it by about
  -1.6% / +4.3%. Deposit search from two to one / eight changes cumulative
  interbank volume by about -100% / +118%.
- Household credit is a strong extensive-margin capability. Disabling it cuts
  the post-burn-in household debt stock by about 50.2% and cumulative total
  originations by about 23.0%, while firm credit remains active. Moving the
  underwriting subsistence share from 0.5 to zero / one changes household debt
  by about -1.4% / +3.5%; its aggregate-origination effect is too noisy to
  resolve. Allocating bank interest equally rather than by deposits moves mean
  income Gini by only about -0.0005 with an interval crossing zero.
- Bank-entry controls require low shared incumbent capitalization and an
  affordable founder stake. Under that predeclared state, disabling bank
  dynamics removes all entries. Moving entry sensitivity from 0.02 to 0.005 /
  0.08 changes cumulative births by about -71% / +65%. Moving the daily entry
  cap from one to zero removes first-window births; raising it to four increases
  first-window entry intensity by about 242%, although the market later
  converges to a similar saturation count. It is an adjustment-speed ceiling,
  not a long-run bank-count target.
- Bank leverage matters only when capital capacity binds. Reducing appetite
  from ten to five lowers first-window new credit by about 5.0% and the loan
  stock by about 3.8%. Raising it to fifteen is unresolved and economically
  negligible, indicating saturation above the product baseline. Raising
  cross-bank leverage dispersion from 0.6 to one lowers the post-burn-in
  aggregate loan stock by about 7.0%; removing dispersion is unresolved. These
  coefficients change allocation and risk capacity, so their long-run
  aggregate sign must not be hard-coded from the immediate lending channel.
- Runs are functional conditional mechanisms. Disabling them removes all
  flight. Under a moderate capital-pressure state, lowering run sensitivity
  from eight to 0.5 reduces cumulative flight by about 41.8%; raising it to
  sixteen adds only about 5.2% and is unresolved, showing upper-range
  saturation. The first difference occurs around day 241. Raising the bank
  health reference from 0.1 to 0.3 increases flight by about 331%, while 0.05
  removes it. Raising fear persistence from 0.952 to 0.99 increases flight by
  about 94%; the lower arm is directionally negative but unresolved.
- Deposit-interest arrears now have their own maintained native observable.
  Under a deliberately extreme 0.5% daily funding-cost stress, enabling the
  memo account produces a mean unpaid stock of about 3.96 million instead of
  silently discarding the obligation. This proves the accounting route; the
  activation rate is a stress instrument, not a plausible calibration target.

The banking screen therefore finds a largely functional core, but it also
identifies several gameplay problems: flat upper or lower ranges, rare-state
controls that need explicit context, and capability labels whose native
semantics are incomplete. Calibration should narrow the ordinary search,
leverage, and run-sensitivity ranges and keep entry, arrears, and run controls
in expert or scenario setup surfaces unless their triggering state is visible.

### 8.12 Government and public-capital screen

The public-sector inventory contains two executable causal Config fields and
two blocked structural fields. The formal dynamic screen covers 20 native
worlds at 100,000 persons, four paired seeds, 1,095 days, and eight native
workers. A preceding one-year screen was retained as horizon-selection evidence
but is not used for the final slow-stock conclusions.

Static execution review revoked false route credit from `government`. Config
defines it as the master fiscal-sector capability, and both the diagnostic and
desktop bridges can clear the capability bit, but the only current physical-
capital vertical requires that bit and rejects the resulting specification
before genesis. A government-off economy is therefore not executable.
`jg_productivity` is also blocked: the Config contract says job-guarantee public
works add public capital, while no native member or equation receives it.

The two working public-capital parameters behave as follows:

- The baseline daily public-capital depreciation rate of 0.000228 is about 8.0%
  compounded annually. Moving it to 0.000057 (about 2.1% annually) raises the
  three-year post-burn-in public-capital stock by about 5.5%; moving it to
  0.000912 (about 28.3% annually) lowers the stock by about 19.6%. Both stock
  directions are resolved, while public investment flow is unchanged. This is
  clean evidence that the stock law, rather than procurement, causes the
  contrast.
- Despite that large stock range, the same depreciation treatments do not
  resolve changes in real GDP per person, output, unemployment, prices, fiscal
  spending, or the deficit over three years. The largest point estimate for GDP
  per person is only +0.25%. At the present public-investment path and elasticity,
  depreciation is physically active but nearly silent in the playable macro
  economy.
- Moving the public-capital output elasticity from 0.10 to 0.20 raises
  post-burn-in real GDP per person by about 1.14%, real output by 1.19%, and
  lowers unemployment by about 0.32 percentage points. Mean wages rise about
  0.14%. Government spending rises about 1.21% and real government consumption
  about 2.69% through the endogenous fiscal-output reference; the public-capital
  stock itself has no resolved change.
- Setting the elasticity to zero produces the expected negative point response:
  GDP per person falls about 0.59% and output about 0.60%. Its four-seed interval
  narrowly includes zero, so this lower arm is directionally consistent but not
  formally resolved. The one-year panel was weaker still, confirming that this
  mechanism must be assessed as a slow stock-productivity channel.

The current calibration is economically coherent but weak as gameplay. Public-
capital elasticity is live and modestly salient at the upper arm; depreciation
mostly changes an invisible stock. The later interaction stage must estimate
`gov_investment_share x public_capital_gamma x public_capital_depreciation`.
Until that response surface is known, the depreciation rate belongs in expert
setup rather than a prominent player control, and it should not be made salient
by adding an artificial direct GDP effect.

### 8.13 Securities and capital-market screen

The securities inventory has 21 executable causal fields, one denomination
invariance field, two deliberately fixed invariance choices, one superseded
compatibility name, and six genuine native route gaps. The gaps are
`equity_ema_lambda`, `lambda_q`, `q_invest_cap`, `q_invest_floor`,
`q_invest_smooth`, and `wealth_effect`. In particular, `lambda_q` is not
credited merely because C++ uses a similarly named equity-price smoother: its
Config definition is a Tobin-q-to-real-investment sensitivity and no native
real-investment equation consumes it.

The working fields were evaluated in four paired 100,000-person seeds with
eight native workers. Eighteen direct mechanisms use a 90-day screen (116
worlds); `w_chartist` and `w_fundamental` use a 365-day price-dynamics screen
(20 worlds); `trend_lambda` uses a 365-day high-chartist activation shared by
control and treatment (12 worlds); and `shares_per_firm` uses a 90-day
denomination-invariance screen (12 worlds). Every direct direction check
passes. The three directionally heterogeneous price-feedback fields pass the
separate practical gate: at least 75% of paired paths move by at least 0.1% in
absolute relative volatility, while their signed average remains explicitly
reported as state-dependent rather than being given a false universal sign.

Two implementation defects were found and repaired before the final screens:

1. Bank equity valuation read the current day's scratch P&L before that P&L
   was closed, resetting the income signal to zero every tick. It now reads the
   prior committed bank P&L, and `bank_equity_lambda` moves bank fundamental
   value by about -72% at 0.0005 and +273% at 0.01 relative to the product
   baseline.
2. C++ household equity demand normalized fundamental and trend signals only
   across a watchlist. Common valuation or momentum signals therefore changed
   relative weights but cancelled from the household's aggregate equity target.
   The native engine now applies average signal pressure to the total target
   equity share, with a bounded unlevered cap and a safe zero-attractiveness
   sell path. This restores the stabilising fundamentalist and momentum
   feedback channels without adding a new market loop.

The new maintained observables separate stocks and flows that aggregate market
value concealed: household and bank bond market values; household firm- and
bank-equity market values; firm and bank equity turnover; and firm and bank
fundamental values. They make it possible to test ownership, market activity,
and valuation independently.

The principal causal results are:

- Government bonds are live. Removing `bonds` eliminates household holdings,
  bank holdings, and outstanding face value. Moving `bond_theta` from 0.15 to
  0.02 lowers household holdings by about 44.9%; moving it to 0.40 raises them
  by about 13.1%. Removing bank bond appetite removes all bank bond holdings,
  but increasing appetite from 0.03 to 0.15 adds only about 0.27%, a real
  supply-cap saturation rather than a silent route.
- Bank equity is fully modular: disabling the capability removes capitalization,
  household positions, and turnover; disabling only trading removes turnover.
  Moving `bank_theta_equity` from 0.10 to 0.02 or 0.25 changes bank market
  value by about -1.28% or +2.31% and turnover by about -80% or +148%.
- Firm equity has distinct funding, ownership, leverage, and trading channels.
  Disabling equity finance removes primary issuance; disabling per-firm equity
  removes market capitalization and turnover; disabling margin credit removes
  margin originations and balances. Diffuse rather than founder ownership cuts
  the equity-ownership Gini by about 96.4% at genesis.
- `lambda_p`, `portfolio_adjust`, `resid_income_lambda`, and `theta_equity`
  are all materially live. The price-adjustment gain changes market-cap
  volatility by about -81% and +86% at the low and high arms; portfolio
  adjustment changes first-window turnover by about -78% and +259%; residual
  income learning changes fundamental-value volatility by about -17% and
  +91%; and a 0.10/0.60 household equity target changes first-window turnover
  by about -65%/+89% while moving initial market capitalization by
  -0.049%/+0.064%.
- The valuation discount floor lowers firm and bank fundamentals when binding.
  The risk-premium treatment moves the same fundamentals in the expected
  inverse direction at both low and high arms. A broader watchlist changes
  turnover by roughly -3.7%/+3.7% and slightly diversifies ownership; it is a
  market-structure choice, not a macro-growth lever.
- Price-feedback controls are causal but path-dependent. Relative to the
  stable product setting, `w_chartist=20` produces a mean absolute 2.41%
  market-cap-volatility response across seeds; `w_fundamental=2` produces
  3.42%; and, conditional on active chartist demand,
  `trend_lambda=0.10` produces 3.59%. Their signed effects can reverse with
  the endogenous price path, so they belong in a clearly labelled market-regime
  or advanced setup surface rather than being presented as monotonic growth
  controls.
- `shares_per_firm` is exact denomination invariance. Changing it to either 50
  or 200 leaves real output, aggregate firm fundamental value, and aggregate
  firm market capitalization bitwise unchanged across all four seeds. It
  should remain an internal technical parameter, not a gameplay setting.

The screen closes the observable and route defects in the implemented
securities core, but not the six semantic gaps above. The next interaction
stage should estimate `theta_equity x portfolio_adjust`,
`lambda_p x w_chartist x trend_lambda`, and
`margin_credit x bank_theta_equity x bank_equity_lambda`; it should also test
whether the bank-bond appetite saturation is calibrated to a plausible supply
elasticity. These are model and calibration questions, not reasons to inflate
individual coefficients blindly.

The full native acceptance run also exposed two regression fixtures rather
than two economic-route failures. M7 checkpoints previously serialized job
contracts but not each firm's live roster order. Because separations use an
O(1) swap erase, restoring the contracts in identifier order changed payroll
summation at the last binary digit and broke exact continuation in M9. The
checkpoint schema now preserves roster order, retaining the fast runtime data
structure while restoring byte-exact continuation. Separately, the M4
stochastic envelope still represented the pre-fix fallback-dividend clearing
path. Its v2 ranges were re-estimated from 256 deterministic native seeds after
the clearing fix; the frozen 32-seed panel and all fresh-process checkpoint
tests now pass.

### 8.14 Housing and construction screen

The housing inventory contains 29 immutable Config fields. Twenty-eight have
an executable native route and now have reviewed contracts; the remaining
`housing_wealth_effect` is correctly blocked because the current C++
consumption equation has no housing-wealth term. Six fields are identifiable
on the neutral product baseline, sixteen use a shared market, rental-pressure,
distress, construction-shortage, or investor-choice activation, and six annual
affordability-feedback fields require a multi-year activation. Conditional
mechanisms are never credited from an inactive balanced genesis.

The final short-horizon screens use four paired seeds, 100,000 persons, 90
days, and eight native workers. The neutral block executes 40 worlds and the
activated block executes 132 worlds. The annual feedback block adds 40 worlds
at 800 days so that an affordability baseline is formed before the treatment
is judged. All maintained values remain finite and all native state invariants
hold.

One genuinely silent implementation was found and repaired. Housing listings
were globally sorted by asking price and every buyer walked from the cheapest
listing. Consequently `housing_search_k >= 1` could never change a purchase:
if the cheapest listing was unaffordable, every later listing was at least as
expensive. Buyers now receive a deterministic household-specific opportunity
set of K active listings and choose its cheapest member. This keeps exact
replay and O(K) search while giving search frictions economic content. Under a
shared heterogeneous-listing activation, reducing K from five to one lowers
90-day sales by about 0.85%; the four paired paths agree on the direction.

The principal causal results are:

- The price and rent genesis anchors are exact and strong. Moving the opening
  price-to-income multiple from 3.5 to 2.0/6.0 changes the first-window house
  price by -42.9%/+71.4%. Moving the opening rental yield from 5% to 2%/10%
  changes first-window rent by -60%/+100%.
- In a liquid voluntary market, a 0.1%/5% listing markdown changes the house
  price by about +0.36%/-4.10% relative to the 0.5% baseline; a 0%/20% asking
  markup changes it by about -4.29%/+12.89%. Raising the buyer liquidity buffer
  from 25% to 50% reduces both sales and mortgage originations by about 1.26%,
  while lowering it to 5% raises both by about 1.19%.
- Capability boundaries are complete. Disabling resale eliminates sales,
  transfer volume, and purchase mortgages; disabling mortgages eliminates
  mortgage originations and principal; disabling rentals eliminates rent
  settlement; disabling housing removes the dwelling stock and its dependent
  flows. A seven-day market interval raises 90-day sales about 38.1% relative
  to monthly clearing, while a 90-day interval removes the control window's
  transactions.
- Rental adjustment is conditional rather than silent. Under a common rental
  shortage, setting the adjustment speed to zero removes rent movement and a
  0.20 speed materially amplifies it. The rent-burden ceiling is intentionally
  nonlinear: lowering it to 10% binds and reduces rent, while raising an
  already slack ceiling is not credited as a causal failure. The investor
  premium changes vacant-owner listings only when rental and deposit returns
  straddle the decision threshold.
- Under a common dwelling shortage, construction and land-fee credit are live.
  Disabling construction removes all 90-day construction output and 50 permit-
  capped completions; disabling land-fee credit removes the same 50
  completions. Halving builder productivity reduces construction output about
  83.6%, while quadrupling it raises output about 1,330%. The demand-price gain
  changes output by roughly +6.6%/+22.5% at 0.5/2.0. A 0.25 finished-unit
  buffer raises output about 24.7%, whereas a buffer of one per developer
  overexpands planned inventory, exhausts financing against a tight permit
  cap, and collapses output by about 95.9%. That non-monotonicity is retained
  as a real leverage-and-capacity trade-off rather than forced into a false
  monotonic contract.
- Annual affordability feedback is both delayed and material. Under worsening
  affordability, removing versus strengthening the elasticity changes the
  final-window fertility multiplier by +4.36%/-12.01% and the leaving-home
  multiplier by +8.90%/-15.68%. Raising the lower clamps to 0.99 limits those
  declines by about 3.31% and 7.82%. Under improving affordability, lowering
  each upper clamp to one cuts the corresponding positive response by about
  15.5% and 28.6%. All eight directional checks have confidence intervals that
  exclude zero across four paired seeds.

Balanced genesis intentionally has no uncovered housing demand, so zero
construction in the neutral first year is not evidence that the construction
module is disconnected. Conversely, the audit does not hide the missing
housing wealth-to-consumption route: it remains explicit native backlog work
and cannot be presented as a weak elasticity.

### 8.15 Energy production, inventories, and deprivation screen

All twelve immutable energy Config fields have an executable native route and
now have reviewed causal contracts. Eight are identified on the neutral
product baseline; inventory-gap and price-trend controls use shared 90-day
activations; and the two fuel-poverty mortality controls use a shared two-year
activation so that the calibration period ends before the hazard response is
estimated. The final screens use four paired seeds, 100,000 persons, and eight
native workers. The direct block executes 60 worlds, the short activated block
24 worlds, and the mortality block 24 worlds. Every declared check passes or
passes the predeclared heterogeneous-path criterion.

The screen found one real causal defect and one observability gap:

- `energy_mortality_gamma` and `energy_mortality_mult_hi` previously changed
  the published fuel-poverty mortality multiplier but never changed a person's
  death draw. The M8 signal now enters the next day's M7 age-specific death
  hazard. A native extension-seam regression proves that the same population
  and random stream realizes more deaths under a larger external multiplier.
  Disabling household energy also closes this dependent mortality channel, so
  the Config capability cascade always remains valid.
- `kappa_E` changed the amount of physical capital needed by energy producers,
  but the maintained metrics exposed only capacity, which is deliberately
  close to invariant because genesis rescales capital against capital
  productivity. The native analytic catalog now publishes
  `metric.source.m8.energy.producer_capital`. Raising `kappa_E` from 1.05 to
  1.60 reduces sector capital about 34.35%; lowering it to 0.60 raises sector
  capital about 75.04%. Its aggregate investment spillover is smaller and
  seed-dependent, as expected for a sector that is a minority of total firms.

The principal causal results are:

- Energy labor productivity is strongly live. Lowering `a_E` to 0.70 raises
  energy-sector labor requirements about 48.2% and changes production about
  -5.1%; raising it to 1.40 lowers labor requirements about 23.2% and changes
  production about +2.1%. Production is demand-cleared and therefore treated
  as a nonzero equilibrium response rather than forced to be monotonic.
- The downstream inventory target has the intended stock meaning. Moving
  `energy_coverage_ticks` from 14 to 3/30 changes observed coverage about
  -36.6%/+59.9%, with industry orders moving in the same direction during the
  accumulation window. Disabling the parent energy capability removes
  production and industry energy orders exactly.
- Household and industrial demand scales are material and transparent.
  Moving the household budget share from 7% to 3%/14% changes requested units
  about -57.1%/+100% and cumulative spending about -57.2%/+87.5%; disabling
  household energy removes both flows. Moving industrial energy intensity
  from 0.05 to 0.01/0.12 changes first-window industry orders about
  -79.9%/+138.1% and cumulative input spending about -79.2%/+120.4%.
- `energy_util0` is not merely an opening seed: the producer planning rule
  reuses it as desired utilization. Moving it from 0.85 to 0.55/1.00 changes
  first-window capacity about +54.6%/-14.9% and utilization about
  -35.6%/+11.7%. It belongs among structural calibration controls, not among
  disposable genesis noise.
- Inventory adjustment is nonlinear. Under a shared stock-gap activation,
  both a nearly frozen 0.001 gap-close speed and an aggressive 0.20 speed raise
  first-window industry orders relative to the calibrated 0.02 value, while
  reducing production about 2.0% and 31.2%. The baseline sits near a local
  balance between replenishment, financing, and production overshoot; this
  control is therefore judged by a nonzero dynamic contract rather than a
  false larger-is-better rule.
- Hoarding behaves conditionally as designed. During a shared rising-price
  episode, setting `energy_hoarding_beta` to zero cuts first-window industry
  orders about 6.9% and unmet demand about 14.1%; raising it from one to five
  increases them about 29.1% and 72.9%. It is silent in a flat-price regime by
  economic construction, not because the route is missing.
- The repaired mortality channel is quantitatively material. Under common
  persistent fuel poverty, removing the elasticity lowers two-year deaths by
  about 12.6%, while raising it from two to four raises deaths about 12.0%.
  Tightening the mortality cap from 1.3 to 1.0 lowers deaths about 11.7%; a cap
  of two raises them about 25.9%. All death and multiplier confidence intervals
  exclude zero across the four paired seeds.

The energy module therefore has no remaining unrouted or observationally
silent immutable Config field. The next interaction stage should estimate the
joint response of household need, industrial intensity, inventory coverage,
and hoarding under supply loss; it should also calibrate the mortality channel
against empirical excess-mortality evidence before exposing wide ranges in a
player-facing setup screen.

### 8.16 Open-economy coupling screen

All eighteen World Config entries have now been adjudicated. Fifteen are
executable structural treatments spanning trade, FX adjustment, capital
mobility, migration, remittances, peg reserves, and clearing-union loss
sharing. `base_seed` and `couple` are derived construction metadata rather than
independent treatments. `periods_per_year` is also excluded: the current
product has an invariant civil calendar of 365 one-day ticks and deliberately
replaces the obsolete twelve-period seed at the native bridge.

The accepted experiments use three heterogeneous economies, 100,000 persons
per economy, four paired seeds, and eight native workers. Trade, capital, and
migration are estimated over 90 days; peg reserves over 180 days; and dealer
loss sharing over 730 days so that two annual boundaries are crossed. A World
contract is always judged under a shared cross-country identification state:
an importer configuration for trade capacity, an exporter configuration for
iceberg friction, a realistic daily interest-rate gradient for capital flows,
a persistent real-wage gradient for migration, and a stressed imbalance for
peg and clearing-union mechanisms.

The audit found one genuinely silent implementation. The
`fx_loss_mutualization` rule was mapped through Config, bindings, C ABI, and
checkpoints but was never read by the C++ World advance. The native engine now
accumulates conversion volume, measures dealer net worth at each annual
boundary, and—only when that net worth is negative—allocates the loss across
member treasuries in proportion to their conversion volume. The transfer is
posted to each domestic ledger and FX inventory, enters the current account,
survives checkpoint continuation, and is published as
`metric.source.m9.country.fx_mutualization_paid`. In the four-seed two-year
stress screen, enabling the rule produces an average cumulative player-country
levy of about 26,133 currency units; the confidence interval is roughly
21,524–30,741, while the disabled control remains exactly zero.

The principal causal results are:

- The parent trade capability is complete. Disabling it, together with the
  required dependent capital and migration capabilities, removes player-country
  imports and World trade routes exactly. Moving the daily import cap from 15%
  of output to 3% lowers cumulative imports about 74.3% and route count about
  58.0%; raising it to 30% increases them about 62.2% and 71.1%.
- Iceberg friction has a direct physical interpretation. In the common
  exporter scenario, eliminating the baseline 3% friction eliminates transit
  loss, while raising friction to 15% increases cumulative destroyed goods
  about 383.5%. A separate exporter scenario is necessary because the loss is
  correctly recorded by origin, not by the importing player country.
- FX dynamics and intermediation are live. Reducing the dealer-inventory
  adjustment coefficient from 0.05 to 0.01 cuts exchange-rate volatility about
  79.5%; raising it to 0.20 increases volatility about 324.6%. Introducing a
  1% conversion spread creates about 654 units of cumulative dealer spread
  revenue over the 90-day screen from a zero-spread control.
- Capital-account responses remain clear at realistic daily interest rates.
  The shared 0.030%, 0.005%, and 0.0134% daily rates correspond roughly to
  11.6%, 1.8%, and 5.0% effective annual rates. Disabling capital mobility
  removes the high-rate country's cumulative inflow of about 396 units.
  Moving the adjustment speed from 0.20 to 0.05/0.50 changes that inflow about
  -75.0%/+149.9%; moving structural mobility from 1.0 to 0.2/0.8 changes it
  about -80.0%/-20.0%. All intervals exclude zero without an extreme-rate
  activation.
- Migration and remittances are quantitatively material. Disabling migration
  removes hosted migrants and remittance outflows. Moving the daily migration
  rate from 0.0005 to 0.0001/0.005 changes hosted stock about -80.0%/+821.2%
  and cumulative remittances about -80.0%/+846.1%. Under a binding common
  pressure, moving the population ceiling from 25% to 5%/40% changes hosted
  stock about -80.0%/+24.7%. Faster wage-signal updating accelerates first-
  window migration, and a 5%/50% remittance share changes host outflows about
  -75.0%/+146.7% relative to the 20% baseline.
- Peg seed reserves have the expected buffer meaning. Under identical defense
  pressure, reducing opening reserves from 5,000 to 1,000 lowers the first-
  window remaining stock by about 2,609; raising them to 20,000 increases it by
  about 14,996. Both four-seed intervals are narrow and exclude zero.

The World screen also corrected an experimental-framework trap: country-level
trade journals cannot all be interpreted from economy zero. Player-country
imports, exporter-country iceberg loss, and World route/dealer metrics now use
separate predeclared scenarios instead of treating an inapplicable zero as a
silent mechanism. No executable immutable open-economy Config remains unrouted
or causally silent. The next interaction stage should combine trade friction,
capital mobility, migration, and peg defense under persistent productivity and
energy differences, then calibrate ranges against external empirical evidence.

### 8.17 Interaction and package screen

P3 is complete. The accepted screen contains seven predeclared structural
packages, each evaluated with a regular resolution-IV, 16-arm two-level design,
four independent paired seeds, 100,000 persons per country, and eight native
workers. Each package also has a product-reference run for every seed. The
accepted matrix therefore contains 476 native paths. All paths completed
without a stability, finite-value, checkpoint, or Config-contract failure.

The resolution-IV design estimates every main effect without contamination
from a two-factor interaction, but it deliberately aliases two-factor terms.
The strongest economically interpretable alias in each package was therefore
registered before inspection as a separate 2x2 full-factorial follow-up. Those
seven follow-ups add 140 native paths and identify the selected interaction
without aliases. A first 730-day housing matrix is retained only as a rejected
artifact: it ended immediately before the second annual affordability update
and incorrectly made the fertility and leaving-home multipliers look silent.
The accepted housing matrix spans 800 days and has a regression test preventing
the horizon from falling below that threshold.

All 46 package factors resolve at least one maintained mechanism or outcome in
the accepted matrix:

| Package | Resolved factors | Principal high-minus-low effects | Isolated interaction |
|---|---:|---|---|
| Productive capacity | 6 / 6 | `A` raises real GDP per capita about 37.8%; `alpha` raises it about 53.0%; a high capital coefficient `v` raises unemployment about 30.4 percentage points and lowers real GDP per capita about 19.6% | high `alpha` buffers the unemployment effect of high `v` by about 15.0 percentage points; the interaction also changes prices and investment |
| Labor institutions | 7 / 7 | search intensity lowers unemployment about 2.37 percentage points; matching friction raises it about 2.94 points; the tested reservation-markup range lowers participation about 45.5 points | search intensity offsets the unemployment effect of matching friction by about 3.16 percentage points and raises employment and hires |
| Credit architecture | 7 / 7 | interbank availability and run sensitivity dominate flight and interbank volumes under the common stress state; household credit raises loan principal and new lending | interbank availability strongly amplifies the transmission of run sensitivity to flight volume, bank capital, loan principal, and new lending |
| Housing and family formation | 7 / 7 | builder productivity raises cumulative construction about 190%; mortgages create the entire purchase-mortgage flow; rent adjustment raises cumulative rent about 69%; fertility and leaving-home elasticities lower their stressed final-window multipliers about 10.9% and 12.7% | productive builders generate about 149 additional mortgage originations when mortgage finance is available beyond the sum of the separate effects |
| Energy dependence | 6 / 6 | household need and industrial intensity materially raise requested energy; mortality sensitivity adds about 768 deaths in the stressed two-year window; coverage and hoarding change unfilled demand and fuel poverty | joint household and industrial dependence induces additional production, leaving about 733,000 fewer unfilled units and 18.7 percentage points less fuel poverty than a linear sum predicts |
| Firm dynamism | 6 / 6 | the entry hurdle and response change births; exit hazard and grace duration change exits; switching creates all observed switches and retool destruction | retool loss only operates when switching is enabled; their interaction destroys about 9.97 million capital units, lowers firm profit about 545,000, and lowers mean real output about 3,696 |
| Open economy | 7 / 7 | trade caps, friction, capital mobility, FX adjustment, migration, remittance intensity, and wage smoothing all resolve on their direct flows; migration and remittance shares have the largest flow effects | high migration and high remittance intensity are complementary, adding about 8.72 million remittances beyond the additive prediction |

Several outcomes are intentionally not accepted as evidence of a universally
plausible magnitude. Capability switches naturally produce +/-200% relative
effects when the low arm removes a flow. The credit package is a run-pressure
scenario, not a neutral forecast. Conversely, zero bank failures in that
one-year stress matrix means the rare failure tail still requires its dedicated
many-seed experiment; large deposit flight is not a substitute for observing a
failure.

The package screen also sharpens the gameplay disposition:

- `alpha`, `v`, `reservation_markup`, and `suspension_timer` are highly salient
  but the tested ranges are too wide for an ordinary start-menu slider. They
  need narrower presets or expert-only exposure, not additional amplification.
- `run_sensitivity`, interbank capability, energy demand intensity, and the
  housing affordability elasticities are regime-dependent structural choices.
  Their descriptions must state the activation state and delay rather than
  promising a constant marginal effect.
- no package factor is now classified as mechanically or observationally
  silent. Weak neutral-baseline fields retain their conditional contract instead
  of being made artificially stronger.
- large interactions reject one-knob-at-a-time balance decisions. Product
  presets must be validated as packages, especially capital formation, labor
  search, bank liquidity, housing finance, energy dependence, firm switching,
  and migration/remittances.

### 8.18 External calibration crosswalk

Structural coefficients are not calibrated by forcing them to equal an
observable national statistic. Calibration instead targets the maintained
model outcomes generated by a package and uses common statistical definitions:

| Model family | External target and definition |
|---|---|
| Production and investment | World Bank WDI gross capital formation as a share of GDP, sourced from national accounts, for investment and capital-accumulation envelopes ([metadata](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/NE.GDI.TOTL.ZS)) |
| Labor | ILOSTAT labor-force participation, employment, unemployment, and underemployment definitions; unemployment alone is not treated as welfare ([methods](https://ilostat.ilo.org/methods/concepts-and-definitions/description-labour-force-statistics/)) |
| Credit | BIS household and non-financial-corporation core debt, split by borrower and expressed relative to GDP; total credit and domestic-bank credit are kept distinct ([methodology](https://data.bis.org/topics/TOTAL_CREDIT?m=6_380_66)) |
| Housing | OECD nominal and real house prices plus price-to-income and price-to-rent ratios; price-to-income is the affordability anchor rather than the raw simulated house-price unit ([definition](https://www.oecd.org/en/data/indicators/housing-prices.html)) |
| Energy | IEA primary-energy intensity in energy per unit of PPP GDP, supplemented by the engine's physical shortage and deprivation measures ([definition](https://www.iea.org/reports/sdg7-data-and-projections/energy-intensity)) |
| Migration and remittances | World Bank bilateral migration/remittance estimates, with explicit undercounting and informal-flow caveats, plus IMF balance-of-payments concepts for external flows ([methodology](https://blogs.worldbank.org/en/peoplemove/bilateral-remittance-matrix-new), [IMF EBA](https://www.imf.org/en/publications/wp/issues/2023/03/02/2022-update-of-the-external-balance-assessment-methodology-530509)) |

These sources define comparable outcome envelopes. They do not justify a single
global default: country profiles should draw internally coherent targets from
the same period and institutional regime. The million-person confirmation stage
tests finite-size robustness before any final range is frozen.

## 9. Execution gates

### P0 - Static ownership and routing

- Generate the 455-field ledger from the canonical schema.
- Verify the all-module playable baseline.
- Locate every native route.
- Adjudicate every missing route.
- Prevent an unrouted field from being reported as a small elasticity.

### P1 - Native paired-run harness

- Build treatment manifests from the ledger.
- Run paired seed blocks with eight native workers.
- Store daily maintained metrics and summary estimands.
- Record commit, build, Config hash, seed, duration, population, and timing.
- Support resume and deduplicate completed runs.

### P2 - Module screening

- Run 100,000-person one-year and five-year screens.
- Produce route, sign, salience, stability, and timing scorecards.
- Repair no-effect, wrong-sign, clock, and observability failures per module.

### P3 - Interaction and activation scenarios

- Run the seven combination packages.
- Run stress-only and rare-event mechanisms in predeclared scenarios.
- Decompose direct effects, spillovers, and interactions.

### P4 - Large-scale confirmation and empirical calibration

- Confirm material results at one million people.
- Compare finite-size bias between 100,000 and one million people.
- Calibrate plausible ranges against primary empirical sources.
- Freeze per-field causal contracts and regression thresholds.

### P5 - Policy audit handoff

- Move runtime levers to the Policy experiment matrix.
- Reuse the same estimators, outcome catalog, activation scenarios, and
  acceptance gates.

## 10. Reproducible artifacts

The static ledger is generated with:

```bash
.venv/bin/python scripts/config_causality_audit.py \
  --json-output artifacts/config-audit/config_inventory.json \
  --markdown-output artifacts/config-audit/config_inventory.md \
  --fail-on-disabled-module
```

Generated results live under `artifacts/config-audit/` and are not committed.
Source code, schemas, field dispositions, experiment manifests, tests, and this
protocol are committed. The audit does not use the legacy Python simulation as
an oracle; Python only orchestrates the native C++ engine and analyzes results.

The native product-baseline comparison and treatment contracts are generated
with:

```bash
PYTHONPATH="$PWD/build/native/m11-release/native:$PWD" \
  .venv/bin/python scripts/config_native_baseline_audit.py \
  --output artifacts/config-audit/native_baseline.json

.venv/bin/python scripts/config_causality_contracts.py \
  --output artifacts/config-audit/config_contracts.json
```

A curated module batch is resumable and reuses the paired controls:

```bash
PYTHONPATH="$PWD/build/native/m11-release/native:$PWD" \
  .venv/bin/python scripts/config_causality_batch.py \
  --module production_and_technology \
  --population 100000 --days 365 --workers 8 \
  --output-dir artifacts/config-audit/production-1y
```

Reviewed conditional contracts use a shared activation for both sides of every
paired comparison. Contracts with the same horizon, country count, metrics, and
activation reuse one control block:

```bash
PYTHONPATH="$PWD/build/native/m11-release/native:$PWD" \
  .venv/bin/python scripts/config_causality_batch.py \
  --module production_and_technology --activation \
  --population 100000 --days 90 --workers 8 \
  --output-dir artifacts/config-audit/production-90d-activation
```
