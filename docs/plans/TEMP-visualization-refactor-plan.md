# Visualization Refactor Plan: Indicator Registry And Dashboard Spec

This plan is the working specification for the visualization refactor. It
defines the indicator taxonomy, the broad CSV recording surface, the default
high-information figure set for each category, and the implementation rules that
will let static PNG generation and the Streamlit/Plotly comparison tool share
one metric vocabulary.

## Scope

- Define stable indicator categories that survive future model versions.
- Separate "what the CSV records" from "what the figures show".
- Prefer recording every cheap, well-defined observation in CSV.
- Choose only the highest-information indicators for default figures.
- Standardize canonical names, aliases, feature gates, units, and derivation
  status before writing plotting code.
- Make cross-version comparison possible without rerunning old simulations.

## Recording Vs Visualization Principle

The visualization refactor has two different selection layers:

1. **CSV recording layer:** broad and lossless. If an indicator is cheap to
   compute, well-defined, and useful for diagnosis, record it. CSV should preserve
   optional detail so later analysis does not require rerunning a 4000-tick
   simulation.
2. **Figure layer:** narrow and information-dense. Figures should show only the
   most useful indicators for reading the economy quickly. A metric can be
   recorded in CSV without appearing in the default static figures.

Therefore, category drilldowns should first list all record-worthy metrics, then
separately select the smaller visualization set.

## Dashboard Tiers

The refactor should not turn "one huge diagnostic figure" into "fifteen huge
diagnostic figures". The same metric registry should support three display
tiers:

1. **Overview:** a short cross-category surface for quick economic triage. This
   should contain the smallest set of headline indicators needed to answer
   whether the run is alive, healthy, stressed, or policy-distorted.
2. **Category Default:** each category keeps its curated 20 indicator set and
   grouped panels. These are the default static PNG groups and the default
   Streamlit category tabs.
3. **Deep Dive:** every recorded CSV column and every safe derived metric remains
   queryable in the interactive tool, but does not appear in default static
   output unless explicitly selected.

## Metric Registry Rules

Before implementation, convert the tables below into a registry with one row per
metric. Grouped CSV tables are convenient for reading, but the implementation
needs a machine-friendly source of truth.

Each registry entry should include:

| Field | Meaning |
|---|---|
| `metric_id` | Canonical snake_case name used by the visualization layer. |
| `legacy_names` | Existing CSV names accepted for backward compatibility. |
| `category_owner` | The category that owns the definition of the metric. |
| `reused_in_categories` | Other categories that use the same metric as context. |
| `status` | `recorded`, `recorded_when_enabled`, `derived_from_series`, `derived_from_metadata`, `derived_from_baseline`, `add_from_state`, or `future_extension`. |
| `feature_gate` | Optional feature/config switch required for the metric to exist as a real value. |
| `source` | Current state object, CSV column, derived formula, run metadata, or future module. |
| `formula` | Exact derivation when the metric is not directly recorded. |
| `unit` | Flow, stock, ratio, rate, index, count, currency, or model-specific quantity. |
| `default_visual` | Whether the metric belongs to the default 20 for its category. |
| `panel` | Default panel assignment when visualized. |

Feature-gated metrics should keep stable schema behavior. Prefer exporting a
consistent column with `NaN` plus a disabled flag over silently removing columns
from different versions.

## Canonical Naming Rules

- Keep raw legacy columns readable, but expose canonical names in the plotting
  layer. For example, `hh_wealth_gini` should be labeled or aliased as
  `hh_deposit_gini` when it only measures deposit wealth.
- Keep face, book, and market values separate. Existing `hh_bond_wealth` means
  household bond face value; market-value household bond wealth should use
  `hh_bond_market_value`.
- Normalize aggregate/per-firm equity names. Aggregate `market_cap`,
  `book_value`, and `tobin_q` should map to canonical `equity_market_cap`,
  `equity_book_value`, and `equity_tobin_q` when shown through the visualization
  layer.
- Treat fiscal balance fields carefully. Legacy `gov_spending` and
  `gov_deficit` may omit public investment or bond interest in some contexts.
  Broad fiscal charts should prefer `augmented_gov_spending` and `cash_deficit`.
- Separate private labor slack from policy-buffered slack. `unemployment_rate`
  is private firm-side unemployment; `effective_unemployment` is the no-income
  unemployment measure when job guarantee is enabled.

## Derivation And Metadata Rules

- `derived_from_series` means the metric can be computed from CSV columns alone.
- `derived_from_metadata` means the metric also needs run config or policy
  constants, such as inflation targets, Taylor-rule coefficients, or natural
  unemployment assumptions.
- `derived_from_baseline` means the metric needs another run, version, or
  baseline id, such as cross-version deltas and policy effect estimates.
- Run metadata should be stored beside every generated CSV: model version,
  commit hash, seed, feature switches, policy parameters, scenario label, and
  baseline id when applicable.
- Derived metrics should be reproducible without rerunning the simulation once
  the CSV and metadata artifacts are present.

## Top-Level Indicator Categories

| Category | What It Answers |
|---|---|
| 1. Real Macro Activity | Is the real economy producing, consuming, investing, and growing? |
| 2. Prices And Inflation | Are price levels, inflation, wages, markups, and price dispersion stable? |
| 3. Labor Market | Are workers employed, are firms demanding labor, and is matching tight or slack? |
| 4. Household Welfare And Living Standards | Are households able to consume, avoid poverty, and maintain a basic standard of living? |
| 5. Wealth And Asset Distribution | How are deposits, net worth, equity wealth, bond wealth, and other assets distributed across households? |
| 6. Money And Payments | How much money exists, where is it held, how fast does it circulate, and are payments clearing? |
| 7. Credit And Leverage | How much borrowing exists, who is levered, and how heavy are debt service, defaults, and write-offs? |
| 8. Fiscal Sector | How much does the government tax, spend, transfer, invest, deficit-finance, and owe? |
| 9. Central Bank And Monetary Policy | What is the policy stance, how is it transmitted, and what is on the central bank balance sheet? |
| 10. Banking System | Are banks solvent, liquid, competitive, concentrated, failing, or subject to runs? |
| 11. Securities And Asset Markets | What are stocks and bonds doing: prices, market values, book values, issuance, dividends, and duration effects? |
| 12. Firm Structure And Competition | How many firms exist, how concentrated are markets, and how do firm size, entry, exit, markups, and zombies evolve? |
| 13. Inequality And Distributional Structure | How unequal are income, consumption, wealth, ownership, firm size, and financial claims? |
| 14. Stability And Risk | Is the system conserving, fragile, crisis-prone, frozen, overleveraged, or near a failure cascade? |
| 15. Policy Effects And Transmission | What did fiscal, monetary, welfare, public-capital, and financial-stability policies actually change? |

## Category Notes

### 1. Real Macro Activity

Covers output, consumption, investment, inventories, productivity, capacity use,
and growth. This is the first layer for asking whether the economy is active.

### 2. Prices And Inflation

Covers price indices, inflation, wage inflation, real wages, markups, and price
dispersion. This category separates nominal instability from real activity.

### 3. Labor Market

Covers labor supply, labor demand, employment, unemployment, vacancies,
fill-rate, and labor-market tightness. This category should distinguish private
labor stress from policy-provided employment buffers when those exist.

### 4. Household Welfare And Living Standards

Covers consumption welfare, bottom-tail consumption, poverty, poverty depth,
subsistence-floor pressure, social welfare functions, and household living
standards. This category asks whether ordinary households are doing well, not
just whether aggregate output is high.

### 5. Wealth And Asset Distribution

Covers deposit wealth, net worth, equity wealth, bond wealth, top shares, and
asset concentration. This category is about stocks of household resources rather
than current-period income or consumption.

### 6. Money And Payments

Covers broad money, base money, sector deposits, reserves, money velocity,
payment gridlock, intraday liquidity, and settlement conditions.

### 7. Credit And Leverage

Covers total credit, firm debt, household debt, margin debt, leverage ratios,
new loans, debt service, defaults, write-offs, and bankruptcies.

### 8. Fiscal Sector

Covers taxes, government consumption, public investment, transfers, benefits,
job-guarantee spending, deficits, debt, and debt ratios.

### 9. Central Bank And Monetary Policy

Covers policy rates, real rates, inflation targets, inflation signals, open
market operations, QE/QT-like quantity tools, lender-of-last-resort advances,
and central bank balance-sheet positions.

### 10. Banking System

Covers bank count, bank capital, economic capital, reserves, leverage, loan-book
concentration, deposit concentration, interbank activity, bank equity, runs,
failures, and bank births/deaths.

### 11. Securities And Asset Markets

Covers equity market capitalization, book value, Tobin's q, share turnover,
dividends, equity issuance, bond face value, bond book value, bond market value,
mark-to-market gains/losses, and security ownership.

### 12. Firm Structure And Competition

Covers firm counts, births, deaths, zombies, firm size distributions, market
concentration, markup dispersion, attractiveness concentration, and competitive
dynamics.

### 13. Inequality And Distributional Structure

Covers income inequality, consumption inequality, wealth inequality, ownership
inequality, firm-size inequality, bank-ownership inequality, and top-share
statistics. This category cuts across households, firms, banks, and assets.

### 14. Stability And Risk

Covers conservation drift, accounting invariants, insolvency, liquidity stress,
bank failures, market freezing, excessive leverage, debt-service pressure, and
crisis markers.

### 15. Policy Effects And Transmission

Covers the effect of policy interventions on real activity, inflation, labor,
welfare, financial stability, public capital, credit, banks, and securities.
This is a comparison category: it usually needs before/after or cross-version
views rather than a single raw time series.

## Implementation Roadmap

The category drilldowns are now broad enough to guide implementation. The next
work should happen in this order:

1. **Metric registry:** encode canonical names, aliases, statuses, feature
   gates, units, derivation formulas, default-category flags, and panel
   assignments.
2. **CSV export schema:** make recorded and feature-gated metrics stable across
   versions, preferring consistent columns with `NaN` over missing columns.
3. **Run metadata artifact:** save version, commit, seed, feature switches,
   policy parameters, scenario labels, and baseline ids next to every CSV.
4. **Derived metric layer:** compute series-only, metadata-based, and
   baseline-comparison metrics without rerunning simulations.
5. **Static PNG generator:** generate category figure groups from the registry
   instead of writing one-off version scripts.
6. **Streamlit/Plotly comparison tool:** load one or more CSV+metadata artifacts,
   choose categories/runs, overlay versions, and expose deep-dive columns.
7. **Compatibility pass:** preserve legacy CSV names through aliases and add
   tests for missing-column behavior, canonical naming, and derived formulas.

## Implementation Progress

- Added `macro_sim.visualization` as the first reusable visualization layer.
- Added run artifacts: each generated run now has a `series.csv` plus
  `metadata.json` under a version label. This gives the future comparison app a
  stable import format instead of depending on the old `runs/` registry.
- Added category specs for the first static comparison surface:
  `overview`, `real_macro`, `fiscal_monetary`, `banking`, and `securities`.
  Missing metrics are tolerated and annotated in figures, so older CSVs remain
  readable while the broader metric schema is still being filled in.
- Added a Matplotlib per-version renderer that writes one category PNG group
  inside each version artifact directory. A version artifact is self-contained:
  `series.csv`, `metadata.json`, and `figures/*.png` live together.
- Added `run_two_version_comparison` and the `macro-viz-compare` command entry
  point. The default comparison is `v123` versus `v124`, producing sibling
  version directories such as `outputs/visualizations/.../v123` and
  `outputs/visualizations/.../v124`. Cross-version overlay belongs to the
  future interactive app that imports these artifacts, not to the generated
  static PNGs.
- Set the default visualization benchmark scale to the model's full baseline:
  `5000` households, `500` C-firms, `250` K-firms, `8` banks, and `5000`
  ticks.
- Added `profile.json` at the comparison output root. It records total runtime,
  per-version simulation+CSV time, and per-version rendering time.
- Added focused tests for artifact round-tripping, category PNG generation, and
  a tiny two-version smoke run.

First observable-metrics code pass landed in `macro_sim/reporting/metrics.py`.
It exports current-state metrics without adding behavioral mechanisms:

