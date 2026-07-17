# v25: The Policy Module (DRAFT — skeleton)

**Status**: blank scaffold, design not yet frozen · **Branch**: TBD (`feat/policy-module`, off dev after the v24 merge)
**Goal**: complete the existing Config/Policy split — every lever a real-world authority could
change at a meeting becomes runtime-mutable PolicyState, driven by pluggable controllers
(frontend player / scripted / random / heuristic / RL). The action stream doubles as the
save-container `events.log` and, later, the frontend network protocol.

---

## 0. Boundary principle

> Policy = what an authority (government / central bank / immigration office) can decide at
> runtime. Config = the physics of the world (preferences, technology, demography).

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

Sources: 364 Config fields, ~33 World constructor params (incl. peg_economy), the existing
Policy class (46 levers).

### 1.1 The surprise: Policy already exists and is half-built

`core/policy.py` already holds ~45 live levers with read-points wired (all fiscal
spending/taxes incl. v18 differential VAT, all v17 energy policy, labour floors + JG,
the full Taylor rule + `policy_rate_override` (a hand-set player rate!), OMO/LoLR,
4 macropru handles, 5 housing handles). **P0 = close the gaps below, not build from zero.**

### 1.2 POLICY levers — complete list (≈86), by domain

Location key: **[P]** already in Policy · **[C]** in Config, must migrate · **[W]** World
constructor param, needs a per-economy home.

**Fiscal — spending & transfers** (7): [P] gov_consumption_share, gov_deficit_target,
deficit_u_ref, benefit_replacement, benefit_income_floor, pension_replacement ·
[C] deficit_u_cap, gov_investment_share

**Fiscal — taxes** (12): [P] tax_profit_rate, tax_income_rate, income_allowance,
tax_consumption_rate, tax_necessity_rate, tax_luxury_rate, tax_wealth_rate,
wealth_allowance, tax_energy_rate, tax_energy_windfall · [P] housing_transfer_tax,
housing_property_tax, housing_in_wealth_tax

**Labour institutions** (4): [P] min_wage, job_guarantee, jg_wage_ratio · [C] jg_productivity
(programme design)

**Monetary — rate rule** (9): [P] central_bank(regime), inflation_target, taylor_phi_pi,
taylor_phi_u, rate_inertia, policy_rate_override · [C] r_interest (the baseline/exogenous
rate), r_max (the cap that disarmed CBs in the v1 portrait), deposit_rate

**Monetary — beliefs & measurement** (5): [C] r_neutral, u_natural (the CB's structural
ESTIMATES — the CB chooses them), cb_core_inflation, cb_uses_fixed_basket_cpi (the Germany
lesson: the target-index choice is itself policy), cb_log_inflation

**Monetary — quantity tools** (5): [P] omo, omo_reserve_target, omo_drain_frac, lolr ·
[C] omo_index_deposits

**Treasury debt management** (3): [C] bond_finance_frac, bond_coupon, bond_maturity

**Macroprudential — banks** (9): [C] bank_capital_constraint(regime), bank_leverage_mean
(the κ_bank cap), bank_target_capital_ratio, bank_exposure_limit, bank_min_capital,
bank_bond_duration_limit, bank_resolution_fund(regime), reserve_floor_frac · [P] kappa

**Macroprudential — households & mortgages** (10): [P] margin_ltv, margin_max,
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
  land_convexity NEEDS A SEMANTIC SPLIT (fee-curve shape = policy; physical scarcity = config)
- rental_eviction_arrears [C] — eviction law (same family as foreclosure/bankruptcy timelines)
- unified_bank_rwa [C] — the unified regulatory-capital REGIME switch (its own sub-params are
  already policy)
- firm_credit_min_dscr [C] — economy-wide corporate underwriting floor, isomorphic to
  mortgage_dsti_cap
- firm_capital_haircut / firm_inventory_haircut [C] — collateral haircuts; RULING NEEDED:
  regulatory policy vs per-bank behaviour (if private underwriting, refactor to bank-level)
- infl_ema_lambda [C] — the CB's inflation-signal smoothing (consistency with r*/u*/index
  choice: the CB's measurement apparatus is policy)
- fiscal_uses_national_accounts_gdp [C] — the FISCAL RULE's GDP-measure choice (not shared
  reporting infra)
- bank_migrate_on_failure [C] — REVERSED ruling: purchase-&-assumption vs stranding is bank
  RESOLUTION REGIME, not plumbing

