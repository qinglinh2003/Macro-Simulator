# V23 Plan — Patch Consolidation

> **STATUS: EMPTY PLAN (2026-07-14).** Branch `feat/patches-v23` forked from dev@417ced3
> (v19 growth-foundation arc merged). Scope TBD — v23 is the patch-consolidation version:
> completing what earlier arcs left unfinished, not building new mechanisms.

## Scope

### Tier 1 — the price-index / nominal-anchor coupling (highest leverage, do first)

One measurement weakness feeds two separate major findings, so fixing it is the
prerequisite for re-testing the nominal anchor.

**Root cause.** `price_index = total_revenue / total_sales_u`
([metrics.py:218](../../macro_sim/reporting/metrics.py)) is a **unit-value index**: it
moves whenever the SALES MIX shifts (necessity vs luxury, firms at different price points),
even when no individual price changes. The Phillips autopsy measured ~70% of its variance
as composition, not price. And the central bank's Taylor input `_infl_ema` is built from
this same index ([central_bank.py:20-24](../../macro_sim/systems/central_bank.py)), so the
CB reacts to a composition-contaminated inflation signal.

This one index sits under two findings:
- **Phillips price-side failure** — the wage→price signal (wage Phillips is alive at −0.73)
  is drowned by composition noise in the price index.
- **v19 CB-deflation** — the audit showed the active Taylor CB is the deflation engine
  (frozen +0.17% vs headline −4.62% vs core −7.26%, none at π*); part of this may be the
  rule chasing a noisy unit-value inflation signal rather than true price change.

**Patch #1 — proper fixed-basket price index.** Replace the unit-value index with a
fixed-basket (Laspeyres/Paasche) index that holds the basket weights fixed so only PRICE
change moves it, not the mix. Pure observation change (no mechanism), flag-gated so
flag-off stays bit-identical. Expected to sharpen inflation, the CB's input, the
real-output deflator, and the Phillips price-side simultaneously.

**Then re-run the v19 nominal-anchor audit on the clean index.** If the CB still deflates
under a composition-free signal, escalate to:

**Patch #2 — nominal anchor fix (contingent on the re-audit).** The v19 audit named the
failure: the Taylor rule mistakes productivity / capital-deepening disinflation for demand
weakness. Candidate fixes — a nominal-GDP-level target, or a productivity-adjusted
inflation target — added as a CB-rule variant behind a flag (default off ⇒ bit-identical).
Scope this only after the re-audit shows a clean-index CB still misses π*.

Discipline: both patches flag-gated, default-off bit-identical (cumulative same-seed
digest), pre-register + refute, diagnostic per sub-stage.

### Tier 1 (second) — GDP omits everything except consumption

**Root cause.** `nominal_output = total_produced × price_index` where
`total_produced = sum(f.produced for f in c_firms)` ([metrics.py:196,1018](../../macro_sim/reporting/metrics.py))
— **only the CONSUMPTION sector**. Capital-goods (K) output, energy (E) output, and
government are all absent. Real national accounts have GDP = C + I + G (+NX); this model's
GDP is C alone.

**Why it is Tier 1 — it is not merely a reporting bias, it feeds BEHAVIOUR:**
- `capital_goods.py:54` — the government INVESTMENT budget is `gov_investment_share ×
  _prev_nominal_output`, so public investment is sized off the too-small denominator →
  public capital → the pubcap productivity factor → output.
- `goods.py:175` — the government CONSUMPTION target reads the same `_prev_nominal_output`.
- `policy.py:21` — the fiscal DEFICIT target is a share of "GDP", likewise mis-scaled.
- Every `*_to_gdp` ratio (credit, deficit, debt, gov spending, money velocity,
  debt-service) is biased UP by the missing denominator.
- It cascades into the GROWTH numbers: `real_output` and `per_capita_real_output` are
  C-only, so what v19 reported as "per-capita output growth" is really per-capita
  CONSUMPTION-GOODS output, excluding investment goods and energy.

**The irony:** the model already computes a cross-sector income-side measure —
`va = total_wagebill + max(0, total_profit)` ([metrics.py:1021](../../macro_sim/reporting/metrics.py))
— and never uses it as GDP.

**Patch #3 — a real GDP aggregate.** Define output properly (expenditure side C + I + G,
or the income-side value added the model already has) and route BOTH the `*_to_gdp` ratios
AND the three fiscal rules through it. This CHANGES BEHAVIOUR (the fiscal rules move), so
it is flag-gated with a default-off bit-identical path and needs its own acceptance:
re-check the fiscal ratios against their intended calibration once the denominator is right.

### Tier 1 (third) — the C sector is BLIND to unmet demand

**Root cause.** B2 updates expectations on `signal = firm.sales_prev + firm.rationed_prev`
([planning.py:57](../../macro_sim/behavior/planning.py)), and `rationed_prev` is populated
for **K-firms only** ([capital_goods.py:47](../../macro_sim/systems/capital_goods.py)).
E-firms got their own equivalent in v17
([energy.py:443-445](../../macro_sim/systems/energy.py)). **C-firms have neither** —
`goods.py` computes only an AGGREGATE `econ._unsat_ratio` gauge
([goods.py:207](../../macro_sim/systems/goods.py)) for reporting, never a per-firm signal.