- real activity plan/realization metrics: `production_target_total`,
  `production_realization_rate`, `demand_expected_total`,
  `target_inventory_total`, `inventory_gap_total`, `inventory_gap_ratio`,
  `inventory_to_sales`, `capital_productivity`, `active_producer_share`,
  `active_seller_share`, `investment_target_units`,
  `investment_realization_rate`, `private_capital_depreciation`, and
  `net_private_capital_formation`;
- price/labor distribution metrics: price, markup, and wage quantiles,
  `unit_labor_cost_mean`, `unit_labor_cost_cv`, sector wage splits,
  notional labor demand, cash labor constraint rates, labor rationing shares,
  employment splits, and policy wage-floor indicators;
- household welfare/wealth metrics: real consumption summaries, deposit
  quantiles, debt concentration, full-net-worth summaries, underwater share,
  bond wealth concentration, and gross household assets;
- credit/banking metrics: firm-debt concentration, total new loans, total
  debt-service ratio, bank capital distribution, economic-capital distribution,
  reserve distribution, deposit base distribution, reserve-floor breach share,
  and large-exposure usage;
- fiscal/monetary metrics: `augmented_gov_spending`, `cash_deficit`,
  broad fiscal ratios, inflation/unemployment gaps, Taylor-rule target,
  policy-rate gap, reserve target/gap, and central-bank balance-sheet summary;
- securities metrics: household/bank/CB bond face and market values, owner
  market-value shares, weighted maturity/duration, market-to-face ratio, bond
  discount, and bond share of government debt.

## Current Drilldown: Real Macro Activity

For Real Macro Activity, the current working decision is:

- CSV should record all useful production, consumption, investment, capital,
  inventory, productivity, activity-breadth, and realization-rate indicators.
- Figures should later select only the highest-information subset.

### CSV Recording Set

The CSV layer should be broad. The point is to avoid rerunning long simulations
just because a useful diagnostic was not exported. Some entries are already
recorded, some can be derived from exported columns, and some should be added
when the visualization/metrics layer is refactored.

| Indicator | Status | Purpose |
|---|---|---|
| `real_output` | Already recorded | Core real production level; first read on whether the economy is active. |
| `real_output_growth` | Already recorded | Production momentum; flags expansions, recessions, and volatility. |
| `real_consumption` | Already recorded | Real consumer-goods absorption; closest aggregate proxy for realized living flow. |
| `real_consumption_growth` | Derivable from CSV | Consumption momentum; often turns before output in demand slowdowns. |
| `nominal_output` | Already recorded | Nominal scale anchor for comparing real activity, prices, and money flows. |
| `desired_consumption` | Already recorded | Household demand intention before rationing or market frictions bind. |
| `effective_consumption` | Already recorded | Consumption demand actually executed in money terms. |
| `unsatisfied_demand_ratio` | Already recorded | Share of demand not fulfilled; separates weak demand from constrained supply. |
| `investment_units` | Already recorded | Real private investment in capital-good units. |
| `investment_units_growth` | Derivable from CSV | Investment cycle momentum; useful because investment is usually more volatile than consumption. |
| `investment_spending` | Already recorded | Nominal investment flow; connects real capital formation to money demand. |
| `aggregate_capital` | Already recorded | Private productive capital stock; slow-moving capacity backbone. |
| `aggregate_capital_growth` | Derivable from CSV | Capital-stock momentum; shows whether productive capacity is expanding. |
| `capital_output_ratio` | Derivable from CSV | Capital intensity; useful in CSV but mostly redundant with `capital_productivity` for default charts. |
| `capital_productivity` | Derivable from CSV | Output per unit of private capital; compact read on capital utilization/efficiency. |
| `inventory` | Already recorded | Unsold goods stock; shows accumulation, shortages, or clearing problems. |
| `inventory_investment` | Already recorded | Inventory accumulation/drawdown flow; turns faster than the inventory stock. |
| `inventory_to_sales` | Derivable from CSV | Scale-adjusted inventory pressure; makes inventory comparable across runs. |
| `labor_productivity` | Already recorded | Output per employed worker; connects real activity to labor efficiency. |
| `production_target_total` | Add from current firm state | Aggregate planned production before realized output; needed to diagnose plan failure. |
| `production_realization_rate` | Add from current firm state | Realized production divided by planned production; direct plan-fulfillment metric. |
| `demand_expected_total` | Add from current firm state | Firm-side expected demand; helps distinguish planning error from execution failure. |
| `target_inventory_total` | Add from current firm state | Desired inventory buffer; baseline for inventory-gap diagnosis. |
| `inventory_gap_total` | Add from current firm state | Actual minus target inventory; raw pressure on future production decisions. |
| `inventory_gap_ratio` | Add from current firm state | Scale-adjusted inventory gap; comparable across versions and parameter sets. |
| `investment_target_units` | Add from current firm state | Desired real investment before capital-goods rationing. |
| `investment_realization_rate` | Add from current firm state | Actual investment divided by desired investment; direct investment-market constraint metric. |
| `private_capital_depreciation` | Add from current firm state | Capital lost to depreciation; needed for net capital formation. |
| `net_private_capital_formation` | Add from current firm state | Investment minus depreciation; shows whether private productive capacity is being built or consumed. |
| `active_producer_share` | Add from current firm state | Share of firms producing positive output; breadth of real activity. |
| `active_seller_share` | Add from current firm state | Share of firms selling positive quantity; breadth of market participation. |
| `real_output_per_active_firm` | Add from current firm state | Average production among active firms; separates intensive from extensive margins. |
| `real_sales_per_active_firm` | Add from current firm state | Average realized sales among active firms; detects market concentration or thinning. |
| `capital_deepening` | Add from current firm state | Capital per worker or per active firm; structural production-capacity signal. |
| `household_real_consumption` | Requires goods-market quantity bookkeeping | Household real consumption split; needed once non-household demand is explicit. |
| `government_real_consumption` | Requires goods-market quantity bookkeeping | Government real consumption split; prevents public demand from being hidden in aggregates. |
| `private_real_investment` | Mostly represented by `investment_units` | Real private investment category for national-account-style decomposition. |
| `public_real_investment` | Requires exposing public capital units | Real public-capital formation; needed for public infrastructure policy diagnostics. |
| `real_absorption` | Requires real-flow split | Domestic real demand total: consumption plus investment plus government real demand. |

### Default 20 Figure Indicators

These 20 indicators are the current high-information visualization set for the
default Real Macro Activity figure group. The broader CSV set above should still
be recorded; this set is only the default chart surface.

| Indicator | Status | Why It Belongs In Figures |
|---|---|---|
| `real_output` | Already recorded | The main real activity level; every diagnosis needs this anchor. |
| `real_output_growth` | Already recorded | Shows cyclical momentum and recession timing more clearly than levels alone. |
| `real_consumption` | Already recorded | Measures realized real demand from households, close to living-flow welfare. |
| `real_consumption_growth` | Derivable from CSV | Early warning for demand weakening or overheating. |
| `aggregate_capital` | Already recorded | Shows the economy's productive capacity stock. |
| `desired_consumption` | Already recorded | Demand intention; needed to see whether households wanted to spend. |
| `effective_consumption` | Already recorded | Realized demand; paired with desired consumption to expose rationing. |
| `unsatisfied_demand_ratio` | Already recorded | Compact friction/shortage indicator. |
| `production_target_total` | Add from current firm state | Shows what firms tried to produce before constraints. |
| `production_realization_rate` | Add from current firm state | One-line answer to whether production plans are fulfilled. |
| `investment_units` | Already recorded | Main real capital-formation flow. |
| `investment_target_units` | Add from current firm state | Desired capital formation before rationing or funding constraints. |
| `investment_realization_rate` | Add from current firm state | Whether desired investment actually becomes installed capital. |
| `net_private_capital_formation` | Add from current firm state | Distinguishes gross investment from true capacity growth. |
| `capital_productivity` | Derivable from CSV | More visually useful than `capital_output_ratio`: higher means capital is producing more output. |
| `labor_productivity` | Already recorded | Productivity signal from the labor side. |
| `active_producer_share` | Add from current firm state | Activity breadth; catches cases where aggregate output hides firm exit/inactivity. |
| `inventory` | Already recorded | Stock of unsold goods; important for demand/supply imbalance. |
| `inventory_investment` | Already recorded | Fast-moving inventory flow; detects turning points. |
| `inventory_to_sales` | Derivable from CSV | Scale-adjusted inventory pressure. |

The selected 20 indicators answer six questions:

1. **Scale:** how large are output, consumption, and productive capacity?
2. **Momentum:** are output and consumption accelerating or contracting?
3. **Demand conversion:** do desired household purchases become realized purchases?
4. **Production execution:** do firm plans become actual output?
5. **Investment and capacity:** does investment translate into net capital growth?
6. **Efficiency, breadth, and pressure:** are productivity, active participation, and inventories healthy?

Metrics intentionally kept out of the default figure group but still recorded in
CSV include `nominal_output`, `investment_spending`, `capital_output_ratio`,
`demand_expected_total`, `target_inventory_total`, `inventory_gap_total`,
`inventory_gap_ratio`, `active_seller_share`, per-active-firm averages,
public/private real-flow splits, and `real_absorption`.

### Visualization Design For The 20 Indicators

The default Real Macro Activity visualization should be a grouped figure set,
not one giant all-metrics chart. Use 10 panels, each with a clear diagnostic
question. The static artifact should be publication-quality PNG; the interactive
cross-version tool should render the same groups with Plotly inside Streamlit.

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Real Activity Level | `real_output`, `real_consumption` | Two solid lines, same axis when units are compatible | Are production and realized consumption moving together? |
| 2. Growth Momentum | `real_output_growth`, `real_consumption_growth` | Lines around a horizontal zero reference | Is the real economy expanding, slowing, or contracting? |
| 3. Household Demand Conversion | `desired_consumption`, `effective_consumption` | Desired as dashed line, effective as solid line, optional gap fill | Are households being rationed or unable to execute planned spending? |
| 4. Demand Friction | `unsatisfied_demand_ratio` | Single line or lightly filled area, bounded at zero | Is unmet demand becoming a structural constraint? |
| 5. Production Plan Fulfillment | `production_target_total`, `real_output`, `production_realization_rate` | Target dashed, actual solid, realization rate with 1.0 reference | Are firms producing what they planned? |
| 6. Investment Plan Fulfillment | `investment_target_units`, `investment_units`, `investment_realization_rate` | Target dashed, actual solid, realization rate with 1.0 reference | Is desired investment becoming installed capital? |
| 7. Capital Accumulation | `aggregate_capital`, `net_private_capital_formation` | Capital stock line plus net-formation bars around zero | Is productive capacity growing or being eaten away? |
| 8. Productivity | `capital_productivity`, `labor_productivity` | Indexed lines, base period = 100 | Is efficiency improving on capital and labor margins? |
| 9. Activity Breadth | `active_producer_share` | Bounded line from 0 to 1 | Is aggregate output broad-based or carried by fewer active firms? |
| 10. Inventory Pressure | `inventory`, `inventory_investment`, `inventory_to_sales` | Inventory stock line, inventory-flow bars, inventory/sales ratio line | Are goods piling up, being depleted, or balanced against sales? |

Important implementation note for Panel 5: `production_target_total` should
default to the consumption-goods production target, or be renamed
`c_production_target_total`, when compared directly with `real_output`. If the
metric includes both consumption-goods and capital-goods targets, it mixes units
and should remain a CSV/deep-dive metric instead of appearing in the default
panel.

### Visual Style Rules

- Use Plotly for the Streamlit cross-version comparison tool and Matplotlib for
  archived static PNG output unless implementation evidence suggests otherwise.
- Use consistent semantic styling: target/planned series are dashed neutral
  gray, realized/actual series are saturated solid lines, gaps may use soft
  translucent fills.
- Use zero reference lines for growth, net capital formation, and inventory
  investment.
- Use a 1.0 reference line for realization rates.
- Show raw lines lightly and a rolling mean more prominently when the series is
  noisy; the CSV should still keep raw tick-level data.
- For cross-version comparison, color should encode version/run and line style
  should encode metric. Avoid assigning a unique color to every metric in an
  overlay, because that becomes unreadable quickly.
- Suggested color family, based on a colorblind-safe Okabe-Ito palette:
  `#0072B2` for output, `#009E73` for consumption, `#CC79A7` for
  investment/capital, `#E69F00` for inventory/pressure, `#D55E00` for
  constraint/risk, and neutral gray for planned/target lines.

