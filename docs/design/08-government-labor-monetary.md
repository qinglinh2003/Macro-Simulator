### 27.6 Methods — parallel runs
Seed sweeps now fan across all cores: `prun.py` (`run_jobs(jobs)`), `validate_parallel.py <factory>
<seeds>` (parallel §4). ~7.5× on the 10-core M5. Every result above is 5-seed unless noted.

---

## §28 v9 — the GOVERNMENT sector (built, diagnosed net-NEGATIVE, being repaired)

**Status: in progress.** The government mechanism is built, conserving (A5), and bit-identical when off
(`government=False` ⇒ v8.5, still 8/8). But the default `Config.v9()` scores **§4 5/8** — the government
is a net drag. The diagnosis (§28.4) found the fault is in our *fiscal mechanism*, not "government is bad."

### 28.1 What v9 is — the interactive control surface (PLAN_v9)
A consolidated **Treasury** (central bank deferred to v10). The organising idea: **`Policy` is the only
state mutable DURING a run** (the government's levers — taxes, spending, macroprudential caps); everything
else is frozen `Config`. This split (`policy.py`, seeded from `Config`) is the foundation for the eventual
interactive-software vision. A government running a deficit issues **outside money** (its `GOV` ledger
account goes negative = government debt = private net financial wealth; A5 untouched since transfers
conserve — required making `allow_negative` actually exempt an account from the overdraft gate in
`transfer`, a latent gap).

### 28.2 The build (all A5-safe, off ⇒ bit-identical)
- **Four tax bases:** profit (pre-dividend), **progressive** income (marginal rate above a personal
  allowance), VAT (in the goods market), wealth (on net worth). Flow taxes at real rates; wealth tax
  re-anchored to ~0.2× the per-tick return (a stock tax per tick ≠ a flow tax).
- **Two spends:** unemployment benefit (to the involuntarily unemployed, into `income_realized`),
  government consumption (a buyer in the goods market).
- **Deficit-targeting rule:** gov consumption is sized so the deficit ≈ `gov_deficit_target·GDP`
  (tax-financed G + a controlled deficit). The pure-quantity mode (`g·potential`) overheats a stationary
  economy (u→0, debt explodes); deficit-targeting is self-limiting.
- **Macroprudential:** `margin_ltv`, `margin_max`, `kappa`, `hh_credit_limit` reclassified from Config
  dials into live `Policy` levers.
- **Household bankruptcy:** an insolvent household (net worth ≤0 after the margin call) is discharged —
  repay what cash it has, WRITE OFF the rest (bank absorbs, like a firm default), keep shares, emerge with
  no margin debt. The §27 demand-death exit valve.
- **Normalised fiscal metrics:** `gov_deficit_to_revenue`, `gov_deficit_to_gdp`, `gov_debt_to_gdp` (raw
  stocks are unreadable). Also a float-robustness guard on the CLEARING drains (`> EPS`).

### 28.3 What works, and the §4 verdict
- **Fiscal works early/medium:** a maintained **2–5%-of-GDP deficit** (real-world normal) drives u from
  ~0.05 to ~0.005 and eliminates deep recessions — the functional-finance result (a demand-starved economy
  needs the outside money the §9 drain denies it). **Balanced budget fails** (u stuck ~0.5): a taxing,
  hoarding government *is* a private-sector drain (SFC identity: gov surplus = private deficit).
- **Bankruptcy helps the long run:** late-window u **0.449→0.319** (a continuous ~0.03/tick discharge
  recycles insolvent households back into demand). The §27 intuition confirmed.
- **§4 = 5/8.** Passes T1, T2, **T4 (mean u 0.185)**, T5, **T8**. Fails **T3** (credit comovement −0.02),
  **T6** (firm Zipf slope −2.62, Gini 0.88), **T7** (credit boom-bust). The government is OFF by default,
  so v8.5's 8/8 frontier is preserved; v9 is an opt-in layer that currently trades §4 fit for the mechanism.

### 28.4 DIAGNOSIS — one confirmed error; the long-run degradation is UNPINNED (honest)
Real government is decisively net-positive; ours is net-negative ⇒ **our fiscal design is flawed.** One
error is confirmed; the other proposed cause did not survive testing, and the underlying long-run
degradation resisted ~6 hypotheses. Reported honestly, warts included.
- **Error (CONFIRMED) — the deficit rule was not state-dependent.** A fixed 3%-of-GDP deficit *regardless of
  slack* means that once the economy hits full employment the injection has no idle capacity to activate and
  becomes pure **inflation** (price 1.3→10.5). Fix 2 (§28.6) confirmed the mechanism: tapering the deficit at
  full employment cut inflation to 8.2 and restored **T7**.
- **Credit decoupling (T3, T7)** is *partly realistic*, not an error: a large fiscal state makes the economy
  less credit-cycle-driven, so credit-output comovement falls. (Fix 2 recovered T7 anyway.)
- **Corrected over-attribution #1 (missing supply side):** an early diagnosis blamed the net-negative on the
  absent supply side (no public investment raising productivity). Real *limitation* (our government "spends"
  but doesn't "build"), but NOT the cause — pure tax-and-spend is genuinely positive in a demand-starved
  economy (and is, early). Deferred as a genuine future improvement, not a bug.
- **Corrected over-attribution #2 (procurement concentration):** the leading "government funnels procurement
  to the biggest firms → concentration → long-run u" story was **falsified**. (a) **Competitive procurement**
  (buy cheapest) was NULL — the government is a *minority* of demand. (b) The concentration is HOUSEHOLD-side
  (households buy by attractiveness, never price, §28.5) — but making household demand **price-sensitive**
  (∝ attr^β/price^ε) was ALSO null: over 4000 ticks the Gibrat attractiveness spread reaches orders of
  magnitude, so price^ε (prices vary a few ×) can't counter it. (c) Worse, **concentration→u itself is not
  established:** varying β left firm-output-Gini pinned at ~0.94 while u ranged 0.36–0.51, and the within-run
  corr(Gini,u) is only +0.29 (and that Gini is confounded by ~140 idle firms). So the T6 failure is real and
  robust, but it is **not shown to cause** the long-run u.
- **The long-run u degradation is UNPINNED.** Hypotheses tested and refuted/unsupported (~6): household
  insolvency (~4/1000, households *gain* money share), inflation-as-driver (halving the deficit barely moved
  u), household leverage (very-tight margin cut debt 55k→18k, u unmoved), gov-procurement concentration
  (competitive null), household price-insensitivity (ε null), firm-concentration-as-cause (β test above). It
  is a subtle Gibrat-×-government long-horizon interaction that one-shot experiments could not crack — a
  first-class **open question** needing a dedicated study, not more single guesses. One untested lead: the
  government suppresses the deep crises that, in v8.5, periodically *reset* firm concentration (u there
  mean-reverts to ~0.11; in v9 it degrades) — "stability breeds concentration," Minsky-flavoured.

### 28.5 Structural note — nobody price-competes on the demand side
Since v8.1, the goods market uses PreferentialMatch (demand ∝ attractiveness^β) for **all** buyers, so
**households do not compare prices** — a strong assumption adopted to get the Zipf firm-size law (T6).
Consumers are partly brand-driven (justifying it) but also price-sensitive (which we dropped), removing a
demand-side price brake — plausibly contributing to the v9 inflation. A more realistic demand would blend
both (∝ attractiveness^β / price^ε), keeping Zipf *and* restoring price discipline (deferred, larger change).

### 28.6 Repairs and results — §4 5/8 → **6/8**
1. **Competitive procurement (`_phase3_goods`):** gov demand now buys from the **cheapest** c-firms first (a
   tender), not via PreferentialMatch. **Result: NULL on §4** — it barely moved concentration/u/price.
   Diagnosis corrected: the government is a *minority* of demand; **firm concentration is driven by
   HOUSEHOLD preferential demand** (the majority, which never price-competes — §28.5), so re-routing the
   government's slice can't fix it. Kept anyway as a realism improvement (governments *do* tender).
2. **State-dependent deficit (`deficit_u_ref`):** the deficit target is scaled by `min(1, u/u_ref)` — full
   deficit under slack, **tapering to balance at full employment**. **Result: a real win.** It restored the
   countercyclical stabilizer (deficit ≈0 when u low, ~2% when u high), cut late-run inflation (price index
   11.5→8.2), and — the §4 payoff — **T7 flipped FAIL→PASS** (credit boom-bust comoves again, +0.04→+0.20).
   T3 improved (−0.02→+0.14, near the 0.2 bar) and T6 eased (−2.62→−1.97, Gini 0.88→0.81) but both still fail.

3. **Household price-sensitive demand (`pref_price_elasticity` ε; ∝ attr^β/price^ε):** built to fix the
   household-side concentration (§28.5). **Result: NULL on T6** — firm-output-Gini stayed ~0.92 and the
   Pareto slope ~−1.7 across ε∈{0.5,1,2}; only mild inflation relief (8→6.5). The Gibrat attractiveness
   spread (orders of magnitude over 4000 ticks) swamps price^ε (a few ×). Kept as a realistic, off-by-default
   lever (ε=0 ⇒ bit-identical); it is NOT the T6 fix we hoped.

**Net: `Config.v9()` scores §4 6/8** (fails T3 marginally, T6). Both remaining fails trace to the long-run
firm-concentration/degradation whose cause is **unpinned** (§28.4) — not reachable by any fiscal, procurement,
or demand-side lever we tried.

### 28.7 Deferred (future layers)
- **The long-run-degradation study** (§28.4): the open question. Lead to test — does the government suppress
  the crises that reset concentration? Needs firm turnover/death-rate + attractiveness-spread analysis
  (v8.5 vs v9), not another one-shot macro run.
- **Supply-side public investment** (gov spending → public capital → productivity): the missing role that
  makes real government decisively net-positive (we modeled the government that *spends*, not that *builds*).
- **Central bank (v10):** interest rate, bonds, bond interest, lender of last resort.
- Neutral+SME procurement, consumption/wealth-tax experiments, min-wage lever (built, off by default),
  `pref_price_elasticity` (built, off — didn't fix T6 but disciplines prices).

### 28.8 THOROUGH v8.5-vs-v9 diagnosis (5 seeds, proper scale, full 4000 ticks)
The definitive comparison (supersedes the scattered one-shot findings above). It answers both questions and,
in doing so, **reverses my §28.4 stance on the supply side**.

**Part B — is v9 better or worse? WORSE, on nearly every welfare/stability dimension.**

| dimension | v8.5 | v9 | |
|---|---|---|---|
| unemployment mean | 0.174 | **0.292** | worse +68% |
| unemployment sd / frac u>0.5 | 0.156 / 5% | 0.243 / **23%** | worse (4.5× deep recessions) |
| u early/mid/late | 0.05/0.28/**0.10** | 0.01/0.24/**0.42** | better early, degrades late |
| real output | 1865 | **1581** | worse −15% |
| output CV | 0.167 | **0.314** | worse 2× |
| **real consumption (welfare)** | 1881 | **1608** | **worse −15%** |
| price index (late) / inflation | 1.27 / 0.002 | **8.0 / 0.013** | worse 6× |
| income / wealth / **consumption** Gini | 0.32 / 0.72 / 0.198 | 0.34 / 0.74 / 0.198 | ≈ same |
| **household money share (§9 drain)** | 0.054 | **0.190** | **better 3.5×** |

The government's ONE win — reversing the §9 drain (households finally hold money) — is **hollow**: real
consumption is *lower* (−15%) despite the higher money share, because the inflation it causes erodes the
money and output falls. It put money in households' hands and then inflated it away.

**Part A — the T3 and T6 causal chains.**
- **T3 (credit comovement), partly realistic.** Decomposition: **firm credit turns counter-cyclical**
  (+0.01→−0.11) and **consumption de-couples** (+0.75→+0.56). The deficit supplies demand that isn't
  credit-financed, so credit stops driving the cycle. A large fiscal state genuinely is less credit-driven.
- **T6 (firm concentration) — and the crisis-reset hypothesis is REFUTED.** v9's firm sector **churns MORE,
  not less**: births +71% (1.55→2.66) AND deaths +71% (1.57→2.66), yet **half the firms survive** (129→60)
  and concentration jumps (Gini 0.80→0.95, Pareto −0.53→−1.95). So it is not "government suppresses the
  resets" (the opposite of the data) nor "procurement funnels to giants" (falsified). It is: the government's
  **inflationary, volatile environment** (price 6×, output CV 2×) kills small firms faster, only giants
  survive, and entrants churn in and die without establishing. Concentration is a *symptom of the turbulence*.

**Synthesis — one causal chain, and the corrected conclusion.**
> In a **stationary economy** (fixed productivity) a persistent government deficit has **no productive
> outlet**, so it becomes **inflation + volatility** rather than output → a turbulent environment that
> lowers real output/consumption and churns-and-concentrates the firm sector → the long-run degradation.

This **corrects §28.4**: I had said the missing supply side was "a real limitation but NOT the cause" of the
net-negative. The thorough data says otherwise — **the missing supply side IS the long-run cause.** Pure
tax-and-spend is positive *early* (demand support, u→0), but with **no public-investment outlet** the
sustained deficit inflates and degrades. A real government's deficit funds investment that grows capacity and
absorbs the injection; ours only spends. **So the government that *builds* (not just *spends*) is not a
"nice-to-have" — it is the specific fix that would turn v9 net-positive.** That is the clear next target.
*(Still not fully pinned: why deficit→inflation is so violent here (6×), and the exact turbulence→death
threshold — but the direction, magnitude, and the supply-side conclusion are now solid.)*

---

## §29 v9.1 — the SUPPLY SIDE: government investment → public capital → productivity (the FIX, VALIDATED)

**§28.8's prediction confirmed.** Giving the government the missing supply side flips it from net-NEGATIVE
(v9) to net-**POSITIVE** — and above v8.5. This is the payoff of the whole government arc.

### 29.1 Mechanism (all foundations already existed; only the last link is new)
Government investment buys real capital goods from the K-sector (cheapest-first tender), accumulating an
economy-wide **public capital stock** `K_pub` (`= (1-δ_pub)K_pub + gov capital units`, reusing the firm
capital-accumulation primitive). `K_pub` raises EVERY C-firm's productivity (Barro 1990):
```
Y_f = A · K_f^α · N_f^{1-α} · (1 + K_pub / K_ref)^γ         (K_ref = genesis private C-capital; factor ≥ 1)
```
`gov_investment_share=0` or `γ=0` ⇒ factor 1 ⇒ bit-identical. `K_pub` is a REAL stock (not money), so A5 is
untouched. Side benefit: it is demand for the chronically-sink K-sector (§11.4).

### 29.2 The welfare verdict — v9.1 wins on REAL output, REAL consumption, AND unemployment (5 seeds)
| (steady-state, real terms) | v8.5 (no govt) | v9 (govt, no supply) | **v9.1 (supply side)** |
|---|---|---|---|
| real output | 1878 | 1563 | **2582** (+37% vs v8.5) |
| **real consumption (welfare)** | 1893 | 1589 | **2612** (+38%) |
| unemployment | 0.168 | 0.299 | **0.060** |
| price index (nominal) | 1.4 | 5.2 | 13.9 |

v9 alone was *worse* than v8.5 (§28.8); **v9.1 is decisively better than both.** The public-capital
productivity boost (factor→~1.33) grows real capacity, so the deficit finally buys more real output, not
just higher prices. The one blemish is a higher **nominal** price level — but welfare is REAL, and real
output/consumption are the highest of all three. **The government that BUILDS is net-positive, as in reality.**

### 29.3 §0-ii / §0-iv HONESTY (read this before trusting the win)
The default `Config.v91()` uses **STRONG** parameters — `gov_investment_share=0.10`, `public_capital_gamma
=0.3` — roughly **2–3× the empirical anchors** (real public-investment/GDP ~4%, public-capital output
elasticity ~0.1). At the *anchored* strength the effect is a mere ~3% productivity boost — **too weak to
overcome v9's inflation/degradation in this model**. So the honest reading: the supply-side **mechanism is
validated and the direction is certainly right**, but our model needs an above-empirical public-capital
elasticity to see the flip. NOT tuned to a §4 target (§0-ii intact); tuned — openly, above-anchor — to
demonstrate the mechanism. Why our response is weak: γ~0.1 is modest, K_pub converges to a bounded *level*
(not endogenous growth), and the small K-sector bottlenecks large public investment.

### 29.4 What failed along the way (kept honestly)
- **Composition shift (fund investment WITHIN the deficit, not on top):** collapsed the economy — carving the
  investment out drove government *consumption* (the C-sector's demand floor) to zero, and the small K-sector
  couldn't absorb the investment. Reverted to on-top (investment adds to the deficit → the inflation cost).
- So there is **no free lunch**: consumption supports C-demand (inflationary), investment builds capacity
  (K-sector-bottlenecked, lagged). The real gains come from the *productivity* channel, at a nominal-inflation cost.

### 29.5 §4 and the growth caveat
`K_pub` gives a bounded productivity *level* boost (converges to steady state), so the economy is **near-
stationary with a one-time capacity lift**, not runaway growth — §4's stationarity assumptions still roughly
hold. Score: **§4 = 6/8** (same as v9 — the scorecard tests *structure*, not welfare *levels*, so the real
output/consumption/employment gains don't register). Fails T3 (now the *investment* comovement, +0.07) and
T6 (the rank-size slope came back `nan` — a **measurement breakdown**: the productivity boost + idle firms
degenerate the log-log fit, worth fixing). Notably **T4 mean u = 0.059** — near full employment, the welfare
win showing through a passing test. Read alongside the higher nominal price level.

### 29.6 Status & open items
`Config.v91()` = the supply-side frontier; government off ⇒ v8.5 8/8 preserved; `test_v91_public_capital`.
Open: reduce the nominal inflation without collapsing demand (tax-financed investment? a bigger K-sector?);
endogenous GROWTH (vs level) needs stronger increasing returns; the v10 central bank (rates + growth).

---

## §30 v9.2 — money (non-)neutrality & the indexed-startup fix

### 30.1 The question (a user challenge)
Under money neutrality, inflation is supposed to be a veil — nominal prices rescale, real allocations don't
move. So (the challenge went) our inflation should be roughly *harmless*. I first agreed. Then I **ran it**,
and retracted: **this economy is decisively NON-neutral.**

### 30.2 The test — flex the prices, watch real output move (v9.1 stack, 5 seeds)
Money is non-neutral iff a *purely nominal* knob shifts real outcomes. The cleanest such knob is Calvo price
stickiness `theta_price` (the fraction of firms that may reprice each tick) — flexing it changes nothing real
under neutrality. It changes a lot:
| `theta_price` (higher = more flexible) | real output | unemployment |
|---|---|---|
| 0.10 (sticky, the default) | 2065 | 0.264 |
| 0.60 (flexible) | **2859** (+38%) | **0.036** |
Making prices *more flexible* raises real output ~38% and nearly clears the labor market. **The real cost of
inflation here is sticky-price MISALLOCATION, not the price level itself.** Neutrality fails because the model
has four genuine nominal rigidities: DNWR (strict wage floor, δ=0, §…), Calvo price stickiness, the fixed
nominal loan rate, and the fixed nominal startup endowment. Inflation interacts with each to move real things.

### 30.3 v9.2 — isolate & remove ONE rigidity: the fixed-nominal startup endowment
Entrants get a fixed NOMINAL cash endowment (`startup_deposits`). Under inflation that buys ever fewer workers,
so late entrants are starved → die young → the incumbent tail concentrates. Hypothesis: **this artifact is the
T6/inflation-concentration link.** `index_startup=True` scales the endowment by the price level (a COLA for new
firms) ⇒ **real-invariant entry**. `False` ⇒ bit-identical. A **correctness fix, not a policy lever, not tuned**
(§0-ii): it removes a real non-neutrality regardless of what it does to any §4 target.

### 30.4 Result — NULL on concentration (the honest non-finding)
Indexing entry did **not** move the firm-size tail (5 seeds):
| | firm-size Gini | Pareto slope | real output |
|---|---|---|---|
| v9.1 (fixed-nominal entry) | 0.98 | −2.59 | 2681 |
| v9.2 (indexed entry) | 0.97 | −2.65 | 2640 |
So the startup artifact was **not** the concentration driver. **Concentration is a deep Gibrat / preferential-
attachment property** — unpinned by *every* lever tried (insolvency, leverage, inflation, procurement, price-
insensitivity, crisis-reset, and now indexed entry; §28.8 list). It stays an **open question**, logged, not
tuned away. v9.2 is kept anyway — it correctly kills one non-neutrality and is real-invariant by construction.

### 30.5 Verdict
The inflation cost that matters is **sticky-price misallocation** — a nominal friction whose proper instrument
is a **central bank** (rates, expectations), i.e. **v10**, not another fiscal lever. This corrects my initial
"inflation is probably harmless": in a model *with* nominal rigidities, it is not. `Config.v92()` = v9.1 +
indexed entry; government off ⇒ v8.5 8/8 preserved.

---

## §31 Distributional welfare metrics — the poor are the unemployed

### 31.1 Why (min_wage / subsistence were invisible)
We had labor-floor levers (`min_wage`, `hh_subsistence`) but **no metric that could see them** — every verdict
was an *aggregate* (real output, mean u). So we added a distributional block to `metrics.py` (pure observation,
**bit-identical**, no behavior touched): relative **poverty rate** (consumption < 50% of median), FGT **poverty
gap**, **bottom-decile real consumption** (Rawlsian), **log social welfare** (CRRA/utilitarian mean-log),
**Sen welfare** (mean × (1−Gini)), **income-poverty rate**, and **consumption-floor share** (≤ subsistence).

### 31.2 The verdict — re-reading the whole government arc through the bottom tail (5 seeds)
| | poverty rate | poverty gap | income-pov | **bottom-10% real C** | log-welfare | Sen | cons-Gini |
|---|---|---|---|---|---|---|---|
| v8.5 (no govt) | 0.024 | 0.281 | 0.143 | 0.535 | −0.212 | 0.76 | 0.21 |
| v9 (govt, no supply) | 0.027 | 0.306 | 0.136 | **0.312** | **−0.749** | **0.46** | 0.19 |
| **v9.1 (supply side)** | **0.008** | **0.205** | **0.058** | **0.581** | −0.274 | 0.72 | **0.15** |

- **v9 was REGRESSIVE.** Its damage (§28.8) fell *hardest on the bottom*: bottom-decile real consumption
  collapsed −42% (0.535→0.312), log-welfare −0.21→−0.75, Sen 0.76→0.46. A deficit with no supply outlet
  doesn't just shrink the pie — it shrinks it **from the bottom**.
- **v9.1 is PRO-POOR.** Income poverty **halved** (0.143→0.058), poverty rate cut two-thirds, bottom-decile
  consumption the highest of all three. The supply-side win reaches the bottom.

### 31.3 The mechanism — welfare at the bottom is an EMPLOYMENT story
The through-line: whatever moves **unemployment** moves the bottom decile. v9 raised u to 0.30 → the poor
(who are largely the unemployed) got poorer; v9.1 cut u to 0.06 → they got jobs, wages, consumption. The
productivity boost reaches the poor **through jobs, not through cheaper goods.** This is the pivotal finding
for what comes next: **the highest-leverage anti-poverty instrument in this model is the labor market.**

### 31.4 Discovery — `min_wage` was a no-op flag
Wiring check for the labor version turned up that `min_wage` **existed in `Config` but was never read** —
`plan_wage` never applied a floor. So every prior run's `min_wage` was inert. **v9.3 fixes this first** (a real
wage floor in `plan_wage`), then adds a **job guarantee** (uncapped employer of last resort) — both aimed
squarely at the employment channel §31.3 identifies. (UBI deliberately skipped: least-targeted, and §31.3 says
the lever is *jobs*, not untargeted transfers.)

---

## §32 v9.3 — LABOR welfare: the job guarantee is a state-dependent employment instrument

§31 found welfare at the bottom is an **employment** story, so v9.3 targets the labor market directly. Two
levers: the now-wired **min_wage** floor, and a **JOB GUARANTEE** (employer of last resort). Both foundations
already existed — the JG reuses the benefit's outside-money flow and the v9.1 public-capital channel.

### 32.1 Mechanism (all primitives already existed)
After the private labour market clears, the government hires **every household's residual (unemployed) labour**
at a transitional JG wage (`jg_wage_ratio · mean wage`), **UNCAPPED** — a buffer stock, the defining feature.
It is paid as **outside money** (GOV → household, exactly the benefit's flow, so A5 holds) and **replaces the
dole** for takers (the benefit nets out `jg_labor`). The public-works labour builds **public capital**
(`jg_productivity` units each, reusing the v9.1 K_pub stock). Its deficit swings **on top** of the discretionary
target — an **automatic stabilizer** (§29.4's lesson: carving spending *within* the target collapses demand;
the JG is on-top). Crucially the JG touches only **household** state — the firm-side `unemployment_rate` metric
(T4) is left exactly as-is; we add `effective_unemployment` (no-income) and `jg_employment` (the buffer size).
`job_guarantee=False & min_wage=0` ⇒ **bit-identical to v9.2**.

### 32.2 The verdict — the JG's effect scales with the SLACK it finds (battery: NC=200/NK=100/NH=2000, 4 seeds)
| (steady state) | v9 | **v9+JG** | v9.1 | **v9.3** = v9.1+JG |
|---|---|---|---|---|
| real output | 1586 | **2001** (+26%) | 2536 | **2615** |
| private u (firm-side) | 0.270 | **0.143** | 0.039 | **0.023** |
| effective u (no income) | 0.270 | **0.001** | 0.039 | **0.000** |
| JG employment (buffer) | — | **0.142** | — | **0.023** |
| bottom-10% real C | 0.304 | **0.409** (+35%) | 0.602 | **0.610** |
| log welfare | −0.746 | **−0.525** | −0.282 | **−0.251** |
| Sen welfare | 0.457 | **0.552** | 0.720 | **0.732** |
| consumption Gini | 0.199 | **0.168** | 0.139 | **0.131** |
| deficit / GDP | 0.021 | 0.049 | −0.012 | −0.005 |
| price index (nominal) | 4.05 | 5.98 | 8.96 | 8.74 |

**The JG is a state-dependent instrument — it does exactly as much as the slack requires:**
- **On the demand-starved v9 (u=0.27), it is decisive.** The buffer stock swells to **14% of the labour force**
  and works through TWO channels: (a) direct — it clears *effective* (no-income) unemployment to ≈0; (b) a
  **demand multiplier** — JG wages fund consumption → firms sell more → **private** hiring rises (u 0.27→**0.14**).
  It doesn't just warehouse the unemployed, it **reflates** a demand-starved economy: real output +26%,
  bottom-decile consumption +35%, log-welfare −0.75→−0.53, Sen +0.10, Gini −0.03. This is the direct payoff of
  §31.3 (the poor are the unemployed → give them jobs).
- **On the near-full-employment v9.1 (u=0.04), it is nearly dormant** — the buffer is only 2.3%, mopping up the
  residual the supply side left. Correct buffer-stock behaviour. It still nudges **every** welfare metric the
  right way (log-welfare −0.282→−0.251, income poverty 0.033→0.020, Gini 0.139→0.131), so **`Config.v93()` is the
  new welfare frontier** — a small strict improvement over v9.1.

### 32.3 Cost and an honest blemish
The JG is **deficit-financed and mildly inflationary** — on v9 it adds ~2.8pp to the deficit/GDP (an automatic
stabilizer, so it self-shrinks as slack clears) and lifts the price level ~48%. And a genuine distributional
nuance: **on v9+JG, relative *income* poverty ROSE (0.131→0.159)** even as consumption welfare rose across the
board — because the JG wage (0.5× mean) lifts people only *partway*, so many clear the consumption floor while
still sitting below half of median income. The **consumption**-based measures (the truer welfare read here —
what people actually eat) all improved; the relative *income* line is the one caveat. Recorded, not smoothed over.

### 32.4 min_wage, UBI, and §4
`min_wage` is now a **real** statutory floor (§31.4 fixed the no-op): it binds immediately, bypassing Calvo
(`test_min_wage_floor_binds`). It is left **off** in the default v9.3 — a wage floor's disemployment effect cuts
*against* the same employment channel, so it is kept as a separately-tested lever, not bundled into the frontier.
**UBI skipped** (least-targeted; §31.3 says the lever is jobs). §4 is not re-scored here — the scorecard tests
*structure*, not welfare *levels* (§29.5), and the JG is a welfare lever; a full §4 run on v9.3 is the natural
next check. `test_v93_labor` (5/5); off ⇒ v9.2 bit-identical; full 22-suite regression green.

---

## §33 v10 + v10.1 — the CENTRAL BANK: an endogenous policy rate, and why monetary policy is defanged here

The monetary leg of the policy triad (fiscal ✓ supply ✓ monetary ✗). §30 named it: the sticky-price inflation
cost is "the v10 central bank's job." What v10 actually revealed is deeper — in this economy, conventional
monetary policy barely works, for reasons that turned into the most instructive investigation of the arc.

### 33.1 The mechanism (v10) — one thing: an endogenous policy rate
The frozen `r_interest` becomes a per-tick **policy rate** set by a Taylor rule (tick start, from last tick's
smoothed inflation + unemployment):
```
r = clip( ρ·r_{-1} + (1-ρ)·[ r* + φ_π·(π̄ - π*) - φ_u·(u - u*) ] , 0, r_max )
```
The whole transmission was **already wired to `r_interest`** — the investment/entry hurdle (`return − r`),
equity valuation (`book + ema(π−r·book)/r`), and firm+household debt service (`r·debt`). So v10 only makes the
rate MOVE; no new stock, no new money ⇒ A5 trivially holds. `central_bank=False` ⇒ bit-identical. It is a
**rate-only** bank: no bonds/OMO/reserves/QE (all need a securities layer — PLAN_v10 §9, a deferred v11).

### 33.2 The diagnosis — a "perverse" transmission that turned out to be a real defect
First validation looked alarming: higher r → higher output. Not a bug in v10 — the rate–output relation is
**hump-shaped** (clean on stationary v8.5: output peaks at r≈0.02, contractionary on *both* sides). The
conventional sign holds on the upper branch; the **low branch** was perverse because of an over-strong
**interest-income demand channel**, whose root was a v3-bank shortcut: the bank **split collected interest
EQUALLY across all households** ("bank dividend", plumbing to close the loop) — paying interest even to
zero-deposit hand-to-mouth households (MPC 0.8, spent in full), maximising the demand injection.

### 33.3 v10.1 — pay interest BY DEPOSITS (the fix)
The correct recipient of interest is the **depositor, ∝ deposits**. `interest_by_deposits=True` routes
`payable · D_h/ΣD` (a single bank→household transfer ⇒ A5 untouched; `False` ⇒ bit-identical). On the clean
**v8.5** this **restores conventional monotone-contractionary transmission** — output now falls and u rises
with r across the range (r 0.005→0.05: output 1715→1176, u 0.25→0.47). The equal-split really was the distortion.

### 33.4 But on the FULL v9.3 stack the central bank is DOUBLY DEFANGED (the investigation)
Deposit-proportional did **not** make the full stack conventional. Two independent forces neuter monetary policy:
- **Fiscal dominance (investigation B):** v9.3's inflation is **entirely deficit-driven** — zero deficit ⇒
  inflation ≈ 0 (but u explodes to 0.48, the demand-starved economy); *any* positive deficit ⇒ inflation pins at
  ~0.012 and stays **flat** (0.011→0.012 across deficit 0.015→0.05). The deficit that buys full employment
  brings ~0.012 inflation, period. **The rate cannot reach a fiscally-set price level.**
- **The JG stabilizer (investigation C1):** the job guarantee catches workers a rate hike displaces from private
  firms — with the JG off, a hike raises u **3× more** (r 0.005→0.05: u 0.025→0.082 vs 0.014→0.040). The JG's
  automatic stabilization **absorbs monetary contraction.**
So on v9.3, higher r stays (weakly) expansionary and inflation is untouchable — a conventional Taylor rule
**cannot** work. This is a genuine macro result (fiscal dominance + an employer-of-last-resort blunting the rate),
not a modeling failure.

### 33.5 The tuned stance — 'gentle', and the honest verdict (investigation C2)
The naive default (target 0.001 ≪ the 0.012 structural level) is **pathological** — it reads "inflation far
above target" forever and permanently over-tightens (rate→0.038), worst on nearly every metric. Tuning study
(battery, 4 seeds, means + volatility vs no-CB):
| stance | infl | u | infl-vol | welfare-log | bottom-10% C |
|---|---|---|---|---|---|
| no central bank | 0.0117 | 0.025 | 0.159 | −0.262 | 0.598 |
| target 0.001 (naive) | 0.0189 | 0.059 | 0.234 | −0.215 | 0.587 |
| **gentle (t0.012, φπ1.2, φu1.0)** | **0.0103** | 0.083 | **0.150** | **−0.158** | 0.562 |
| leaning (t0.012, φπ1.5, φu0.0) | 0.0140 | 0.024 | 0.182 | −0.290 | 0.563 |

**No stance Pareto-beats no-CB** (fiscal dominance guarantees a sacrifice ratio). But **'gentle'** — target
anchored to the *structural* inflation, moderate φ — is the only stance that beats no-CB on **inflation level,
inflation volatility, AND aggregate welfare** simultaneously. That is the central bank's real job under fiscal
dominance: **stabilize, don't dominate.** `Config.v10()` adopts gentle as its default. **Honest cost:** gentle's
disinflation is **regressive** — higher u and a lower bottom decile (0.562 vs 0.598), the sacrifice falling on
the poor (the same employment channel as §31). A rate anchored to structure isn't a free lunch; it is a
dual-mandate *choice*, exposed as a live Policy lever.

### 33.6 Status, discipline, deferred
`Config.v10()` = gentle CB on the v9.3 stack; `Config.v101()` = v10 + deposit-proportional interest (the correct
bank). §0-ii: CB params anchored to real monetary magnitudes / the economy's own structural inflation, never to
a §4 target; the perverse-transmission and fiscal-dominance findings were pre-registered probes, honestly
reported (the CB is weaker than hoped). `central_bank=False & interest_by_deposits=False` ⇒ v9.3 bit-identical;
`test_v10_central_bank` (5/5), `test_v101_deposit_interest` (4/4); full 24-suite regression green. **Deferred**
(PLAN_v10 §9): bonds / OMO / reserves / QE (a securities layer, v11); a separate deposit *rate* & loan–deposit
spread (corridor); un-consolidating the CB from the Treasury. **The standing lesson:** with a monetary-financed
deficit and a job guarantee, the economy self-stabilizes fiscally, and monetary policy is left a stabilization
role at a regressive cost — a coherent, if humbling, place for the central bank to enter.

---

## §34 v10.2 — a PROGRESSIVE wealth tax (the threshold that stops taxing the poor)

### 34.1 The defect a threshold fixes
The v9 wealth tax was **flat** — `τ_w` on *all* positive net worth, including zero/low-net-worth hand-to-mouth
households. Real wealth taxes universally carry a large exemption (only the wealthy pay); ours did not. Worse,
in a demand-constrained economy, taxing a cash-poor household's tiny net worth **destroys its consumption** —
a progressive-by-name tax acting regressively. v10.2 adds `wealth_allowance` (exemption = `wealth_allowance ·
mean positive net worth`); only wealth above it is taxed. `wealth_allowance=0` ⇒ flat ⇒ bit-identical.

### 34.2 The verdict — the threshold is decisively pro-poor (v10.1 base, 4 seeds)
Same rate, threshold off vs on (exempt below 1× mean NW):
| | wealth-tax revenue | bottom-10% C | income poverty | wealth Gini | unemployment |
|---|---|---|---|---|---|
| flat 0.002 (v10.1 default) | 334 | 0.562 | 0.180 | 0.762 | 0.083 |
| **progressive 0.002 (v10.2)** | 142 | **0.614** | **0.086** | **0.714** | **0.057** |
| flat 0.02 | 2290 | 0.509 | 0.221 | 0.786 | 0.086 |
| progressive 0.02 | 1111 | **0.569** | **0.162** | **0.683** | **0.071** |

At the default rate the threshold lifts bottom-decile consumption **+9%**, **halves income poverty**
(0.180→0.086), cuts unemployment (0.083→**0.057**), and cuts concentration MORE (Gini 0.762→0.714) — for half
the revenue (only the rich now pay). Mechanism: the flat tax was **demand-destroying at the bottom** (taxing
cash-poor small savers → less spending → higher u); the threshold spares them, so demand holds and the tax
lands only where it should. A tiny cost: slightly lower output and marginally higher inflation (the spared poor
spend a little more).

### 34.3 The reframe (this corrects an earlier over-attribution)
The demand-drain investigation had found "a stronger wealth tax hurts welfare (regressive-through-inflation)."
§34 localizes that: the harm was largely the **flat** structure taxing the poor, not the wealth tax per se.
With a threshold the wealth tax is a genuinely **pro-poor** distributional tool — it drains the idle hoard and
cuts concentration *without* collateral-damaging the bottom. (It still does not "make the economy come alive":
it cannot lower inflation at constant employment or substitute for the deficit's net outside money — those
remain supply-side / fiscal questions.)

### 34.4 Status
`Config.v102()` = v10.1 + `wealth_allowance=1.0` (exempt below mean net worth) — a strict welfare improvement to
the frontier (pro-poor, lower u, less concentration). `wealth_allowance` is a **Policy** lever (the government's
live tax-progressivity dial); the tax rate stays the anchored 0.002. Anchored to real wealth taxes (all carry
exemptions; §0-ii). `wealth_allowance=0` ⇒ v10.1 bit-identical; `test_v102_progressive_wealth` (4/4); full
regression green.

---

