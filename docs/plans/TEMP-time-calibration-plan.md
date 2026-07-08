# Tick–Time Calibration: Mapping One Tick to One Day

**Status:** resolved design decision — `Delta = 1 day` for the economic tick.
**Supersedes:** the "abstract per-tick economy" stance in `04-validation-roadmap-kernel.md`.
**Companion to:** the parameter inventory (this document is its calibration counterpart).

---

## 0. The decision and why it forces a rewrite of the defaults

The economic tick is now **one calendar day**: `Delta = 1/365 year`. This was chosen
because the fastest phenomena we want to *emerge with time structure* — bank runs, margin
spirals, contagion, asset-price discovery — unfold on a daily scale. A tick coarser than a
day collapses these into binary events ("a run happened") instead of resolving their
*path* ("how the run propagated"). Resolving that path is the whole point of an ambitious
financial layer, so the integration step must sit below the natural timescale of the
fastest target process. That is the day.

**Methodological rule (read before touching any number).** We do **not** rescale the old
per-tick defaults into day values. §14 of the inventory already proved the old defaults are
mutually inconsistent — `theta_price=0.25` implies a ~2.5-month tick while `delta_K=0.05`
implies a ~12-month tick, differing by ~5×. That inconsistency is the *signature* of an
abstract tick that no single `Delta` can satisfy. The fix is not to average it away; it is
to **discard the old defaults and re-derive every rate from its real-world natural anchor**
via the conversion law for its mathematical type. Selecting `Delta = 1 day` and re-deriving
from anchors is precisely the act that makes the whole parameter set time-consistent for the
first time.

**Natural-time facts under `Delta = 1 day`:**

| Quantity | In ticks |
|---|---|
| 1 year | 365 ticks |
| 1 quarter | ~91 ticks |
| 1 month | ~30 ticks |
| Business cycle (~5.5 yr) | ~2000 ticks |
| A 4000-tick run | ~11 years |
| Demographic step `dt=1` (1 yr) | 365 ticks |

Note the last two rows: a 4000-tick run is now only ~11 years, so experiments become
**deep and short** (high time resolution, decades of span) rather than shallow and long.
This is the core trade the day tick buys — time resolution at the cost of time span.

---

## 1. The six conversion laws (stated once, referenced everywhere)

Every time-sensitive parameter belongs to exactly one of six mathematical types. The
type — not the parameter's economic role — determines its conversion law. Getting the type
wrong is the *only* way to silently miscalibrate, and §5's invariance test is designed to
catch exactly that. Throughout, `Delta = 1/365` and `H` denotes a chosen natural half-life.

**Type A — Probability of a recurring event** (Calvo repricing, entry hazards, run
probabilities). To hold the natural event frequency fixed, the per-tick probability scales
so expected occurrences per natural period are conserved. For a mean spell of `S` days:
$$p_{\text{day}} = \frac{1}{S_{\text{days}}} \quad\Big(\text{exactly } p = 1-(1-p_{\text{nat}})^{\Delta/\Delta_{\text{nat}}}\Big)$$

**Type B — Compounding rate** (interest, depreciation, inflation, coupons). Values that
compound over time convert geometrically, so `(1+r_day)^365 = 1+r_year`:
$$r_{\text{day}} = (1+r_{\text{year}})^{1/365} - 1, \qquad
\delta_{\text{day}} = 1-(1-\delta_{\text{year}})^{1/365}$$
Never use the linear `r_year/365` here — the short-horizon error is tiny but it accumulates
over a long run and is conceptually wrong.

**Type C — Volatility / stochastic-shock SD** (Gibrat shock, any Gaussian innovation SD).
This is the one that catches people. Variance of a random walk grows *linearly* in time, so
the *standard deviation* grows as the square root:
$$\sigma_{\text{day}} = \sigma_{\text{year}} \cdot \sqrt{1/365} = \frac{\sigma_{\text{year}}}{19.1}$$
**Divide by 19.1, not by 365.** Using the Type-B/linear factor here is the single most
common discretization bug.

