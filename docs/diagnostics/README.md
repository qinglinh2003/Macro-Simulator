# Economic Diagnostic Suite

This suite keeps three forms of evidence separate: simulated economic time series,
same-seed policy or mechanism experiments, and external observations with explicit
source and vintage metadata. Its purpose is to establish whether a symptom is real,
then narrow it to a mechanism or code boundary. It must not turn a single stochastic
path, an abstract-unit level difference, or a known-invalid legacy metric into an
empirical claim.

For the current v23 findings and handoff state, read
[`V23_FINDINGS_20260714.md`](./V23_FINDINGS_20260714.md).

## Quick start

Run these commands from the worktree root:

```bash
uv run macro-diagnostics \
  --profile smoke \
  --matrix causal \
  --workers 10 \
  --output-dir artifacts/diagnostics/v23-smoke

uv run macro-diagnostics \
  --profile audit \
  --matrix causal \
  --seeds 5 \
  --intervention-replicates 3 \
  --workers 10 \
  --output-dir artifacts/diagnostics/v23-causal-replicated

uv run macro-diagnostics \
  --profile audit \
  --matrix root-causes \
  --workers 10 \
  --output-dir artifacts/diagnostics/v23-root-causes
```

Use `smoke` to verify collectors and causal pairing. Use `audit` for mechanisms
that need longer adjustment, including firm exit, bank failure, and capital
formation. Reserve `production` and `soak` for final validation. Every output
directory must be new and empty so that artifacts from separate runs cannot mix.

The default causal matrix contains five baseline seeds and one arm each for a rate
cut, rate hike, energy shock, credit tightening, and fiscal expansion: ten jobs in
total. With `--intervention-replicates 3`, every intervention is replicated over
the first three baseline seeds, producing five baselines plus fifteen arms. The
allowed range is `1..seeds`, and each arm is compared only with its same-seed
baseline.

The root-cause matrix uses one common seed and separately removes JG capital, the
job guarantee, government investment, public-capital productivity, the full public
capital system, exogenous TFP, persistent labor matching, lifecycle consumption,
and bank capital limits. These are permanent structural ablations, not temporary
policy shocks. Some arms, such as `spot_labor` and `no_public_capital_system`,
deliberately remove a bundle of dependent mechanisms. The report therefore labels
this matrix `exploratory_single_seed`: it generates candidates for narrower,
multi-seed experiments and does not identify a unique root cause by itself.

The runner caps independent worker processes at ten and forces BLAS thread counts to
one per process. This avoids turning ten jobs into ten nested thread pools.

## Direct monetary-transmission frontier

`monetary_direct_transmission` is off by default and enabled on the diagnostic
frontier. When off, investment, consumption, and credit use the historical branches;
the new decision functions are not called and consume no additional random numbers.
When enabled, three direct channels use the same per-tick rate clock:

- Firm investment defines expected real loan user cost as
  `max(floor, loan_rate - committed_expected_inflation + depreciation)` and compares
  it with `neutral_loan_rate - inflation_target + depreciation`. The default
  elasticity is `0.5`, and the target-investment multiplier is bounded to
  `[0.5, 1.5]`. Expected inflation reads only a previously committed lag/EMA; it
  never invokes metric collection or reads the current tick's price.
- Indebted households retain the original desired-consumption plan. The cash reserve
  is applied only at the goods-order boundary, after wages, household credit, and
  family transfers have reached live deposits. The order cap is
  `min(desired_budget, max(0, live_deposits - scheduled_service))`. This reservation
  does not move cash; principal and interest are posted exactly once in the following
  debt-service phase.
- Firm credit adds a DSCR edge alongside leverage and bank-capital constraints:
  `expected operating cash flow / ((amort + loan_rate) * post-loan debt) >= 1.25`.
  Expected operating cash flow is currently expected sales less planned wages and
  expected energy input. `firm_credit_dscr_allowed/shortfall/constrained` expose the
  proxy and its binding strength. Holding other state fixed, a higher rate can only
  weakly reduce the credit grant.

Two older couplings are also corrected only on this frontier. Rental investors no
longer treat the policy or loan rate as a deposit return: household cash has zero
contractual nominal return, while an existing household-held interest-bearing
government bond may provide a safe-asset comparator. Bank and per-firm equity
valuation use
`max(valuation_discount_floor, policy_rate + valuation_risk_premium)` per tick. The
default risk premium is `1.34e-4/tick`; this replaces the daily-inconsistent
`max(rate, 0.01)` and removes the discontinuity that previously set the
residual-income premium to zero exactly at a zero policy rate.

