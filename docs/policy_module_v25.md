# v25: The Policy Module (DRAFT — skeleton)

**Status**: blank scaffold, design not yet frozen · **Branch**: TBD (`feat/policy-module`, off dev after the v24 merge)
**Goal**: complete the existing Config/Policy split — every lever a real-world authority could
change at a meeting becomes runtime-mutable PolicyState, driven by pluggable controllers
(frontend player / scripted / random / heuristic / RL). The action stream doubles as the
save-container `events.log` and, later, the frontend network protocol.

---

## 0. Boundary principle

> Policy = what an authority (government / central bank / immigration office) can decide at
> runtime. Config = the immutable rest: structure, CAPABILITIES, physics, preferences,
> technology, demography.

## 1. Lever inventory (P0 deliverable — REVISED after user audit 2026-07-18; NOT yet complete)

> **Status: the original "COMPLETE SWEEP" claim was WRONG and is retracted.** User audit
> (read-only, against 4c0637e) found: Config has **364** dataclass fields (my regex dump
> caught 357 — missed `lambda_I, delta_K, A, a_K, K_firm0, kappa_E, a_E`); 10 fields were
> dumped but never classified; `peg_economy` was omitted from the World list; several
> high-confidence policy items were misclassified as physics/infra; and — the two deeper
> classes — (a) **hard-coded institutions** invisible to any field scan (§1.6), and
> (b) **levers that are listed but not runtime-effective** (§1.7). Completeness gate for
> P0: a MACHINE-VERIFIED classification (script asserts every field appears in exactly one
> bucket) + the hardcoded-institution sweep + per-lever effectiveness tests.

Sources actually swept so far: 370 root-Config fields, 34 World keyword tunables (35 user
params incl. `configs`; the v27 `shocks` input is classified as Shock module, not Policy;
peg_economy: migration into ExternalPolicy PENDING the §5.1
multi-pegger ruling), the existing
Policy class (88 levers). **STILL-UNSWEPT sources — explicit machine-sweep manifest (P0):**
`SocialDynamicsConfig` (35 fields, demographics/social.py) · `RelationshipConfig` (12
fields, demographics/relationships.py) · `LifecycleHouseholdConfig` · the derived snapshots
in `config/schema.py` · function-signature defaults / literal scan of production modules.
EXCLUDED as test harness: `Phase1AcceptanceConfig`.
The machine inventory classifies every entry as one of: live parameter | genesis-only |
derived-from-root-Config | declared-but-unused | policy candidate | true literal/function
default.

### 1.1 The surprise: Policy already exists and is half-built

`core/policy.py` currently DECLARES 46 fields (all fiscal spending/taxes incl. v18
differential VAT, all v17 energy policy, labour floors + JG, the Taylor rule +
`policy_rate_override` (a hand-set player rate!), OMO/LoLR, 4 macropru handles, 5 housing
handles). **Most are behaviour-live, but known dead / init-snapshot / metrics read-point
defects remain — see §1.7.** P0 = close the gaps below, not build from zero.

### 1.2 POLICY levers — CANDIDATE LIST (103 classified: 46[P] + 40[C] + 14[W] + 4[N] − 1
dead; PENDING = 0, all rulings closed 2026-07-18; hard-coded institutions not yet counted),
by domain

Location key: **[P]** already in Policy · **[C]** in Config, must migrate · **[W]** World
constructor param, needs a per-economy home · **[N]** NEW target lever (exists in no
source today).

**Fiscal — spending & transfers** (8): [P] gov_consumption_share, gov_deficit_target,
deficit_u_ref, benefit_replacement, benefit_income_floor, pension_replacement ·
[C] deficit_u_cap, gov_investment_share

**Fiscal — taxes** (13): [P] tax_profit_rate, tax_income_rate, income_allowance,
tax_consumption_rate, tax_necessity_rate, tax_luxury_rate, tax_wealth_rate,
wealth_allowance, tax_energy_rate, tax_energy_windfall · [P] housing_transfer_tax,
housing_property_tax, housing_in_wealth_tax

**Labour institutions** (3): [P] min_wage, job_guarantee, jg_wage_ratio
(jg_productivity moved to PENDING_RULING — technology vs programme design)

