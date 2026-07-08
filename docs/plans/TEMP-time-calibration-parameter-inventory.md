# Tick-Time Calibration Parameter Inventory

Purpose: collect every current parameter whose interpretation changes if we map
one economic tick to a natural-time duration `Delta`. The main economic model
currently treats a tick as an abstract period. Demographic Phase 0 is separate:
its `dt=1.0` is already used as the natural-time step for the Leslie/vital-rate
kernel.

Source files checked:

- `macro_sim/config/model.py`
- `macro_sim/config/schema.py`
- `macro_sim/core/policy.py`
- `macro_sim/behavior/planning.py`
- `macro_sim/systems/*.py`
- `macro_sim/demographics/*.py`
- `docs/design/core/03-market-institutional-axioms.md`
- `docs/design/core/04-validation-roadmap-kernel.md`

Design status:

- `docs/design/core/04-validation-roadmap-kernel.md` currently says one tick is
  an abstract period, not a week/month/year.
- Therefore the main economy has no single authoritative design-time `Delta`.
- These parameters are the candidates that need a shared time calibration.

## 1. Main Economic Horizon

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `n_ticks` | `500` | simulation length in economic ticks | Converts to total natural horizon: `T = n_ticks * Delta`. |

## 2. Planning, Expectations, Price, Wage, Consumption

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `lambda_d` | `0.3` | firm demand-expectation partial adjustment each tick | Memory half-life depends on `Delta`. |
| `lambda_y` | `0.3` | household income-expectation partial adjustment each tick | Memory half-life depends on `Delta`. |
| `theta_price` | `0.25` | Calvo repricing probability per tick | Hard micro-frequency anchor. Mean spell is about `1 / theta_price = 4` ticks. |
| `theta_wage` | `0.15` | Calvo rewage probability per tick | Hard micro-frequency anchor. Mean spell is about `1 / theta_wage = 6.67` ticks. |
| `delta` | `0.0` | downward wage flexibility per tick; forced to strict DNWR by default | If ever relaxed above zero, annualized wage-cut flexibility depends on `Delta`. |
| `eta` | `0.05` | markup adjustment step per planning tick | Effective markup adjustment speed depends on `Delta`. |
| `mu_min`, `mu_max` | `0.0`, `1.0` | markup bounds | Bounds, not rates, but they cap repeated per-tick markup adjustment. |
| `omega` | `0.02` | wage raise step when labor-rationed and rewage draw fires | Wage-growth speed depends on event frequency and `Delta`. |
| `phi` | `0.75` | target inventory as a multiple of expected demand | Interpretable as desired stock coverage in ticks of demand. |
| `search_m` | `1` | sellers each buyer compares in the goods market each tick | Market-search intensity per goods-market tick; not a natural-time rate, but affected by tick frequency. |
| `alpha1` | `0.8` | consumption budget out of expected income each tick | Per-period MPC; natural-time consumption propensity depends on `Delta`. |
| `alpha2` | `0.05` | consumption budget out of wealth each tick | Per-period wealth drawdown; strongly time-scale sensitive. |
| `mpc_dispersion` | `0.0` | cross-household dispersion of MPC parameters at genesis | Distribution parameter, not a rate, but changes per-tick consumption heterogeneity. |
| `wealth_effect` | `0.0` | weight of smoothed equity wealth in consumption wealth term | Per-tick wealth-effect channel if enabled. |
| `mpc_wealth_curvature` | `1.0` | curvature of wealth term in per-tick consumption | Shape parameter, but affects per-period drawdown. |
| `hh_subsistence` | `0.0` | household consumption floor defended by borrowing | Flow floor per tick if household credit is enabled. |