## Remaining Category Drilldowns

The 14 categories after Real Macro Activity follow the same specification shape:

1. Record a broad CSV set, including already recorded, derivable, currently
   observable-but-not-recorded, and future-extension metrics.
2. Pick exactly 20 default figure indicators.
3. Group those 20 indicators into readable panels rather than one giant chart.

For compactness, the CSV tables below group indicators by implementation status.
Treat these grouped rows as authoring notes; the implementation should expand
them into the one-row-per-metric registry described above. The default figure
tables remain explicit and fixed at 20 indicators per category.

### 2. Prices And Inflation

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `price_index`, `mean_price`, `price_std`, `price_cv`, `inflation`, `nominal_output`, `inflation_ema`, `policy_rate`, `real_rate`, `capital_price_index`, `avg_markup`, `markup_std`, `avg_wage`, `wage_std`, `wage_inflation`, `real_wage` | Core price level, inflation, wage-price, markup, and central-bank signal series. |
| Derivable from CSV | `cumulative_inflation`, `log_price_index`, `inflation_volatility`, `inflation_acceleration`, `capital_goods_inflation`, `relative_capital_goods_price`, `markup_cv`, `wage_cv`, `real_wage_growth`, `wage_price_inflation_gap`, `unit_labor_cost_aggregate`, `profit_margin_proxy` | Post-run price momentum, volatility, relative price, and cost-push diagnostics. |
| Add from current state | `inflation_target`, `inflation_gap_to_target`, `tax_inclusive_price_index`, `consumption_tax_rate`, `min_wage`, `job_guarantee_wage`, `price_p10`, `price_p50`, `price_p90`, `price_p90_p10_ratio`, `sales_weighted_price_std`, `unsold_price_mean`, `sales_weighted_markup`, `markup_p10`, `markup_p50`, `markup_p90`, `markup_at_mu_min_share`, `markup_at_mu_max_share`, `unit_labor_cost_mean`, `unit_labor_cost_cv`, `posted_price_target_gap_mean`, `posted_price_target_gap_std`, `inventory_price_pressure_share`, `sector_avg_wage_C`, `sector_avg_wage_K`, `sector_wage_gap_C_vs_K`, `wage_p10`, `wage_p50`, `wage_p90`, `wage_p90_p10_ratio`, `min_wage_binding_share` | Current firm/policy state can expose price distribution, wage distribution, tax-inclusive prices, and sticky-price misalignment. |
| Requires future extension | `price_reset_share`, `wage_reset_share`, `expected_inflation`, `inflation_expectations_gap`, `wage_indexation_pressure`, `multi_good_cpi_subindices`, `producer_price_index_intermediate_inputs`, `import_price_index`, `quality_adjusted_price_index`, `administered_price_share`, `menu_cost_burden` | Requires reset logging, expectations, multiple goods, open economy, quality, administered-price, or menu-cost mechanisms. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `price_index` | Already recorded | Main consumption-price level. |
| 2 | `inflation` | Already recorded | Direct inflation momentum. |
| 3 | `inflation_ema` | Already recorded when central bank is on | The smoothed signal policy responds to. |
| 4 | `inflation_gap_to_target` | Add from policy state | Whether inflation is above or below target. |
| 5 | `policy_rate` | Already recorded when central bank is on | Nominal policy stance. |
| 6 | `real_rate` | Already recorded when central bank is on | Ex-ante real policy stance. |
| 7 | `capital_price_index` | Already recorded when capital sector exists | Investment-goods price pressure. |
| 8 | `relative_capital_goods_price` | Derivable from CSV | Whether capital goods are becoming expensive relative to consumer goods. |
| 9 | `price_cv` | Already recorded | Compact price-dispersion read. |
| 10 | `price_p90_p10_ratio` | Add from firm state | Intuitive high-low posted-price spread. |
| 11 | `avg_markup` | Already recorded | Main cost-plus pricing state. |
| 12 | `markup_std` | Already recorded | Markup heterogeneity. |
| 13 | `sales_weighted_markup` | Add from firm state | Markup actually faced in trades. |
| 14 | `markup_at_bounds_share` | Add from firm/config state | Whether markups are hitting configured bounds. |
| 15 | `unit_labor_cost_aggregate` | Derivable from CSV | Aggregate labor-cost pressure. |
| 16 | `posted_price_target_gap_mean` | Add from firm state | Sticky-price misalignment. |
| 17 | `avg_wage` | Already recorded | Nominal wage level. |
| 18 | `wage_inflation` | Already recorded | Wage-price companion momentum. |
| 19 | `real_wage` | Already recorded | Worker purchasing power. |
| 20 | `wage_price_inflation_gap` | Derivable from CSV | Whether wages are keeping up with prices. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Price Level And Inflation | `price_index`, `inflation` | Price level line plus inflation line around zero | Is the price level stable, drifting, or jumping? |
| 2. Inflation Vs Target | `inflation`, `inflation_ema`, `inflation_target`, `inflation_gap_to_target` | Lines with target reference | Is policy seeing inflation above or below target? |
| 3. Monetary Stance | `policy_rate`, `real_rate` | Lines with zero reference | Is policy actually tight or loose in real terms? |
| 4. Consumption Vs Capital Prices | `price_index`, `capital_price_index`, `relative_capital_goods_price` | Indexed lines plus ratio | Are investment goods becoming relatively expensive? |
| 5. Price Dispersion | `price_cv`, `price_p90_p10_ratio`, `sales_weighted_price_std` | Dispersion lines or fan | Is inflation accompanied by price misallocation? |
| 6. Markup Structure | `avg_markup`, `sales_weighted_markup`, `markup_std` | Multi-line panel | Is pricing pressure broad or concentrated? |
| 7. Markup Bounds And Pressure | `markup_at_mu_min_share`, `markup_at_mu_max_share`, `inventory_price_pressure_share` | Bounded share lines | Are firms pressed against markup limits or inventory pressure? |
| 8. Wage-Price Dynamics | `avg_wage`, `wage_inflation`, `real_wage`, `wage_price_inflation_gap` | Indexed wage lines plus gap | Are workers gaining purchasing power or chasing prices? |
| 9. Cost Pass-Through | `unit_labor_cost_aggregate`, `posted_price_target_gap_mean`, `price_index` | Cost line with zero-gap reference | Are cost shocks passing through or stuck in sticky prices? |

### 3. Labor Market

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `labor_supply`, `labor_demand`, `employment`, `unemployment_rate`, `vacancies_unfilled`, `labor_fill_rate`, `avg_wage`, `wage_std`, `wage_inflation`, `real_wage`, `wages_paid`, `labor_productivity`, `labor_share`, `wages_C`, `wages_K`, `credit_wage`, `jg_employment`, `jg_employment_rate`, `effective_unemployment`, `jg_spending`, `benefit_paid` | Core supply, demand, employment, wage, productivity, and policy-buffer labor measures. |
| Derivable from CSV | `employment_rate`, `private_unemployment_units`, `vacancy_rate`, `labor_market_tightness`, `wage_cv`, `real_wage_growth`, `wagebill_per_worker`, `labor_productivity_growth`, `unit_labor_cost` | Rates, tightness, wage dispersion, and labor-cost transforms. |
| Add from current state | `labor_demand_notional`, `cash_labor_demand_gap`, `cash_labor_constraint_rate`, `cash_constrained_firm_share`, `labor_rationed_firm_share`, `full_unemployed_share`, `underemployed_share`, `labor_sold_gini`, `employment_C`, `employment_K`, `labor_demand_C`, `labor_demand_K`, `jg_wage`, `min_wage`, `min_wage_binding_firm_share`, `benefit_recipient_share` | Current firm and household state can reveal hidden demand, rationing breadth, underemployment, sector splits, and policy wage floors. |
| Requires future extension | `job_spell_length`, `separation_rate`, `hire_rate`, `vacancy_postings`, `matching_function_efficiency`, `skill_specific_unemployment` | Requires persistent job spells, vacancies, search/matching, or skill segmentation. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `labor_supply` | Already recorded | Scale anchor. |
| 2 | `labor_demand_notional` | Add from firm state | Desired hiring before cash constraints. |
| 3 | `labor_demand` | Already recorded | Effective private demand after constraints. |
| 4 | `employment` | Already recorded | Private labor actually hired. |
| 5 | `employment_rate` | Derivable from CSV | Compact employment read. |
| 6 | `unemployment_rate` | Already recorded | Main private slack indicator. |
| 7 | `effective_unemployment` | Already recorded when government is on | No-income unemployment after policy buffer. |
| 8 | `vacancies_unfilled` | Already recorded | Unfilled private demand. |
| 9 | `labor_fill_rate` | Already recorded | Matching/rationing health. |
| 10 | `labor_market_tightness` | Derivable from CSV | Vacancies relative to unemployed labor. |
| 11 | `cash_labor_constraint_rate` | Add from firm state | Hidden demand suppressed by liquidity. |
| 12 | `labor_rationed_firm_share` | Add from firm state | Breadth of labor shortage. |
| 13 | `avg_wage` | Already recorded | Posted wage level. |
| 14 | `real_wage` | Already recorded | Purchasing-power wage. |
| 15 | `wage_inflation` | Already recorded | Wage momentum. |
| 16 | `wage_cv` | Derivable from CSV | Wage dispersion. |
| 17 | `wages_paid` | Already recorded | Household labor-income flow. |
| 18 | `labor_productivity` | Already recorded | Output per worker. |
| 19 | `labor_share` | Already recorded | Functional income distribution. |
| 20 | `jg_employment_rate` | Already recorded when government is on | Size of public buffer stock. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Labor Flow Core | `labor_supply`, `labor_demand_notional`, `labor_demand`, `employment` | Supply reference, notional dashed, effective/actual solid | Do firms want labor, afford labor, and hire labor? |
| 2. Employment And Slack | `employment_rate`, `unemployment_rate` | Bounded 0-1 lines | Is private employment close to full labor use? |
| 3. Policy-Adjusted Slack | `unemployment_rate`, `effective_unemployment`, `jg_employment_rate` | Private slack solid, effective slack dashed, JG area | Is policy absorbing private unemployment? |
| 4. Vacancies And Fill | `vacancies_unfilled`, `labor_fill_rate` | Vacancy line plus fill-rate line with 1.0 reference | Is unemployment demand weakness or unfilled labor demand? |
| 5. Tightness | `labor_market_tightness`, `unemployment_rate` | Tightness line with unemployment backdrop | Is the labor market slack, balanced, or overheated? |
| 6. Hidden Demand Constraint | `labor_demand_notional`, `labor_demand`, `cash_labor_constraint_rate` | Gap fill plus constraint rate | Are firms failing to hire because they lack cash or credit? |
| 7. Rationing Breadth | `labor_rationed_firm_share`, `labor_fill_rate` | Bounded share/rate lines | Are labor shortages concentrated or broad? |
| 8. Wage Level And Momentum | `avg_wage`, `real_wage`, `wage_inflation` | Indexed wage lines plus inflation line | Are wages rising and buying more? |
| 9. Wage Dispersion And Income Flow | `wage_cv`, `wages_paid`, `labor_share` | Dispersion plus wage bill/share lines | Is labor income broadening or becoming uneven? |
| 10. Productivity And Pay | `labor_productivity`, `real_wage`, `labor_share` | Indexed productivity and wage lines | Do productivity gains reach workers? |