**Monetary — rate rule** (7) — **A5 RULED (2026-07-18)**:
[N] `monetary_regime ∈ {"exogenous","taylor","manual"}` with the invariant
`regime == manual ⇔ manual_policy_rate != None` (code fact verified: override already
precedes the central_bank check in set_policy_rate, so manual works with CB "off") ·
[P] inflation_target, taylor_phi_pi, taylor_phi_u, rate_inertia, policy_rate_override
(RENAMED `manual_policy_rate` at migration) · [C] r_max.
**`central_bank_enabled` is DROPPED** (verified: OMO/LoLR read policy.omo/lolr +
structural capabilities bonds/interbank — cfg.central_bank never gated an institution,
only the rule/frozen switch); `Policy.central_bank` is DELETED at migration;
`Config.central_bank` consumed only by from_legacy_config.
**`r_interest` demotes to `PolicySeed.initial_policy_rate`** (seeds `_rate`, provides the
exogenous fixed rate, legacy compat) — NOT a runtime lever, so there is exactly ONE manual
rate path (regime=manual); ScheduledController hikes go through manual, never the seed.
Sensor rule: inflation EMA updates under taylor AND manual (exogenous stays frozen for
legacy trajectories) — no hidden jump on manual→taylor. Regime switches are ATOMIC action
batches; manual→taylor re-enters inertia from the CURRENT `_rate`.

**Monetary — beliefs & measurement** (5): [C] r_neutral, u_natural (the CB's structural
ESTIMATES — the CB chooses them), cb_core_inflation, cb_uses_fixed_basket_cpi (the Germany
lesson: the target-index choice is itself policy), cb_log_inflation

**Monetary — quantity tools** (5): [P] omo, omo_reserve_target, omo_drain_frac, lolr ·
[C] omo_index_deposits

**Treasury debt management** (3): [C] bond_finance_frac, bond_coupon, bond_maturity

**Macroprudential — banks** (9): [C] bank_capital_constraint(regime) · **[N]
bank_leverage_cap** (bank_leverage_mean itself STAYS Config as the genesis risk-appetite
draw, per §1.7) · [C] bank_target_capital_ratio, bank_exposure_limit, bank_min_capital,
bank_bond_duration_limit, bank_resolution_fund(regime), reserve_floor_frac · [P] kappa

(Tagging rule, machine-parse friendly: a tag is re-stated at EVERY source change.)

**Macroprudential — households & mortgages** (11): [P] margin_ltv, margin_max,
hh_credit_limit, mortgage_ltv_cap · [C] mortgage_underwriting(regime), mortgage_dsti_cap,
mortgage_stress_rate_addon, mortgage_risk_weight, mortgage_min_capital_ratio,
mortgage_foreclosure_ltv, mortgage_arrears_floor

**Insolvency law** (2): [C] bankrupt_persist, household_bankruptcy(regime)

**Housing supply** (1): [P] housing_permits

**Energy policy** (9): [P] spr_target_units, spr_flow_cap, soe_price_at_cost,
energy_price_cap, energy_rationing, energy_cap_compensation, energy_subsidy_rate,
energy_subsidy_threshold · [C] soe_efirm (ownership regime = a NATIONALISATION lever)

**External — trade & capital** (7, all [W], no per-economy owner today): capital_control,
tariff, import_quota, export_subsidy, sanctions, remittance_tax, outward_remittance_tax

**External — FX regime** (3): [W] peg(regime), peg_anchor, peg_reserve_scale
(defence intensity; peg_reserves0 is a genesis ENDOWMENT = structure)

**Migration** (3): [W] immigration_cap, emigration_cap, guest_worker_return

**Reclassified INTO policy by the user audit** (were physics/infra in the first cut):
- external_interest_settlement_fraction [W] — source calls it external CONTRACT POLICY;
  tests mutate it mid-run to cure arrears (test_capital.py:326)
- land_fee_share [C] — the developers' land fee to the fiscus (land INSTITUTION, not physics);
  land_convexity: see PENDING_RULING
- rental_eviction_arrears [C] — eviction law (same family as foreclosure/bankruptcy timelines)
- unified_bank_rwa [C] — the unified regulatory-capital REGIME switch (its own sub-params are
  already policy)
- firm_credit_min_dscr [C] — economy-wide corporate underwriting floor, isomorphic to
  mortgage_dsti_cap

- infl_ema_lambda [C] — the CB's inflation-signal smoothing (consistency with r*/u*/index
  choice: the CB's measurement apparatus is policy)
- fiscal_uses_national_accounts_gdp [C] — the FISCAL RULE's GDP-measure choice (not shared
  reporting infra)
- bank_migrate_on_failure [C] — REVERSED ruling: purchase-&-assumption vs stranding is bank
  RESOLUTION REGIME, not plumbing

**PENDING_RULING: ALL FIVE CLOSED (user rulings, 2026-07-18):**
- firm_capital_haircut / firm_inventory_haircut → **[C] Policy** as
  `regulatory_firm_capital_haircut` / `regulatory_firm_inventory_haircut`
  (uniform macroprudential haircuts; effective_semantics = **new-credit-only** — a raised
  haircut shrinks NEW lending capacity, never restates existing loans). Future private
  underwriting: `effective = max(regulatory, bank.private_haircut)` with the bank side as
  agent behaviour.