**This is the exact bug that killed the K sector.** The B2 docstring says it outright: "a
stocked-out seller reads zero sales as zero demand and expectations spiral to extinction
(the K-sector deadlock)". Two arcs (v16-L6, v17) each independently rediscovered the disease
in their own sector and patched it locally; nobody generalised it to the LARGEST sector.

**Why C hasn't visibly died:** C-firms are large and household demand is broad and
persistent, so a C-firm rarely sits at zero sales long enough to spiral. Instead the bug
manifests as a CHRONIC DOWNWARD BIAS in demand expectations whenever demand is rationed —
i.e. exactly during stock-outs, energy shocks, and crises. C-firms cannot see the demand
they failed to serve, so they under-plan production, under-hire, and the recovery is
systematically under-powered; the low expectation is then self-fulfilling. Every
supply-shock experiment in the model (the v17 energy shocks, the crisis scenarios, and
plausibly the "demand-constrained mutes productivity" reading) carries this bias.

**Patch #4 — per-firm unmet-demand (footfall) signal for C-firms**, mirroring
`capital_goods.py:47`: split unfilled buy-order units across C-sellers into `rationed_demand`
(expectations only, never revenue). The order book already exists in `goods.py`, so the data
is there. Flag-gated, default-off bit-identical.

### Tier 1 (fourth) — THE CREDIT SYSTEM HAS NO P&L: neither borrower nor lender books its costs

Both sides of every credit relationship omit their interest / credit costs from profit. This
is one root cause with two faces, and it mutes the financial-fragility arcs (v3/v8/v11) BY
CONSTRUCTION.

#### (a) Firm profit omits INTEREST and DEPRECIATION

**Root cause.** `f.profit = f.revenue - f.wagebill - f.energy_cost_used`
([settlement.py:40](../../macro_sim/systems/settlement.py)) — this is EBITDA, not profit.
Interest is never netted (grep finds only `bk.profit = bk.interest_income`: the BANK books
interest income, the borrowing FIRM never books interest expense — an accounting asymmetry).
Depreciation is never expensed either (the comment correctly notes investment is an asset
swap, but then depreciation should be the expense, and it is absent).

**Everything downstream is built on this overstated profit:**
- `div_pool = rho × max(0, profit − taxes)` — **dividends are paid out of pre-interest,
  pre-depreciation profit**: a heavily indebted firm distributes as if it were debt-free.
- `ptax = tax_profit_rate × profit` — **the profit-tax base is EBITDA**. Interest is not
  deductible, so the **debt tax shield — a first-order corporate-finance force — does not
  exist**.
- [equity.py:134](../../macro_sim/systems/equity.py): `residual_income_ema += λ((f.profit −
  r×book) − …)` — the valuation/investment channel subtracts an IMPUTED capital charge on
  BOOK value while the ACTUAL interest on ACTUAL debt never enters.
- `va = wagebill + max(0, profit)` → **labor_share is systematically understated**.

**Leverage therefore carries NO profit-and-loss penalty:** debt shows up only as a cash drain
in the debt-service phase, never reducing distributable profit, the tax base, or the
valuation signal.

#### (b) Bank profit omits its COST OF FUNDS and its LOAN LOSSES

**Root cause.** `bk.profit = bk.interest_income`
([credit.py:122](../../macro_sim/systems/credit.py)) — gross interest income, with **no
expenses at all**:
- **Funding is free.** Banks pay no deposit interest. `deposit_rate_disp` is only a mean-zero
  cross-bank SPREAD that drives depositor migration (the competition mechanism); no deposit
  interest is ever transferred. So the loan rate is the entire margin and a rising policy
  rate raises bank profit monotonically — **there is no net-interest-margin squeeze, ever.**
- **Loan losses never hit the P&L.** Write-offs reduce the bank's ledger balance (capital) but
  not `bk.profit`, and dividends are `min(bk.rho × max(0, bk.profit), capital)` — so a bank
  keeps paying dividends out of gross interest income straight through a credit bust,
  draining capital exactly when it should be retaining it. The opposite of the intended
  fragility dynamic.

**Why (a)+(b) together are the most serious finding: they do not merely contaminate
measurements — they defeat a whole arc's intended mechanism.** The entire point of the
v3/v8/v11 credit + Minsky + bank-failure arcs is that leverage should breed financial
fragility, and fragility should register in profitability, dividends, valuation and bank
capital. Here it registers only in cash, on both sides. The financial accelerator is muted
by construction.

**Patch #5 — a real P&L on both sides.** Firms: net interest expense (and a depreciation
charge) into `f.profit` before dividends, the profit tax, `va`, and the equity/
residual-income channel — which also restores the missing **debt tax shield**. Banks: expense
the cost of funds and provision loan losses before `bk.profit` and its dividend. This CHANGES
BEHAVIOUR substantially (dividends fall, tax bases move, leveraged firms are visibly less
profitable, banks can suffer margin compression and stop paying dividends into a bust), so it
is flag-gated with a default-off bit-identical path and needs a real acceptance:
**pre-register that the financial accelerator STRENGTHENS** and re-test the Minsky dynamics
the v8/v11 arcs were after.