**Type D — EMA / smoothing speed and its twin, retention.** These have no external anchor;
you fix their *natural half-life* `H` and invert. Two parameterizations:
- *Speed* `lambda` (update fraction, e.g. most `lambda_*`): `lambda_day = 1 - (1/2)^{Delta/H}`
- *Retention* `rho` (persistence, e.g. `rate_inertia`, `run_fear_persistence`, the `*0.999`
  decays): `rho_day = (1/2)^{Delta/H}`

They are the same operation with `1 - lambda = rho`; keep straight which face a parameter
wears. Under a fine tick, retention parameters move *toward 1* (daily updates need more
inertia to achieve the same smoothing).

**Type E — Step size / partial-adjustment speed** (`eta`, `lambda_p`, `lambda_I`,
`portfolio_adjust`, `omo_drain_frac`, `amort`). The conversion depends entirely on **what
clock the parameter is mounted on**:
- *Mounted per-tick* (runs every tick): treat as Type-D speed — shrink the step so the
  natural adjustment half-life is preserved.
- *Mounted on an event* (fires only when a repricing / rewage / issuance event fires):
  **leave it unchanged** — its frequency is already throttled by that event's Type-A
  probability.

This is why `eta` (markup step, fires on a repricing event) is unchanged while `lambda_p`
(price groping, fires every tick) must shrink. The mounting decision, not the parameter, is
what matters.

**Type F — Dimensionless ratio / level / stock target** (tax rates on flows, `theta_equity`,
weights, bounds, thresholds, all of inventory §13). **Unchanged.** A ratio of two quantities
that scale together is invariant; the per-tick base it multiplies auto-rescales. *Exception:*
a rate levied on a **stock** per period (wealth tax) is not Type F — see the traps in §4.

---

## 2. Multi-timescale mounting (the day tick's real architectural cost)

A day tick spans four natural timescales. Running every process every tick is both wasteful
(population) and wrong (quarterly GDP read daily has aliasing artifacts). So each process
**registers its own mounting cadence** on the shared daily clock — the generalization of the
event-queue protocol already used for loan amortization (B6), vital events (P2), and
irregular player policies. Calibration and mounting are decided together.

| Process | Natural cadence | Mounted every | Reads which signal layer |
|---|---|---|---|
| Financial (asset price, runs, margin) | daily | 1 tick | daily live (own balances, prices) |
| Real cash-flow / liquidity | ~monthly | ~21 ticks | daily live |
| Pricing / wages | monthly–quarterly | on Calvo event | last-period local signal |
| Firm / bank entry, dividends | quarterly | ~91 ticks (batch) | last-quarter aggregates |
| Player (gov / CB) decisions | quarterly | ~91 ticks | last-quarter aggregates |
| Population (births / deaths) | annual | 365 ticks (batch) | annual-aggregated economy |

**Signal layering (M3(c) under a fine tick).** M3(c)'s "plan on last-period aggregates"
splits by signal frequency: financial agents read *yesterday's* live state; the central bank
reads *last quarter's* GDP/inflation — because a quarterly aggregate does not exist between
its 91-tick computations. Do not let the CB read a nonexistent daily GDP, and do not force
financial agents to wait for quarterly signals. Maintain two explicit signal layers: **daily
live** and **quarterly settled**.

---

## 3. Parameter-by-parameter calibration

Each row gives: **Type** (§1 letter), the **natural anchor assumed** (override with your own
target), the **day-tick value**, and a note. Values are computed from the anchor via the
type's law. "—" in the day-value column means unchanged.