- land_convexity → **[C] Policy** as `land_fee_stock_elasticity`, in the land-fiscal block
  with land_fee_share; effective_semantics = **new-construction-only**. DOCTRINE: physical
  land scarcity, if ever modelled, gets its own Config (`land_scarcity_cost_elasticity`)
  and must be a REAL resource cost — never a fiscal transfer sharing a parameter with the
  fee schedule.
- jg_productivity → **stays Config** (public-works TECHNOLOGY; a government cannot vote
  engineering efficiency). NEW **[N] `jg_public_works_share` ∈ [0,1]**: the government's
  programme-composition choice; `jg_capital = cfg.jg_productivity × policy.share × jg_emp`.
  DEFAULT 1.0 = today's implicit share (bit-identical; 0 would silently gut legacy JG).
- deposit_rate → **stays Config**, renamed `deposit_rate_base` at migration (private bank
  pricing base — NOT a central-bank rate). Three-layer target:
  `bank_rate = max(base + bank.spread, policy.deposit_rate_floor)`; NEW **[N]
  `deposit_rate_floor`** (default 0.0 = never binds = bit-identical); full administered
  regime (`deposit_rate_regime`) deferred until deposit competition is genuinely active.
  FILED DEFECT: deposit_rate_disp drives depositor shopping while actual interest uses the
  global rate — benchmark and quote are conflated.
- ALL renames carry legacy-name aliases + deprecation warnings in from_legacy_config.

### 1.3 Ambiguous — rulings taken (flag any objection)

| Field | Ruling | Reason |
|---|---|---|
| r_neutral / u_natural | policy | the CB's own estimates, revisable at a meeting |
| cb_log_inflation | policy | the CB's measurement method choice |
| bank_leverage_mean | config (REVISED) | genesis risk-appetite draw; the live cap is the NEW bank_leverage_cap lever |
| bankrupt_persist / foreclosure params | policy | insolvency/foreclosure law |
| soe_efirm | policy | runtime flip = nationalisation/privatisation event |
| jg_productivity | PENDING_RULING | technology vs programme design (see 1.2) |
| bank_migrate_on_failure | ~~config~~ → **policy** | user audit: resolution regime (P&A vs stranding) |
| fiscal_uses_national_accounts_gdp | ~~config~~ → **policy** | user audit: the fiscal rule's own measure choice |
| master switches | config, via the CAPABILITY/REGIME split | `X_enabled` = Config capability; the live regime choice (monetary_regime, job_guarantee, lolr, peg, …) = Policy. Resolves the central_bank contradiction |
| migration_rate / migration_max_share | config | behavioural propensity, not a cap |
| energy_shock_at/magnitude/duration | **shock module** | exogenous events, not policy |

### 1.4 Root-Config/World working residual — nested-source verification pending

(Previously titled "complete"; renamed — unswept nested configs make completeness a P0
machine-inventory deliverable, not a claim. The machine registry must use
SOURCE-QUALIFIED ids (`Config.omo` vs `Policy.omo`): Config and Policy share **43
same-name fields**, so bare names cannot prove one-bucket-per-source-field.)

Formally placed here (audit round 3/4): `Config.bank_leverage_mean` (genesis risk-appetite
draw, physics); `Config.central_bank` → pending semantic split / planned RENAME to
`central_bank_enabled` (capability flag, mechanism) — the target name does not exist as a
source field today.

**Previously UNCLASSIFIED (user audit; now placed)**: demographics_population (structure),
public_capital_gamma, public_capital_depreciation (physics — public-capital technology),
lambda_I, delta_K, A, a_K, K_firm0, kappa_E, a_E (physics/genesis — capital & energy
technology; missed by the regex dump). [W] peg_economy: recorded — **PROPOSED (not
frozen)**: delete in favour of each economy's own peg choice in ExternalPolicy; blocked on
the §5.1 multi-pegger / cyclic-peg / anchor-switch ruling; migration note mandatory.

**Structure / genesis / scale** (immutable by nature): n_households, n_firms, n_ticks, seed,
simulation_start_date,
a, n_firms_c, n_firms_k, n_firms_e, n_banks, n_builders, d_household0, d_firm0, d_cfirm0,
d_kfirm0, d_efirm0, d_bank0, p_firm0, p_kfirm0, p_efirm0, w_firm0, inv_firm0, inv_kfirm0,
mu_firm0, demand_e_firm0, startup_deposits, startup_capital, float_shares, shares_per_firm,
watchlist_size, genesis_founder_pool, founder_owned_genesis, bank_capital_frac,
house_price_income_years, ticks_per_year, energy_util0, [W] peg_reserves0, base_seed,
periods_per_year.

