# C1 lever governance table (v26 §5) — USER REVIEW GATE

**Draft for review.** 102 levers × the nine C1 columns. Time in ticks (365/y:
30≈1mo, 91≈1q, 182≈2q, 365≈1y). `impl` = implementation_lag, `e-lag` =
emergency_implementation_lag (— = not emergency-eligible or same as impl),
`hold` = min_hold_ticks, `emg` = emergency whitelist, `scale` = control_scale
(frontend notch / RL normalization / cost distance), `step` = max_step ruling
(— = UNBOUNDED, reason in notes), `adm` = admin_weight, `cost` = cost_class.

**Global rulings proposed:**
1. Every UNBOUNDED max_step (—) is deliberate: enum/bool/set levers step by
   nature; crisis ceilings (r_max), quota replans and SPR ops are priced by
   cost_class instead of a step bound.
2. NullableRange None→value transitions bypass max_step mechanically; proposal:
   first-set / unset are charged as `regime_switch` regardless of the listed
   cost_class ([REVIEW] items 4/8).
3. Per-tick-rate units ([REVIEW units]): the engine's rate levers are per-tick
   (5e-5 ≈ 1.8%/yr). All rate scales/steps below use that convention — confirm.
4. `soe_price_at_cost` sits in the energy seat but `soe_efirm` (ownership)
   stays treasury: operating rule vs ownership. enabled_if links them.



## central_bank (24 levers)

| lever | type/range | group | impl | e-lag | hold | emg | scale | step | adm | cost | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| inflation_target | Range[-0.02,0.02] | monetary | 0 | — | 365 | — | 0.0001 | 0.0005 | 2 | major | target revision is rare and reputational [REVIEW per-tick units] |
| taylor_phi_pi | Range[0.0,10.0] | monetary | 0 | — | 365 | — | 0.25 | 1.0 | 2 | major | rule redesign |
| taylor_phi_u | Range[0.0,10.0] | monetary | 0 | — | 365 | — | 0.25 | 1.0 | 2 | major | rule redesign |
| rate_inertia | Range[0.0,0.9999] | monetary | 0 | — | 365 | — | 0.05 | 0.2 | 2 | major |  |
| manual_policy_rate | NullableRange[0.0,0.01] | monetary | 0 | 0 | 45 | ✓ | 5e-05 | 0.00025 | 1 | ordinary | per-TICK rate: scale 5e-5~1.8%/yr; max_step 2.5e-4~9%/yr covers emergency hikes [REVIEW units] |
| monetary_regime ⟨ST⟩ | Choices('exogenous', 'taylor', 'manual') | monetary | 0 | 0 | 91 | ✓ | — | — | 3 | regime_switch | enum; regime churn priced via cost_class + hold |
| r_neutral | Range[0.0,0.05] | monetary | 0 | — | 91 | — | 5e-05 | 0.0001 | 1 | ordinary | estimate revision [REVIEW units] |
| u_natural | Range[0.0,0.5] | monetary | 0 | — | 91 | — | 0.005 | 0.01 | 1 | ordinary | estimate revision |
| r_max | Range[1e-06,0.5] | monetary | 0 | 0 | 182 | ✓ | 5e-05 | — | 2 | major | ceiling moves are crisis acts: UNBOUNDED step, priced by cost [REVIEW] |
| infl_ema_lambda | Range[0.0001,1.0] | measurement | 0 | — | 365 | — | 0.01 | 0.05 | 2 | major | sensor methodology |
| cb_core_inflation | Bool | measurement | 0 | — | 365 | — | — | — | 2 | major | methodology switch; bool |
| cb_uses_fixed_basket_cpi | Bool | measurement | 0 | — | 365 | — | — | — | 2 | major | methodology switch; bool |
| cb_log_inflation | Bool | measurement | 0 | — | 365 | — | — | — | 2 | major | methodology switch; bool |
| omo | Bool | liquidity | 0 | 0 | 45 | ✓ | — | — | 1 | operational | standing-facility switch |
| omo_reserve_target | Range[0.0,5.0] | liquidity | 0 | 0 | 45 | ✓ | 0.1 | 0.5 | 0.5 | operational |  |
| omo_drain_frac | Range[0.0,1.0] | liquidity | 0 | 0 | 45 | ✓ | 0.02 | 0.1 | 0.5 | operational |  |
| lolr | Bool | liquidity | 0 | 0 | 45 | ✓ | — | — | 1 | operational | standing-facility switch |
| reserve_floor_frac | Range[0.0,1.0] | liquidity | 0 | 0 | 91 | ✓ | 0.01 | 0.05 | 1 | ordinary |  |
| omo_index_deposits | Bool | liquidity | 0 | — | 91 | — | — | — | 1 | major | target-indexing regime |
| capital_control | Range[0.0,1.0] | fx | 0 | 0 | 91 | ✓ | 0.1 | 0.25 | 2 | major | [REVIEW seat: CB vs external_affairs] |
| external_interest_settlement_fraction | Range[0.0,1.0] | fx | 30 | 0 | 91 | ✓ | 0.1 | 0.25 | 1 | major | [REVIEW seat: settlement policy CB vs external_affairs] |
| fx_regime ⟨ST⟩ | Choices('float', 'peg') | fx | 0 | 0 | 365 | ✓ | — | — | 3 | regime_switch | adoption/exit; mechanics at barrier [REVIEW seat] |
| peg_anchor ⟨ST⟩ | EconomyId | fx | 0 | 0 | 365 | ✓ | — | — | 3 | regime_switch | anchor change [REVIEW seat] |
| peg_reserve_scale | Range[1.0,1000000000.0] | fx | 0 | 0 | 91 | ✓ | — | — | 0.5 | operational | engine drain-scaling unit: UNBOUNDED step, operational [REVIEW units] |