### 3.1 Planning, expectations, price, wage, consumption (inventory §2)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `lambda_d` | D-speed | expectation half-life ~1 quarter | **0.0076** | `1-(1/2)^{1/91}`; use `H=1yr`→0.0019 for stickier expectations |
| `lambda_y` | D-speed | half-life ~1 quarter | **0.0076** | same as `lambda_d` |
| `theta_price` | A | regular-price spell ~9 months (274 d) | **0.0037** | `1/274`; range 8mo→0.0041, 11mo→0.0030 |
| `theta_wage` | A | wage spell ~12 months (365 d) | **0.0027** | `1/365` |
| `delta` (wage flex) | B | strict DNWR (annual 0%) | **0.0** | stays 0; if ever relaxed, `1-(1-δ_yr)^{1/365}` |
| `eta` | E-event | mounted on repricing event | **—** | throttled by `theta_price`; do not shrink |
| `mu_min`, `mu_max` | F | bounds | **—** | 0.0, 1.0 unchanged |
| `omega` (wage raise) | E-event | mounted on rewage event | **—** | fires only when rewage draw fires; unchanged |
| `phi` (inventory) | **trap** | coverage ~2 months of demand | **~60** | stock/flow ratio — see §4; express as *days of demand covered* |
| `search_m` | F | search intensity per shopping trip | **—** | unchanged, but note goods market now runs daily (§4) |
| `alpha1` | F | flow-to-flow MPC | **—** | 0.8 unchanged (fraction of each period's income) |
| `alpha2` | **trap** | wealth drawdown ~2%/yr | **5.5e-5** | stock-to-flow — linear: `0.02/365`; see §4 |
| `mpc_dispersion` | F | dispersion of a rescaled param | **—** | rescales *with* `alpha1/alpha2`; at 0 stays 0 |
| `wealth_effect` | trap | like `alpha2` (stock-to-flow) | linear/365 | if enabled, scale as `alpha2`; default 0 |
| `mpc_wealth_curvature` | F | shape | **—** | 1.0 unchanged |
| `hh_subsistence` | flow | annual subsistence flow | `/365` | per-tick consumption floor; default 0 |

### 3.2 Production, investment, capital (inventory §3)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `lambda_I` | E-per-tick | capital-adjustment half-life ~1 yr | **0.0019** | `1-(1/2)^{1/365}`; `H=2yr`→0.00095 |
| `delta_K` | B | annual depreciation ~8% | **2.28e-4** | `1-(0.92)^{1/365}`; **was 0.05, discard** |
| `lambda_q` | E-per-tick | if enabled, half-life ~1 quarter | 0.0076 | default 0 |
| `q_invest_smooth` | D-speed | 1.0 = no smoothing | **—** | keep 1.0, or set `H` if daily q is too noisy |
| `q_invest_floor`,`cap` | F | multiplier bounds | **—** | 0.5, 2.0 unchanged |
| `public_capital_depreciation` | B | annual ~8% (or lower for infra) | **2.28e-4** | as `delta_K`; infra 4%/yr→1.12e-4 |
| `public_capital_gamma` | F | elasticity | **—** | unchanged |
| `jg_productivity` | F | output per unit labor (flow/flow) | **—** | productivity level, unchanged; default 0 |

### 3.3 Credit, interest, debt service (inventory §4)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `r_interest` | B | annual 5% | **1.34e-4** | `(1.05)^{1/365}-1`; **was 0.01, discard** |
| `r_neutral` | B | annual 5% | **1.34e-4** | match `r_interest` |
| `r_max` | B | annual cap ~20% | **5.0e-4** | `(1.20)^{1/365}-1` |
| `amort` | E→linear | firm loan duration ~2.5 yr | **0.0011** | `1/(365·2.5)`; set by target duration |
| `hh_amort` | E→linear | household debt duration ~5 yr | **5.5e-4** | `1/(365·5)`; mortgages longer |
| `bank_spread_disp` | B-linear | annual spread SD `s` | `s/365` | cross-bank rate spread; default 0 |
| `interbank_rate_base` | B-linear | annual spread | `/365` | rate spread; default 0 |
| `interbank_tightness` | B-linear | annual spread | `/365` | rate spread; default 0 |
| `deposit_rate_disp` | B-linear | annual spread SD | `/365` | default 0 |
| `bank_target_capital_ratio` | F | stock ratio | **—** | unchanged |
| `rho` (dividend payout) | F + **mount** | payout ratio | **—** | ratio invariant, **but batch to quarterly** — see §4 |

### 3.4 Central bank and inflation rule (inventory §5)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `inflation_target` | B | annual 2% | **5.4e-5** | `(1.02)^{1/365}-1`; default 0 stays 0 |
| `infl_ema_lambda` | D-speed | inflation-signal half-life ~1 yr | **0.0019** | `1-(1/2)^{1/365}` |
| `rate_inertia` | D-**retention** | smoothing half-life ~1 quarter | **0.9924** | `(1/2)^{1/91}`; **was 0.8 — moves toward 1** |
| `taylor_phi_pi` | F | dimensionless slope | **—** | 1.5 unchanged (both π-gap and rate scale together) |
| `taylor_phi_u` | **trap** | maps invariant u-gap → per-tick rate | **0.0014** | `0.5/365` — **scales while `phi_pi` does not**; see §4 |
| `u_natural` | F | level | **—** | 0.05 unchanged |
| `omo_drain_frac` | E-per-tick | OMO half-life ~1 week | **0.094** | `1-(1/2)^{1/7}`; OMO is fast |
| `omo_reserve_target` | F | stock target | **—** | unchanged |

### 3.5 Securities / bonds (inventory §6)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `bond_coupon` | B | annual 4% | **1.08e-4** | `(1.04)^{1/365}-1`; or simple `/365`≈1.10e-4 |
| `bond_maturity` | count | v123 2 yr / v124 1 yr | **730 / 365** | maturity_years × 365 |
| `bond_finance_frac` | F | stock target | **—** | unchanged |
| `bond_theta` | F | portfolio stock target | **—** | 0.15 unchanged (reached via `portfolio_adjust`) |
| `bank_bond_appetite` | E-event | mounted on issuance event | **—** | unchanged if per-issuance; default 0 |
| `bank_bond_duration_limit` | F | stock limit | **—** | unchanged |

### 3.6 Firm entry / exit (inventory §7)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `bankrupt_persist` | count | insolvency grace ~1.5 yr | **~548** | years × 365; 1yr→365, 2yr→730 |
| `entry_beta` | A + **mount** | **batch entry to quarterly** | **—** | firms don't enter daily; evaluate every ~91 ticks |
| `entry_max` | count + **mount** | max per *quarter* | **—** | keep as per-quarter cap under quarterly batch |
| `gibrat_sigma` | **C** | annual growth vol ~0.10 | **0.0052** | `0.10/19.1` — **√Δ, divide by 19.1 not 365**; see §4 |
| `pref_attach_beta` | F | demand exponent | **—** | 1.0 unchanged |
| `pref_price_elasticity` | F | elasticity | **—** | unchanged |
| `gibrat_entry_a0` | F | initial condition | **—** | 0.2 unchanged |

### 3.7 Equity, portfolios, margin (inventory §8)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `lambda_p` | E-per-tick | price-discovery half-life ~5 days | **~0.13** | `1-(1/2)^{1/5}`; **daily tick ≈ natural for equity** — keep near 0.1 |
| `trend_lambda` | D-speed | momentum half-life ~1 month | **0.023** | `1-(1/2)^{1/30}` |
| `equity_ema_lambda` | D-speed | wealth-effect half-life ~1 quarter | **0.0076** | |
| `resid_income_lambda` | D-speed | valuation half-life ~1 yr | **0.0019** | |
| `portfolio_adjust` | E-per-tick | rebalancing half-life ~2 weeks | **0.048** | **was 1.0 (instant)** — daily full rebalance is 365×/yr |
| `lambda_issue` | E-event | mounted on issuance | **—** | default 0 |
| `theta_equity` | F | stock target | **—** | 0.3 unchanged |
| `w_chartist`,`w_fundamental` | F | weights | **—** | 0.0, 1.0 unchanged (returns they weight do scale) |
| `margin_ltv`,`margin_max` | F | stock/leverage ratios | **—** | 0.5, 2.0 unchanged |

### 3.8 Banking dynamics, runs, bank equity (inventory §9)

| Parameter | Type | Natural anchor assumed | Day value | Note |
|---|---|---|---:|---|
| `bank_equity_lambda` | D-speed | earnings half-life ~1 yr | **0.0019** | |
| `bank_theta_equity` | F | stock target | **—** | 0.1 unchanged |
| `bank_entry_beta` | A + **mount** | batch to quarterly | **—** | banks don't enter daily; default 0 |
| `bank_entry_max` | count + **mount** | max per quarter | **—** | quarterly batch |
| `run_sensitivity` | A | **naturally per-day** | keep | runs are the fast process the day tick is *for*; default 0 |
| `run_fear_persistence` | D-**retention** | panic half-life ~2 weeks | **0.952** | `(1/2)^{1/14}`; **was 0.9 — fast, short H** |
| `run_health_ref` | F | threshold | **—** | unchanged |
| `run_market_weight` | F | weight | **—** | unchanged |
| `bank_search_m`,`deposit_search_m` | F | search intensity per event | **—** | unchanged |
| `reserve_floor_frac` | F | liquidity constraint | **—** | unchanged |

### 3.9 Fiscal, labor policy, taxes (inventory §10)

Almost all fiscal parameters are **Type F ratios of flows** and are unchanged — the per-tick
base (daily GDP / income) auto-rescales. Two exceptions are flagged.

| Parameter | Type | Day value | Note |
|---|---|---:|---|
| `gov_consumption_share` | F | **—** | share of daily potential output; base auto-scales |
| `gov_deficit_target` | F | **—** | share of daily GDP |
| `deficit_u_ref` | F | **—** | reference level |
| `benefit_replacement` | F | **—** | ratio to wage reference |
| `tax_profit_rate` | F | **—** | rate on a *flow* (profit) — invariant |
| `tax_income_rate` | F | **—** | rate on a flow — invariant |
| `tax_consumption_rate` | F | **—** | per-transaction VAT — invariant |
| `tax_wealth_rate` | **trap** | `/365` | rate on a *stock* per period — **scales**; see §4 |
| `income_allowance`,`wealth_allowance` | F | **—** | ratios/levels, unchanged |
| `gov_investment_share` | F | **—** | share of prior daily output |
| `min_wage` | level | ratio-ize | if absolute per-tick wage it scales `/365`; **better: express as ratio to mean wage** |
| `jg_wage_ratio` | F | **—** | ratio to mean wage, invariant |

### 3.10 Hard-coded tick-sensitive constants (inventory §11)

These are not `Config` fields but behave as per-tick parameters. They need the same
treatment and should ideally be lifted into `Config` during the calibration refactor.

| Location / constant | Type | Day treatment | Note |
|---|---|---|---|
| equity `clip(±0.5, excess_demand)` | ~C | tighten ~√Δ | bounds a one-day price move; a daily equity move should be realistically capped (e.g. ±few %) — shrink toward `0.5/19.1` scale, or keep as a safety clamp and verify daily moves |
| equity `0.5*book`, `0.2*shares` issuance caps | flow | `×Δ` or batch | per-tick financing-flow caps; scale down or mount on issuance events |
| banking `share_peak * 0.999` | D-**retention** | **0.9981** | peak-memory half-life ~1 yr → `(1/2)^{1/365}`; set by desired memory |
| banking `max(0, 0.5 - health)` | F | **—** | run-pressure threshold; structural, unchanged |
| banking `+0.25` fear jump on failure | event | **—** | discrete jump on an *event*, invariant |
| banking `+0.02 * queue/hh` fear increment | linear | `×Δ` | **per-tick accumulation** — scales down; recalibrate so daily panic build matches a natural rate |
| banking `range(8)` founder search | F | **—** | search intensity per entry event, unchanged |
| firm_demographics `range(12)` funder search | F | **—** | unchanged |

### 3.11 Demographic Phase 0 (inventory §12) — unchanged, but now coupled

The demographic kernel already runs in natural time (`dt=1.0` = one year). **Do not convert
its hazards to daily.** Instead, couple it to the economy by the mounting protocol:

- **`dt` stays 1.0 (one year).** Population events **batch at 365 economic ticks**.
- **`makeham_a`, `gompertz_b`, `gompertz_theta`, `infant_extra`** — per-year hazards,
  **unchanged**. Continue computing `q(a) = 1 - exp(-∫μ·dt)` with `dt=1` (one year).
  Converting these to a daily hazard would mean drawing "did this agent die today?" with
  probability ~3e-8 for young agents — burning compute on astronomically many non-events.
  Annual batching is the intended resolution of the P5 open question.
- **`tfr`, `fertility_peak_age`, `fertility_width`, `omega`, `sex_ratio_at_birth`** —
  age/lifetime parameters, **unchanged**.
- **Coupling rule (locks P5):** `365 economic ticks = 1 demographic dt = 1 year`. Vital
  events fire on every 365th tick through the existing P2 `transfer` machinery (birth =
  balance-sheet entry, death = estate transfer). When Phase 2 later couples economy →
  demography, **aggregate economic flows over the 365-tick year** before feeding annual
  vital-rate updates — never let fertility respond to a single daily income flow, or you
  inject a spurious daily-frequency signal into an annual process.

### 3.12 Non-anchors (inventory §13) — unchanged

Scales, genesis balances, technology levels, stock/leverage limits, boolean switches, and
distribution shapes are not time-rates and are unchanged. One caveat: nominal genesis levels
(`p_firm0`, `w_firm0`, `p_kfirm0`, …) define an arbitrary nominal scale for the whole system
and are initial conditions, not rates — which is why policy parameters are best expressed as
*ratios* to emergent means (`jg_wage_ratio`, `benefit_replacement`) rather than absolute
per-tick levels.

---

## 4. Silent-failure traps (the six that break without erroring)

Every one of these converts by a law *different* from what its economic neighbors suggest.
These are where a wrong type assignment produces a plausible-looking but wrong economy.

1. **`gibrat_sigma` uses √Δ, not linear.** It is a random-walk innovation SD, so
   `σ_day = σ_year/19.1`, not `/365`. Using the linear factor understates firm-growth
   volatility by ~19×, killing the fat tail in firm size you want to emerge. **The single
   most likely bug.**

2. **`taylor_phi_u` scales but `taylor_phi_pi` does not.** `phi_pi` multiplies a per-tick
   inflation gap (which scales with Δ) to produce a per-tick rate (also scales) → the ratio
   is invariant. `phi_u` multiplies an *unemployment gap* (a level, invariant) to produce a
   per-tick rate (scales) → so `phi_u` must scale `/365`. Leaving `phi_u` at its annual
   value makes the CB react ~365× too hard to unemployment.

3. **`phi` (inventory) is a stock/flow ratio.** Target inventory = `phi × expected demand`,
   and expected demand is now a *daily* flow. To keep the same *natural* coverage (e.g. two
   months of sales), `phi` must be re-expressed as **days of demand covered** (~60), not left
   at 0.75. Otherwise desired inventory silently shrinks to ~a day of sales.

4. **`alpha2` scales, `alpha1` does not.** `alpha1·Y` is flow-out-of-flow (spend a fraction
   of each period's income) → invariant. `alpha2·V` is flow-out-of-*stock* (consume a
   fraction of wealth each period) → scales linearly `/365`. Consuming 5% of wealth *per day*
   would liquidate a household in weeks. Set `alpha2` from a target annual wealth-drawdown.

5. **`tax_wealth_rate` scales; every other tax does not.** Taxes on flows (profit, income,
   consumption) are invariant ratios. A wealth tax is levied on a *stock per period*, so a
   daily wealth tax must be `annual/365`. This is the only tax that changes.

6. **Retention parameters move toward 1, not down.** `rate_inertia` (0.8→0.99),
   `run_fear_persistence` (0.9→0.95), the `*0.999` peak decay — under a finer tick these
   *increase* toward 1, because achieving the same natural smoothing requires more per-tick
   inertia when updates are more frequent. Intuition says "smaller tick, smaller number,"
   which is backwards for retention.

---

## 5. Invariance test (the validation, and it does not touch the test set)

After re-deriving everything, **do not trust the numbers — test them.** This is the time
analog of M3(a)'s ordering-invariance discipline: it checks *invariance*, not fit, so it does
not violate §0-ii.

**Protocol.** Pick two ticks (e.g. daily and monthly). Re-derive *all* rates from the same
natural anchors for each. Run both. In **natural-time units**, the macro results must agree:
annualized growth, unemployment-volatility amplitude, and any cycle period *in years* should
coincide (within Monte-Carlo noise).

- **Agree** → your conversion laws are correct and `Delta` is a genuine label.
- **Systematic disagreement** → you have a discretization artifact. It is almost always in
  **Type C (`gibrat_sigma`'s √Δ)** or in an **E-parameter's mounting judgment** (per-tick vs
  event). The test localizes which parameter's law is wrong.

---

## 6. The §0-ii red line (non-negotiable)

You now hold a cycle-producing economy *and* the freedom to adjust these parameters. That
combination is the most dangerous in the project. The line:

> You may adjust a Type-A/B/C anchor **only** to make it consistent with `Delta` (i.e. its
> real-world natural value converted by the type's law). You may **never** adjust any
> parameter to make a §4 macro regularity — business-cycle period, Okun slope, Phillips
> slope — hit a target.

The operational test is a single question you must be able to answer for every adjustment:
*"What is the real-world natural value, and which law converts it?"* If the justification is
ever "this makes the cycle come out at 5.5 years," you are training on the test set. Anchor
`Delta` to **micro frequencies** (price/wage spells, loan durations, depreciation rates);
let the macro periods **emerge** and then compare them — never fit them.

In particular: the business cycle should *emerge* near ~2000 ticks. Verify this by finding
the spectral peak `P` in ticks and computing `P/365` years — **not** by tuning any parameter
so the peak lands there. A self-emergent ~5.5-year cycle is a validation; a tuned one is
circular.

---

## 7. Implementation checklist

1. **Discard** the old per-tick defaults (they encode no single `Delta`; §14 conflict).
2. **Type-tag** every parameter A/B/C/D/E/F per §1.
3. **Re-derive** each from its natural anchor: A `1/spell_days`, B geometric `^(1/365)`,
   C `σ/19.1`, D half-life inversion, E by mounting (per-tick shrink / event unchanged),
   F unchanged.
4. **Handle the six traps** (§4) explicitly — `gibrat_sigma`, `phi_u`, `phi`, `alpha2`,
   `tax_wealth_rate`, retention params.
5. **Set mounting cadences** (§2): financial per-tick, real ~monthly, entry/dividends/player
   quarterly-batch, population annual-batch. Lift the §11 hard-coded constants into `Config`.
6. **Couple demography** at 365:1, `dt=1` unchanged, aggregate economic flows to annual.
7. **Run the invariance test** (§5): daily vs monthly must agree in natural-time units;
   disagreement → check Type C and E-mounting first.
8. **Hold the red line** (§6): anchors justified by micro natural values only; macro
   regularities emerge and are compared, never fit.

The through-line: selecting `Delta = 1 day` is not a relabeling of the abstract economy — it
is the act that makes the parameter set time-consistent for the first time, by forcing every
rate back onto a real-world anchor. The cost is the multi-timescale mounting you now must
manage explicitly; the payoff is a financial layer fast enough for crises to emerge *with
time structure*, and an economy whose clock, population, player decisions, and macro signals
are all finally on the same, real, calendar.