## 3. Production, Investment, Capital Accumulation

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `lambda_I` | `0.25` | accelerator investment partial-adjustment speed per tick | Capital adjustment half-life depends on `Delta`. |
| `delta_K` | `0.05` | private capital depreciation per tick | Hard stock-decay anchor; annualizes as `1 - (1-delta_K)^(1/Delta)`. |
| `lambda_q` | `0.0` | Tobin-q investment sensitivity applied each planning tick | Per-period financial-to-real response if enabled. |
| `q_invest_smooth` | `1.0` | EMA speed for q driving investment | q-signal memory depends on `Delta`. |
| `q_invest_floor` | `0.5` | lower multiplier on investment target | Not itself a rate, but applies each tick through investment. |
| `q_invest_cap` | `2.0` | upper multiplier on investment target | Not itself a rate, but applies each tick through investment. |
| `public_capital_depreciation` | `0.05` | public capital depreciation per tick | Same time-scale issue as `delta_K`. |
| `public_capital_gamma` | `0.0` | productivity elasticity of public capital stock | Not a rate, but acts on each tick's production when enabled. |
| `jg_productivity` | `0.0` | public-capital units built per unit JG labor per tick | Per-tick public investment flow if job guarantee is enabled. |

## 4. Credit, Interest, Debt Service

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `r_interest` | `0.01` | loan/policy interest rate per tick when CB off | Hard financial rate anchor. |
| `r_neutral` | `0.01` | neutral policy rate per tick | Annualization depends on `Delta`. |
| `r_max` | `0.10` | policy-rate cap per tick | Natural-time cap depends on `Delta`. |
| `amort` | `0.1` | firm principal amortization fraction per tick | Debt maturity/repayment speed depends on `Delta`. |
| `hh_amort` | `0.1` | household non-margin debt amortization fraction per tick | Household debt duration depends on `Delta`. |
| `bank_spread_disp` | `0.0` | cross-bank loan-rate spread SD in per-tick rate units | Annualized spread depends on `Delta`. |
| `interbank_rate_base` | `0.0` | interbank spread over policy rate per tick | Annualized spread depends on `Delta`. |
| `interbank_tightness` | `0.0` | tightness-driven interbank spread in per-tick rate units | Annualized spread depends on `Delta`. |
| `deposit_rate_disp` | `0.0` | deposit-rate spread SD in per-tick rate units | Annualized spread depends on `Delta`. |
| `bank_target_capital_ratio` | `0.0` | target bank capital as share of loan book | Stock ratio, not a time rate; affects per-tick payout behavior. |
| `rho` | `0.5` | dividend payout ratio of positive tick profit; also bank payout baseline | Per-period payout/retention speed depends on accounting period. |

## 5. Central Bank And Inflation Rule

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `inflation_target` | `0.0` | per-tick inflation target | Hard macro policy-rate calibration candidate. |
| `infl_ema_lambda` | `0.02` | EMA speed for per-tick inflation signal | Inflation-memory half-life depends on `Delta`. |
| `rate_inertia` | `0.8` | policy-rate smoothing per tick | Monetary-policy adjustment speed depends on `Delta`. |
| `taylor_phi_pi` | `1.5` | response to per-tick inflation gap | Dimensionless slope, but attached to per-tick inflation/rate units. |
| `taylor_phi_u` | `0.5` | response to unemployment gap | Converts unemployment gap into a per-tick rate change. |
| `u_natural` | `0.05` | unemployment reference used by the Taylor rule | Level anchor, not a rate; included because it shapes the per-tick rule. |
| `omo_drain_frac` | `0.1` | fraction of reserve gap drained/injected each tick | Quantity-policy adjustment half-life depends on `Delta`. |
| `omo_reserve_target` | `0.0` | reserve stock target as fraction of genesis reserves | Stock target, not time-based; paired with `omo_drain_frac`. |

## 6. Securities / Bonds

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `bond_coupon` | `0.0` | coupon rate per tick on bond face value | Annualized coupon depends on `Delta`. |
| `bond_maturity` | `1` | maturity in ticks | Converts directly to natural maturity: `maturity * Delta`. |
| `bond_finance_frac` | `0.0` | target share of government debt financed by bonds | Stock target, not itself a rate. |
| `bond_theta` | `0.0` | household target wealth share in bonds | Portfolio stock target; reached through per-tick issuance/trading. |
| `bank_bond_appetite` | `0.0` | fraction of excess reserves banks try to put into bonds during issuance | Per-issuance/tick portfolio adjustment intensity. |
| `bank_bond_duration_limit` | `0.0` | cap on bank bond book relative to economic capital | Stock limit; not a time rate. |

