# Policy Remediation Plan v39

## R7 acceptance

- Status: `accepted`
- Source revision: `243be5a79daa02114eced9129382e4a97c5074ca`
- Native extension SHA-256: `c9e15a31f1fabc57f2fa7b8a627893efeaced7631395f30dfa2020545de992f4`
- R7 acceptance hash: `60d079d45a39084cab5c5af0cb59c07d1b76676702bfc91a5e71cda8d6e150d3`
- Machine report: `docs/policy_remediation_r7_acceptance_v39.json`
- Scale evidence: `docs/policy_remediation_r7_scale_evidence_v39.json`
- Scope: seven scale- or rare-event-sensitive policies, 56 matched native records, 112 control/treatment branches, and zero cache hits.
- Formal protocol: 100,000 and 1,000,000 persons per country, four matched seeds, eight native workers per session, one concurrent million-person record, and no legacy Python economic simulation.

All seven candidates pass their preregistered direct-effect and execution gates.
`mortgage_foreclosure_ltv`, `gov_investment_share`, `bankrupt_persist`, and
`rental_eviction_arrears` follow first-order population scaling.
`soe_efirm`, `tariff`, and `fx_regime` preserve the required matched-seed
direction and materiality but require an explicit fitted finite-size dependency.
The largest record took 777.5 seconds and the largest estimated paired-world
peak was 8,016,790,908 bytes, below the 1,200-second and 16-GiB budgets.

R7 also fixes the fiscal allocation defect exposed by the scale run. Public
investment now competes directly for current capital-goods supply, and only
realizable investment outlays reduce the residual deficit-targeted government
consumption budget. A change from a 4% to a 2% investment share consequently
reduces both public fixed-capital formation and the public-capital stock in all
four matched seeds at both scales, with estimated population elasticities of
0.999 and 0.989 respectively. Rare-event opportunity detection now recognizes
both event creation and event prevention, so a stricter eviction-protection
threshold is not rejected merely because treatment successfully produces zero
evictions. SOE acceptance is gated on its direct transaction-price channel;
the mixed-direction energy-production response remains explicit exploratory
evidence rather than being hidden or used as a false direct-mechanism gate.

## R6 acceptance

- Status: `accepted`
- Mechanism revision: `6a4b14555ed06b36a5b467d2f9bf4d16472927dc`
- Crisis reduction revision: `e5d8b81aeb6ec552f8ffa12304d324b77abd9af0`
- Classification revision: `eb2a674a9f05adbaa7f4ad96babcd3e30107cf2f`
- R6 acceptance hash: `cb4a5bdea705804f17db6fa7665525fbfbaa99490316d9cc219c656b82ecfac0`
- Machine report: `docs/policy_remediation_r6_acceptance_v39.json`
- Mechanism evidence: `docs/policy_remediation_r6_p2_evidence_v39.json`
- Crisis evidence: `docs/policy_remediation_r6_crisis_evidence_v39.json`
- Scope: 36 behavior candidates, 72 preregistered policy-state cells, 68 runnable crisis cells, and four explicit job-guarantee binding-state exclusions.
- Formal protocol: 100,000 persons per country, four matched mechanism seeds, eight matched crisis seeds, eight native workers per session, eight concurrent crisis seed jobs, 104 fresh mechanism runs, 704 fresh crisis branches, and zero cache hits.

All 36 candidates have a final player-surface classification: two `effective`,
22 `conditional`, nine `expert_only`, three `structural`, and zero `removed`.
Every retained non-structural lever either crosses the preregistered gameplay
salience floor or passes an anchor-crisis benefit gate; no lever is retained on
statistical detectability alone. `manual_policy_rate` remains an expert policy,
not a structural policy: its Registry state-transition label enforces atomic
manual-regime validation and does not change its economic meaning as an
adjustable interest rate.

R6 reports mechanism direction, effect-to-materiality-floor magnitude, first
response and peak timing, adverse-state guardrails, and empirical scope
separately. `effective` is deliberately strict: only `benefit_income_floor` and
`pension_replacement` are salient in ordinary and binding states, pass an
anchor-crisis benefit gate, and avoid a supported adverse-state harm. A
`conditional` or `expert_only` classification is not a claim of general crisis
efficacy; the UI must expose the recorded binding state and trade-off.

The formal diagnostics loaded and hashed the extension under the current
worktree `build/native/m11-release/native` directory. An installed wheel or
stale virtual-environment extension now fails before R6 simulation begins.
Python only orchestrates native C++ checkpoints, branches, and metric reduction;
the legacy Python economic simulator is not used. These results are model-based
calibration evidence, not external empirical estimates. R7 subsequently
confirms or explicitly models the finite-size behavior of all seven scale- and
rare-event-sensitive candidates.