### 4. Household Welfare And Living Standards

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `desired_consumption`, `effective_consumption`, `bottom10_consumption`, `unsatisfied_demand_ratio`, `poverty_rate`, `poverty_gap`, `income_poverty_rate`, `consumption_floor_share`, `welfare_log`, `sen_welfare`, `consumption_gini`, `income_gini`, `hh_income`, `real_wage`, `hh_saving`, `savings_rate`, `effective_unemployment`, `jg_employment_rate`, `benefit_paid`, `jg_spending`, `consumption_credit_share`, `household_leverage`, `hh_bankruptcies`, `hh_bond_wealth` | Consumption, poverty, inequality, income, employment-buffer, credit-stress, and near-money welfare supports. |
| Derivable from CSV | `real_household_consumption`, `mean_real_consumption_per_household`, `consumption_realization_rate`, `welfare_transfer_total`, `household_net_fiscal_flow` | Deflated living-flow and fiscal-support transforms. |
| Add from current state | `median_real_consumption`, `bottom25_consumption`, `subsistence_gap_ratio`, `median_real_household_income`, `hh_debt_service_burden`, `household_underwater_share`, `benefit_recipient_share` | Current household states can expose typical, lower-tail, subsistence-gap, and balance-sheet welfare stress. |
| Requires future extension | `housing_service_flow`, `health_or_education_access`, `age_adjusted_welfare`, `leisure_welfare`, `multi_good_real_consumption_basket` | Requires housing, demographics, leisure, or multi-good consumption mechanisms. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `desired_consumption` | Already recorded | What households attempted to consume. |
| 2 | `effective_consumption` | Already recorded | What households actually bought. |
| 3 | `mean_real_consumption_per_household` | Derivable from CSV | Average real living standard. |
| 4 | `median_real_consumption` | Add from household state | Typical household living standard. |
| 5 | `bottom10_consumption` | Already recorded | Lower-tail welfare floor. |
| 6 | `consumption_realization_rate` | Derivable from CSV | Planned-to-realized demand conversion. |
| 7 | `unsatisfied_demand_ratio` | Already recorded | Market rationing/friction readout. |
| 8 | `poverty_rate` | Already recorded | Poverty incidence. |
| 9 | `poverty_gap` | Already recorded | Poverty depth. |
| 10 | `income_poverty_rate` | Already recorded | Income-side poverty check. |
| 11 | `consumption_floor_share` | Already recorded | Subsistence-floor pressure. |
| 12 | `welfare_log` | Already recorded | Concave social welfare. |
| 13 | `sen_welfare` | Already recorded | Level-and-equality welfare. |
| 14 | `consumption_gini` | Already recorded | Consumption inequality. |
| 15 | `income_gini` | Already recorded | Income inequality. |
| 16 | `real_wage` | Already recorded | Purchasing-power channel. |
| 17 | `effective_unemployment` | Already recorded when government is on | No-income labor stress. |
| 18 | `jg_employment_rate` | Already recorded when government is on | Public employment buffer. |
| 19 | `welfare_transfer_total` | Derivable from CSV | Direct income-floor support. |
| 20 | `household_underwater_share` | Add normalized metric | Balance-sheet distress as welfare risk. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Consumption Conversion | `desired_consumption`, `effective_consumption`, `consumption_realization_rate`, `unsatisfied_demand_ratio` | Desired dashed, effective solid, bounded rates on secondary axis | Do household plans become realized consumption? |
| 2. Real Living Level | `mean_real_consumption_per_household`, `median_real_consumption`, `bottom10_consumption` | Three real-consumption lines | Are average, typical, and lower-tail living standards rising together? |
| 3. Poverty Incidence | `poverty_rate`, `income_poverty_rate` | Bounded lines | Is poverty visible in consumption, income, or both? |
| 4. Poverty Depth | `poverty_gap`, `consumption_floor_share` | Lines or light filled areas | Are poor households shallowly or deeply below the floor? |
| 5. Social Welfare | `welfare_log`, `sen_welfare` | Indexed lines, base = 100 | Does aggregate welfare improve after diminishing utility and equality? |
| 6. Distribution Smoothing | `income_gini`, `consumption_gini` | Paired Gini lines | Is consumption smoother than income? |
| 7. Purchasing Power | `real_wage` | Single line with rolling mean | Can earned income buy more over time? |
| 8. Employment Floor | `effective_unemployment`, `jg_employment_rate` | Bounded lines, JG area fill | Is policy absorbing no-income unemployment? |
| 9. Transfer Support | `welfare_transfer_total` | Line or stacked benefits/JG split | How much direct support sustains households? |
| 10. Financial Stress | `household_underwater_share` | Bounded stress line, bankruptcy markers when present | Are household balance sheets threatening living standards? |

### 5. Wealth And Asset Distribution

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `hh_money`, `hh_money_share`, `hh_wealth_gini`, `hh_wealth_top10_share`, `hh_wealth_cv`, `hh_wealth_min`, `hh_wealth_max`, `household_debt_total`, `hh_networth_gini`, `hh_networth_min`, `hh_networth_median`, `hh_wealth_gini_incl_equity`, `market_cap`, `equity_market_cap`, `equity_wealth_share`, `equity_ownership_gini`, `bank_equity_total`, `bank_equity_gini`, `hh_bond_wealth`, `hh_full_networth_gini`, `hh_full_networth_top10`, `share_underwater`, `share_margin_underwater` | Existing liquid wealth, debt, net worth, equity, bank-equity, bond-face, and underwater measures. |
| Derivable from CSV | `debt_to_gross_assets`, `deposit_share_of_full_wealth`, `equity_share_of_full_wealth`, `bond_share_of_full_wealth`, `networth_growth`, `top10_gap_vs_median` | Balance-sheet shares and changes after canonical full-wealth totals exist. |
| Add from current state | `hh_deposit_p10`, `hh_deposit_median`, `hh_deposit_p90`, `household_debt_gini`, `household_debt_top10_share`, `equity_wealth_top10_share`, `bank_equity_top10_share`, `hh_bond_market_value`, `bond_wealth_gini`, `bond_wealth_top10_share`, `bond_wealth_share`, `hh_full_networth_total`, `hh_full_networth_skew`, `hh_full_networth_excess_kurtosis`, `wealth_upper_tail_slope`, `gross_household_assets_total` | Current holdings, debt, owners, and bond lots can expose quantiles, market-value wealth, and tail shape. |
| Requires future extension | `housing_wealth`, `pension_wealth`, `human_capital_wealth`, `foreign_asset_wealth`, `wealth_by_age_cohort` | Requires new asset classes, demographics, or open-economy claims. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `hh_deposit_gini` | Alias from `hh_wealth_gini` | Baseline liquid-wealth inequality. |
| 2 | `hh_deposit_top10_share` | Alias from `hh_wealth_top10_share` | Compact concentration read. |
| 3 | `hh_deposit_p10` | Add from state | Bottom liquid-wealth condition. |
| 4 | `hh_deposit_median` | Add from state | Typical household liquid wealth. |
| 5 | `hh_deposit_p90` | Add from state | Upper-liquid-wealth reference. |
| 6 | `hh_wealth_gini_incl_equity` | Already recorded | How firm equity changes wealth concentration. |
| 7 | `hh_full_networth_gini` | Already recorded in margin mode; canonicalize | Headline full balance-sheet inequality. |
| 8 | `hh_full_networth_top10_share` | Alias from `hh_full_networth_top10` | Top-decile full wealth share. |
| 9 | `hh_full_networth_skew` | Add from state | Right-tail shape. |
| 10 | `hh_full_networth_excess_kurtosis` | Add from state | Outlier-driven heavy-tail signal. |
| 11 | `wealth_upper_tail_slope` | Add from state | Pareto/rank-size tail read. |
| 12 | `equity_wealth_share` | Already recorded | Importance of firm equity in household wealth. |
| 13 | `equity_ownership_gini` | Already recorded | Firm-equity ownership concentration. |
| 14 | `equity_wealth_top10_share` | Add from holdings | Top-holder equity concentration. |
| 15 | `bank_equity_gini` | Already recorded | Bank-owner concentration. |
| 16 | `hh_bond_market_value` | Add from bond lots | Bond wealth at market value. |
| 17 | `bond_wealth_share` | Add or derive | Safe-asset share of household wealth. |
| 18 | `bond_wealth_gini` | Add from bond market values | Bond ownership concentration. |
| 19 | `share_underwater` | Already recorded | Net-debtor prevalence. |
| 20 | `share_margin_underwater` | Already recorded | Market-net-worth distress prevalence. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Liquid Wealth Concentration | `hh_deposit_gini`, `hh_deposit_top10_share` | Bounded lines | Are deposits concentrating? |
| 2. Liquid Wealth Ladder | `hh_deposit_p10`, `hh_deposit_median`, `hh_deposit_p90` | Quantile fan | Is the whole distribution moving or only the top? |
| 3. Gross Vs Full Wealth | `hh_wealth_gini_incl_equity`, `hh_full_networth_gini`, `hh_full_networth_top10_share` | Bounded lines | Does debt change the wealth story? |
| 4. Wealth Tail Shape | `hh_full_networth_skew`, `hh_full_networth_excess_kurtosis`, `wealth_upper_tail_slope` | Small multiples | Is the rich tail smooth or outlier-driven? |
| 5. Firm-Equity Channel | `equity_wealth_share`, `equity_ownership_gini`, `equity_wealth_top10_share` | Share/concentration lines | Is firm equity the main concentration channel? |
| 6. Bank-Equity Channel | `bank_equity_gini` | Optional bounded line | Are bank profits concentrating owner wealth? |
| 7. Bond Wealth Channel | `hh_bond_market_value`, `bond_wealth_share`, `bond_wealth_gini` | Market-value line plus share/concentration | Are bonds broad safe assets or concentrated claims? |
| 8. Underwater Households | `share_underwater`, `share_margin_underwater` | Bounded stress lines | How much of the household sector has negative net worth? |

### 6. Money And Payments

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `total_money`, `broad_money`, `net_worth`, `conservation_drift`, `money_velocity`, `hh_money`, `firm_money`, `c_firm_money`, `k_firm_money`, `bank_money`, `hh_money_share`, `wages_paid`, `consumption_spending`, `dividends_paid`, `investment_spending`, `tax_total`, `gov_spending`, `bank_reserves_total`, `cb_reserves`, `reserve_M`, `peak_intraday_overdraft`, `payments_gridlocked`, `interbank_volume`, `bank_deposit_hhi`, `bank_deposit_flight` | Money stock, location, velocity, payment rails, reserve settlement, gridlock, and deposit-flight metrics. |
| Derivable from CSV | `firm_money_share`, `bank_money_share`, `money_creation_gap`, `settlement_payment_volume_total`, `payment_velocity_by_rail`, `reserve_to_deposit_ratio` | Shares and throughput transforms. |
| Add from current state | `genesis_money`, `bank_money_total`, `fiscal_deposit_balance`, `clearing_balance`, `total_reserves`, `reserve_conservation_drift`, `bank_reserve_min`, `bank_reserve_median`, `deposit_base_by_bank_p10_p50_p90` | Ledger and reserve overlay can expose base anchors, clearing leaks, and reserve distribution. |
| Requires future extension | `payment_attempt_value`, `payment_blocked_value`, `payment_delay_duration`, `intraday_credit_usage_by_payment`, `payment_network_centrality` | Requires payment-attempt logging and richer payment network tracking. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `total_money` | Already recorded | Headline deposit money stock. |
| 2 | `genesis_money` | Add from ledger | Conserved A5 anchor. |
| 3 | `net_worth` | Already recorded when bank exists | Confirms A5 under credit/security layers. |
| 4 | `conservation_drift` | Already recorded | Accounting-integrity warning. |
| 5 | `money_velocity` | Already recorded | Money circulation intensity. |
| 6 | `hh_money` | Already recorded | Household liquidity. |
| 7 | `firm_money` | Already recorded | Firm liquidity. |
| 8 | `c_firm_money` | Already recorded when capital sector exists | Consumption-firm liquidity. |
| 9 | `k_firm_money` | Already recorded when capital sector exists | Capital-firm liquidity. |
| 10 | `bank_money` | Already recorded when bank exists | Bank retained-money/equity sink. |
| 11 | `hh_money_share` | Already recorded | Household share of money. |
| 12 | `wages_paid` | Already recorded | Main income payment rail. |
| 13 | `consumption_spending` | Already recorded | Main goods payment rail. |
| 14 | `dividends_paid` | Already recorded | Profit-return rail. |
| 15 | `investment_spending` | Already recorded when capital sector exists | Investment payment rail. |
| 16 | `bank_reserves_total` | Already recorded when interbank exists | Bank settlement liquidity. |
| 17 | `cb_reserves` | Already recorded when interbank exists | Reserve absorption/injection location. |
| 18 | `reserve_M` | Already recorded in bonds block; generalize | Reserve-layer base money. |
| 19 | `peak_intraday_overdraft` | Already recorded when interbank exists | Intraday liquidity stress. |
| 20 | `payments_gridlocked` | Already recorded when interbank exists | Settlement blockage signal. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Deposit Money Identity | `total_money`, `genesis_money`, `net_worth`, `conservation_drift` | Stock lines plus drift axis | Is money creation happening while A5 holds? |
| 2. Money Velocity | `money_velocity`, `total_money` | Velocity line with money backdrop | Is money circulating or sitting idle? |
| 3. Sector Money Location | `hh_money`, `firm_money`, `bank_money`, `hh_money_share` | Sector stock lines plus share | Where is money accumulating? |
| 4. Firm-Sector Liquidity | `c_firm_money`, `k_firm_money` | Two stock lines | Is money trapped in one firm sector? |
| 5. Core Payment Rails | `wages_paid`, `consumption_spending`, `dividends_paid` | Flow lines | Are income, spending, and payout loops balanced? |
| 6. Investment Payment Rail | `investment_spending`, `c_firm_money`, `k_firm_money` | Flow line plus stocks | Is investment moving money between firm sectors? |
| 7. Reserve Stock Split | `reserve_M`, `bank_reserves_total`, `cb_reserves` | Stacked or overlaid reserve lines | Are reserves held by banks or absorbed by CB? |
| 8. Intraday Liquidity Stress | `peak_intraday_overdraft` | Stress line with zero baseline | Are payments creating reserve overdraft pressure? |
| 9. Payment Gridlock | `payments_gridlocked`, `peak_intraday_overdraft` | Count line plus overdraft backdrop | Are settlement frictions binding? |