### 1.3 Ambiguous — rulings taken (flag any objection)

| Field | Ruling | Reason |
|---|---|---|
| r_neutral / u_natural | policy | the CB's own estimates, revisable at a meeting |
| cb_log_inflation | policy | the CB's measurement method choice |
| bank_leverage_mean | policy | documented as the κ_bank CAP (regulation), dispersion stays physics |
| bankrupt_persist / foreclosure params | policy | insolvency/foreclosure law |
| soe_efirm | policy | runtime flip = nationalisation/privatisation event |
| jg_productivity | policy | programme design choice |
| bank_migrate_on_failure | ~~config~~ → **policy** | user audit: resolution regime (P&A vs stranding) |
| fiscal_uses_national_accounts_gdp | ~~config~~ → **policy** | user audit: the fiscal rule's own measure choice |
| master switches (government, bonds, capital_market, …) | config | constitutional/model composition; regime FLAGS listed above (job_guarantee, lolr, peg, …) stay policy |
| migration_rate / migration_max_share | config | behavioural propensity, not a cap |
| energy_shock_at/magnitude/duration | **shock module** | exogenous events, not policy |

### 1.4 NON-policy fields — complete residual classification (nothing omitted)

**Previously UNCLASSIFIED (user audit; now placed)**: demographics_population (structure),
public_capital_gamma, public_capital_depreciation (physics — public-capital technology),
lambda_I, delta_K, A, a_K, K_firm0, kappa_E, a_E (physics/genesis — capital & energy
technology; missed by the regex dump). [W] peg_economy: recorded — the new architecture
DELETES it in favour of each economy's own peg choice in ExternalPolicy; migration note
mandatory.

**Structure / genesis / scale** (immutable by nature): n_households, n_firms, n_ticks, seed,
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
investment_user_cost_elasticity/_min/_max/_floor, firm_credit_min_dscr,
valuation_discount_floor, valuation_risk_premium, firm_capital_haircut,
firm_inventory_haircut, energy_intensity, energy_coverage_ticks, energy_gap_close,
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
rent_adjust, rent_burden_cap, rental_eviction_arrears, rental_investor_premium,
housing_ask_markup, housing_forced_discount, housing_ask_decay, housing_search_k,
housing_buyer_buffer, housing_distress_floor, housing_session_interval,
builder_productivity, builder_demand_seed, land_fee_share, land_convexity,
housing_wealth_effect, family_transfer_buffer, switch_retool_loss, switch_return_gap,
switch_pressure_days, switch_hazard, necessity_share0, n_firm_share, subsistence_share,
tfp_drift_rate, tfp_drift_sigma, tfp_law, tfp_learning_theta, tfp_drift_c/_k/_e,
[W] fx_lambda, fx_friction, fx_trade_cap, capital_mobility, capital_adjust,
migration_rate, migration_max_share, remittance_share, wage_smoothing,
external_interest_settlement_fraction.

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
mortgage_enabled, unified_bank_rwa, housing_rental_enabled, housing_construction_enabled,
labor_accounting, labor_matching, labor_fractional_hours, labor_second_job,
labor_suspension, labor_matching_friction, labor_relationship_wages, labor_job_ladder,
labor_person_efficiency, labor_participation, capital_rationed_signal,
consumption_rationed_signal, firm_subscale_exit, capital_firm_entry, firm_full_pnl,
capital_service_pricing, priced_firm_balance_sheet, bank_enabled, bank_realized_pnl,
bank_assignment, bank_migrate_on_failure, bank_rate_competition, bank_relationship_lock_in,
interbank, bank_equity, bank_equity_trading, bank_dynamics, bank_runs, bonds, government,
capital_market, per_firm_equity, equity_finance, household_credit,
household_interest_arrears, margin_credit, gibrat_growth, firm_dynamics, symmetric_k,
k_replacement_floor, energy_enabled, energy_household, deprivation_gauges,
national_accounts_metrics, fiscal_uses_national_accounts_gdp, consumption_strata,
family_transfers, sector_switching, monetary_direct_transmission, interest_by_deposits,
index_startup, capital_annual_clock, pro_rata_dividends, demo feedback/burnin flags,
[W] couple, trade, capital, migration.