## R5 acceptance

- Status: `accepted`
- Base revision: `6f3a007bd7b6b7d447923109375cf07eb3e9e4f2` (accepted R4)
- Implementation revision: `95930333ce7ae8df11933af6c3d7be9e391cfbc5`
- Machine report: `docs/policy_remediation_r5_acceptance_v39.json`
- Full P3 evidence: `docs/policy_remediation_r5_p3_evidence_v39.json`
- Scope: 11 structural/ordinary states, 11 crisis scenarios, 10 native shock kinds, 8 fixed seeds, and five acceptance gates per crisis.
- Formal protocol: 100,000 persons per country, eight native workers per session, eight concurrent seed jobs, 176 fresh native runs, and zero cache hits.
- Verification: 74/74 native tests, 156/156 focused Python/native-binding tests, and all five contract generators/checkers passed.

Every state and crisis is accepted. Each crisis passes entry, propagation,
severity, recovery, and replay/accounting integrity. Ten crisis severity checks
are ordered in 8/8 seeds; trade interruption is ordered in 7/8 seeds and passes
the preregistered 6/8 threshold. Every crisis includes at least one native replay
check, and every per-seed integrity row passes.

R5 repairs shock lifecycle and replay semantics, sovereign-risk repricing,
housing-specific mortgage credit rationing, and fixed-exchange-rate reserve defense
under exogenous capital outflow pressure. It also replaces noisy peak statistics
with mechanism-aligned cumulative or acute-window measures where the earlier P3
gate did not measure the declared crisis reliably.

The P3 v3 payload retains its historical workflow label
`accepted_with_explicit_defects`; that enum is emitted for every error-free P3 run
and is not conditional on exclusions. The R5 acceptance report therefore freezes
the explicit result: `errors=[]`, 11/11 accepted crises, zero exclusions, and all
five gates passing. Crisis calibration contains no Policy treatment. Single-policy
effect size and gameplay calibration remain reserved for R6.

## R4 acceptance

- Status: `accepted`
- Base revision: `160dcbcfe2380679c4ab5ecab36a3f27e3a26e38` (accepted R3)
- R4 acceptance hash: `6d3f463d8f6b30ec35fe2800fc171707705b95a898aa46a0bd04b594d77bdb50`
- Machine report: `docs/policy_remediation_r4_acceptance_v39.json`
- Scope: 7 Policy levers, 29 declared proximal metrics, 20 new maintained native source metrics, and 8 direct native behavior checks.
- Verification: 46/46 native tests and 3/3 deterministic R4 contract tests passed with eight workers.
- Evidence consequence: frozen P0-P8 results remain historical but are invalidated for current product claims until regenerated.

R4 provides deterministic opportunities for bank liquidity support, bank resolution
funding, failed-bank account and loan migration, margin allocation, household
bankruptcy, and housing permits. Each policy now records the eligible opportunity
before the policy decision, so non-activation is distinguishable from a scenario in
which nothing could happen. The fixtures cover activation, non-activation, and
withdrawal at the direct event or state-transition boundary.

Unified bank RWA now uses one common bank-level asset envelope: ordinary credit
enters at full weight and mortgages enter at the configured mortgage risk weight.
The general-credit and mortgage paths share the same live capital ratio and asset
stock, while the legacy non-unified path remains available when the policy is off.

These are local state-machine repairs. Economy-wide effect magnitude and gameplay
calibration remain reserved for R6; crisis-library repair remains reserved for R5.

## R3 acceptance

- Status: `accepted`
- Base revision: `78a384f701d751f017054be9eb7314d14e6f18a1` (accepted R2)
- R3 acceptance hash: `4f5631b6f63ebc43d984dbb43bd1c077c58d5d48bb5fe7bdf9d13933f3b198ec`
- Machine report: `docs/policy_remediation_r3_acceptance_v39.json`
- Scope: 6 Policy levers, 14 maintained native source metrics, and 5 matched-seed dose/withdrawal mechanism fixtures.
- Verification: 46/46 native tests and 3/3 deterministic R3 contract tests passed with eight workers.
- Evidence consequence: frozen P0-P8 results remain historical but are invalidated for current product claims until regenerated.