Canonical later-version values:

- `Config.v123()`: `bond_coupon=0.01`, `bond_theta=0.15`, `bond_maturity=8`.
- `Config.v124()`: `bond_coupon=0.01`, `bond_theta=0.15`, `bond_maturity=4`,
  `omo_drain_frac=0.03`, `bank_bond_appetite=0.03`.

## 7. Firm Demographics / Firm Entry-Exit

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `bankrupt_persist` | `10` | ticks a C-firm may remain insolvent before death | Converts to legal/economic insolvency grace period. |
| `entry_beta` | `0.4` | firm entry sensitivity to excess profit rate | Entry intensity is evaluated each tick. |
| `entry_max` | `3` | max new consumption firms per tick | Entry-flow cap depends on `Delta`. |
| `gibrat_sigma` | `0.05` | lognormal attractiveness shock size per tick | Hard stochastic growth-volatility calibration candidate. |
| `pref_attach_beta` | `1.0` | demand exponent on attractiveness | Not a time rate, but acts every goods-market tick. |
| `pref_price_elasticity` | `0.0` | demand price-elasticity in preferential matching | Not a time rate, but acts every goods-market tick. |
| `gibrat_entry_a0` | `0.2` | entrant initial attractiveness | Initial condition for entrant dynamics, not a rate. |

## 8. Equity, Portfolios, Margin

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `lambda_p` | `0.1` | equity/bank-equity price groping speed per tick | Market-price adjustment speed depends on `Delta`. |
| `trend_lambda` | `0.3` | adaptive momentum/trend update speed per tick | Trend-memory half-life depends on `Delta`. |
| `equity_ema_lambda` | `0.1` | household equity wealth EMA speed | Wealth-effect memory depends on `Delta`. |
| `resid_income_lambda` | `0.1` | residual-income smoothing for per-firm valuation | Valuation-memory half-life depends on `Delta`. |
| `portfolio_adjust` | `1.0` | fraction of portfolio gap traded each tick | Portfolio rebalancing speed depends on `Delta`. |
| `lambda_issue` | `0.0` | equity issuance intensity per tick when q>1 | Equity-finance flow speed depends on `Delta`. |
| `theta_equity` | `0.3` | target equity share of household wealth | Stock target; not a rate, but approached per tick via `portfolio_adjust`. |
| `w_chartist` | `0.0` | weight on trend-following demand | Not time-dimensional, but trend itself uses per-tick returns. |
| `w_fundamental` | `1.0` | weight on value-price demand | Not time-dimensional. |
| `margin_ltv` | `0.5` | margin loan-to-value cap | Stock ratio, not a time rate. |
| `margin_max` | `2.0` | max target equity share under margin | Stock/leverage ceiling, not a time rate. |

## 9. Banking Dynamics, Runs, Bank Equity

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `bank_equity_lambda` | `0.1` | bank earnings EMA speed | Valuation-memory half-life depends on `Delta`. |
| `bank_theta_equity` | `0.1` | target household wealth share in bank equity | Stock target; reached per tick through bank-stock trading. |
| `bank_entry_beta` | `0.0` | de-novo bank entry probability/intensity from ROE excess | Entry intensity is evaluated each tick. |
| `bank_entry_max` | `1` | max de-novo banks per tick | Entry-flow cap depends on `Delta`. |
| `run_sensitivity` | `0.0` | run-flight intensity response to bank distress | Run probability/intensity per tick. |
| `run_fear_persistence` | `0.9` | panic/fear persistence multiplier each tick | Panic-memory half-life depends on `Delta`. |
| `run_health_ref` | `0.1` | health threshold for run pressure | Stock-ratio threshold, not a time rate. |
| `run_market_weight` | `0.5` | market-vs-book weight in run health | Not a time rate. |
| `bank_search_m` | `2` | loan-bank search sample size per credit tick | Not a rate; market-search intensity per tick. |
| `deposit_search_m` | `2` | deposit-bank search sample size per deposit-competition tick | Not a rate; market-search intensity per tick. |
| `reserve_floor_frac` | `0.0` | intraday reserve floor relative to bank capital/deposits | Stock/liquidity constraint, not a natural-time rate. |