Important limits remain. Loans have no fixed/floating vintage, maturity, or reset
date, so all outstanding debt still reads the live rate. There is no contractual
deposit interest and therefore no net-saver Euler or target-wealth substitution
channel. Investment user cost has no expected relative capital-goods price. DSCR
uses a planning proxy rather than a complete cash-flow forecast. Mortgages retain
their separate stressed-DSTI and collateral-capital constraints. Local derivative
signs must not be extrapolated into an unconditional aggregate-output response.

## Capital-service-pricing frontier

`capital_service_pricing` is off by default and enabled on the diagnostic frontier.
It adds the following long-run unit cost to consumption, capital-goods, and energy
firms:

```text
P_K * K_open * (delta_K + marginal_loan_rate) / planned_output
```

`K_open` is the opening physical capital stock before depreciation. `P_K` is the
last committed capital-goods transaction unit value, held when there is no trade and
initialized from `p_kfirm0`. Both rates use the per-tick clock. Energy capacity also
depends on productive capital and cannot remain a free capacity input.

The term affects the long-run cost-plus quote only. It does not move cash and is not
deducted a second time in P&L. `firm_full_pnl` separately recognizes replacement-cost
depreciation and cash interest actually paid. The current implementation assumes zero
expected capital-goods price inflation; it does not substitute current CPI for a
capital-gain expectation. If planned output is zero, it retains the existing quote
fallback instead of dividing fixed cost by EPS, and reports the unallocated service
cost through diagnostic fields.

## Priced firm balance sheet and borrowing-base frontier

`priced_firm_balance_sheet` is off by default and enabled on the diagnostic frontier.
Genesis, firm entry, aggregate and per-firm equity, Tobin's q, return denominators,
and firm credit all read one nominal valuation helper. They no longer add physical
`Firm.capital` or inventory quantities directly to cash and debt.

Capital uses the last committed capital-goods unit value, held when there is no
trade and initialized from `p_kfirm0`. Finished goods and WIP use
`min(posted price, observable current unit replacement cost)` so that a firm cannot
expand net worth or credit merely by raising its quote. Energy input inventory uses
its recorded average acquisition cost. A shell firm with unavailable cost inputs
conservatively receives zero inventory value rather than an unauditable quote value.

The layer distinguishes three objects:

- replacement-cost book equity = cash + capital value + conservative inventory
  value - debt;
- eligible collateral = `(1 - capital_haircut) * capital_value +
  (1 - inventory_haircut) * inventory_value`;
- borrowing-base proxy = cash + eligible collateral - existing debt, combined with
  equity leverage, DSCR, bank supply, and RWA limits by taking the minimum.

Here, `haircut` is a deduction rate: a larger haircut means less capacity. Revaluation
changes observations and decision inputs only; it creates no deposits, cancels no
loans, and recognizes no cash profit. The relevant audit fields include
`firm_replacement_cost_capital_value`, `firm_priced_inventory_value`,
`firm_book_equity_priced`, `firm_eligible_collateral_value`,
`firm_borrowing_base_proxy/headroom`, and request-level borrowing-base
shortfall/constrained fields.

The word `proxy` is substantive. Default still lacks lien priority, seizure and sale,
bank recovery, and residual write-off journals. The suite must retain the high,
`known_scope_limit` finding `credit.collateral_recovery_missing` until that legal and
disposal layer exists. The current borrowing base cannot identify LGD.

## Evidence gates

Every dynamic run first passes a data-validity gate. Records and probes must be
complete for every tick, keep a stable field set, contain finite required values, and
match the requested horizon. Invalid data cannot enter attribution.

A temporary intervention must also satisfy all of the following:

- exactly one baseline matches an arm;
- seed, population, firm counts, bank count, and structural configuration match;
- response windows match;
- all pre-intervention record and probe summaries match value for value;
- the first-stage variable moves in the expected direction by at least its threshold.

Difference-in-differences is computed only after those checks pass. A single-seed
effect is exploratory; at least three valid pairs are required before promoting it to
replicated evidence. Static audit proves that a code structure exists, not its
dynamic magnitude.

Interpret `measurement_status` literally:

- `valid`: the metric directly supports the claim;
- `proxy`: it supports only a direction or mechanism clue;
- `legacy_invalid` or `blocked_by_*`: the concept is defective and cannot calibrate a
  real-world level;
- `exploratory_single_seed`: the result has not been replicated across seeds.

## Run artifacts and measurement perimeter

The top-level output directory contains:

- `manifest.json`: source revision, dirty diff summary, configuration, Python and
  platform metadata, thread limits, and dependency-lock hash;