### 7. Credit And Leverage

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `total_credit`, `credit_to_M`, `aggregate_leverage`, `n_firms_borrowing`, `new_loans`, `credit_wage`, `credit_investment`, `interest_paid`, `principal_repaid`, `credit_to_gdp`, `debt_service_ratio`, `household_debt_total`, `household_credit_new`, `hh_interest_paid`, `household_leverage`, `share_underwater`, `household_margin_debt`, `avg_household_leverage`, `margin_deleveraged`, `margin_credit_new`, `share_margin_underwater`, `writeoffs`, `bank_leverage`, `bank_rate_spread_sd`, `bank_loanbook_hhi` | Core credit stock, flow, debt-service, household leverage, margin, writeoff, and bank-credit structure. |
| Derivable from CSV | `credit_growth`, `net_credit_flow`, `firm_credit_share`, `household_credit_share`, `credit_wage_share`, `credit_investment_share`, `repayment_to_new_loan_ratio`, `interest_to_gdp`, `principal_to_gdp`, `margin_debt_share`, `debt_per_borrower` | Credit-cycle and allocation transforms. |
| Add from current state | `firm_debt_total`, `firm_debt_gini`, `firm_debt_top10_share`, `household_principal_paid`, `firm_interest_paid`, `firm_principal_repaid`, `loan_request_total`, `loan_granted_total`, `loan_denied_total`, `credit_grant_rate`, `bank_capacity_total`, `bank_capacity_min`, `large_exposure_usage_max`, `cash_constrained_borrower_share`, `margin_call_count`, `default_rate_by_sector` | Current ledger, bank-capacity, and request/grant phases can expose constrained demand and balance-sheet fragility. |
| Requires future extension | `loan_maturity_profile`, `floating_vs_fixed_rate_share`, `collateral_value`, `credit_score_distribution`, `arrears_duration`, `loan_loss_provisions` | Requires richer loan contracts, collateral, credit risk, or arrears accounting. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `total_credit` | Already recorded | Headline private credit stock. |
| 2 | `credit_to_gdp` | Already recorded | Macro leverage relative to output. |
| 3 | `credit_to_M` | Already recorded | Credit scale relative to base money. |
| 4 | `aggregate_leverage` | Already recorded | Economy-wide firm leverage proxy. |
| 5 | `new_loans` | Already recorded | Credit creation flow. |
| 6 | `net_credit_flow` | Derivable from CSV | New lending net of repayments. |
| 7 | `credit_wage` | Already recorded | Credit funding wage bills. |
| 8 | `credit_investment` | Already recorded | Credit funding investment. |
| 9 | `n_firms_borrowing` | Already recorded | Borrower breadth. |
| 10 | `firm_debt_total` | Add from ledger | Firm-sector debt stock. |
| 11 | `household_debt_total` | Already recorded | Household debt stock. |
| 12 | `household_credit_new` | Already recorded | Household consumption-credit flow. |
| 13 | `household_leverage` | Already recorded | Household debt-to-income burden. |
| 14 | `household_margin_debt` | Already recorded | Securities-backed household leverage. |
| 15 | `margin_credit_new` | Already recorded | New margin borrowing. |
| 16 | `margin_deleveraged` | Already recorded | Forced deleveraging/fire-sale pressure. |
| 17 | `interest_paid` | Already recorded | Interest burden flow. |
| 18 | `principal_repaid` | Already recorded | Debt-amortization flow. |
| 19 | `debt_service_ratio` | Already recorded | Total debt service relative to output. |
| 20 | `writeoffs` | Already recorded when firm dynamics on | Realized bad-debt losses. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Credit Stock | `total_credit`, `credit_to_gdp`, `credit_to_M` | Stock line plus ratios | Is credit expanding faster than the economy? |
| 2. Credit Flow | `new_loans`, `principal_repaid`, `net_credit_flow` | Bars around zero plus lines | Is credit creation or repayment dominating? |
| 3. Credit Allocation | `credit_wage`, `credit_investment`, `credit_wage_share`, `credit_investment_share` | Stacked flow/area | Is credit financing payroll or capital formation? |
| 4. Borrower Breadth | `n_firms_borrowing`, `firm_debt_total` | Count and stock | Is debt broad or concentrated? |
| 5. Household Credit | `household_debt_total`, `household_credit_new`, `household_leverage` | Stock/flow/rate panel | Are households leaning on credit to consume? |
| 6. Margin Leverage | `household_margin_debt`, `margin_credit_new`, `margin_deleveraged` | Stock plus flow bars | Is market leverage building or being forced down? |
| 7. Debt Service | `interest_paid`, `principal_repaid`, `debt_service_ratio` | Flow lines plus ratio | Is debt service crowding out demand? |
| 8. Credit Losses | `writeoffs`, `default_rate_by_sector` | Bars and rate line | Are defaults becoming systemic? |
| 9. Bank Constraint Channel | `bank_capacity_min`, `loan_denied_total`, `credit_grant_rate` | Constraint lines | Is credit demand being denied by bank capacity? |

### 8. Fiscal Sector

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `tax_profit`, `tax_income`, `tax_consumption`, `tax_wealth`, `tax_total`, `benefit_paid`, `gov_consumption`, `jg_spending`, `jg_employment`, `jg_employment_rate`, `effective_unemployment`, `gov_spending`, `gov_deficit`, `gov_debt`, `gov_deficit_to_revenue`, `gov_deficit_to_gdp`, `gov_debt_to_gdp`, `gov_spending_share_of_gdp`, `public_capital`, `public_investment`, `pubcap_factor`, `public_to_private_capital`, `gov_interest_bill`, `cb_claim_on_tsy`, `tga`, `hh_bankruptcies` | Tax, spending, deficit, debt, public-capital, interest, and household-support fiscal series. |
| Derivable from CSV | `primary_deficit`, `interest_share_of_spending`, `tax_mix_shares`, `spending_mix_shares`, `transfer_share_of_spending`, `fiscal_impulse`, `debt_growth`, `household_net_fiscal_flow`, `public_investment_share_of_gdp`, `cash_deficit_to_gdp`, `augmented_gov_spending_share_of_gdp` | Fiscal composition and impulse transforms once complete fiscal-flow fields exist. |
| Add from current state | `fiscal_deposit_balance`, `augmented_gov_spending`, `cash_deficit`, `gov_consumption_real_units`, `gov_investment_units`, `jg_capital_units`, `benefit_recipient_share`, `effective_tax_rate_income`, `effective_tax_rate_consumption`, `effective_tax_rate_wealth`, `bond_financed_debt_share`, `automatic_stabilizer_component`, `discretionary_deficit_component` | Current ledger/policy state can expose fiscal account, complete cash-flow balance, real public demand, and stabilizer mechanics. |
| Requires future extension | `pension_spending`, `health_spending`, `education_spending`, `age_transfer_profile`, `local_government_balance`, `tax_compliance_gap` | Requires richer public programs and demographics. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `tax_total` | Already recorded | Aggregate fiscal drain. |
| 2 | `tax_profit` | Already recorded | Profit-tax component. |
| 3 | `tax_income` | Already recorded | Income-tax component. |
| 4 | `tax_consumption` | Already recorded | Consumption-tax component. |
| 5 | `tax_wealth` | Already recorded | Wealth-tax component. |
| 6 | `augmented_gov_spending` | Add or derive from complete fiscal flows | Aggregate fiscal injection including public investment and bond interest where relevant. |
| 7 | `gov_consumption` | Already recorded | Public consumption demand. |
| 8 | `benefit_paid` | Already recorded | Transfer floor. |
| 9 | `jg_spending` | Already recorded | Job-guarantee wage bill. |
| 10 | `public_investment` | Already recorded | Public capital formation flow. |
| 11 | `cash_deficit` | Add or derive from complete fiscal flows | Broad net fiscal injection on a cash-flow basis. |
| 12 | `cash_deficit_to_gdp` | Derive after `cash_deficit` exists | Broad deficit normalized by output. |
| 13 | `gov_debt` | Already recorded | Government liability stock. |
| 14 | `gov_debt_to_gdp` | Already recorded | Debt burden relative to output. |
| 15 | `augmented_gov_spending_share_of_gdp` | Derive after `augmented_gov_spending` exists | Broad fiscal footprint. |
| 16 | `gov_interest_bill` | Already recorded when bonds on | Coupon/interest burden. |
| 17 | `public_capital` | Already recorded when public capital on | Public infrastructure stock. |
| 18 | `pubcap_factor` | Already recorded when public capital on | Productivity effect of public capital. |
| 19 | `jg_employment_rate` | Already recorded | Labor buffer size. |
| 20 | `effective_unemployment` | Already recorded | Welfare effect of fiscal labor buffer. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Fiscal Flow Balance | `augmented_gov_spending`, `tax_total`, `cash_deficit` | Spending/tax lines plus deficit bars | Is fiscal policy injecting or draining demand? |
| 2. Tax Mix | `tax_profit`, `tax_income`, `tax_consumption`, `tax_wealth` | Stacked areas | Which tax base funds the state? |
| 3. Spending Mix | `gov_consumption`, `benefit_paid`, `jg_spending`, `public_investment` | Stacked areas | Where does public spending go? |
| 4. Deficit Ratios | `cash_deficit_to_gdp`, `gov_deficit_to_revenue` | Lines with zero reference | Is the broad deficit large relative to the economy and tax base? |
| 5. Debt Stock | `gov_debt`, `gov_debt_to_gdp` | Stock line plus ratio | Is debt stabilizing or compounding? |
| 6. Interest Burden | `gov_interest_bill`, `interest_share_of_spending` | Flow and share | Are coupons crowding out useful spending? |
| 7. Public Capital | `public_investment`, `public_capital`, `pubcap_factor` | Flow bars plus stock/effect lines | Is public investment raising productivity? |
| 8. Labor Buffer | `jg_spending`, `jg_employment_rate`, `effective_unemployment` | JG area plus unemployment lines | Is fiscal policy absorbing labor slack? |
| 9. Household Fiscal Net | `household_net_fiscal_flow`, `benefit_paid`, `tax_income`, `tax_consumption`, `tax_wealth` | Net line with components | Is fiscal policy supporting or extracting from households? |