R3 closes every native route defect recorded by P1. Fiscal policy can now select
the lagged full national-accounts GDP basis; the unemployment-sensitive deficit
ceiling reports the multiplier, effective target, and procurement budget it applies.
The general bank-capital switch exposes gross lending headroom and rejected credit.
Mortgage underwriting now applies bank-level risk-weighted capital capacity, while
the arrears floor is observable as a liquidity-protection boundary before
foreclosure. Zero mortgage risk weight or zero minimum capital ratio explicitly
means that this RWA gate is non-binding rather than rejecting all applications.

These are direct route and mechanism repairs. Their local dose and withdrawal
behavior is accepted; economy-wide effect magnitude and gameplay calibration remain
reserved for R6, and unified whole-bank RWA state-machine behavior remains in R4.

## R2 acceptance

- Status: `accepted`
- Base revision: `6848cd67b5bb3ef9b58b7596e76d1cc572bcd905` (accepted R1)
- R2 acceptance hash: `1ae7b90f8cd5b28f0ce7c7c8a2a1574a1a0bad5d1d806cb812114bee11d6a522`
- Machine report: `docs/policy_remediation_r2_acceptance_v39.json`
- Scope: 12 Policy levers, 27 declared proximal metrics, and 28 new maintained native source metrics.
- Verification: 46/46 native tests and 3/3 deterministic R2 contract tests passed with eight workers.
- Evidence consequence: frozen P0-P8 results remain historical but are invalidated for current product claims until regenerated.

R2 distinguishes issuance terms from the weighted outstanding sovereign-bond stock,
records mortgage underwriting terms on each originated contract, exposes current
firm-credit and collateral gates, and reports housing wealth-tax and construction
land-fee assessment bases directly. OMO now has a duration-adjusted sovereign-flow
observable. These are observability repairs only; causal size and gameplay value
remain subject to R6 recalibration.

## R1 acceptance

- Status: `accepted`
- Base revision: `585b1e87043eb0564562e19b28cb520576e4a516` (accepted R0)
- R1 acceptance hash: `0cc75df491985c44e99c7be6d0f7eafb9872898284f3a804e80e5e34976241ce`
- Machine report: `docs/policy_remediation_r1_acceptance_v39.json`
- Verification: 46/46 native tests and 3/3 R1 parity tests passed with eight workers.
- Evidence consequence: frozen P0-P8 results remain historical but are invalidated for current product claims until regenerated.

### Canonical R1 domains

| Lever | Canonical domain | Controller scale / maximum step | Ruling |
|---|---|---|---|
| `margin_ltv` | `[0, 1]` | `0.025 / 0.10` | A 100% loan-to-value ceiling is risky but economically coherent, so the native validator now accepts the closed upper boundary. |
| `margin_max` | `[0, 10]` | `0.25 / 1.0` | Exposure below net worth is a legal macroprudential stance; the native lower bound is therefore zero rather than one. |
| `import_quota` | `null or [0, 1]` | `0.05 / 0.20` | The value is a share of normal import capacity. Values above one previously expanded capacity and contradicted quota semantics. |
| `immigration_cap` | `null or [0, 1]` | `0.025 / 0.10` | The value is a hosted migrant-stock ceiling as a share of host population; `null` remains the explicit open-border state. |

Registry, controller metadata, M0 inventory, M1 generated contracts, M11 player-facing contracts, native validators, and checkpoint round trips now agree on these domains. Invalid M11 actions are rejected by the generated contract before policy dispatch with `ErrorCode::out_of_range` and the canonical numeric-domain message.

R1 changes validation and reachability only. It does not claim that the four policies have accepted causal magnitude or gameplay value; `margin_max` still proceeds to R4 opportunity testing, while all affected empirical claims must be rebuilt under the invalidation rule.

## R0 acceptance

- Status: `accepted`
- Baseline revision: `390fbcb6517e99251239c3ded5cf956701a860c6`
- R0 acceptance hash: `28986b8a65829cb2b525bb8f48cd13fb266318a6f84119e11edc917d4dfe6436`
- Frozen P0 root: `6f71f6debc79e8d64862a2cf3c7c351a791fecee0cd50d64f69dfad6dbf0e5a6`
- Scope: deterministic planning and provenance only; no simulator or policy behavior changed.

## Executive decision

The frozen P0-P8 evidence covers **102** canonical Policy levers. R0 classifies **27** as mandatory repairs, **36** as behavior-review candidates, and **39** as no-change entries under current evidence.

A behavior-review label does not mean that a mechanism is broken. It means its accepted effect, dose, state dependence, empirical direction, safety, or scale scope must be retested after upstream repairs. A no-change label is also not a permanent exemption; those levers remain under the final regression gate.

## Evidence boundary