## 10. Fiscal, Labor Policy, Taxes

These are mostly per-period fiscal flow rates or stock taxes. If one tick is
mapped to natural time, their annualized interpretation changes.

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `gov_consumption_share` | `0.0` | real government demand as share of potential output each tick | Per-tick government demand flow. |
| `gov_deficit_target` | `0.0` | target deficit as share of tick GDP | Per-tick fiscal stance. |
| `deficit_u_ref` | `0.0` | unemployment reference for state-dependent deficit taper | Not a rate; affects per-tick fiscal stance. |
| `benefit_replacement` | `0.0` | unemployment benefit as share of wage reference per tick | Per-tick transfer flow. |
| `tax_profit_rate` | `0.0` | tax rate on positive firm profit each tick | Period tax on per-tick profit. |
| `tax_income_rate` | `0.0` | tax rate on household income each tick | Period tax on per-tick income. |
| `tax_consumption_rate` | `0.0` | VAT on goods purchases | Per-transaction, less directly time-scaled. |
| `tax_wealth_rate` | `0.0` | wealth tax on household net worth per tick | Hard stock-tax time-scale issue. |
| `income_allowance` | `0.0` | income-tax allowance as fraction of mean income | Not time-dimensional. |
| `wealth_allowance` | `0.0` | wealth-tax allowance as multiple of mean net worth | Not time-dimensional. |
| `gov_investment_share` | `0.0` | government investment budget as share of prior nominal output | Per-tick public investment flow. |
| `min_wage` | `0.0` | wage floor binding immediately in each planning tick | Level, not time-dimensional. |
| `jg_wage_ratio` | `0.0` | job-guarantee wage as ratio of mean wage | Level ratio; payments are per tick. |

## 11. Hard-Coded Tick-Sensitive Constants

These are not `Config` fields, but they behave like per-tick parameters and
should be considered during calibration or later refactoring.

| Location | Value | Current meaning | Time-calibration role |
|---|---:|---|---|
| `macro_sim/systems/equity.py` | `max(-0.5, min(0.5, excess_demand))` | caps equity price-impact signal before multiplying by `lambda_p` | Limits one-tick equity price adjustment; effective volatility depends on `Delta`. |
| `macro_sim/systems/equity.py` | `0.5 * book`, `0.2 * shares_outstanding` | per-firm equity issuance caps per tick when `equity_finance` is enabled | Caps financing flow per tick. |
| `macro_sim/systems/banking.py` | `bank.share_peak * 0.999` | decays remembered bank-stock peak each tick | Panic/market-health memory half-life depends on `Delta`. |
| `macro_sim/systems/banking.py` | `max(0.0, 0.5 - health)` | run pressure threshold at bank health below 0.5 | Threshold, not a rate, but part of per-tick run intensity. |
| `macro_sim/systems/banking.py` | `+0.25` | system fear jump when a bank suspends/fails during a run tick | Panic jump per event/tick. |
| `macro_sim/systems/banking.py` | `+0.02 * len(queue) / len(households)` | system fear increment after non-suspended run withdrawals | Panic accumulation per tick. |
| `macro_sim/systems/banking.py` | `range(8)` | random founder search attempts per bank-entry tick | Search intensity per entry tick. |
| `macro_sim/systems/firm_demographics.py` | `range(12)` | random funder search attempts per firm-entry tick | Search intensity per entry tick. |

## 12. Demographic Phase 0 Natural-Time Parameters

The demographic kernel is not currently coupled to the economic tick. It has its
own `dt`, used to convert vital rates into survival/fertility probabilities and
to compute Leslie growth diagnostics.