### 9. Central Bank And Monetary Policy

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `policy_rate`, `inflation_ema`, `real_rate`, `cb_reserves`, `cb_absorbed`, `omo_flow`, `lolr_advances`, `reserve_M`, `bank_reserves_total`, `interbank_rate`, `interbank_volume`, `peak_intraday_overdraft`, `payments_gridlocked`, `bond_mtm_pnl`, `bank_economic_capital_min` | Policy-rate stance, reserve quantity tools, interbank activation, LoLR, and duration-loss transmission. |
| Derivable from series | `rate_change`, `real_rate_change`, `omo_cumulative_flow`, `lolr_flow`, `policy_shock_size`, `interbank_policy_spread`, `reserve_drain_intensity` | Dynamic stance and transmission transforms that only need recorded time series. |
| Derivable from metadata/config | `inflation_gap_to_target`, `unemployment_gap`, `taylor_rate_target`, `policy_rate_gap`, `reserve_to_target_gap`, `reserve_gap` | Policy-rule and reserve-target gaps that need targets or rule parameters saved with the run. |
| Add from current state | `inflation_target`, `u_natural`, `omo_reserve_target_value`, `bank_lolr_recipient_count`, `cb_balance_sheet_assets`, `cb_balance_sheet_liabilities`, `cb_net_position` | Current config/policy/ledger state can expose reaction-function targets and balance-sheet composition. |
| Requires future extension | `expected_inflation`, `neutral_rate_estimate`, `yield_curve`, `forward_guidance_signal`, `central_bank_remittances`, `term_premium`, `exchange_rate_policy` | Requires expectations, richer bond curve, CB income, or open-economy channels. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `policy_rate` | Already recorded | Main policy instrument. |
| 2 | `real_rate` | Already recorded | Real stance after inflation. |
| 3 | `inflation_ema` | Already recorded | Smoothed inflation signal. |
| 4 | `inflation_gap_to_target` | Derive from series + metadata | Inflation mandate error. |
| 5 | `unemployment_rate` | Already recorded | Slack signal in the Taylor rule. |
| 6 | `unemployment_gap` | Derive from series + metadata | Labor-side mandate error. |
| 7 | `taylor_rate_target` | Derive from series + metadata | Unsmoothed policy-rate prescription. |
| 8 | `policy_rate_gap` | Derive from series + metadata | Actual rate relative to rule prescription. |
| 9 | `rate_change` | Derivable from CSV | Policy impulse. |
| 10 | `reserve_M` | Already recorded in bonds block; generalize | Base reserve quantity. |
| 11 | `bank_reserves_total` | Already recorded | Bank settlement liquidity. |
| 12 | `cb_reserves` | Already recorded | Reserve absorption at CB node. |
| 13 | `cb_absorbed` | Already recorded | Cumulative OMO drain. |
| 14 | `omo_flow` | Already recorded | This-tick reserve drain/injection. |
| 15 | `reserve_gap` | Derive from reserves + metadata | Distance from OMO target. |
| 16 | `interbank_rate` | Already recorded | Money-market transmission price. |
| 17 | `interbank_volume` | Already recorded | Money-market transmission quantity. |
| 18 | `peak_intraday_overdraft` | Already recorded | Reserve scarcity stress. |
| 19 | `lolr_advances` | Already recorded | Emergency liquidity support. |
| 20 | `bank_economic_capital_min` | Already recorded when bonds on | Bank solvency channel of duration losses. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Policy Rate Stance | `policy_rate`, `real_rate`, `rate_change` | Rate lines plus change bars | Is policy tightening or easing? |
| 2. Inflation Mandate | `inflation_ema`, `inflation_target`, `inflation_gap_to_target` | Signal line, target line, gap bars | Is inflation on target? |
| 3. Employment Mandate | `unemployment_rate`, `u_natural`, `unemployment_gap` | Lines and gap | Is slack above or below target? |
| 4. Taylor Rule Mechanics | `taylor_rate_target`, `policy_rate`, `policy_rate_gap` | Target vs actual | Is inertia or caps binding policy? |
| 5. Reserve Quantity Tool | `reserve_M`, `bank_reserves_total`, `cb_absorbed`, `omo_flow` | Stock lines and flow bars | Is OMO draining or injecting reserves? |
| 6. Reserve Targeting | `bank_reserves_total`, `omo_reserve_target_value`, `reserve_gap` | Current vs target lines | Are reserves scarce by design? |
| 7. Interbank Transmission | `interbank_rate`, `interbank_volume`, `peak_intraday_overdraft` | Rate/volume/stress panel | Is the money market transmitting scarcity? |
| 8. LoLR Support | `lolr_advances`, `bank_lolr_recipient_count`, `bank_economic_capital_min` | Support line plus capital stress | Is emergency liquidity stabilizing solvent banks? |
| 9. Duration Channel | `policy_rate`, `bond_mtm_pnl`, `bank_economic_capital_min` | Policy line plus MTM/capital | Are rate hikes damaging bank capital through bonds? |

### 10. Banking System

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `banks_alive`, `n_bank_failures`, `bank_capital`, `bank_leverage`, `bank_size_gini`, `bank_loanbook_hhi`, `bank_rate_spread_sd`, `bank_reserves_total`, `cb_reserves`, `interbank_rate`, `interbank_volume`, `interbank_contagion_loss`, `peak_intraday_overdraft`, `payments_gridlocked`, `bank_deposit_hhi`, `bank_births`, `bank_deaths`, `bank_equity_total`, `bank_equity_gini`, `bank_deposit_flight`, `bank_fear`, `bank_min_price_peak`, `bank_stock_turnover`, `bank_bond_face`, `bank_economic_capital_min` | Bank count, capital, leverage, concentration, reserves, interbank, runs, bank equity, and bond-duration exposure. |
| Derivable from CSV | `bank_failure_rate`, `bank_entry_exit_net`, `bank_capital_to_assets`, `loanbook_per_bank`, `reserves_per_bank`, `interbank_spread_to_policy`, `deposit_flight_to_deposits`, `bank_bond_share_of_assets` | Sector health, competition, and stress transforms. |
| Add from current state | `bank_capital_min`, `bank_capital_median`, `bank_economic_capital_total`, `bank_economic_capital_median`, `bank_reserve_min`, `bank_reserve_median`, `bank_deposit_total`, `bank_deposit_p90_p10`, `bank_roe_mean`, `bank_roe_dispersion`, `run_intensity_mean`, `lolr_recipient_count`, `duration_exposure_max`, `large_exposure_usage_max` | Current bank list, owner maps, loan books, reserves, and run state can expose cross-bank distribution and fragility. |
| Requires future extension | `liquidity_coverage_ratio`, `net_stable_funding_ratio`, `nonperforming_loan_ratio`, `deposit_insurance_fund`, `bank_resolution_cost` | Requires richer regulatory/liquidity and resolution mechanics. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `banks_alive` | Already recorded | Sector population. |
| 2 | `bank_births` | Already recorded | Entry flow. |
| 3 | `bank_deaths` | Already recorded | Exit flow. |
| 4 | `n_bank_failures` | Already recorded | Cumulative failures. |
| 5 | `bank_capital` | Already recorded | Book capital stock. |
| 6 | `bank_economic_capital_min` | Already recorded when bonds on | Worst mark-to-market solvency. |
| 7 | `bank_leverage` | Already recorded | Aggregate leverage. |
| 8 | `bank_size_gini` | Already recorded | Bank-size inequality. |
| 9 | `bank_loanbook_hhi` | Already recorded | Loan concentration. |
| 10 | `bank_deposit_hhi` | Already recorded | Deposit concentration. |
| 11 | `bank_rate_spread_sd` | Already recorded | Loan-rate competition dispersion. |
| 12 | `bank_reserves_total` | Already recorded | Settlement liquidity. |
| 13 | `peak_intraday_overdraft` | Already recorded | Intraday reserve stress. |
| 14 | `interbank_rate` | Already recorded | Interbank funding price. |
| 15 | `interbank_volume` | Already recorded | Interbank funding quantity. |
| 16 | `interbank_contagion_loss` | Already recorded | Failure cascade loss. |
| 17 | `bank_deposit_flight` | Already recorded | Run flight volume. |
| 18 | `bank_fear` | Already recorded | Systemic run panic. |
| 19 | `bank_min_price_peak` | Already recorded | Worst bank-stock distress. |
| 20 | `bank_bond_face` | Already recorded | Bank bond exposure. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Bank Population | `banks_alive`, `bank_births`, `bank_deaths`, `n_bank_failures` | Count line plus entry/exit bars | Is the banking sector stable or churning? |
| 2. Capital And Solvency | `bank_capital`, `bank_economic_capital_min`, `bank_leverage` | Capital lines and leverage | Are banks solvent after market-value losses? |
| 3. Concentration | `bank_size_gini`, `bank_loanbook_hhi`, `bank_deposit_hhi` | Bounded concentration lines | Is banking becoming too concentrated? |
| 4. Credit Competition | `bank_rate_spread_sd`, `bank_loanbook_hhi` | Spread dispersion plus HHI | Is price competition changing market share? |
| 5. Reserve Liquidity | `bank_reserves_total`, `peak_intraday_overdraft`, `payments_gridlocked` | Reserve line plus stress markers | Are banks liquid enough to settle payments? |
| 6. Interbank Market | `interbank_rate`, `interbank_volume`, `interbank_contagion_loss` | Rate/volume/loss panel | Is interbank funding stabilizing or spreading losses? |
| 7. Run Dynamics | `bank_deposit_flight`, `bank_fear`, `bank_min_price_peak` | Flight line, fear line, distress line | Are runs driven by fear and market distress? |
| 8. Bond Exposure | `bank_bond_face`, `bond_mtm_pnl`, `bank_economic_capital_min` | Exposure line plus MTM/capital | Are bond books threatening solvency? |
| 9. Bank Ownership | `bank_equity_total`, `bank_equity_gini`, `bank_stock_turnover` | Equity value/concentration/turnover | Are bank profits and ownership concentrated? |

### 11. Securities And Asset Markets

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `stock_price`, `market_cap`, `book_value`, `fundamental_ps`, `bubble_gap`, `tobin_q`, `equity_trend`, `equity_turnover`, `hh_wealth_gini_incl_equity`, `equity_wealth_share`, `dividend_yield`, `shares_outstanding`, `equity_market_cap`, `tobin_q_mean`, `tobin_q_dispersion`, `n_firms_q_above_1`, `share_price_dispersion`, `equity_ownership_gini`, `investment_q_corr`, `shares_conservation_drift`, `equity_raised`, `shares_outstanding_total`, `bonds_outstanding`, `bond_book_total`, `bond_market_total`, `bond_mtm_pnl`, `hh_bond_wealth`, `bank_bond_face`, `gov_interest_bill` | Equity valuation, turnover, ownership, issuance, investment-q link, share conservation, bond face/book/market, and coupon flows. |
| Derivable from CSV | `stock_return`, `market_cap_to_output`, `price_to_book`, `bond_market_to_face`, `bond_discount`, `bond_return`, `equity_turnover_value`, `bond_share_of_gov_debt`, `dividend_payout_ratio` | Asset-return, valuation, duration-discount, and market-depth transforms. |
| Add from current state | `hh_bond_market_value`, `bank_bond_market_value`, `bond_owner_share_households`, `bond_owner_share_banks`, `bond_owner_share_cb`, `bond_duration_weighted`, `bond_maturity_weighted`, `bond_yield_to_maturity`, `share_price_p10`, `share_price_p50`, `share_price_p90`, `equity_wealth_top10_share`, `order_buy_pressure`, `order_sell_pressure` | Bond lots, per-firm stocks, and order books can expose ownership, duration, yields, and price-distribution details. |
| Requires future extension | `secondary_bond_turnover`, `short_interest`, `bid_ask_spread`, `market_depth`, `options_open_interest`, `mutual_fund_flows`, `foreign_security_holdings` | Requires secondary-market microstructure, derivatives, funds, shorting, or open economy. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `stock_price` | Already recorded in aggregate equity mode | Equity price level. |
| 2 | `market_cap` | Already recorded in aggregate equity mode | Aggregate equity value. |
| 3 | `book_value` | Already recorded in aggregate equity mode | Accounting value anchor. |
| 4 | `tobin_q` | Already recorded in aggregate equity mode | Market-to-book valuation. |
| 5 | `bubble_gap` | Already recorded | Valuation gap. |
| 6 | `dividend_yield` | Already recorded | Cash return on equity. |
| 7 | `equity_turnover` | Already recorded | Trading activity. |
| 8 | `equity_raised` | Already recorded in per-firm mode | Equity finance into firms. |
| 9 | `tobin_q_dispersion` | Already recorded in per-firm mode | Cross-firm valuation spread. |
| 10 | `investment_q_corr` | Already recorded in per-firm mode | Financial-to-real investment channel. |
| 11 | `equity_wealth_share` | Already recorded | Equity importance in household wealth. |
| 12 | `equity_ownership_gini` | Already recorded | Ownership concentration. |
| 13 | `bonds_outstanding` | Already recorded | Government security face value. |
| 14 | `bond_book_total` | Already recorded | Historical-cost bond value. |
| 15 | `bond_market_total` | Already recorded | Market-value bond stock. |
| 16 | `bond_mtm_pnl` | Already recorded | Mark-to-market duration gain/loss. |
| 17 | `hh_bond_market_value` | Add from bond lots | Household bond wealth for portfolios. |
| 18 | `bank_bond_face` | Already recorded | Bank bond exposure. |
| 19 | `gov_interest_bill` | Already recorded | Coupon flow from bond market. |
| 20 | `shares_conservation_drift` | Already recorded | Share-accounting integrity. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Equity Valuation | `stock_price`, `market_cap`, `book_value`, `tobin_q` | Price/value lines plus q | Are stocks priced near fundamentals? |
| 2. Bubble And Yield | `bubble_gap`, `dividend_yield`, `equity_trend` | Gap line, yield line, trend line | Is equity return coming from cash flow or bubble momentum? |
| 3. Trading And Issuance | `equity_turnover`, `equity_raised` | Turnover line plus issuance bars | Is the market trading and funding firms? |
| 4. Per-Firm Valuation Spread | `tobin_q_mean`, `tobin_q_dispersion`, `n_firms_q_above_1` | Mean/dispersion/share lines | Are valuations broad or concentrated? |
| 5. Finance-To-Investment Channel | `investment_q_corr`, `equity_raised`, `investment_units` | Correlation line plus flows | Does market valuation guide real investment? |
| 6. Equity Ownership | `equity_wealth_share`, `equity_ownership_gini`, `hh_wealth_gini_incl_equity` | Share/concentration lines | Is equity concentrating household wealth? |
| 7. Bond Stock Values | `bonds_outstanding`, `bond_book_total`, `bond_market_total` | Face/book/market lines | Do face, book, and market values diverge? |
| 8. Duration Losses | `policy_rate`, `bond_mtm_pnl`, `bank_bond_face` | Rate and MTM/carry exposure | Are rate moves creating bond losses? |
| 9. Bond Income And Ownership | `gov_interest_bill`, `hh_bond_market_value`, `bank_bond_face` | Coupon flow plus owner stocks | Who receives and bears government security exposure? |