- P0 identity is the common root exposed by P1-P7, not a copied standalone ignored artifact.
- P2 does not expose a P1 acceptance binding; R0 pins P1 and P2 independently on the same P0 root.
- R0 verifies exposed cross-stage identities but does not rerun upstream native experiments.

### Frozen acceptance identities

| Stage | Status | Acceptance hash | Source revision |
|---|---|---|---|
| P1 | `accepted_with_explicit_defects` | `8d930386225337a1e5af100da92764d373d768356bb236160f4a095769c64d00` | `not exposed` |
| P2 | `accepted_with_explicit_defects` | `0a112ee71733089ade75d7916dda6ccf9cfdc0ec64b40bcb5484c716a425949c` | `484b6df49daf13a871fa669268663bfc7e8bdbfb` |
| P3 | `accepted_with_explicit_defects` | `f7e8b218a8d989a31af8a89bc97c2b12fe0a5780953d2fd013c2ea0289721933` | `e096064df93af33c1e098106159eb7432cd20ce9` |
| P4 | `accepted_with_explicit_defects` | `38f3702aa2e45c8de274b15416a52e17b9d33bff2b390a8b5cc3ec3f546a8df2` | `4dbcefa5c0b0ee6e90c7f8923d3d1cbe319f5dfe` |
| P5 | `accepted_with_explicit_defects` | `26839f8523bbb508bf426b28cdc4afebf4688e1a220856e18eb48a5c56fb79c1` | `3c53b41b98fbae9a36ba9cb5506139668bc77aed` |
| P6 | `accepted_with_explicit_defects` | `2558901f5fd9192b8b12ade4fb499dd2de64d8b36f4a929ceeebb4cf43c4a5fb` | `3e4fcd1d9d26c32f0c7c1ada86e2e388873ca317` |
| P7 | `accepted_with_explicit_defects` | `c0107cee11076a681aa2f35363950beb9690b78f2adec46375bd3427209540af` | `c9b71435f009f938b70ae8d0084c76a5688fe5c6` |
| P8 | `accepted_with_explicit_limitations` | `49da53cbf12e9b4723494ae072a9dac81e97bebe81c0f7d4d27b712a923d3cf3` | `25e7e68ff5b1791ad0310867d434bee4812a3a22` |

Only `CR_DEMAND_RECESSION` is currently accepted for player-facing policy-efficacy claims. R5 must repair the other ten crisis scenarios before they can be used to judge a policy.

## Ordered milestones

| Phase | Purpose | Policy queue | Invalidates |
|---|---|---:|---|
| R0 | Remediation ledger and evidence invalidation map | 102 | none |
| R1 | Registry and native validation parity | 4 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R2 | Contract-level observability | 12 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R3 | Direct route and mechanism repair | 6 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R4 | Opportunity and state-machine repair | 7 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R5 | Crisis and structural-state library repair | 0 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R6 | Single-policy calibration and reclassification | 36 | P2, P4, P5, P6, P7, P8 |
| R7 | Scale and rare-event confirmation | 7 | P6, P7, P8 |
| R8 | Policy packages and interaction robustness | 0 | P5, P7, P8 |
| R9 | Controller, UI, and final acceptance | 0 | P8 |

### R0: Remediation ledger and evidence invalidation map

Freeze scope, ordering, acceptance gates, and provenance before mechanism edits.

Exit criteria:

- All 102 Registry levers appear exactly once in the primary ledger.
- The 27/36/39 classification and source hashes reproduce deterministically.
- Every repair queue has explicit gates and an evidence invalidation rule.

### R1: Registry and native validation parity

Make the player-facing domain equal the native acceptance domain.

Exit criteria:

- Boundary and near-boundary values agree across Registry, controller, checkpoint, and native validators.
- Invalid values fail before dispatch with one canonical reason.

Queue:

`margin_ltv`, `margin_max`, `import_quota`, `immigration_cap`

### R2: Contract-level observability

Expose enough native observables to prove cohort terms, gates, flows, and long-yield transmission.

Exit criteria:

- Every repaired lever has a declared proximal observable that changes at the correct read point.
- Stock-versus-new-contract semantics are distinguishable without proxy inference.
- OMO has a comparable sovereign-duration or long-yield outcome.

Queue:

`bond_coupon`, `bond_maturity`, `omo`, `mortgage_underwriting`, `mortgage_dsti_cap`, `mortgage_stress_rate_addon`, `housing_in_wealth_tax`, `firm_credit_min_dscr`, `regulatory_firm_capital_haircut`, `regulatory_firm_inventory_haircut`, `land_fee_share`, `land_fee_stock_elasticity`