**Physics — behavioural parameters**: lambda_d, lambda_y, phi, eta, mu_min, mu_max,
theta_price, delta, wage_indexation, omega, theta_wage, alpha1, alpha2,
lifecycle_alpha_income, lifecycle_alpha_wealth_draw, mpc_dispersion, mpc_wealth_curvature,
rho, search_m, alpha, v, dis_slope, gibrat_sigma, pref_attach_beta, pref_price_elasticity,
gibrat_entry_a0, portfolio_adjust, q_invest_smooth, lambda_p, w_chartist, w_fundamental,
theta_equity, trend_lambda, wealth_effect, equity_ema_lambda, resid_income_lambda, lambda_q,
q_invest_floor, q_invest_cap, lambda_issue, hh_subsistence, hh_amort, amort,
investment_user_cost_elasticity/_min/_max/_floor,
valuation_discount_floor, valuation_risk_premium, energy_intensity, energy_coverage_ticks, energy_gap_close,
energy_hoarding_beta, energy_hh_share, energy_mortality_gamma, energy_mortality_mult_hi,
welfare_quit_hazard, reservation_markup, efficiency_sigma, job_search_intensity,
ladder_search_intensity, ladder_premium, churn_annual, lambda_fire, layoff_band,
layoff_target_smooth, suspension_timer, suspension_quit_discount, inventory_gap_close,
subscale_viability_workers, subscale_grace_days, subscale_exit_hazard, k_entry_demand,
k_entry_hazard, entry_beta, entry_max, shell_exit_ticks, real_entry_signal, entry_hurdle,
capital_clock_demand_smoothing, bank_leverage_disp, bank_spread_disp, bank_search_m,
deposit_rate_disp, deposit_search_m, bank_equity_lambda, bank_theta_equity, bank_entry_beta,
bank_entry_max, run_sensitivity, run_health_ref, run_market_weight, run_fear_persistence,
interbank_rate_base, interbank_tightness, bond_theta, bank_bond_appetite, rent_yield0,
rent_adjust, rent_burden_cap, rental_investor_premium,
housing_ask_markup, housing_forced_discount, housing_ask_decay, housing_search_k,
housing_buyer_buffer, housing_distress_floor, housing_session_interval,
builder_productivity, builder_demand_seed, builder_demand_price_gain,
builder_inventory_buffer,
housing_wealth_effect, family_transfer_buffer, switch_retool_loss, switch_return_gap,
switch_pressure_days, switch_hazard, necessity_share0, n_firm_share, subsistence_share,
tfp_drift_rate, tfp_drift_sigma, tfp_law, tfp_learning_theta, tfp_drift_c/_k/_e,
[W] fx_lambda, fx_friction, fx_spread, fx_trade_cap, capital_mobility, capital_adjust,
migration_rate, migration_max_share, remittance_share, wage_smoothing.

**Physics — demography**: demographics_tfr, demographics_mortality_scale,
demographic_marriage_enabled, demographic_divorce_enabled,
demographic_marriage_market_interval_days, demographic_annual_marriage_rate_peak,
demographic_annual_divorce_rate_base, demographic_adult_leaving_home_enabled,
demographic_leave_home_min_age, demographic_leave_home_peak_end_age,
demographic_annual_leave_rate_peak, demographic_annual_leave_rate_late,
fertility_income_elasticity + mult bounds, mortality_income_elasticity + mult bounds,
mortality_rank_gradient, fertility_rank_gradient, strat_mult_lo/hi, marriage_assortativity,
housing_leave_elasticity + bounds, housing_fertility_elasticity + bounds.

**Mechanism flags (model composition — Config)**: demographics_enabled,
demographic_lifecycle_consumption, housing_enabled, housing_market_enabled,
mortgage_enabled, housing_rental_enabled, housing_construction_enabled,
labor_accounting, labor_matching, labor_fractional_hours, labor_second_job,
labor_suspension, labor_matching_friction, labor_relationship_wages, labor_job_ladder,
labor_person_efficiency, labor_participation, capital_rationed_signal,
consumption_rationed_signal, firm_subscale_exit, capital_firm_entry, firm_full_pnl,
capital_service_pricing, priced_firm_balance_sheet, bank_enabled, bank_realized_pnl,
bank_assignment, bank_rate_competition, bank_relationship_lock_in,
interbank, bank_equity, bank_equity_trading, bank_dynamics, bank_runs, bonds, government,
capital_market, per_firm_equity, equity_finance, household_credit,
household_interest_arrears, margin_credit, gibrat_growth, firm_dynamics, symmetric_k,
k_replacement_floor, energy_enabled, energy_household, deprivation_gauges,
national_accounts_metrics, consumption_strata,
family_transfers, sector_switching, monetary_direct_transmission, interest_by_deposits,
index_startup, capital_annual_clock, pro_rata_dividends, builder_land_fee_credit,
deposit_interest_arrears, demo feedback/burnin flags,
[W] couple, trade, capital, migration, fx_loss_mutualization.