## treasury (32 levers)

| lever | type/range | group | impl | e-lag | hold | emg | scale | step | adm | cost | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gov_consumption_share | Range[0.0,0.6] | fiscal_stance | 30 | 0 | 91 | ✓ | 0.005 | 0.02 | 1 | ordinary |  |
| gov_deficit_target | Range[0.0,0.3] | fiscal_stance | 30 | 0 | 91 | ✓ | 0.005 | 0.02 | 1 | ordinary |  |
| deficit_u_ref | Range[0.0,1.0] | fiscal_stance | 30 | — | 182 | — | 0.01 | — | 1 | ordinary | cap scale 0.5; ref scale 0.01 [split scales] |
| benefit_replacement | Range[0.0,1.5] | welfare | 30 | 0 | 182 | — | 0.05 | 0.15 | 2 | major | entitlement changes; pension hold 365 |
| benefit_income_floor | Range[0.0,1.5] | welfare | 30 | 0 | 182 | — | 0.05 | 0.15 | 2 | major | entitlement changes; pension hold 365 |
| pension_replacement | Range[0.0,1.5] | welfare | 91 | — | 365 | — | 0.05 | 0.1 | 2 | major | pension reform is slow law |
| tax_profit_rate | Range[0.0,0.8] | tax | 91 | 30 | 182 | — | 0.01 | 0.05 | 2 | major | legislated; 1pp notch |
| tax_income_rate | Range[0.0,0.8] | tax | 91 | 30 | 182 | — | 0.01 | 0.05 | 2 | major | legislated; 1pp notch |
| income_allowance | Range[0.0,5.0] | tax | 91 | — | 182 | — | 0.1 | 0.5 | 1 | ordinary |  |
| tax_consumption_rate | Range[0.0,0.6] | tax | 91 | 30 | 182 | — | 0.01 | 0.05 | 2 | major | legislated; 1pp notch |
| tax_necessity_rate | NullableRange[0.0,0.6] | tax | 91 | 30 | 182 | — | 0.01 | 0.05 | 2 | major | nullable: None->rate is a regime introduction, cost regime_switch on first set [REVIEW] |
| tax_luxury_rate | NullableRange[0.0,0.8] | tax | 91 | 30 | 182 | — | 0.01 | 0.05 | 2 | major | nullable: None->rate is a regime introduction, cost regime_switch on first set [REVIEW] |
| tax_wealth_rate | Range[0.0,0.05] | tax | 91 | — | 365 | — | 0.002 | 0.01 | 2 | major |  |
| wealth_allowance | Range[0.0,10.0] | tax | 91 | — | 182 | — | 0.1 | 0.5 | 1 | ordinary |  |
| tax_energy_rate | Range[0.0,1.0] | energy_fiscal | 30 | 0 | 91 | ✓ | 0.05 | 0.2 | 1 | major | windfall taxes historically move fast in crises |
| tax_energy_windfall | Range[0.0,0.9] | energy_fiscal | 30 | 0 | 91 | ✓ | 0.05 | 0.2 | 1 | major | windfall taxes historically move fast in crises |
| min_wage | Range[0.0,10.0] | welfare | 91 | — | 365 | — | 0.05 | — | 2 | major | wage-unit scale [REVIEW units]; annual review pattern |
| job_guarantee | Bool | welfare | 91 | — | 365 | — | — | — | 3 | regime_switch | program on/off |
| jg_wage_ratio | Range[0.0,1.5] | welfare | 30 | — | 91 | — | 0.05 | 0.15 | 1 | ordinary |  |
| fiscal_uses_national_accounts_gdp | Bool | measurement | 0 | — | 365 | — | — | — | 2 | major |  |
| bond_finance_frac | Range[0.0,1.0] | debt_mgmt | 0 | 0 | 91 | ✓ | 0.05 | 0.25 | 0.5 | operational |  |
| bond_coupon ⟨NC⟩ | Range[0.0,0.01] | debt_mgmt | 0 | 0 | 91 | — | 5e-05 | 0.00025 | 0.5 | operational | NEW_CONTRACTS cohort; per-tick rate [REVIEW units] |
| bond_maturity ⟨NC⟩ | IntRange[1,36500] | debt_mgmt | 0 | 0 | 91 | — | 30 | 365 | 0.5 | operational | int ticks; tenor choice |
| housing_transfer_tax | Range[0.0,0.3] | tax | 91 | — | 182 | — | 0.005 | 0.02 | 1 | major |  |
| housing_property_tax | Range[0.0,0.1] | tax | 91 | — | 182 | — | 0.005 | 0.02 | 1 | major |  |
| housing_in_wealth_tax | Bool | tax | 91 | — | 365 | — | — | — | 2 | major | base redefinition; bool |
| jg_public_works_share | Range[0.0,1.0] | welfare | 30 | — | 91 | — | 0.05 | 0.15 | 1 | ordinary |  |
| deficit_u_cap | Range[0.0,10.0] | fiscal_stance | 30 | — | 182 | — | 0.5 | 2.0 | 1 | ordinary |  |
| gov_investment_share | Range[0.0,0.2] | fiscal_stance | 91 | 30 | 182 | — | 0.005 | 0.02 | 2 | major | public investment programs are slow to start |
| land_fee_share ⟨NC⟩ | Range[0.0,1.0] | land | 91 | — | 182 | — | 0.05 | 0.2 | 1 | major |  |
| land_fee_stock_elasticity ⟨NC⟩ | Range[0.0,10.0] | land | 91 | — | 365 | — | 0.25 | 1.0 | 2 | major |  |
| soe_efirm ⟨ST⟩ | Bool | ownership | 91 | — | 365 | — | — | — | 3 | regime_switch | nationalize/privatize E0; transition handler |