### 12. Firm Structure And Competition

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `firm_count_c`, `births`, `deaths`, `writeoffs`, `n_zombies`, `n_firms_producing`, `n_firms_selling`, `firm_size_gini_output`, `firm_size_top_share_output`, `firm_deposits_gini`, `firm_deposits_max`, `firm_attractiveness_gini`, `firm_size_pareto_slope`, `avg_markup`, `markup_std`, `price_cv`, `bank_loanbook_hhi` | Firm demographics, concentration, size distribution, zombies, pricing dispersion, and credit concentration. |
| Derivable from CSV | `entry_rate`, `exit_rate`, `net_entry`, `zombie_share`, `active_producer_share`, `active_seller_share`, `output_per_firm`, `output_per_active_firm`, `sales_per_active_firm`, `markup_cv`, `birth_death_ratio` | Rates and per-firm transforms. |
| Add from current state | `firm_revenue_gini`, `firm_profit_gini`, `market_share_hhi_sales`, `market_share_hhi_output`, `top_firm_sales_share`, `top_firm_output_share`, `sector_count_C`, `sector_count_K`, `firm_age_mean`, `firm_age_p90`, `profit_rate_mean`, `profit_rate_dispersion`, `cash_constrained_firm_share`, `labor_rationed_firm_share` | Current firm arrays can expose revenue/profit concentration, sector structure, and constraint breadth; ages require adding birth tick. |
| Requires future extension | `merger_count`, `acquisition_count`, `product_variety_count`, `sectoral_entry_barriers`, `antitrust_intervention_count` | Requires M&A, product categories, and policy interventions. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `firm_count_c` | Already recorded | Number of consumption firms. |
| 2 | `births` | Already recorded | Entry flow. |
| 3 | `deaths` | Already recorded | Exit flow. |
| 4 | `entry_rate` | Derivable from CSV | Scale-adjusted entry. |
| 5 | `exit_rate` | Derivable from CSV | Scale-adjusted exit. |
| 6 | `n_zombies` | Already recorded | Insolvent-firm overhang. |
| 7 | `zombie_share` | Derivable from CSV | Zombie breadth. |
| 8 | `n_firms_producing` | Already recorded | Active production count. |
| 9 | `active_producer_share` | Derivable from CSV | Production breadth. |
| 10 | `n_firms_selling` | Already recorded | Active seller count. |
| 11 | `active_seller_share` | Derivable from CSV | Market participation breadth. |
| 12 | `firm_size_gini_output` | Already recorded | Output concentration. |
| 13 | `firm_size_top_share_output` | Already recorded | Top-firm output share. |
| 14 | `firm_size_pareto_slope` | Already recorded when Gibrat on | Tail-shape diagnostic. |
| 15 | `firm_deposits_gini` | Already recorded | Financial resource concentration. |
| 16 | `firm_deposits_max` | Already recorded | Largest firm cash endpoint. |
| 17 | `avg_markup` | Already recorded | Average pricing power. |
| 18 | `markup_std` | Already recorded | Pricing-power dispersion. |
| 19 | `price_cv` | Already recorded | Price competition dispersion. |
| 20 | `firm_attractiveness_gini` | Already recorded when Gibrat on | Demand-attractiveness concentration. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Firm Population | `firm_count_c`, `births`, `deaths`, `net_entry` | Count line plus entry/exit bars | Is the firm sector renewing or shrinking? |
| 2. Entry/Exit Rates | `entry_rate`, `exit_rate` | Rate lines | Are demographics stable after scale changes? |
| 3. Zombie Overhang | `n_zombies`, `zombie_share`, `writeoffs` | Zombie lines plus writeoff bars | Are insolvent firms lingering or exiting? |
| 4. Activity Breadth | `n_firms_producing`, `active_producer_share`, `n_firms_selling`, `active_seller_share` | Counts and shares | Is activity broad-based? |
| 5. Output Concentration | `firm_size_gini_output`, `firm_size_top_share_output`, `firm_size_pareto_slope` | Concentration lines | Is production becoming winner-take-all? |
| 6. Financial Concentration | `firm_deposits_gini`, `firm_deposits_max` | Gini plus max cash | Is cash concentrating in a few firms? |
| 7. Pricing Competition | `avg_markup`, `markup_std`, `price_cv` | Markup/price dispersion | Is competition compressing or widening prices? |
| 8. Attractiveness Dynamics | `firm_attractiveness_gini`, `firm_size_gini_output` | Paired concentration lines | Does demand attractiveness translate into size concentration? |
| 9. Constraint Breadth | `cash_constrained_firm_share`, `labor_rationed_firm_share` | Bounded share lines | Are firms limited by finance or labor? |

### 13. Inequality And Distributional Structure

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `income_gini`, `consumption_gini`, `hh_wealth_gini`, `hh_wealth_top10_share`, `hh_wealth_cv`, `hh_networth_gini`, `hh_full_networth_gini`, `hh_full_networth_top10`, `equity_ownership_gini`, `equity_wealth_share`, `bank_equity_gini`, `firm_deposits_gini`, `firm_size_gini_output`, `firm_size_top_share_output`, `firm_attractiveness_gini`, `bank_size_gini`, `bank_loanbook_hhi`, `bank_deposit_hhi` | Existing household, firm, bank, equity, income, consumption, and deposit concentration metrics. |
| Derivable from CSV | `income_consumption_gini_gap`, `wealth_income_gini_gap`, `top10_to_bottom10_consumption_ratio`, `deposit_top10_gap`, `firm_top_share_gap`, `concentration_composite_index` | Cross-distribution and composite inequality diagnostics. |
| Add from current state | `income_top10_share`, `consumption_top10_share`, `consumption_p10_p50_p90`, `income_p10_p50_p90`, `household_debt_gini`, `household_debt_top10_share`, `bond_wealth_gini`, `bond_wealth_top10_share`, `labor_sold_gini`, `wage_gini`, `full_networth_p10_p50_p90`, `ownership_overlap_top10` | Current household/firm/bond/labor states can expose richer quantiles and ownership overlaps. |
| Requires future extension | `inequality_by_age`, `inequality_by_skill`, `regional_inequality`, `intergenerational_mobility`, `racial_or_group_inequality` | Requires demographics, regions, groups, or family linkage. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `income_gini` | Already recorded | Income inequality. |
| 2 | `consumption_gini` | Already recorded | Consumption inequality. |
| 3 | `hh_wealth_gini` | Already recorded | Deposit-wealth inequality. |
| 4 | `hh_wealth_top10_share` | Already recorded | Deposit top share. |
| 5 | `hh_networth_gini` | Already recorded when household credit on | Net financial wealth inequality. |
| 6 | `hh_full_networth_gini` | Already recorded in margin mode | Full balance-sheet inequality. |
| 7 | `hh_full_networth_top10` | Already recorded | Full wealth top share. |
| 8 | `equity_ownership_gini` | Already recorded | Firm-equity ownership inequality. |
| 9 | `equity_wealth_share` | Already recorded | Equity weight in wealth inequality. |
| 10 | `bank_equity_gini` | Already recorded | Bank-equity ownership inequality. |
| 11 | `bond_wealth_gini` | Add from bond market values | Safe-asset ownership inequality. |
| 12 | `household_debt_gini` | Add from ledger debt | Debt concentration. |
| 13 | `share_underwater` | Already recorded | Lower-tail financial distress. |
| 14 | `firm_size_gini_output` | Already recorded | Firm output inequality. |
| 15 | `firm_size_top_share_output` | Already recorded | Top-firm output share. |
| 16 | `firm_deposits_gini` | Already recorded | Firm cash concentration. |
| 17 | `firm_attractiveness_gini` | Already recorded when Gibrat on | Demand-side firm inequality. |
| 18 | `bank_size_gini` | Already recorded | Bank size inequality. |
| 19 | `bank_loanbook_hhi` | Already recorded | Bank credit concentration. |
| 20 | `bank_deposit_hhi` | Already recorded | Bank deposit concentration. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Income Vs Consumption Inequality | `income_gini`, `consumption_gini`, `income_consumption_gini_gap` | Paired Gini lines | Is consumption smoothing income inequality? |
| 2. Household Wealth Inequality | `hh_wealth_gini`, `hh_wealth_top10_share`, `hh_networth_gini`, `hh_full_networth_gini` | Bounded lines | How does inequality change from deposits to full net worth? |
| 3. Top Wealth Control | `hh_full_networth_top10`, `full_networth_p10_p50_p90` | Top-share line plus quantile fan | Is wealth growth broad or top-heavy? |
| 4. Asset Ownership Channels | `equity_ownership_gini`, `bank_equity_gini`, `bond_wealth_gini` | Concentration lines | Which asset class drives ownership inequality? |
| 5. Debt Inequality And Distress | `household_debt_gini`, `share_underwater`, `share_margin_underwater` | Debt concentration plus distress lines | Is inequality coming through debt burdens? |
| 6. Firm Inequality | `firm_size_gini_output`, `firm_size_top_share_output`, `firm_deposits_gini` | Firm concentration lines | Is market structure becoming concentrated? |
| 7. Bank Concentration | `bank_size_gini`, `bank_loanbook_hhi`, `bank_deposit_hhi` | Bounded concentration lines | Are financial intermediaries concentrating? |
| 8. Composite Distribution Heatmap | selected Ginis/top shares | Heatmap across categories | Which inequality channel is most stressed by version/run? |