**Infra / numerics / diagnostics**: claims_reconcile_interval, ledger_rel_tol,
bond_maturity_bucket, capital_service_min_utilization, rental_vacancy_deadband,
rental_rent_floor_wage_share, housing_demand_step, housing_ask_floor_wage_share,
cpi_item_link_cap,
cpi_rebase_interval_days, demo_feedback_burnin_years,
demo_signal_halflife_years, housing_signal_burnin_years, energy_signal_burnin_years,
deprivation_burnin_years, deprivation_acute_days, deprivation_chronic_days,
_capital_annual_clock_applied.

**Shock module (excluded here)**: energy_shock_at, energy_shock_magnitude,
energy_shock_duration.

### 1.5 P0 gap analysis (the actual work)

1. **40 existing [C] fields migrate into Policy (3 with renames + legacy aliases:
   regulatory haircuts, land_fee_stock_elasticity) + [N] bank_leverage_cap /
   jg_public_works_share / deposit_rate_floor are created; [N] monetary_regime replaces
   the dead `Policy.central_bank`** (banking macropru block, mortgage regulation block, monetary beliefs/measurement incl.
   infl_ema_lambda + fiscal_uses_national_accounts_gdp, Treasury debt management,
   insolvency law + eviction law, land fee, DSCR, unified_bank_rwa,
   bank_migrate_on_failure, deficit_u_cap, gov_investment_share, soe_efirm,
   r_interest/r_max, omo_index_deposits) + their read-point rewires. All five former
   PENDING_RULING items are closed (see 1.2).
2. **The external domain needs a per-economy owner**: 14 [W] levers (incl.
   external_interest_settlement_fraction) live as World
   constructor vectors with no Policy home. Create `ExternalPolicy` inside each economy's
   PolicyState; World reads per tick (peg regime: pegger's own choice + anchor consent
   question deferred).
3. **Registry validation**: every lever declares a PER-TYPE validation rule (numeric:
   min/max/max_step; bool/enum: choices; set & bilateral actions: membership + pair rules)
   — one declaration = validation + random-controller domain + RL action space.
4. The run spec provides a full `initial_policy` (PolicySeed); `from_legacy_config` exists
   only as the versioned compatibility converter for old YAML; NullController = freeze
   `initial_policy` = bit-identical; checkpoints store the full Policy snapshot.

### 1.6 Hard-coded institutions a field scan CANNOT see (user audit; sweep = P0 work item)

Real-world-changeable rules living as literals in code — each needs a ruling
(promote to lever | document as model simplification):

- **Monetary**: policy-rate FLOOR hard-coded 0 (r_max exists, r_min does not) — central_bank.py:54
- **Labour/pension law**: working age 18–64, pension eligibility 65 — economic_state.py:389;
  split out labor_min_age / statutory_retirement_age / pension_eligibility_age
- **Family & inheritance law**: estate tax fixed 0; intestate succession fixed
  spouse/children 50/50 (inheritance.py:49); probate window fixed 365d (economic_bridge.py:2065) — TRUE literals.
  CORRECTION (audit round 4, fact-checked): marriage min-age, remarriage cooldown and the
  close-kin flag are ALL `SocialDynamicsConfig` fields (not RelationshipConfig; unswept
  nested source; enter the machine inventory as policy candidates there). The same-sex
  restriction (`a.sex == b.sex`, social.py:402) and the 50/50 marital-gain split
  (`target_gain = .../2.0`, marriage_economics.py:61) ARE true hard-coded literals and stay
  in this section; probate window literal at economic_bridge.py:2065
- **Financial regulation literals**: ordinary-credit RWA fixed 100%; resolution fund covers
  100% of residual; LoLR funds the FULL gap; mortgages fixed non-recourse; household
  bankruptcy = full discharge of residual margin debt
- **Second-tier**: SPR sells at 99.9% of market; energy price-cap compensation fixed at
  100% of the gap; government procurement sector composition non-adjustable

### 1.7 Listed-but-NOT-runtime-effective (the dangerous class; per-lever tests will gate)

- **Policy.central_bank is a DEAD FIELD**: the rate path checks cfg.central_bank
  (central_bank.py:43); mutating econ.policy.central_bank does nothing
- **MortgageBook snapshots policy at Economy init** (economy.py:366): only LTV re-syncs at
  runtime; DSTI / risk-weight / foreclosure params are stale copies
- **soe_efirm only writes Firm.state_owned at creation** (energy.py:171): runtime flip does
  not (de)nationalise existing firms; ownership/payment transition semantics missing
- **bank_leverage_mean is a GENESIS DRAW parameter** (per-bank risk appetite), not a live
  cap. Ruling: keep appetite distribution in Config; create a separate bank_leverage_cap
  policy lever