## regulator (29 levers)

| lever | type/range | group | impl | e-lag | hold | emg | scale | step | adm | cost | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bank_capital_constraint | Bool | macroprudential | 30 | — | 365 | — | — | — | 3 | regime_switch | capital-regime switch; bool |
| bank_leverage_cap | Range[0.0,50.0] | macroprudential | 30 | 0 | 91 | ✓ | 0.5 | 2.0 | 1 | major |  |
| bank_target_capital_ratio | Range[0.0,1.0] | macroprudential | 30 | 0 | 182 | ✓ | 0.01 | 0.05 | 2 | major | Basel-style ratchets; emergency RELAXATION is the crisis act |
| bank_exposure_limit | Range[0.0,1.0] | macroprudential | 30 | 0 | 182 | ✓ | 0.01 | 0.05 | 2 | major | Basel-style ratchets; emergency RELAXATION is the crisis act |
| bank_min_capital | Range[0.0,100000.0] | macroprudential | 91 | — | 365 | — | 100.0 | — | 2 | major | absolute money units [REVIEW units + scale] |
| bank_bond_duration_limit | Range[0.0,20.0] | macroprudential | 30 | 0 | 91 | ✓ | 0.25 | 1.0 | 1 | ordinary |  |
| bank_resolution_fund | Bool | resolution | 91 | 0 | 365 | ✓ | — | — | 2 | major | resolution regime; emergency activation allowed |
| margin_ltv | Range[0.0,1.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.05 | 0.15 | 1 | major |  |
| margin_max | Range[0.0,10.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.5 | 2.0 | 1 | ordinary |  |
| kappa | Range[0.0,20.0] | macroprudential | 30 | 0 | 91 | ✓ | 0.5 | 2.0 | 1 | major |  |
| hh_credit_limit | Range[0.0,20.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.5 | 2.0 | 1 | ordinary |  |
| mortgage_ltv_cap | Range[0.0,1.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.05 | 0.15 | 1 | major |  |
| mortgage_underwriting | Bool | credit_rules | 30 | — | 365 | — | — | — | 2 | major |  |
| mortgage_dsti_cap ⟨NC⟩ | Range[0.0,2.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.05 | 0.15 | 1 | major |  |
| mortgage_stress_rate_addon ⟨NC⟩ | Range[0.0,0.01] | credit_rules | 30 | 0 | 91 | — | 5e-05 | 0.00025 | 1 | ordinary | per-tick rate addon [REVIEW units] |
| mortgage_risk_weight | Range[0.0,2.0] | credit_rules | 30 | 0 | 182 | — | 0.1 | 0.25 | 1 | major |  |
| mortgage_min_capital_ratio | Range[0.0,1.0] | macroprudential | 30 | 0 | 182 | ✓ | 0.01 | 0.05 | 2 | major | Basel-style ratchets; emergency RELAXATION is the crisis act |
| mortgage_foreclosure_ltv | Range[0.5,5.0] | insolvency_law | 91 | 30 | 365 | — | 0.25 | 1.0 | 2 | major |  |
| mortgage_arrears_floor | Range[0.0,100.0] | insolvency_law | 91 | 30 | 365 | ✓ | 5.0 | 30.0 | 2 | major | forbearance = crisis tool |
| housing_permits | Range[0.0,100000.0] | housing_rules | 91 | — | 365 | — | 10.0 | — | 2 | major | [REVIEW seat + scale] |
| deposit_rate_floor | Range[0.0,0.01] | credit_rules | 30 | — | 182 | — | 5e-05 | 0.00025 | 1 | major | per-tick rate [REVIEW units]; dead without bank_realized_pnl (capability) |
| bankrupt_persist | IntRange[1,3650] | insolvency_law | 91 | 30 | 365 | ✓ | 10 | 90 | 2 | major | insolvency forbearance (int) |
| household_bankruptcy | Bool | insolvency_law | 91 | — | 365 | — | — | — | 2 | major | discharge regime; bool |
| rental_eviction_arrears | IntRange[1,3650] | insolvency_law | 91 | 30 | 365 | ✓ | 5 | 30 | 2 | major | eviction moratorium = crisis tool (int) |
| bank_migrate_on_failure | Bool | resolution | 91 | 0 | 365 | ✓ | — | — | 2 | major | resolution regime; emergency activation allowed |
| unified_bank_rwa | Bool | macroprudential | 30 | — | 365 | — | — | — | 3 | regime_switch | capital-regime switch; bool |
| firm_credit_min_dscr ⟨NC⟩ | Range[0.0,5.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.25 | 0.5 | 1 | major |  |
| regulatory_firm_capital_haircut ⟨NC⟩ | Range[0.0,1.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.05 | 0.15 | 1 | ordinary |  |
| regulatory_firm_inventory_haircut ⟨NC⟩ | Range[0.0,1.0] | credit_rules | 30 | 0 | 91 | ✓ | 0.05 | 0.15 | 1 | ordinary |  |

## external_affairs (9 levers)

| lever | type/range | group | impl | e-lag | hold | emg | scale | step | adm | cost | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tariff | Range[0.0,5.0] | trade | 30 | 0 | 91 | ✓ | 0.05 | 0.25 | 1 | major | trade war moves fast when it moves |
| import_quota | NullableRange[0.0,100.0] | trade | 30 | 0 | 91 | ✓ | 0.1 | 0.5 | 1 | major | nullable: None<->cap is a regime act [REVIEW: cost None->set as regime_switch] |
| export_subsidy | Range[-0.99,0.99] | trade | 30 | 0 | 91 | — | 0.05 | 0.2 | 1 | major |  |
| sanctions_imposed_on | EconomySet | strategic | 0 | 0 | 91 | ✓ | — | — | 3 | regime_switch | set-valued; impose/lift are political acts, immediate by nature |
| immigration_cap | NullableRange[0.0,10.0] | migration | 30 | 0 | 182 | ✓ | 0.05 | 0.25 | 2 | major |  |
| emigration_cap | NullableRange[0.0,1.0] | migration | 30 | 0 | 182 | ✓ | 0.05 | 0.25 | 2 | major |  |
| remittance_tax | Range[0.0,0.9] | migration | 30 | — | 91 | — | 0.05 | 0.2 | 1 | ordinary |  |
| outward_remittance_tax | Range[0.0,0.9] | migration | 30 | — | 91 | — | 0.05 | 0.2 | 1 | ordinary |  |
| guest_worker_return | Range[0.0,1.0] | migration | 30 | — | 182 | — | 0.05 | 0.2 | 1 | major |  |

## energy (8 levers)

| lever | type/range | group | impl | e-lag | hold | emg | scale | step | adm | cost | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spr_target_units | Range[0.0,1000000.0] | energy_ops | 0 | 0 | 91 | ✓ | 1000.0 | — | 0.5 | operational | engine stock units [REVIEW units + scale]; release = crisis act |
| spr_flow_cap | Range[0.0,10000.0] | energy_ops | 0 | 0 | 91 | ✓ | 100.0 | — | 0.5 | operational | [REVIEW units] |
| soe_price_at_cost | Bool | energy_ops | 0 | 0 | 91 | ✓ | — | — | 2 | major | SOE operating-price rule; enabled_if soe_efirm (ownership stays treasury) |
| energy_price_cap | Range[0.0,1000.0] | energy_ops | 0 | 0 | 91 | ✓ | 1.0 | — | 2 | major | [REVIEW units] |
| energy_rationing | Choices('market', 'household_first', 'industry_first') | energy_ops | 0 | 0 | 91 | ✓ | — | — | 3 | regime_switch | enum allocation regime |
| energy_cap_compensation | Bool | energy_ops | 30 | 0 | 91 | ✓ | — | — | 1 | major | fiscal compensation switch |
| energy_subsidy_rate | Range[0.0,1.0] | energy_welfare | 30 | 0 | 91 | ✓ | 0.05 | 0.2 | 1 | major |  |
| energy_subsidy_threshold | Range[0.0,10.0] | energy_welfare | 30 | 0 | 91 | ✓ | 0.05 | 0.2 | 1 | major |  |

## Open review points (21)

- **tax_necessity_rate** — nullable: None->rate is a regime introduction, cost regime_switch on first set [REVIEW]
- **tax_luxury_rate** — nullable: None->rate is a regime introduction, cost regime_switch on first set [REVIEW]
- **spr_target_units** — engine stock units [REVIEW units + scale]; release = crisis act
- **spr_flow_cap** — [REVIEW units]
- **energy_price_cap** — [REVIEW units]
- **min_wage** — wage-unit scale [REVIEW units]; annual review pattern
- **inflation_target** — target revision is rare and reputational [REVIEW per-tick units]
- **manual_policy_rate** — per-TICK rate: scale 5e-5~1.8%/yr; max_step 2.5e-4~9%/yr covers emergency hikes [REVIEW units]
- **r_neutral** — estimate revision [REVIEW units]
- **r_max** — ceiling moves are crisis acts: UNBOUNDED step, priced by cost [REVIEW]
- **bond_coupon** — NEW_CONTRACTS cohort; per-tick rate [REVIEW units]
- **bank_min_capital** — absolute money units [REVIEW units + scale]
- **mortgage_stress_rate_addon** — per-tick rate addon [REVIEW units]
- **housing_permits** — [REVIEW seat + scale]
- **deposit_rate_floor** — per-tick rate [REVIEW units]; dead without bank_realized_pnl (capability)
- **import_quota** — nullable: None<->cap is a regime act [REVIEW: cost None->set as regime_switch]
- **capital_control** — [REVIEW seat: CB vs external_affairs]
- **external_interest_settlement_fraction** — [REVIEW seat: settlement policy CB vs external_affairs]
- **fx_regime** — adoption/exit; mechanics at barrier [REVIEW seat]
- **peg_anchor** — anchor change [REVIEW seat]
- **peg_reserve_scale** — engine drain-scaling unit: UNBOUNDED step, operational [REVIEW units]

## Seat totals

| seat | levers |
|---|---|
| central_bank | 24 |
| treasury | 32 |
| regulator | 29 |
| external_affairs | 9 |
| energy | 8 |

⟨NC⟩ = NEW_CONTRACTS semantics; ⟨ST⟩ = STATE_TRANSITION (handler-gated).
Emergency e-lag=0 means the emergency session executes at its own boundary;
'—' in e-lag with emg=✓ means the ordinary impl lag also applies in emergencies.