### 14. Stability And Risk

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `conservation_drift`, `shares_conservation_drift`, `unemployment_rate`, `unsatisfied_demand_ratio`, `inflation`, `writeoffs`, `n_zombies`, `deaths`, `bank_insolvent`, `bank_economic_capital_min`, `banks_alive`, `n_bank_failures`, `bank_fear`, `bank_deposit_flight`, `peak_intraday_overdraft`, `payments_gridlocked`, `interbank_contagion_loss`, `bond_mtm_pnl`, `margin_deleveraged`, `share_margin_underwater`, `hh_bankruptcies`, `gov_debt_to_gdp`, `debt_service_ratio` | Accounting, real-economy, price, default, bank, payment, bond, household, fiscal, and leverage risk. |
| Derivable from CSV | `reserve_conservation_drift`, `inflation_volatility`, `output_drawdown`, `recession_flag`, `bank_failure_rate`, `default_rate`, `crisis_duration`, `risk_composite_index`, `stress_regime_label` | Cross-series stress transforms and regime labels. |
| Add from current state | `security_identity_drift`, `negative_capital_bank_count`, `near_failure_bank_count`, `reserve_floor_breach_share`, `cash_constrained_firm_share`, `labor_rationed_firm_share`, `household_underwater_share`, `systemic_crisis_flag`, `max_bank_run_intensity`, `payment_blocked_value` | Current hard gates and agent state can expose fragility before failure. |
| Requires future extension | `bankruptcy_cascade_graph`, `supply_chain_failure_count`, `fire_sale_price_impact`, `depositor_loss_rate`, `deposit_insurance_loss`, `macro_stress_test_loss` | Requires network exposures, supply chains, fire-sale pricing, insurance, or stress-test engines. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `conservation_drift` | Already recorded | Core accounting safety gate. |
| 2 | `reserve_conservation_drift` | Derivable/add from reserve state | Reserve-layer accounting gate. |
| 3 | `shares_conservation_drift` | Already recorded | Equity-share accounting gate. |
| 4 | `real_output_growth` | Already recorded | Recession momentum. |
| 5 | `output_drawdown` | Derivable from CSV | Depth from previous peak. |
| 6 | `unemployment_rate` | Already recorded | Labor-market stress. |
| 7 | `unsatisfied_demand_ratio` | Already recorded | Goods-market stress. |
| 8 | `inflation_volatility` | Derivable from CSV | Price-instability stress. |
| 9 | `bank_economic_capital_min` | Already recorded when bonds on | Worst bank solvency. |
| 10 | `banks_alive` | Already recorded | Banking-sector survival. |
| 11 | `n_bank_failures` | Already recorded | Banking failure count. |
| 12 | `bank_fear` | Already recorded | Run panic. |
| 13 | `bank_deposit_flight` | Already recorded | Run flow. |
| 14 | `peak_intraday_overdraft` | Already recorded | Payment-liquidity stress. |
| 15 | `payments_gridlocked` | Already recorded | Payment blockage. |
| 16 | `interbank_contagion_loss` | Already recorded | Interbank cascade loss. |
| 17 | `writeoffs` | Already recorded | Credit-loss realization. |
| 18 | `n_zombies` | Already recorded | Insolvent-firm overhang. |
| 19 | `bond_mtm_pnl` | Already recorded | Duration-loss stress. |
| 20 | `share_margin_underwater` | Already recorded | Household balance-sheet distress. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Accounting Gates | `conservation_drift`, `reserve_conservation_drift`, `shares_conservation_drift` | Log-scale drift lines | Are invariants intact? |
| 2. Real Stress | `real_output_growth`, `output_drawdown`, `unemployment_rate` | Growth and drawdown lines | Is the economy in recession stress? |
| 3. Market Friction Stress | `unsatisfied_demand_ratio`, `inflation_volatility` | Stress lines | Are goods or prices unstable? |
| 4. Bank Solvency | `bank_economic_capital_min`, `banks_alive`, `n_bank_failures` | Capital line plus failure markers | Are banks failing or near failure? |
| 5. Run Stress | `bank_fear`, `bank_deposit_flight`, `bank_min_price_peak` | Fear/flight/distress lines | Are depositor runs building? |
| 6. Payment Stress | `peak_intraday_overdraft`, `payments_gridlocked`, `interbank_volume` | Overdraft/gridlock/funding panel | Is the payment system seizing? |
| 7. Contagion And Losses | `interbank_contagion_loss`, `writeoffs`, `bond_mtm_pnl` | Loss bars/lines | Where are losses coming from? |
| 8. Firm And Household Distress | `n_zombies`, `deaths`, `share_margin_underwater`, `hh_bankruptcies` | Distress lines and event bars | Is stress spreading to real agents? |
| 9. Composite Risk | `risk_composite_index`, `stress_regime_label` | Score line plus regime bands | When should a run be treated as crisis? |

### 15. Policy Effects And Transmission

CSV recording set:

| Status | Indicators | Purpose |
|---|---|---|
| Already recorded | `policy_rate`, `real_rate`, `inflation_ema`, `gov_deficit_to_gdp`, `gov_debt_to_gdp`, `gov_spending_share_of_gdp`, `tax_total`, `benefit_paid`, `jg_spending`, `jg_employment_rate`, `public_investment`, `public_capital`, `pubcap_factor`, `effective_unemployment`, `unemployment_rate`, `poverty_rate`, `bottom10_consumption`, `bank_economic_capital_min`, `omo_flow`, `lolr_advances`, `cb_absorbed`, `bank_loanbook_hhi` | Existing outcome series for fiscal, monetary, welfare, public-capital, banking, OMO, and LoLR policy channels. |
| Derivable from series/metadata | `policy_impulse`, `fiscal_multiplier_proxy`, `inflation_gap_to_target`, `cash_deficit_to_gdp`, `augmented_gov_spending_share_of_gdp` | Policy-intensity and mandate-gap transforms that need recorded series plus run metadata. |
| Derived from baseline comparison | `unemployment_change_vs_baseline`, `poverty_change_vs_baseline`, `output_change_vs_baseline`, `inflation_change_vs_baseline`, `bank_survival_change_vs_baseline`, `welfare_gain_vs_baseline` | Cross-version/cross-run comparisons in the Streamlit tool. |
| Add from current policy/config state | `tax_profit_rate`, `tax_income_rate`, `tax_consumption_rate`, `tax_wealth_rate`, `benefit_replacement`, `gov_deficit_target`, `gov_consumption_share`, `gov_investment_share`, `min_wage`, `job_guarantee_enabled`, `jg_wage_ratio`, `inflation_target`, `taylor_phi_pi`, `taylor_phi_u`, `rate_inertia`, `omo_reserve_target`, `omo_drain_frac`, `lolr_enabled`, `bank_target_capital_ratio`, `bank_exposure_limit`, `bond_finance_frac`, `bond_theta`, `bank_bond_appetite` | Policy levers must be recorded beside outcomes so comparisons are interpretable. |
| Requires future extension | `counterfactual_baseline_id`, `randomized_policy_experiment_id`, `policy_rule_switch_log`, `welfare_weighted_policy_score`, `distributional_incidence_by_group` | Requires experiment metadata, policy regime logs, and demographic/group structure. |

Default 20 figure indicators:

| # | Indicator | Status | Why It Belongs In Figures |
|---:|---|---|---|
| 1 | `policy_rate` | Already recorded | Monetary stance. |
| 2 | `real_rate` | Already recorded | Real monetary stance. |
| 3 | `inflation_gap_to_target` | Derive from series + metadata | Price-stability policy error. |
| 4 | `cash_deficit_to_gdp` | Derive after `cash_deficit` exists | Broad fiscal impulse scale. |
| 5 | `gov_debt_to_gdp` | Already recorded | Fiscal sustainability context. |
| 6 | `augmented_gov_spending_share_of_gdp` | Derive after `augmented_gov_spending` exists | Broad public-sector footprint. |
| 7 | `tax_total` | Already recorded | Fiscal drain. |
| 8 | `benefit_paid` | Already recorded | Transfer channel. |
| 9 | `jg_spending` | Already recorded | Job-guarantee fiscal channel. |
| 10 | `jg_employment_rate` | Already recorded | Employment-buffer channel. |
| 11 | `public_investment` | Already recorded | Public-capital flow. |
| 12 | `public_capital` | Already recorded | Public-capital stock. |
| 13 | `pubcap_factor` | Already recorded | Productivity transmission. |
| 14 | `effective_unemployment` | Already recorded | Labor/welfare policy outcome. |
| 15 | `unemployment_rate` | Already recorded | Private labor-market outcome. |
| 16 | `poverty_rate` | Already recorded | Distributional outcome. |
| 17 | `bottom10_consumption` | Already recorded | Lower-tail welfare outcome. |
| 18 | `bank_economic_capital_min` | Already recorded when bonds on | Financial-stability outcome. |
| 19 | `omo_flow` | Already recorded | Quantity-policy impulse. |
| 20 | `lolr_advances` | Already recorded | Emergency-liquidity support. |

Visualization design:

| Panel | Metrics | Chart Form | Diagnostic Question |
|---|---|---|---|
| 1. Monetary Policy Transmission | `policy_rate`, `real_rate`, `inflation_gap_to_target`, `unemployment_rate` | Rate lines plus mandate gaps | Is monetary policy stabilizing inflation or raising slack? |
| 2. Fiscal Impulse | `cash_deficit_to_gdp`, `augmented_gov_spending_share_of_gdp`, `tax_total` | Deficit/share lines plus tax drain | How strong is fiscal demand support? |
| 3. Fiscal Sustainability | `gov_debt_to_gdp`, `gov_interest_bill`, `cash_deficit_to_gdp` | Debt and deficit lines | Is policy accumulating unsustainable debt pressure? |
| 4. Welfare Policy | `benefit_paid`, `poverty_rate`, `bottom10_consumption` | Transfer line plus welfare outcomes | Do transfers reach the bottom tail? |
| 5. Job Guarantee | `jg_spending`, `jg_employment_rate`, `effective_unemployment` | JG area plus unemployment line | Does public employment absorb slack? |
| 6. Public Capital | `public_investment`, `public_capital`, `pubcap_factor` | Flow, stock, productivity factor | Does public investment raise productive capacity? |
| 7. OMO/QT Transmission | `omo_flow`, `cb_absorbed`, `bank_reserves_total`, `interbank_rate` | Flow bars plus reserve/rate lines | Does reserve draining activate interbank transmission? |
| 8. LoLR And Stability | `lolr_advances`, `bank_economic_capital_min`, `banks_alive` | Support line plus stability outcomes | Does emergency liquidity prevent solvent-bank failure? |
| 9. Cross-Version Effects | selected outcome deltas vs baseline | Small multiple overlays by run/version | Which policy package improves welfare without destabilizing banks? |

## Cross-Category Implementation Notes

- Prefer canonical metric aliases in the refactor. Existing names such as
  `hh_wealth_gini` mostly mean deposit-only wealth, so the visualization layer
  should expose/label them as `hh_deposit_gini` while preserving backward
  compatibility.
- Keep face, book, and market values separate. In particular, existing
  `hh_bond_wealth` is face-value holdings from the bond index, not market-value
  household wealth. Add `hh_bond_face` and `hh_bond_market_value`.
- Normalize aggregate/per-firm equity names. Current aggregate equity uses
  `market_cap`, `book_value`, and `tobin_q`; per-firm equity uses
  `equity_market_cap`, `tobin_q_mean`, and related columns. The visualization
  schema should provide canonical `equity_market_cap`, `equity_book_value`, and
  `equity_tobin_q`.
- Treat current fiscal `gov_spending` and `gov_deficit` carefully: they do not
  fully include public investment and bond interest in every context. Add or
  derive `augmented_gov_spending` and `cash_deficit` for broad fiscal-balance
  charts.
- Distinguish nominal public flows from real public quantities. `gov_consumption`
  and `public_investment` are nominal flows; real public consumption and public
  capital units need explicit quantity bookkeeping.
- Separate private labor slack from policy-buffered slack. `unemployment_rate`
  is private firm-side unemployment; `effective_unemployment` is the better
  no-income unemployment measure when job guarantee is enabled.
- Generalize credit metrics. Current `new_loans` is firm-credit origination and
  current `debt_service_ratio` omits some household principal/margin flows. Add
  `new_loans_total` and `total_debt_service_ratio`.
- Generalize household distress metrics. `hh_bankruptcies` is currently emitted
  inside the government metrics block even though the mechanism lives in the
  margin/equity bankruptcy path; it should be recorded unconditionally when the
  mechanism is enabled.
- Record policy/config levers alongside outcomes for cross-version comparison:
  fiscal tax/spending rates, Taylor-rule coefficients, OMO settings, LoLR switch,
  bond-finance settings, and bank regulatory settings.
- Feature-gated metrics should have stable schema behavior. The CSV/export layer
  should prefer consistent columns with `NaN` or explicit disabled flags over
  silently absent columns when comparing versions.