- **bond_coupon is not stored per lot**: runtime change would retroactively re-coupon the
  whole stock. Correct semantics: new-issue-only (or declare floating-rate explicitly)
- **jg_productivity / deposit_rate**: see PENDING_RULING (semantic splits before promotion)
- **Legacy Config cannot CONFIGURE three Policy initial values** (precision fix, round 5:
  `from_config` does construct a complete Policy — via dataclass defaults — but
  tax_necessity_rate, tax_luxury_rate, policy_rate_override have no Config counterparts to
  set them from; policy.py:97). **DECIDED (round 3) seed architecture** (PolicySeed carries
  a `policy_schema_version`): the run spec carries a full `initial_policy` (PolicySeed);
  `from_legacy_config` remains ONLY as old-YAML compatibility; a checkpoint stores the
  full Policy snapshot; `events.log` stores only post-genesis deltas. (All body text now
  states this directly; no superseded phrasing remains.)
- **OMO split-brain**: behaviour reads Policy but the metrics enable-check and fallback
  still read Config (metrics.py:1629) — mutating Policy desynchronises behaviour from
  observation; per-lever effectiveness tests must cover the METRIC path too
- **STATE-DEPENDENT CLAMP SHADOWING (B1 batch-2 catch)**: the ENTIRE Taylor family
  (inflation_target, φπ, φu, rate_inertia) is inert at the ZLB — the v13 world's
  deflationary rate path is clipped at the hard-coded 0 floor, so both A/B arms read
  0.0 identically; an over-strong liftoff pins BOTH arms at r_max instead (the ceiling
  twin). Liveness is only observable in the INTERIOR (tuned liftoff: π* = −2e-3 →
  mean rate ~3.7e-4 between 0 and r_max 5e-4). Registry/matrix consequence: lever
  effectiveness can be STATE-dependent; the coverage matrix records the state
  constructed for each test.
- **FIXTURE GAPS (documented skips)**: LOLR needs a bank-run crisis fixture (calm
  fixtures leave lolr_advances ≡ 0); macroprudential caps (kappa, hh_credit_limit,
  margin_ltv, margin_max) multiply a ZERO base in small stable v13 economies
  (credit-dormant: firms self-finance, total_credit == 0 for 150+ ticks even with thin
  firms) — stressed fixtures deferred; the X2 extreme world exercises both at scale.
- **DIRECTION ANOMALY (B1 batch-3, filed to investigate)**: soe_price_at_cost RAISES the
  market average energy price ~3% in the small fixture — cost ≤ markup price should pull
  the ask average down. Suspects: price-metric weighting (transaction/composition) or SOE
  unit cost exceeding its markup-discounted ask. Lever proven live; direction unasserted.
- **SHADOWED_BY: benefit_replacement ⟂ job_guarantee (B1 catch)**: the uncapped JG
  absorbs ALL unsold labour, so the unemployment-benefit base is identically zero while
  job_guarantee=True — the rate lever is inert (economically correct; must be a declared
  registry relationship). Companion metric note: `benefit_paid` INCLUDES pensions
  (settlement.py:265 double-posts) — misleading name, observe benefit−pension for the
  pure component. `job_guarantee_wage` is a PASSIVE posted-wage gauge (ratio × mean wage,
  regardless of the flag); the activity gauge is jg_employment, observable only in slack
  windows (genesis clearing works).
- **PRECEDENCE SHADOWING (historical behavior, removed in the native engine)**:
  `gov_consumption_share` was a NO-OP while `gov_deficit_target>0` in the old
  Python branch order. The native fiscal rule treats the deficit target as the
  discretionary envelope and the consumption share as its composition cap, so
  both levers now remain effective.

## 2. Architecture (three layers)

- **Controller** (pluggable): `Null` (constant, bit-identical) · `Scheduled` (tick→value script;
  the shock-module cousin) · `Random` (bounded walk, own RNG stream) · `Heuristic` ·
  `RLAdapter` (gym-style) · later `Frontend`.
- **PolicyState**: per-economy registry. Each lever declares (user-audit-extended schema):
  a PER-TYPE **validation union** (numeric: min/max/max_step · bool/enum: choices · set &
  bilateral: membership + pair rules) · **owner/scope** (single economy | bilateral | world)
  · **type/choices/nullability/shape** · **effective_semantics** (immediate |
  new-contracts-only | restates-stock | state-transition) **each binding a concrete
  `handler_id`/`transition_spec` — an enum tag with no handler is invalid; filled
  per-lever** · **capability dependency** (e.g. OMO requires bonds+banking) · **the unique
  runtime read-point** (metrics must read the same source) · **player_help**（全部 102 个杠杆
  均含通俗定义、模型传导、决策取舍和建议观察指标；由政策模块统一维护，前端不自行猜测）。
  One declaration = validation +
  random domain + RL action space + frontend form + player-facing explanation. World-level policies are OWNED by each
  economy's PolicyState; the World applies them via the NORMATIVE execution order:
  **collect from all economies → validate jointly → commit atomically at the coupling
  barrier** (no one-tick skew from per-economy ordering).
