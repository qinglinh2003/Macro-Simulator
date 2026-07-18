# v26 Controller 政策杠杆表

本表是当前 `CONTROL_SPECS` 与 `REGISTRY` 的可审阅快照，共 **102** 个杠杆。
时间单位均为 tick；`regular lag` 是常规实施滞后，`emergency lag` 是紧急情境的覆盖滞后，
`—` 表示不适用或未设置。`scale` 用于前端步进、RL 归一化和调整成本；
`max_step` 是单次决策允许的最大数值变动。

| name | type | range / choices | owner | group | regular lag | emergency lag | min hold | emergency | scale | max_step | admin | cost |
|---|---|---|---|---|---:|---:|---:|:---:|---:|---:|---:|---|
| `gov_consumption_share` | float | [0, 0.6] | `treasury` | `fiscal_stance` | 7 | 1 | 45 | 是 | 0.01 | 0.05 | 1 | `ordinary` |
| `gov_deficit_target` | float | [0, 0.3] | `treasury` | `fiscal_stance` | 7 | 1 | 45 | 是 | 0.005 | 0.02 | 1 | `ordinary` |
| `deficit_u_ref` | float | [0, 1] | `treasury` | `fiscal_stance` | 7 | — | 91 | 否 | 0.05 | 0.2 | 1 | `ordinary` |
| `benefit_replacement` | float | [0, 1.5] | `treasury` | `fiscal_stance` | 7 | 1 | 91 | 是 | 0.05 | 0.2 | 1 | `ordinary` |
| `benefit_income_floor` | float | [0, 1.5] | `treasury` | `fiscal_stance` | 7 | 1 | 91 | 是 | 0.05 | 0.2 | 1 | `ordinary` |
| `pension_replacement` | float | [0, 1.5] | `treasury` | `fiscal_stance` | 30 | — | 365 | 否 | 0.05 | 0.2 | 2 | `major` |
| `tax_profit_rate` | float | [0, 0.8] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.025 | 0.1 | 2 | `major` |
| `tax_income_rate` | float | [0, 0.8] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.025 | 0.1 | 2 | `major` |
| `income_allowance` | float | [0, 5] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.1 | 0.5 | 2 | `major` |
| `tax_consumption_rate` | float | [0, 0.6] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.025 | 0.1 | 2 | `major` |
| `tax_necessity_rate` | float\|null | [0, 0.6] 或 null | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.025 | 0.1 | 2 | `major` |
| `tax_luxury_rate` | float\|null | [0, 0.8] 或 null | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.025 | 0.1 | 2 | `major` |
| `tax_wealth_rate` | float | [0, 0.05] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.001 | 0.005 | 2 | `major` |
| `wealth_allowance` | float | [0, 10] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.25 | 1 | 2 | `major` |
| `tax_energy_rate` | float | [0, 1] | `treasury` | `tax_and_transfers` | 14 | 1 | 91 | 是 | 0.025 | 0.1 | 2 | `major` |
| `tax_energy_windfall` | float | [0, 0.9] | `treasury` | `tax_and_transfers` | 30 | 7 | 91 | 是 | 0.025 | 0.1 | 2 | `major` |
| `spr_target_units` | float | [0, 1000000] | `energy` | `energy_operations` | 7 | 0 | 30 | 是 | 10000 | 100000 | 0.5 | `operational` |
| `spr_flow_cap` | float | [0, 10000] | `energy` | `energy_operations` | 1 | 0 | 7 | 是 | 100 | 1000 | 0.5 | `operational` |
| `soe_price_at_cost` | bool | true / false | `energy` | `energy_operations` | 1 | 0 | 7 | 是 | — | — | 0.5 | `operational` |
| `energy_price_cap` | float | [0, 1000] | `energy` | `energy_operations` | 1 | 0 | 7 | 是 | 0.1 | 1 | 0.5 | `operational` |
| `energy_rationing` | enum | {`market`, `household_first`, `industry_first`} | `energy` | `energy_operations` | 1 | 0 | 7 | 是 | — | — | 0.5 | `operational` |
| `energy_cap_compensation` | bool | true / false | `treasury` | `tax_and_transfers` | 7 | 1 | 30 | 是 | — | — | 2 | `major` |
| `energy_subsidy_rate` | float | [0, 1] | `treasury` | `tax_and_transfers` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 2 | `major` |
| `energy_subsidy_threshold` | float | [0, 10] | `treasury` | `tax_and_transfers` | 7 | 1 | 91 | 是 | 0.25 | 1 | 2 | `major` |
| `min_wage` | float | [0, 10] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.05 | 0.25 | 2 | `major` |
| `job_guarantee` | bool | true / false | `treasury` | `fiscal_stance` | 7 | 1 | 91 | 是 | — | — | 2 | `major` |
| `jg_wage_ratio` | float | [0, 1.5] | `treasury` | `fiscal_stance` | 7 | 1 | 91 | 是 | 0.05 | 0.2 | 1 | `ordinary` |
| `inflation_target` | float | [-0.02, 0.02] | `central_bank` | `monetary_stance` | 1 | — | 365 | 否 | 0.00025 | 0.001 | 2 | `major` |
| `taylor_phi_pi` | float | [0, 10] | `central_bank` | `monetary_stance` | 1 | — | 91 | 否 | 0.1 | 0.5 | 1 | `ordinary` |
| `taylor_phi_u` | float | [0, 10] | `central_bank` | `monetary_stance` | 1 | — | 91 | 否 | 0.1 | 0.5 | 1 | `ordinary` |
| `rate_inertia` | float | [0, 0.9999] | `central_bank` | `monetary_stance` | 1 | — | 91 | 否 | 0.025 | 0.1 | 1 | `ordinary` |
| `manual_policy_rate` | float\|null | [0, 0.01] 或 null | `central_bank` | `monetary_stance` | 0 | 0 | 5 | 是 | 0.0001 | 0.001 | 0.5 | `operational` |
| `monetary_regime` | enum | {`exogenous`, `taylor`, `manual`} | `central_bank` | `monetary_stance` | 1 | 0 | 45 | 是 | — | — | 3 | `regime_switch` |
| `r_neutral` | float | [0, 0.05] | `central_bank` | `monetary_stance` | 1 | — | 91 | 否 | 0.0005 | 0.0025 | 1 | `ordinary` |
| `u_natural` | float | [0, 0.5] | `central_bank` | `monetary_stance` | 1 | — | 91 | 否 | 0.005 | 0.02 | 1 | `ordinary` |
| `r_max` | float | [1e-06, 0.5] | `central_bank` | `monetary_stance` | 1 | — | 91 | 否 | 0.005 | 0.025 | 1 | `ordinary` |
| `infl_ema_lambda` | float | [0.0001, 1] | `central_bank` | `monetary_stance` | 1 | — | 91 | 否 | 0.01 | 0.05 | 1 | `ordinary` |
| `cb_core_inflation` | bool | true / false | `central_bank` | `monetary_stance` | 7 | — | 365 | 否 | — | — | 2 | `major` |
| `cb_uses_fixed_basket_cpi` | bool | true / false | `central_bank` | `monetary_stance` | 7 | — | 365 | 否 | — | — | 2 | `major` |
| `cb_log_inflation` | bool | true / false | `central_bank` | `monetary_stance` | 7 | — | 365 | 否 | — | — | 2 | `major` |
| `fiscal_uses_national_accounts_gdp` | bool | true / false | `treasury` | `fiscal_stance` | 30 | — | 365 | 否 | — | — | 2 | `major` |
| `bond_finance_frac` | float | [0, 1] | `treasury` | `debt_management` | 7 | 1 | 45 | 是 | 0.05 | 0.2 | 1 | `ordinary` |
| `bond_coupon` | float | [0, 0.01] | `treasury` | `debt_management` | 1 | — | 45 | 否 | 0.0001 | 0.001 | 1 | `ordinary` |
| `bond_maturity` | int | [1, 36500] | `treasury` | `debt_management` | 1 | — | 91 | 否 | 365 | 3650 | 1 | `ordinary` |
| `omo` | bool | true / false | `central_bank` | `liquidity_operations` | 1 | 0 | 7 | 是 | — | — | 0.5 | `operational` |
| `omo_reserve_target` | float | [0, 5] | `central_bank` | `liquidity_operations` | 1 | 0 | 7 | 是 | 0.05 | 0.25 | 0.5 | `operational` |
| `omo_drain_frac` | float | [0, 1] | `central_bank` | `liquidity_operations` | 1 | 0 | 7 | 是 | 0.05 | 0.25 | 0.5 | `operational` |
| `lolr` | bool | true / false | `central_bank` | `liquidity_operations` | 1 | 0 | 7 | 是 | — | — | 0.5 | `operational` |
| `bank_capital_constraint` | bool | true / false | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | — | — | 3 | `regime_switch` |
| `bank_leverage_cap` | float | [0, 50] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.5 | 2 | 1 | `ordinary` |
| `bank_target_capital_ratio` | float | [0, 1] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.01 | 0.05 | 1 | `ordinary` |
| `bank_exposure_limit` | float | [0, 1] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 1 | `ordinary` |
| `bank_min_capital` | float | [0, 100000] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 1000 | 10000 | 1 | `ordinary` |
| `bank_bond_duration_limit` | float | [0, 20] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.5 | 2 | 1 | `ordinary` |
| `bank_resolution_fund` | bool | true / false | `regulator` | `structural_law` | 30 | 0 | 365 | 是 | — | — | 3 | `regime_switch` |
| `reserve_floor_frac` | float | [0, 1] | `central_bank` | `liquidity_operations` | 1 | 0 | 30 | 是 | 0.025 | 0.1 | 0.5 | `operational` |
| `margin_ltv` | float | [0, 1] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 1 | `ordinary` |
| `margin_max` | float | [0, 10] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.25 | 1 | 1 | `ordinary` |
| `kappa` | float | [0, 20] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.25 | 1 | 1 | `ordinary` |
| `hh_credit_limit` | float | [0, 20] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.25 | 1 | 1 | `ordinary` |
| `mortgage_ltv_cap` | float | [0, 1] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 1 | `ordinary` |
| `mortgage_underwriting` | bool | true / false | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | — | — | 2 | `major` |
| `mortgage_dsti_cap` | float | [0, 2] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 1 | `ordinary` |
| `mortgage_stress_rate_addon` | float | [0, 0.01] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.0001 | 0.0005 | 1 | `ordinary` |
| `mortgage_risk_weight` | float | [0, 2] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 1 | `ordinary` |
| `mortgage_min_capital_ratio` | float | [0, 1] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.01 | 0.05 | 1 | `ordinary` |
| `mortgage_foreclosure_ltv` | float | [0.5, 5] | `regulator` | `structural_law` | 30 | — | 365 | 否 | 0.05 | 0.2 | 2 | `major` |
| `mortgage_arrears_floor` | float | [0, 100] | `regulator` | `structural_law` | 30 | — | 365 | 否 | 0.5 | 2 | 2 | `major` |
| `housing_permits` | float | [0, 100000] | `treasury` | `fiscal_stance` | 30 | — | 91 | 否 | 10 | 100 | 2 | `major` |
| `housing_transfer_tax` | float | [0, 0.3] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.01 | 0.05 | 2 | `major` |
| `housing_property_tax` | float | [0, 0.1] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.0025 | 0.01 | 2 | `major` |
| `housing_in_wealth_tax` | bool | true / false | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | — | — | 2 | `major` |
| `jg_public_works_share` | float | [0, 1] | `treasury` | `fiscal_stance` | 7 | 1 | 91 | 是 | 0.05 | 0.2 | 1 | `ordinary` |
| `deposit_rate_floor` | float | [0, 0.01] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.0001 | 0.0005 | 1 | `ordinary` |
| `deficit_u_cap` | float | [0, 10] | `treasury` | `fiscal_stance` | 7 | 1 | 91 | 是 | 0.1 | 0.5 | 1 | `ordinary` |
| `gov_investment_share` | float | [0, 0.2] | `treasury` | `fiscal_stance` | 30 | — | 91 | 否 | 0.005 | 0.02 | 2 | `major` |
| `omo_index_deposits` | bool | true / false | `central_bank` | `liquidity_operations` | 7 | 0 | 91 | 是 | — | — | 2 | `major` |
| `bankrupt_persist` | int | [1, 3650] | `regulator` | `structural_law` | 30 | — | 365 | 否 | 30 | 180 | 2 | `major` |
| `household_bankruptcy` | bool | true / false | `regulator` | `structural_law` | 30 | — | 365 | 否 | — | — | 3 | `regime_switch` |
| `rental_eviction_arrears` | int | [1, 3650] | `regulator` | `structural_law` | 30 | — | 365 | 否 | 30 | 180 | 2 | `major` |
| `bank_migrate_on_failure` | bool | true / false | `regulator` | `macroprudential` | 7 | 0 | 91 | 是 | — | — | 2 | `major` |
| `unified_bank_rwa` | bool | true / false | `regulator` | `structural_law` | 30 | — | 365 | 否 | — | — | 3 | `regime_switch` |
| `firm_credit_min_dscr` | float | [0, 5] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.1 | 0.5 | 1 | `ordinary` |
| `regulatory_firm_capital_haircut` | float | [0, 1] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 1 | `ordinary` |
| `regulatory_firm_inventory_haircut` | float | [0, 1] | `regulator` | `macroprudential` | 7 | 1 | 91 | 是 | 0.025 | 0.1 | 1 | `ordinary` |
| `land_fee_share` | float | [0, 1] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.025 | 0.1 | 2 | `major` |
| `land_fee_stock_elasticity` | float | [0, 10] | `treasury` | `tax_and_transfers` | 30 | — | 365 | 否 | 0.1 | 0.5 | 2 | `major` |
| `soe_efirm` | bool | true / false | `energy` | `energy_structure` | 30 | — | 365 | 否 | — | — | 3 | `regime_switch` |
| `tariff` | float | [0, 5] | `external_affairs` | `trade_and_migration` | 14 | — | 91 | 否 | 0.05 | 0.25 | 1 | `ordinary` |
| `import_quota` | float\|null | [0, 100] 或 null | `external_affairs` | `trade_and_migration` | 14 | — | 91 | 否 | 1 | 10 | 1 | `ordinary` |
| `export_subsidy` | float | [-0.99, 0.99] | `external_affairs` | `trade_and_migration` | 14 | — | 91 | 否 | 0.025 | 0.1 | 1 | `ordinary` |
| `capital_control` | float | [0, 1] | `central_bank` | `fx_operations` | 7 | 0 | 30 | 是 | 0.05 | 0.2 | 1 | `operational` |
| `external_interest_settlement_fraction` | float | [0, 1] | `central_bank` | `fx_operations` | 7 | 1 | 30 | 是 | 0.05 | 0.2 | 1 | `operational` |
| `sanctions_imposed_on` | set&lt;int&gt; | [0, N-1] 的目标集合、排除自身 | `external_affairs` | `trade_and_migration` | 1 | 0 | 30 | 是 | — | — | 3 | `regime_switch` |
| `immigration_cap` | float\|null | [0, 10] 或 null | `external_affairs` | `trade_and_migration` | 30 | 1 | 91 | 是 | 0.05 | 0.25 | 2 | `major` |
| `emigration_cap` | float\|null | [0, 1] 或 null | `external_affairs` | `trade_and_migration` | 30 | 1 | 91 | 是 | 0.025 | 0.1 | 2 | `major` |
| `remittance_tax` | float | [0, 0.9] | `external_affairs` | `trade_and_migration` | 14 | — | 91 | 否 | 0.025 | 0.1 | 1 | `ordinary` |
| `outward_remittance_tax` | float | [0, 0.9] | `external_affairs` | `trade_and_migration` | 14 | — | 91 | 否 | 0.025 | 0.1 | 1 | `ordinary` |
| `guest_worker_return` | float | [0, 1] | `external_affairs` | `trade_and_migration` | 30 | — | 91 | 否 | 0.025 | 0.1 | 1 | `ordinary` |
| `fx_regime` | enum | {`float`, `peg`} | `central_bank` | `fx_operations` | 7 | 0 | 91 | 是 | — | — | 3 | `regime_switch` |
| `peg_anchor` | int\|null | [0, N-1]、非自身，或 null | `central_bank` | `fx_operations` | 7 | 0 | 91 | 是 | — | — | 3 | `regime_switch` |
| `peg_reserve_scale` | float | [1, 1000000000] | `central_bank` | `fx_operations` | 1 | 0 | 7 | 是 | 10000 | 100000 | 0.5 | `operational` |