- `diagnostics.json`: structured findings, paired responses, ablation attribution,
  and open-economy identities;
- `REPORT.md`: sorted human-readable findings;
- `world_diagnostics.json`: bilateral trade, current account, NFA, valuation, and FX
  dealer identities;
- `runs/<name>/series.csv`: official model records;
- `runs/<name>/probes.csv`: additional root-cause probes;
- `runs/<name>/summary.json` and `findings.json`: per-run summaries and findings.

Probes deliberately separate quantities that are easy to conflate: inventory
quantity change versus revaluation, final demand versus legacy `nominal_output`, open
unemployment versus the JG buffer, credit requests versus borrower and bank-capital
shortfalls, public-capital flows versus stocks, and K-sector planned labor, actual
employment, and output.

The diagnostic frontier enables observation-only v23 national accounts. Growth,
output, and price findings prefer `real_gdp`, `nominal_gdp`,
`real_gdp_per_capita`, and `cpi_fixed_basket`. Legacy `real_output`,
`nominal_output`, and `price_index` remain for compatibility but are not authoritative
GDP or CPI measures.

Real production GDP uses one common base price per C, K, E, and builder sector rather
than storing a separate birth-date price for each firm. Entry after inflation
therefore cannot create real growth merely because an otherwise homogeneous entrant
has a newer price vintage. Fixed-basket CPI rebases every 365 accepted observations by
default. It accumulates actual household purchase quantities inside the window,
filters exited products at the boundary, includes surviving entrants with purchase
weight, and chain-links the new basket to the accepted old-basket level on that date.
Rebasing itself therefore does not create an inflation jump.

Unobserved expenditure scope remains in an explicit reconciliation residual rather
than disappearing. The income approach retains the legacy cash-income residual and
reports `output value - cash revenue` separately for C, K, E, housing, and other
sectors. Unsold inventory and builder WIP are positive accruals; sales of existing
assets such as old dwellings are negative accruals. Combining those entries with an
explicit cash-intermediate-input versus production-input adjustment produces accrued
GOS, accrued income, and the genuinely unexplained residual. Only the final
unexplained remainder is treated as an unknown accounting gap. The reconciliation
identity is an implementation gate back to the production anchor, not independent
validation by three autonomous accounts.

Economy-local trade journals add nominal exports and imports directly to expenditure
GDP. Real exports use the common C-sector base price and real imports use the
`goods:FXDEALER` item base price. Until service, tax, financial-intermediation,
imputed-housing, and non-consumption trade scopes are complete, `real_gdp` and
`nominal_gdp` remain registered as `proxy` and are suitable for growth comparisons,
not level calibration.

Stock/GDP ratios no longer call `today's GDP * 365` an annual observation without a
label. The first 364 accepted observations expose
`nominal_gdp_annualized_daily_run_rate` and
`credit_to_annualized_daily_gdp`. From observation 365 onward,
`nominal_gdp_trailing_365d`, `credit_to_trailing_365d_gdp`, and corresponding public
debt ratios use an actual rolling flow. `*_to_best_available_annual_gdp` and
`annual_gdp_ratio_uses_trailing_observations` distinguish the fallback from a full
window. Legacy `credit_to_gdp` is compatibility-only.

The frontier also enables `bank_realized_pnl` and `unified_bank_rwa`. Realized bank
P&L includes loan interest, bond coupons, interbank and external interest, and
recognized credit loss; dividends cannot exceed current positive income. Historical
presets keep this off for trajectory compatibility. Unified RWA puts ordinary firm
and consumer loans at 100% risk weight and mortgages at `mortgage_risk_weight` inside
one `capital / mortgage_min_capital_ratio` limit. Gross-loan leverage and
large-exposure limits remain additional constraints. Official fields include
`bank_rwa_total`, `bank_rwa_limit_total`, `bank_rwa_headroom_min`, and
`bank_rwa_capital_ratio_min`; deep probes report maximum utilization. A breach by the
existing stock closes new lending but does not imply forced asset sales.

The household-credit frontier enables `household_interest_arrears`. Opening arrears
and current accrued interest receive cash before ordinary consumption and mortgage
principal; margin principal remains in the equity margin-call phase. Unpaid interest
is a persistent Household memo stock, not ledger principal, a bank loan asset, or
RWA. Banks recognize only interest cash received. The hard bridge is:

```text
opening arrears + accrued interest
= cash paid + arrears extinguished + closing arrears
```

Principal write-off extinguishes memo arrears in proportion to
`principal reduction / principal before`; extinguishing arrears does not add another
bank credit loss.