- **Read-point migration**: modules read `econ.policy.X`, never `cfg.X`. Initial values
  come from the run spec's `initial_policy` (PolicySeed); legacy YAML passes through
  `from_legacy_config`.

## 3. Disciplines (inherited from v24 lessons)

1. Bit-identity: NullController freezing `initial_policy` (legacy runs: the
   `from_legacy_config` conversion of today's Config) == today's behaviour; digest-gated.
   Decision point fixed at top-of-tick; controller uses an isolated RNG stream.
2. Checkpoint-able: controller state pickles; **policy is STATE and must resume exactly**
   (the inverse of the "tolerances are policy, not state" lesson).
3. Actions are events: every change logged with the PROVISIONAL ENVELOPE
   `(tick, actor_economy, lever, old, new, actor, target, direction, scope, sequence,
   schema_version)` (bilateral fields null for domestic levers; the bilateral
   initiator/direction/consent semantics are pending the §5.1 ruling, so the envelope is
   not yet frozen) → `.msim` events.log slot → replay / audit / frontend protocol in one
   schema.
4. Explicit observation contract: `observe()` returns a curated snapshot — the RL observation
   space and the frontend UI data contract.

## 4. Phases & acceptance

| Phase | Content | Acceptance |
|---|---|---|
| P0 | Machine-verified inventory + hardcoded-institution sweep + PolicyState extension + read-point migration | digest bit-identical; full suite green; **per-lever effectiveness test: mutate ONLY policy mid-run, assert behaviour responds** (a digest gate alone cannot catch dead fields like Policy.central_bank) |
| P1 | Null/Scheduled/Random controllers + action log + checkpoint integration | Scheduled replay bit-identical; boundedness tests |
| P2 | observe() contract + demo heuristic (counter-cyclical fiscal) | 30y portrait A/B: heuristic vs Null |
| P3 | gym env adapter (step = N ticks; reward = injectable callable) | RL interface smoke with random policy |

## 5. Open questions (rulings pending)

- [ ] Reward left as injectable callable in P3 (research question, not module scope)?
- [x] World-level policy ownership: **DECIDED — per-economy PolicyState**.
- [x] **A6 RULED (2026-07-18) — bilateral semantics**:
  - **Sanctions**: unilateral OWNERSHIP, symmetric EFFECT. Each economy's PolicyState
    holds `sanctions_imposed_on: frozenset[EconomyId]`; the world derives
    `sanctioned(i,j) = j in imposed[i] or i in imposed[j]` (the old global pair-set
    becomes a derived cache, never authoritative). An imposer can lift only its own
    stance; the block persists while ANY stance stands. Events:
    `actor_economy=i, target=j, operation=add/remove, effect=symmetric_block`.
    **SCOPE (code fact)**: sanctions currently gate TRADE partner choice and MIGRATION
    only — capital flows do not call sanctioned(); P0 documents this exact scope, no
    silent "all cross-border flows" claim.
  - **Peg**: NO anchor consent (the anchor is a referenced currency; all defence costs
    and break risk are the pegger's). Anchor CHANGE is a transition handler: liquidate/
    convert old-anchor reserves → acquire new-anchor reserves → reset pent_up →
    re-anchor at the current cross rate → full event.
  - **Multi-pegger**: data model is multi from P0 — per-pegger
    `PegState{anchor, intact, pent_up, reserve_account_id, reserve_scale}` in
    `world.peg_states: dict[EconomyId, PegState]`, reserve accounts keyed
    `CBRES:{pegger_id}` (a shared account would corrupt multi-pegger reserves).
    P0 runtime constraint: ≤1 pegger, anchor ≠ pegger, anchor must not itself peg.
    P1 relaxes to many peggers; anchor-not-pegger stays (kills chains and cycles:
    A→USD, B→USD, C→EUR legal; A→B→USD and A↔B illegal). `peg_economy` DELETED —
    derived from `[e for e in economies if e.policy.fx_regime == "peg"]`; legacy World
    configs map through the converter.
  - **CROSS-ISSUE = FILED CURRENT DEFECT**: peg_defense computes pressure from STATIC
    `cfg.r_interest` and the WORLD MEAN — live Taylor/manual rate moves never affected
    reserve pressure in ANY run to date (including all three portraits). Must become
    `mismatch = anchor._rate − pegger._rate` (live rates, own anchor).

### 5.1 Pre-freeze implementation closure (audit round 3 — must land before P0 code)

1. `monetary_regime`: define the concrete choices + the legacy-config mapping (whether
   `central_bank` is truly an institutional capability is itself unverified).
2. **Full metrics/diagnostics read-point sweep** — the split-brain is not just OMO:
   r_neutral, u_natural, mortgage capital ratios, bank capital/exposure/reserve params all
   have Config-reading metric paths.
3. World-level policies: collect → validate → **atomically commit at the coupling barrier**
   (no one-tick skew from per-economy ordering).
4. peg_economy deletion: specify multi-pegger support or its rejection, cyclic-peg
   detection, reserve-account ownership, anchor switching.
5. Bilateral event-log schema: `target / direction / scope / sequence / schema_version`.
6. Typed validation: `(min,max,max_step)` fits numerics only; bool / enum / set /
   bilateral actions get per-type validation rules.
7. `effective_semantics` must BIND actual transition/cohort handlers (SOE ownership
   transition, peg break/switch, bond new-issue cohorts, mortgage stock restatement) —
   an enum tag with no handler is a dead promise.
- [ ] Lever set for P0: full sweep vs start with fiscal+monetary only?
- [ ] Action cadence: every tick vs policy-meeting interval (e.g. every 30 ticks)?

## 6. Relationship to the shock module (the OTHER v25 candidate)

ScheduledController already covers POLICY shocks. The exogenous-shock module (crises:
disasters, pandemics, embargoes, productivity/energy shocks) is a separate module hitting
PHYSICS levers — designed after this one; shares the events.log schema.

---

## 6. Implementation close-out (2026-07-18, B-track COMPLETE)

The ledger closed at **102 candidates, every one with an owner**:
`88 [P] (Policy) + 14 [W] (ExternalPolicy) + 0 [C] + 0 [N] + 0 PENDING`
(dead `Policy.central_bank` deleted; every [N] absorbed into [P]).
Frontier digest `43ed38f7` bit-exact through every batch.

| Batch | Commit | Content |
|---|---|---|
| B1-B3 | 87d6ab0..b69a8e2 | effectiveness scaffold (40+ A/B tests), B2 defect fixes, registry + set_lever |
| B4c | cd2c6cc | monetary beliefs & measurement (8) |
| B4a+b | f96a67f | bank macroprudential (8) + mortgage regulation via `_sync_policy` (7) |
| B4d | 001f662 | Treasury debt mgmt; **bond_coupon = first real NEW_CONTRACTS cohort** (per-lot coupon; merge key includes it) |
| B4e | b066259 | final 14 [C]; 3 renames w/ legacy aliases; RentalMarket anti-snapshot sync; **soe_efirm = first STATE_TRANSITION handler** |
| [N] | 4262b07 | **monetary_regime** (A5 three-state; manual<=>batched-rate atomicity; sensor runs in manual), jg_public_works_share, deposit_rate_floor |
| B5a | de7fc0a | **ExternalPolicy**: per-economy ownership of 11 unilateral [W] levers; atomic barrier commit; A6 sanctions (unilateral ownership / symmetric OR effect) |
| B5b | d986255 | **PegState multi-pegger data model**; CBRES:{pegger_id}; fx_regime authority (peg_economy deleted); runtime adoption / anchor change / voluntary exit; **the live-rate pressure defect FIXED** |
| B6 | (this) | **PolicySeed** (r_interest -> initial_policy_rate; genesis rate + Gordon anchor + exogenous pin); metrics split-brain swept |

### Findings the effectiveness scaffold produced (beyond dead levers)
1. Taylor family two-sided clamp shadowing (ZLB AND r_max) -> interior-liftoff technique.
2. The historical Python presets precedence-shadowed
   `gov_consumption_share` with `gov_deficit_target`; the native engine no
   longer does so.
3. bond issuance is demand-constrained: finance_frac upward moves are supply-cap-shadowed.
4. deposit_rate AND deposit_rate_floor are DEAD outside bank_realized_pnl (the whole
   deposit-interest leg lives in finalize_bank_pnl) -- capability requirement filed.
5. Stable v13 fixtures produce ZERO firm insolvencies in 240 ticks (bankrupt_persist
   unobservable at any legal value; boundary-proof technique).
6. Public investment is leftover-constrained in a cleared K market (stock gauge useless).
7. The trilemma tests' "independence" was an artifact of the static-rate defect: under
   live rates an active Taylor pair CONVERGES -- pinning requires regime=exogenous.

### Follow-on design threads (not levers)
- Shock module (deferred by user ruling)
- Random/heuristic/RL controllers are implemented and locally accepted in
  [`controllers_v26.md`](controllers_v26.md); the future frontend/transport remains
  outside that engine contract.
- P1 multi-pegger runtime (data model ready), sanctions scope extension to capital flows
- §1.6 hardcoded institutions promoted piecemeal (estate tax, probate window, working-age
  bounds remain documented literals)