### R3: Direct route and mechanism repair

Connect stored Policy state to the intended native decision and settlement paths.

Exit criteria:

- Each repaired route is read by the intended native mechanism.
- Local and meaningful doses move the declared proximal metric in matched-seed tests.
- Withdrawal or restoration returns the mechanism to its reference behavior where applicable.

Queue:

`fiscal_uses_national_accounts_gdp`, `bank_capital_constraint`, `mortgage_risk_weight`, `mortgage_min_capital_ratio`, `mortgage_arrears_floor`, `deficit_u_cap`

### R4: Opportunity and state-machine repair

Create deterministic binding fixtures for rare legal, liquidity, housing, and failure transitions.

Exit criteria:

- The intended opportunity occurs in every preregistered seed.
- The treatment changes the event decision or state transition, not merely a downstream proxy.
- Activation, non-activation, and withdrawal paths are all covered.

Queue:

`lolr`, `bank_resolution_fund`, `margin_max`, `housing_permits`, `household_bankruptcy`, `bank_migrate_on_failure`, `unified_bank_rwa`

### R5: Crisis and structural-state library repair

Accept the ten crisis scenarios that P3 withheld before policy-efficacy retesting.

Exit criteria:

- Each scenario passes activation, severity, persistence, contamination, and accounting gates.
- Crisis calibration remains separate from policy calibration.

### R6: Single-policy calibration and reclassification

Retest the 36 behavior candidates across relevant states, doses, and horizons.

Exit criteria:

- Each candidate is classified as effective, conditional, expert-only, structural, or removed from the player surface.
- Direction, magnitude, timing, guardrails, and empirical scope are reported separately.
- No lever is retained solely because a statistically detectable but gameplay-silent effect exists.

Queue:

`gov_consumption_share`, `gov_deficit_target`, `deficit_u_ref`, `benefit_replacement`, `benefit_income_floor`, `pension_replacement`, `tax_income_rate`, `energy_price_cap`, `energy_rationing`, `min_wage`, `job_guarantee`, `jg_wage_ratio`, `inflation_target`, `taylor_phi_pi`, `taylor_phi_u`, `rate_inertia`, `manual_policy_rate`, `monetary_regime`, `r_neutral`, `u_natural`, `r_max`, `infl_ema_lambda`, `cb_core_inflation`, `cb_uses_fixed_basket_cpi`, `cb_log_inflation`, `omo`, `bank_min_capital`, `mortgage_ltv_cap`, `mortgage_foreclosure_ltv`, `jg_public_works_share`, `gov_investment_share`, `bankrupt_persist`, `rental_eviction_arrears`, `soe_efirm`, `tariff`, `fx_regime`

### R7: Scale and rare-event confirmation

Close finite-size dependencies and previously blocked million-person paths.

Exit criteria:

- 100k and 1M matched-seed signs agree or the scale dependency is explicitly modeled.
- All previously blocked paths finish within the preregistered wall-clock and memory budgets.

Queue:

`mortgage_foreclosure_ltv`, `gov_investment_share`, `bankrupt_persist`, `rental_eviction_arrears`, `soe_efirm`, `tariff`, `fx_regime`

### R8: Policy packages and interaction robustness

Rebuild crisis packages only from accepted single-policy and scenario evidence.

Exit criteria:

- Every package passes primary, guardrail, withdrawal, severity, and alternative-state gates.
- Factorial and ablation evidence identifies essential, redundant, and harmful components.

### R9: Controller, UI, and final acceptance

Refresh delivery timing, human ingress, heuristic, random, and RL transfer evidence after engine repair.

Exit criteria:

- The UI domain and definitions match the accepted Registry and evidence scope.
- Free-immediate and institutional delivery paths share identical economic execution after their documented lags.
- The full native acceptance suite passes with eight test workers.

## Evidence invalidation rule

Frozen audit results remain historical evidence, but a material repair removes their authority for current product claims. The affected stages below must be regenerated before a repaired lever, crisis, package, UI statement, or controller comparison is accepted again.

| Repair phase | Audit stages to regenerate |
|---|---|
| R0 | none |
| R1 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R2 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R3 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R4 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R5 | P0, P1, P2, P3, P4, P5, P6, P7, P8 |
| R6 | P2, P4, P5, P6, P7, P8 |
| R7 | P6, P7, P8 |
| R8 | P5, P7, P8 |
| R9 | P8 |

## Mandatory repair ledger