### Tier 1 (fifth) — CAPITAL IS A FREE INPUT: it enters neither the price nor the profit
### ⇒ the pricing rule manufactures the deflation we have been chasing since v17

**Root cause.** Capital is never charged for, anywhere:
- **Pricing.** `unit_cost` = unit LABOR cost (+ the v17 Leontief energy term) × the v5 scale
  diseconomy ([planning.py:101-122](../../macro_sim/behavior/planning.py)). No capital cost,
  no interest. B3 then posts `p = (1 + markup) × unit_cost` — **priced as if capital were
  free**.
- **Profit.** `f.profit = revenue − wages − energy` (Tier-1 #4 above). No depreciation, no
  interest.

**The consequence, and it is the deepest finding in this list: the pricing rule mechanically
converts CAPITAL DEEPENING into DEFLATION.** As the economy accumulates capital and
substitutes it for labour, labour input per unit of output falls, so unit LABOUR cost falls,
so `unit_cost` falls, so posted prices fall. But the capital cost that REPLACED that labour is
invisible to the pricing rule. True unit cost (labour + capital consumption) does not fall
nearly as much. Real economies do not deflate from capital deepening precisely because the
capital has to be paid for; here it does not.

**This unifies the mysteries of the last two arcs:**
- the persistent −4 to −8%/yr deflation in every v17/v19 portrait;
- **why TFP drift could not stop it** — drift raises output per worker, which lowers unit
  labour cost further, which deflates MORE. That is exactly what the v19 audit measured
  ("TFP drift barely moves the nominal outcome");
- the overstated profit and the dividends paid out of EBITDA;
- and it puts the v19 headline in a new light: **the CB may be reacting to a deflation the
  PRICING RULE manufactures.** "The central bank is the deflation engine" may itself be a
  downstream symptom.

**Patch #6 — charge for capital.** Put a capital-consumption term (depreciation, or a rental
rate on the capital employed per unit) into `unit_cost` so pricing sees the input it is
actually using, and expense depreciation in `f.profit` (shared with Patch #5). Flag-gated,
default-off bit-identical. **This RE-SCOPES patches #1 and #2: fix the COST side first, then
re-run the nominal-anchor audit** — the CB may look very different once it is no longer
chasing a structurally manufactured disinflation.

### Tier 1 (sixth) — firm net worth is CASH ONLY: capital is not collateral, so the
### collateral channel of the financial accelerator cannot exist

**Root cause.** `credit_grant` caps debt at `kappa · NW` where **`NW = deposits − debt`** —
purely FINANCIAL net worth ([planning.py:240-247](../../macro_sim/behavior/planning.py)). The
firm's capital stock and inventory — its actual productive assets — are not in it. A grep for
`collateral` across firm lending returns NOTHING: there is no collateral concept in firm
credit at all (households have mortgage LTV; firms have nothing).

So a capital-rich, cash-poor firm cannot borrow, while a cash-rich, capital-less firm borrows
freely — backwards from real collateral-based lending, where the capital stock IS the
collateral. The docstring claims "this one line is the whole Minsky-leverage engine", but the
engine is built on financial net worth alone, so **the collateral channel of the financial
accelerator (Bernanke-Gertler: asset prices → collateral value → borrowing capacity →
investment) cannot exist.**

Together with Tier-1 #4, **BOTH channels of the financial accelerator are absent by
construction** — the P&L channel (leverage never bites in profit) and the collateral channel
(assets never support borrowing).

**Patch #7 — capital as collateral.** Add the (depreciated, possibly marked) capital stock and
inventory to the firm's borrowing base, so asset values feed borrowing capacity. Flag-gated,
default-off bit-identical; acceptance pre-registers that the financial accelerator now
produces the asset-price → investment feedback the v8 arc was after.

### Minor notes (fold into whichever patch touches the same file)

- **Unemployment mixes units.** `unemployment_rate = 1 − total_hired / labor_supply`
  ([metrics.py:277](../../macro_sim/reporting/metrics.py)): the numerator `total_hired` is in
  EFFICIENCY UNITS under `labor_person_efficiency` (v16 L4), the denominator `labor_supply`
  is in HEADS (the demographic profile's labor supply). Because e_i is mean-one and there is
  no selection on e at hire, Σe ≈ the employed head count, so this injects NOISE rather than
  a systematic bias — but the noise lands in the CB's Taylor input and the Phillips estimate,
  so fix it while the price-index patch is in the same file.
- **Duplicate key.** `per_capita_real_output` and `real_output_per_capita`
  ([metrics.py:1440,1464](../../macro_sim/reporting/metrics.py)) compute the identical thing.

### Tier 2+ — DROPPED

The earlier Tier 2-4 candidates (shell-household behavioural leakage, the year-2750
bank-shakeout diagnosis, §4 re-score, distress_floor ruling, v16 hot calibrations,
housing×energy coupling) are OUT of v23 scope by decision — v23 targets root-cause,
pervasive-contamination defects only.