| Parameter | Default | Current meaning | Time-calibration role |
|---|---:|---|---|
| `Phase0VitalRates.dt` | `1.0` | demographic time step used in mortality/fertility integration | Currently interpretable as one natural year in the Phase 0 kernel. |
| `makeham_a` | `3e-4` | age-independent mortality hazard component | Natural-time mortality hazard; must be converted if demographic tick changes. |
| `gompertz_b` | `6e-5` | Gompertz mortality baseline | Natural-time mortality hazard scale. |
| `gompertz_theta` | `0.0866` | Gompertz aging rate by age | Age-time scale parameter. |
| `infant_extra` | `0.010` | extra mortality hazard over age interval `[0,1)` | Natural-time infant mortality component. |
| `tfr` | `2.5` | total fertility over lifetime | Not per tick, but fertility curve is scaled by `dt`. |
| `fertility_peak_age` | `28.0` | peak age of fertility curve | Age-time parameter. |
| `fertility_width` | `6.0` | width of fertility curve in age units | Age-time parameter. |
| `omega` | `100` | maximum age bucket | Age-time horizon. |
| `sex_ratio_at_birth` | `1.05` | male/female sex ratio at birth | Not time-dimensional. |

## 13. Parameters Explicitly Not Time Calibration Anchors

These are important model parameters, but they are scale, stock, distribution,
or structural parameters rather than per-tick natural-time rates:

- Reproducibility: `seed`.
- Agent counts and simulation scale: `n_households`, `n_firms`, `n_firms_c`,
  `n_firms_k`, `n_banks`, `watchlist_size`, `float_shares`,
  `shares_per_firm`.
- Genesis balances and initial conditions: `d_household0`, `d_firm0`,
  `d_bank0`, `bank_capital_frac`, `d_cfirm0`, `d_kfirm0`, `startup_deposits`,
  `startup_capital`, `K_firm0`, `p_firm0`, `w_firm0`, `p_kfirm0`,
  `inv_firm0`, `inv_kfirm0`, `mu_firm0`, `demand_e_firm0`.
- Production/technology levels and elasticities: `a`, `a_K`, `A`, `alpha`,
  `v`, `dis_slope`.
- Markup and distributional shape parameters already listed above because they
  interact with per-tick rules: `mu_min`, `mu_max`, `mpc_dispersion`.
- Stock/leverage limits and ratios: `kappa`, `bank_leverage_mean`,
  `bank_leverage_disp`, `bank_exposure_limit`, `bank_min_capital`,
  `hh_credit_limit`, `bond_finance_frac`, `omo_reserve_target`,
  `bank_bond_duration_limit`.
- Boolean switches and routing modes: all `*_enabled`/feature flags,
  `bank_enabled`, `bank_capital_constraint`, `bank_assignment`,
  `bank_migrate_on_failure`, `bank_rate_competition`, `interbank`,
  `bank_equity`, `bank_equity_trading`, `bank_dynamics`, `bank_runs`,
  `bonds`, `omo`, `lolr`, `bank_resolution_fund`, `firm_dynamics`,
  `capital_enabled`, `capital_market`, `per_firm_equity`, `equity_finance`,
  `household_credit`, `household_bankruptcy`, `margin_credit`, `government`,
  `job_guarantee`, `central_bank`, `interest_by_deposits`, `index_startup`,
  `symmetric_k`, `k_replacement_floor`, `gibrat_growth`,
  `pro_rata_dividends`, `founder_owned_genesis`.
- Founder-class size: `genesis_founder_pool`.

## 14. Calibration Notes For External Review

Strong candidate anchors:

1. `theta_price`: observed micro price spell.
2. `theta_wage`: observed wage revision spell.
3. `delta_K` / `public_capital_depreciation`: observed depreciation rate.
4. `r_interest`, `r_neutral`, `bond_coupon`: observed annual financial rates.
5. `amort`, `hh_amort`, `bond_maturity`: observed loan/bond duration.
6. `gibrat_sigma`: firm growth volatility per natural period.

Current likely conflict:

- `theta_price=0.25` implies a mean price spell of about 4 ticks. If the target
  natural spell is 8-11 months, then one tick is about 2.0-2.75 months.
- With that same `Delta`, `delta_K=0.05/tick` annualizes to roughly 20-26%,
  which is high for broad productive capital.
- If instead `delta_K=0.05` is read as annual depreciation, then one tick is
  about one year and `theta_price=0.25` implies prices change about once every
  four years.

So the current model should be treated as an abstract per-tick economy until
these anchors are reconciled.