| Lever | Owner / group | Phases | Frozen dispositions | Repair intent |
|---|---|---|---|---|
| `fiscal_uses_national_accounts_gdp` | `treasury` / `fiscal_stance` | R3 | `engine_route_defect/blocked_by_p2_defect` | `repair_engine_route_defect` |
| `bond_coupon` | `treasury` / `debt_management` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `bond_maturity` | `treasury` / `debt_management` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `lolr` | `central_bank` / `liquidity_operations` | R4 | `unsupported_by_current_engine/blocked_by_p2_defect` | `repair_unsupported_by_current_engine` |
| `bank_capital_constraint` | `regulator` / `macroprudential` | R3 | `mechanism_defect/blocked_by_p2_defect` | `repair_mechanism_defect` |
| `bank_resolution_fund` | `regulator` / `structural_law` | R4 | `unsupported_by_current_engine/blocked_by_p2_defect` | `repair_unsupported_by_current_engine` |
| `margin_ltv` | `regulator` / `macroprudential` | R1 | `accepted/secondary_effect_detected` | `recalibrate_or_reclassify` |
| `margin_max` | `regulator` / `macroprudential` | R1, R4 | `unsupported_by_current_engine/blocked_by_p2_defect` | `repair_unsupported_by_current_engine` |
| `mortgage_underwriting` | `regulator` / `macroprudential` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `mortgage_dsti_cap` | `regulator` / `macroprudential` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `mortgage_stress_rate_addon` | `regulator` / `macroprudential` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `mortgage_risk_weight` | `regulator` / `macroprudential` | R3 | `engine_route_defect/blocked_by_p2_defect` | `repair_engine_route_defect` |
| `mortgage_min_capital_ratio` | `regulator` / `macroprudential` | R3 | `engine_route_defect/blocked_by_p2_defect` | `repair_engine_route_defect` |
| `mortgage_arrears_floor` | `regulator` / `structural_law` | R3 | `mechanism_defect/blocked_by_p2_defect` | `repair_mechanism_defect` |
| `housing_permits` | `treasury` / `fiscal_stance` | R4 | `unsupported_by_current_engine/blocked_by_p2_defect` | `repair_unsupported_by_current_engine` |
| `housing_in_wealth_tax` | `treasury` / `tax_and_transfers` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `deficit_u_cap` | `treasury` / `fiscal_stance` | R3 | `mechanism_defect/blocked_by_p2_defect` | `repair_mechanism_defect` |
| `household_bankruptcy` | `regulator` / `structural_law` | R4 | `unsupported_by_current_engine/blocked_by_p2_defect` | `repair_unsupported_by_current_engine` |
| `bank_migrate_on_failure` | `regulator` / `macroprudential` | R4 | `unsupported_by_current_engine/blocked_by_p2_defect` | `repair_unsupported_by_current_engine` |
| `unified_bank_rwa` | `regulator` / `structural_law` | R4 | `unsupported_by_current_engine/blocked_by_p2_defect` | `repair_unsupported_by_current_engine` |
| `firm_credit_min_dscr` | `regulator` / `macroprudential` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `regulatory_firm_capital_haircut` | `regulator` / `macroprudential` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `regulatory_firm_inventory_haircut` | `regulator` / `macroprudential` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `land_fee_share` | `treasury` / `tax_and_transfers` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `land_fee_stock_elasticity` | `treasury` / `tax_and_transfers` | R2 | `observable_defect/blocked_by_p2_defect` | `repair_observable_defect` |
| `import_quota` | `external_affairs` / `trade_and_migration` | R1 | `accepted/blocked_by_scenario_topology` | `recalibrate_or_reclassify` |
| `immigration_cap` | `external_affairs` / `trade_and_migration` | R1 | `accepted/blocked_by_scenario_topology` | `recalibrate_or_reclassify` |

## Behavior-review ledger