Bank ownership and open-economy settlement follow explicit attribution boundaries.
With `bank_relationship_lock_in`, only debt-free borrowers choose a bank before their
first loan; a borrower with ordinary debt or a mortgage shadow returns to the same
lender for a top-up until real refinancing, repayment, or loan-sale cash legs exist.
Cross-border factor income is no longer charged to the first surviving bank in a
list. A government economy uses a Treasury/CB aggregate account; a no-government
economy uses an `EXTISSUER` aggregate liability account that may be negative.
`FXDEALER` settles reserves through neutral `CLEARING`, so bank ordering or failure
does not change the commercial-bank counterparty. Unpaid external interest remains
attributed by debtor-country x creditor-country, old arrears are paid before current
accrual, flows use transaction-time FX, and closing arrears use the closing rate.

## Current structural boundaries

These are persistent model-scope findings, not mechanisms completed by the current
patch set:

- **Fractional hours / single Job:** `LaborMarket.jobs` allows at most one private
  employer per person. A part-time incumbent cannot enter a second-job pool, so
  residual hours can flow to JG while private vacancies remain high. The job ladder
  transfers rather than combines contracts. Official records now expose
  underemployed heads and residual hours; the suite reports
  `labor.fractional_single_job_fragmentation` when they coexist with vacancies.
- **Typed loans / vintages:** each borrower's ledger principal is still one scalar.
  Consumer, mortgage, and margin obligations lack complete per-contract subledgers,
  and loans lack fixed/floating type, origination date, reset schedule, maturity, and
  contract arrears. Household interest arrears follow the Household account rather
  than a typed claim, so inheritance or household restructuring cannot transfer them
  with exact exposure attribution.
- **Deposit funding cost:** `interest_by_deposits` is a profit-distribution rule, not
  contractual account-level deposit interest. Bank P&L recognizes realized credit
  loss and wholesale interest legs but still lacks real deposit funding cost.
- **Collateral recovery:** the priced borrowing base constrains credit and exposes
  solvency, but default has no lien priority, seizure/sale, bank recovery, or
  conserving residual write-off journal.
- **Inventory COGS:** inventories are priced on the balance sheet, but the income
  statement expenses current production cash cost. It has no inventory-cost lots or
  weighted-average roll-forward and does not match COGS to current sales.
- **Aggregate external ownership:** `EXTISSUER`/Treasury and `CLEARING` remove
  arbitrary-bank coupling. External arrears retain country-pair attribution, but NFA
  principal, maturity, restructuring loss, and ultimate domestic owners are not yet
  allocated among households, firms, commercial banks, and sovereigns.

## Connecting real observed data

Observed-data CSV files must contain exactly these columns:

```text
metric_id,geography,period,frequency,value,unit,source,series_id,vintage,seasonal_adjustment,notes
```

`vintage` is the ISO date on which an observation was available, not the simulation
date. Every row retains source, original series ID, geography, frequency, unit, and
seasonal-adjustment status. A unit change inside a series is rejected. `latest`
selects the newest available vintage per period; a historical vintage enables
real-time-data replay.

Registered crosswalks are:

| Model metric | External series | Comparison | Limits |
|---|---|---|---|
| `real_gdp` | FRED `GDPC1` | quarterly SAAR log changes | `proxy`; abstract units and incomplete domestic-value-added scope, levels are not comparable |
| `nominal_gdp` | FRED `GDP` | quarterly SAAR log changes | `proxy`; basic-price and narrower model scope, growth paths only |
| `gdp_nominal_exports/imports/net_exports` | none | -- | economy-local basic-price cash journal; expenditure GDP includes it, but product scope is mainly consumption goods |
| `gdp_real_exports/imports/net_exports` | none | -- | fixed-price quantity journal; exports use the C base price and imports use the `goods:FXDEALER` item base price |
| `cpi_fixed_basket` | FRED `CPIAUCSL` | monthly means, both rebased to 100 | periodically rebased, chain-linked Laspeyres basket; product taxes are not yet in item journals |
| `cpi_fixed_basket_inflation_yoy` | raw FRED `CPIAUCSL` | adapter derives exact `CPI_t / CPI_t-12 - 1` | requires the exact same month one year earlier; no interpolation; model needs 365 prior observations |
| `real_output` | none | -- | compatibility proxy covering only consumption goods |
| `nominal_output` | none | -- | legacy pseudo-GDP, `legacy_invalid` |
| `price_index` / `inflation_yoy` | none | -- | transaction unit value contaminated by composition, `legacy_invalid` |
| `labor_u_rate` | FRED `UNRATE` | levels | `proxy`; JG and searching unemployment are separate, survey-status bridge incomplete |
| `person_unemployment_rate` | none | -- | population bridge subtracts only private employment and mechanically leaves JG on the unemployment side |
| `policy_rate` | FRED `FEDFUNDS` | levels | annual percentage divided by `100*365` to match the simple daily model rate |