**Infra / numerics / diagnostics**: claims_reconcile_interval, ledger_rel_tol,
bond_maturity_bucket, capital_service_min_utilization, rental_vacancy_deadband,
rental_rent_floor_wage_share, housing_demand_step, cpi_item_link_cap,
cpi_rebase_interval_days, infl_ema_lambda, demo_feedback_burnin_years,
demo_signal_halflife_years, housing_signal_burnin_years, energy_signal_burnin_years,
deprivation_burnin_years, deprivation_acute_days, deprivation_chronic_days,
_capital_annual_clock_applied.

**Shock module (excluded here)**: energy_shock_at, energy_shock_magnitude,
energy_shock_duration.

### 1.5 P0 gap analysis (the actual work)

1. **~30 [C] levers migrate into Policy** (banking macropru block, mortgage regulation
   block, monetary beliefs/measurement, Treasury debt management, insolvency law,
   deficit_u_cap, gov_investment_share, jg_productivity, soe_efirm, r_interest/r_max/
   deposit_rate, omo_index_deposits) + their read-point rewires.
2. **The external domain needs a per-economy owner**: 13 [W] levers live as World
   constructor vectors with no Policy home. Create `ExternalPolicy` inside each economy's
   PolicyState; World reads per tick (peg regime: pegger's own choice + anchor consent
   question deferred).
3. **Bounds table**: every policy lever gains (min, max, max_step_per_tick) — one
   declaration = validation + random-controller domain + RL action space.
4. `Policy.from_config` grows accordingly; NullController = freeze-at-seed = bit-identical.

### 1.6 Hard-coded institutions a field scan CANNOT see (user audit; sweep = P0 work item)

Real-world-changeable rules living as literals in code — each needs a ruling
(promote to lever | document as model simplification):

- **Monetary**: policy-rate FLOOR hard-coded 0 (r_max exists, r_min does not) — central_bank.py:54
- **Labour/pension law**: working age 18–64, pension eligibility 65 — economic_state.py:389;
  split out labor_min_age / statutory_retirement_age / pension_eligibility_age
- **Family & inheritance law** (demographics modules): estate tax fixed 0; intestate
  succession fixed spouse/children 50/50; probate window fixed 365d; marriage min-age,
  remarriage cooling period, consanguinity ban, same-sex restriction, 50/50 marital
  property split — inheritance.py:49, social.py:31
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
- **jg_productivity** is closer to a technology parameter; **deposit_rate** is currently a
  commercial-bank contract cost — both need semantic splits before promotion

## 2. Architecture (three layers)

- **Controller** (pluggable): `Null` (constant, bit-identical) · `Scheduled` (tick→value script;
  the shock-module cousin) · `Random` (bounded walk, own RNG stream) · `Heuristic` ·
  `RLAdapter` (gym-style) · later `Frontend`.
- **PolicyState**: per-economy registry. Each lever declares (user-audit-extended schema):
  `(min, max, max_step_per_tick)` · **owner/scope** (single economy | bilateral | world) ·
  **type/choices/nullability/shape** (bool, enum, int, nullable, vector, sanction-pair set) ·
  **effective_semantics** (immediate | new-contracts-only | restates-stock | state-transition)
  · **capability dependency** (e.g. OMO requires bonds+banking) · **the unique runtime
  read-point** (metrics must read the same source). One declaration = validation + random
  domain + RL action space + frontend form. World-level policies are OWNED by each economy's
  PolicyState; World reads them per tick.
- **Read-point migration**: modules read `econ.policy.X`, never `cfg.X`; genesis seeds
  policy ← cfg.

## 3. Disciplines (inherited from v24 lessons)

1. Bit-identity: NullController seeded from cfg == today's behavior; digest-gated.
   Decision point fixed at top-of-tick; controller uses an isolated RNG stream.
2. Checkpoint-able: controller state pickles; **policy is STATE and must resume exactly**
   (the inverse of the "tolerances are policy, not state" lesson).
3. Actions are events: every change logged `(tick, economy, lever, old, new, actor)` →
   `.msim` events.log slot → replay / audit / frontend protocol in one schema.
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
- [ ] World-level policy ownership: per-economy PolicyState (proposed) vs World-held vectors?
- [ ] Lever set for P0: full sweep vs start with fiscal+monetary only?
- [ ] Action cadence: every tick vs policy-meeting interval (e.g. every 30 ticks)?

## 6. Relationship to the shock module (the OTHER v25 candidate)

ScheduledController already covers POLICY shocks. The exogenous-shock module (crises:
disasters, pandemics, embargoes, productivity/energy shocks) is a separate module hitting
PHYSICS levers — designed after this one; shares the events.log schema.