| Lever | Owner / group | Phases | Frozen dispositions | Repair intent |
|---|---|---|---|---|
| `gov_consumption_share` | `treasury` / `fiscal_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `gov_deficit_target` | `treasury` / `fiscal_stance` | R6 | `accepted/primary_no_supported_benefit` | `recalibrate_or_reclassify` |
| `deficit_u_ref` | `treasury` / `fiscal_stance` | R6 | `accepted/primary_no_supported_benefit` | `recalibrate_or_reclassify` |
| `benefit_replacement` | `labor_social` / `labor_and_welfare` | R6 | `accepted/primary_no_supported_benefit` | `recalibrate_or_reclassify` |
| `benefit_income_floor` | `labor_social` / `labor_and_welfare` | R6 | `accepted/accepted_crisis_efficacy/finite_size_confirmed` | `recalibrate_or_reclassify` |
| `pension_replacement` | `labor_social` / `labor_and_welfare` | R6 | `accepted/accepted_crisis_efficacy` | `recalibrate_or_reclassify` |
| `tax_income_rate` | `treasury` / `tax_and_transfers` | R6 | `accepted/secondary_effect_detected/finite_size_confirmed` | `recalibrate_or_reclassify` |
| `energy_price_cap` | `energy` / `energy_operations` | R6 | `accepted/safety_concern/finite_size_confirmed` | `recalibrate_or_reclassify` |
| `energy_rationing` | `energy` / `energy_operations` | R6 | `accepted/safety_concern` | `recalibrate_or_reclassify` |
| `min_wage` | `labor_social` / `labor_and_welfare` | R6 | `accepted/primary_no_supported_benefit` | `recalibrate_or_reclassify` |
| `job_guarantee` | `labor_social` / `labor_and_welfare` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `jg_wage_ratio` | `labor_social` / `labor_and_welfare` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `inflation_target` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_no_supported_benefit` | `recalibrate_or_reclassify` |
| `taylor_phi_pi` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `taylor_phi_u` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `rate_inertia` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `manual_policy_rate` | `central_bank` / `monetary_stance` | R6 | `accepted/accepted_crisis_efficacy/finite_size_confirmed` | `recalibrate_or_reclassify` |
| `monetary_regime` | `central_bank` / `monetary_stance` | R6 | `accepted/primary_no_supported_benefit` | `recalibrate_or_reclassify` |
| `r_neutral` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_no_supported_benefit` | `recalibrate_or_reclassify` |
| `u_natural` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `r_max` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `infl_ema_lambda` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `cb_core_inflation` | `central_bank` / `monetary_stance` | R6 | `accepted_expert_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `cb_uses_fixed_basket_cpi` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `cb_log_inflation` | `central_bank` / `monetary_stance` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `omo` | `central_bank` / `liquidity_operations` | R2, R6 | `accepted/safety_passed/finite_size_confirmed` | `recalibrate_or_reclassify` |
| `bank_min_capital` | `regulator` / `macroprudential` | R6 | `accepted_activation_only/secondary_inactive_in_crisis/finite_size_confirmed` | `recalibrate_or_reclassify` |
| `mortgage_ltv_cap` | `regulator` / `macroprudential` | R6 | `accepted_activation_only/secondary_effect_detected` | `recalibrate_or_reclassify` |
| `mortgage_foreclosure_ltv` | `regulator` / `structural_law` | R6, R7 | `accepted_activation_only/secondary_inactive_in_crisis/scale_execution_blocked` | `recalibrate_or_reclassify` |
| `jg_public_works_share` | `labor_social` / `labor_and_welfare` | R6 | `accepted_activation_only/primary_nonbinding_in_crisis` | `recalibrate_or_reclassify` |
| `gov_investment_share` | `treasury` / `fiscal_stance` | R6, R7 | `accepted/accepted_crisis_efficacy/finite_size_dependency` | `recalibrate_or_reclassify` |
| `bankrupt_persist` | `regulator` / `structural_law` | R6, R7 | `accepted/secondary_effect_detected/finite_size_dependency` | `recalibrate_or_reclassify` |
| `rental_eviction_arrears` | `regulator` / `structural_law` | R6, R7 | `accepted_activation_only/secondary_inactive_in_crisis/scale_execution_blocked` | `recalibrate_or_reclassify` |
| `soe_efirm` | `energy` / `energy_structure` | R6, R7 | `accepted_structural_long_horizon/not_applicable/finite_size_dependency` | `recalibrate_or_reclassify` |
| `tariff` | `external_affairs` / `trade_and_migration` | R6, R7 | `accepted/blocked_by_scenario_topology/scale_execution_blocked` | `recalibrate_or_reclassify` |
| `fx_regime` | `central_bank` / `fx_operations` | R6, R7 | `accepted/blocked_by_scenario_topology/scale_execution_blocked` | `recalibrate_or_reclassify` |

## No-change ledger under current evidence