Example:

```bash
uv run macro-empirical-diagnostics \
  --simulation-csv artifacts/diagnostics/v23-audit/runs/baseline_s0/series.csv \
  --observed-csv data/observed/us_macro_vintage.csv \
  --metric-id labor_u_rate \
  --tick-origin 0 \
  --burn-in-ticks 730 \
  --simulation-start-date 2000-01-01 \
  --geography USA \
  --source FRED \
  --series-id UNRATE \
  --seasonal-adjustment seasonally_adjusted \
  --vintage 2026-07-14 \
  --output-dir artifacts/diagnostics/empirical-unemployment
```

`simulation-start-date` labels the first retained post-burn tick, not model genesis.
The adapter validates the simulation CSV once: headers must be unique; ticks must be
strict integers, unique, and consecutive from `--tick-origin`; at least one row must
remain after `--burn-in-ticks`. Artifacts record raw and retained tick ranges, cutoff,
dropped rows, and mapped calendar range so that a genesis transient cannot silently
be relabeled as historical time.

Single-metric calls remain compatible. With one `--metric-id`, the selected data must
have exactly one `source/series/frequency/unit/seasonal_adjustment` provenance, and the
CLI still writes the schema-v1 `empirical_diagnostic.json` alias. Every call also
writes schema-v2 `empirical_diagnostics.json` and `REPORT.md`.

Batch mode accepts repeated `--metric-id` values, or no metric IDs to process every
unique provenance group for a geography. It validates the simulation CSV once and
then aligns each provenance group at its own frequency and vintage. Groups are never
concatenated. Missing model columns, unavailable vintages, or inadequate overlap are
recorded as `failed` or `skipped` while other groups continue. A failed group, no
successful groups, or a missing explicitly requested metric returns nonzero unless
the caller supplies `--allow-missing-requested`.

Outputs use stable ordering for series, findings, aligned periods, and vintages. Both
input files are SHA-256 checked before reading, after all groups, and after artifact
writing; a change during execution fails the diagnostic.

Schema v2 separates `inputs`, `input_integrity`, `request`, `summary`, aggregate
`findings`, and per-provenance `series`. A successful series contains its full
`diagnostic`, `classification`, structured symptom findings, and all aligned values.
Screening thresholds depend on transformed frequency: monthly series need at least
24 comparison observations; quarterly GDP log changes need at least 12 growth
observations, or 13 consecutive levels; the default for other domains is eight.
Aligned months, quarters, or years must be consecutive, and lags or differences never
cross a gap.

Screening always uses the registered comparison mode: GDP uses log changes, CPI
indices are rebased, and only ratio metrics use levels. A forced incompatible mode
may emit exploratory distance but is classified
`blocked_by_comparison_override`. Proxy metrics such as the current unemployment
bridge are explicitly marked `proxy_not_calibration`.

Every empirical finding carries `inference_scope=descriptive_non_causal`, measurement
status, caveats, evidence, thresholds, and routing IDs (`probe_ids`,
`root_cause_ids`, and `ablation_ids`). Those IDs route the next probe, pair, or
ablation; they are not causes inferred from path distance.

Daily flows aggregate by calendar sum, stocks take period end, and rates use their
registered mean or compounding rule. GDP SAAR crosswalks annualize only complete model
periods. Incomplete periods are dropped unless `--allow-partial-periods` is explicit.
Empirical CPI YoY does not average the model's daily trailing-365 field. Both model and
FRED form monthly CPI levels first, then derive exact same-month
`CPI_t / CPI_t-12 - 1`; missing current or lagged months are neither interpolated nor
bridged.

## Interpretation limits

The observed-data layer does not download, backfill, or guess observations. Data
acquisition, licensing, and vintage archiving remain the caller's responsibility.
Abstract model currency levels are not comparable with dollar levels, so GDP is
currently a growth-path comparison only. Although v23 metrics pass internal identity
and definition tests, they are not complete SNA/NIPA accounts: economy-local world net
exports are included, but the product boundary remains consumption-heavy and housing
and financial services are incomplete. Legacy headline fields are compatibility-only
and must not drive calibration.

The safe repair order is: fix hard identities and wrong couplings, correct measurement
definitions, confirm mechanism direction with paired experiments, and only then use
observed data to calibrate magnitudes. After every behavioral patch, write to a new
empty output directory and retain old reports as traceable evidence.