| Lever | Owner / group | Phases | Frozen dispositions | Repair intent |
|---|---|---|---|---|
| `tax_profit_rate` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `income_allowance` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `tax_consumption_rate` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `tax_necessity_rate` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `tax_luxury_rate` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `tax_wealth_rate` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `wealth_allowance` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `tax_energy_rate` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `tax_energy_windfall` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `spr_target_units` | `energy` / `energy_operations` | regression only | `accepted_activation_only/safety_passed` | `preserve_current_behavior` |
| `spr_flow_cap` | `energy` / `energy_operations` | regression only | `accepted_activation_only/safety_passed` | `preserve_current_behavior` |
| `soe_price_at_cost` | `energy` / `energy_operations` | regression only | `accepted_activation_only/safety_passed` | `preserve_current_behavior` |
| `energy_cap_compensation` | `treasury` / `tax_and_transfers` | regression only | `accepted_activation_only/secondary_inactive_in_crisis` | `preserve_current_behavior` |
| `energy_subsidy_rate` | `treasury` / `tax_and_transfers` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `energy_subsidy_threshold` | `treasury` / `tax_and_transfers` | regression only | `accepted_activation_only/secondary_inactive_in_crisis` | `preserve_current_behavior` |
| `bond_finance_frac` | `treasury` / `debt_management` | regression only | `accepted/safety_passed/finite_size_confirmed` | `preserve_current_behavior` |
| `omo_reserve_target` | `central_bank` / `liquidity_operations` | regression only | `accepted/safety_passed` | `preserve_current_behavior` |
| `omo_drain_frac` | `central_bank` / `liquidity_operations` | regression only | `accepted/safety_passed` | `preserve_current_behavior` |
| `bank_leverage_cap` | `regulator` / `macroprudential` | regression only | `accepted_activation_only/secondary_effect_detected` | `preserve_current_behavior` |
| `bank_target_capital_ratio` | `regulator` / `macroprudential` | regression only | `accepted_activation_only/secondary_inactive_in_crisis` | `preserve_current_behavior` |
| `bank_exposure_limit` | `regulator` / `macroprudential` | regression only | `accepted_activation_only/secondary_inactive_in_crisis` | `preserve_current_behavior` |
| `bank_bond_duration_limit` | `regulator` / `macroprudential` | regression only | `accepted/secondary_inactive_in_crisis` | `preserve_current_behavior` |
| `reserve_floor_frac` | `central_bank` / `liquidity_operations` | regression only | `accepted/safety_passed` | `preserve_current_behavior` |
| `kappa` | `regulator` / `macroprudential` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `hh_credit_limit` | `regulator` / `macroprudential` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `housing_transfer_tax` | `treasury` / `tax_and_transfers` | regression only | `accepted_activation_only/secondary_effect_detected` | `preserve_current_behavior` |
| `housing_property_tax` | `treasury` / `tax_and_transfers` | regression only | `accepted_activation_only/secondary_effect_detected` | `preserve_current_behavior` |
| `deposit_rate_floor` | `regulator` / `macroprudential` | regression only | `accepted/secondary_effect_detected` | `preserve_current_behavior` |
| `omo_index_deposits` | `central_bank` / `liquidity_operations` | regression only | `accepted/safety_passed` | `preserve_current_behavior` |
| `export_subsidy` | `external_affairs` / `trade_and_migration` | regression only | `accepted/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `capital_control` | `central_bank` / `fx_operations` | regression only | `accepted_activation_only/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `external_interest_settlement_fraction` | `central_bank` / `fx_operations` | regression only | `accepted_activation_only/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `sanctions_imposed_on` | `external_affairs` / `trade_and_migration` | regression only | `accepted/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `emigration_cap` | `external_affairs` / `trade_and_migration` | regression only | `accepted/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `remittance_tax` | `external_affairs` / `trade_and_migration` | regression only | `accepted/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `outward_remittance_tax` | `external_affairs` / `trade_and_migration` | regression only | `accepted/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `guest_worker_return` | `external_affairs` / `trade_and_migration` | regression only | `accepted/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `peg_anchor` | `central_bank` / `fx_operations` | regression only | `accepted/blocked_by_scenario_topology` | `preserve_current_behavior` |
| `peg_reserve_scale` | `central_bank` / `fx_operations` | regression only | `accepted_activation_only/blocked_by_scenario_topology` | `preserve_current_behavior` |

## R0 non-goals and stop rule

- R0 changes no Registry domain, native route, economic equation, scenario, or controller behavior.
- The 36 behavior candidates are hypotheses for retesting, not a declaration that all 36 mechanisms are broken.
- The 39 no-change entries have no current modification evidence; they remain subject to final regression and future evidence.
- P8 human paths are transport fixtures rather than participant performance data, and its RL run is only a transfer probe.
- R0 stops after this ledger, its machine-readable twin, focused tests, and an eight-worker acceptance run are committed.
- R1 must start on a new milestone decision; R0 does not silently include validation or engine repairs.
