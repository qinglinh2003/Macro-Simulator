## 21. v8 — Household margin credit: borrowing that finally brings an asset

§20 showed household *consumption* credit brings only debt (you consume the asset; it drains to
firms). The fix (from the double-entry logic): households must borrow to buy **assets they retain**.
v8 adds **margin credit** — households borrow *against their equity* (an LTV limit) to lever into
stocks, on the full v7/v6.2 stack (cumulative; `margin_credit`, off ⇒ v7 bit-identical).

### 21.1 Mechanism
- **Levered demand.** When `margin_credit`, a household's target equity share of NET WORTH rises
  with bullishness (mean demand pressure) up to `margin_max`; buys beyond cash are funded by a
  **margin loan** capped by `margin_ltv · equity_value`. So the borrowed money buys an asset — debt
  and equity both go up, net worth is (initially) unchanged, but the position is *leveraged*.
- **Margin calls.** After repricing, a household whose margin debt exceeds the LTV on its (fallen)
  equity **delevers** — repays from cash raised by the forced sells its dropped levered target
  triggered. Fire sales feed next tick's prices (the crisis channel).
- Margin debt is **interest-only** (the consumption-debt amortisation doesn't touch it); repaid by
  sales/calls. Both conservations exact (A5 ~1e-8, per-firm float ~1e-12).

### 21.2 Finding (round 7): the first mechanism to concentrate wealth WITHOUT crushing everyone
1. **Borrowing brings an asset.** Unlike v7 (consumption debt → net-debtors underwater), margin debt
   is equity-collateralised: borrowers hold the asset against it and **stay solvent** on full net
   worth (cash + equity − debt). The original problem is solved.
2. **Leverage concentrates wealth in a bubble.** At the default appetite (`theta_equity=0.3`), a
   leveraged bubble raises the top-decile share of full net worth and the net-worth Gini (to ~0.32
   at 120 firms) versus a near-flat calm baseline — capital gains, amplified by leverage, accrue to
   whoever levered into the winners. This is the **first** layer to produce real wealth
   concentration *without* the demand collapse (v7 thrift/debt trap) or the mirror-only inertia (v6
   equity). Magnitude is scale-sensitive (clearer at moderate N).
3. **Leverage has an endogenous stability ceiling.** Push the equity appetite higher
   (`theta_equity≥0.7`) and leverage **runs away** — equity ≈ margin debt, net worth collapses to
   ~0, the economy freezes. Too much margin is self-destructive: the credit-collateral fragility,
   emergent. So the concentration lives in a bounded window between "no leverage" and "leverage
   blow-up".
4. **Margin amplifies volatility** (output CV ~0.05 → ~0.09) — the leverage/margin-call feedback is
   destabilising, the seed of the credit-collateral crisis (a full boom-bust-cascade needs multi-
   bank contagion, still out).

### 21.3 Parameter budget & acceptance
New: `margin_credit`, `margin_ltv`, `margin_max`. `Config.v8()` = v7 + margin on. **Acceptance met**
(`test_v8_margin_credit`, 5/5): v7 bit-identical off; money + per-firm-float conservation through
margin borrowing and calls; borrowing brings assets (borrowers not underwater); leverage
concentrates in a bubble; margin calls deleverage. The §21.2 findings — concentration without
collapse, and the leverage ceiling — are the substantive result: **v8 is the first layer to make
"a few get rich" happen through a realistic, conserving mechanism.**

---

## 22. §4 re-validation on the full v8 stack — 7/8, and the wealth tail finally right-shaped

Re-ran the §4 held-out validation (`validate_v8.py`) on `Config.v8()` (everything on: banks, credit,
capital, firm demographics, per-firm equity + q-investment + equity finance, household consumption
credit, **household margin credit**), 200C/100K/2000H, 4000 ticks, 3 seeds, T8 measured on **full net
worth** (cash + equity − debt). **Score 7/8** — up from v4's 6/8, and, crucially, *not bought by
breaking the others*.

| target | verdict | v8 | vs v4 baseline |
|---|---|---|---|
| T1 Phillips | ✅ | slope −0.02, corr −0.12 | weaker, still negative |
| T2 Okun | ✅ | **−0.87** | robust |
| T3 BC comovement | ✅ | I +0.75, N +0.97, **credit +0.52**, C +0.88 | credit comovement **stronger** (was +0.23) |
| T4 endogenous unemployment | ✅ | mean 0.19, range 0–**0.73** | higher & more volatile (margin) |
| T5 fat-tailed growth | ✅ | excess kurt +0.83 | ~unchanged |
| T6 Zipf firm size | ✅* | output slope −0.86 (this run); **−0.75±0.26** over 5 seeds | steepened from −0.38, but noisy + flat tail |
| T7 credit boom-bust | ✅ | lev CV 0.19, **corr +0.56** | comovement **stronger** (was +0.23) |
| T8 wealth tail | ❌* | skew +0.23, **kurt +15.3**, top-10% **0.45**, upper-tail slope −0.33 | flipped shape, but outlier-driven |

### 22.1 Margin credit did not damage the cycle regularities — it strengthened some
The risk was that leverage/margin-call volatility would wreck the business-cycle facts. It did the
opposite: **T3 (credit comovement +0.23→+0.52) and T7 (credit–output +0.23→+0.56) both strengthened**
— credit and the real cycle are now more tightly coupled, as one expects once households as well as
firms borrow procyclically. The cost is more volatile unemployment (T4 range to 0.73) — the intended
crisis seed, not a bug.

### 22.2 T6 and T8: both concentrated harder, but both have the SAME flat tail
v8 pushed both distributions toward concentration — but neither has a clean power-law *tail*, and the
diagnosis is identical for both.
- **T8 (wealth).** v4 baseline was left-skewed and thin (skew −0.53, excess kurt −0.32, top-10% 0.12
  — "everyone equal"). v8 flips it: **right-skewed (+0.23), heavy-tailed (kurt +15.3), concentrated
  (top-10% 0.45)** — leveraged capital gains build a real elite, the first realistic conserving
  mechanism to get the *right qualitative shape*. But the upper-tail rank-size slope is **−0.33**
  (flat, far from Pareto −1) and the +15 kurtosis is a **few leverage outliers**, not a smooth power
  law. So the strict criterion (skew>0.5 + clean tail) marks it FAIL.
- **T6 (firm size).** The full-distribution slope steepened from −0.38 (v4) to **−0.75±0.26** over 5
  seeds (this validation's −0.86 was a lucky draw in that noisy range) — a real concentration gain,
  but *noisy* (per-seed −0.41 to −1.19) and, again, the **upper-tail is flat (−0.32)**.

**The unification.** Both upper tails sit at ≈ −0.33 — neither firm size nor wealth is a smooth
power law; both are "concentrated body, flat/outlier tail." The single missing ingredient is the
same: **multiplicative (Gibrat) growth** — persistent proportional random growth that spreads the
top continuously into a Pareto tail instead of piling it on a few outliers. Add that one mechanism
and both T6 and T8 should convert from "shape roughly right" to "clean power-law tail" together.
T6's "✅" here is therefore best read as **borderline/noisy**, not a robust pass.

---

## 23. v8.1 — Gibrat growth closes the last gap: 8/8 held-out regularities

§22 pinned the one missing ingredient for T6 (firm-size Zipf) AND T8 (wealth tail): **multiplicative
(Gibrat) growth**, absent because firm size mean-reverts to a common accelerator target. v8.1 supplies
it, on the full v8 stack (cumulative; `gibrat_growth`, off ⇒ v8 bit-identical).

### 23.1 Mechanism (Simon/Gabaix, as a demand-allocation change only)
- **Market share as a geometric random walk.** Each C-firm carries an attractiveness `a_f`;
  each tick `a_f *= exp(σ_g·z − σ_g²/2)` (mean-preserving lognormal — a Gibrat shock, no aggregate
  drift).
- **Size-biased demand.** The goods market allocates demand ∝ `a_f^β` (`PreferentialMatch`), so a
  bigger customer base sells more → grows more, *proportionally* (β≈1 = linear preferential
  attachment). Entrants start small (`a0` = the reflecting barrier), failures exit (v4). Barrier +
  multiplicative growth ⇒ **Pareto**. It touches only *which* seller a buyer picks — money and shares
  conservation are untouched (no new invariant).

### 23.2 Finding (round 8): 8/8 — every held-out §4 regularity, for the first time
Re-validation (`validate_v81.py`, `Config.v81`, 200C/2000H, 4000 ticks, 3 seeds): **8/8**.
- **T6 much improved, near Zipf but still noisy.** Firm-size output rank-size slope **−1.25** in the
  validation (from v8's flat −0.75±0.26 and v4's −0.38). But a 3-seed σ-sweep (150C, upper tail) is
  *noisy and non-monotonic* — σ=0.02→−1.23±0.46, 0.03→−1.76, 0.05→−0.80±0.05, 0.08→−1.06 — so the
  slope lands **around** Zipf across σ rather than the σ knob setting it precisely, and it is
  measure/scale-sensitive (upper-tail −0.80 vs full −1.25 at σ=0.05). So: dramatically steeper than
  the old flat tail and genuinely in the Pareto range, **but not a clean, stable −1**.
- **T8 flips to PASS.** Full-net-worth skew **+2.11** (was +0.23 under v8), excess kurt +36 — the Zipf
  firm tail propagates to wealth through the v8 equity/margin chain, clearing the skew criterion.
- The other six hold; T5 growth is now *very* fat (excess kurt +52) and cycles/comovement survive.

### 23.3 Two honest caveats — 8/8 is not "solved"
1. **T8's tail is still not a clean Pareto.** It passes on skew+kurtosis (right-skewed, heavy), but the
   wealth *upper-tail* slope is −0.42 (vs firm size's −1.25) — the +36 kurtosis is outlier-driven. The
   throttle is §18's **ownership diversification**: the Zipf firms are broadly held (genesis split +
   portfolio rebalancing), so wealth inherits only *part* of the firm tail. A clean wealth Pareto would
   need concentrated, persistent ownership of the winners (a v8.2 hook: founders/levered buyers holding
   the Gibrat winners without diversifying).
2. **Concentration is not free.** At the default σ, unemployment rises to ~0.39 (from v8's 0.19): funnelling
   demand onto a Zipf-few firms strands labour at the losers. So 8/8 sits in a regime that is *more
   concentrated and more depressed* — the same concentration↔employment tension seen throughout, now on
   the demand side. The interesting frontier is the σ that buys a clean tail at the least employment cost.

### 23.4 Parameter budget & acceptance
New: `gibrat_growth`, `gibrat_sigma`, `pref_attach_beta`, `gibrat_entry_a0`. `Config.v81()` = v8 + Gibrat.
**Acceptance met** (`test_v81_gibrat`, 5/5): v8 bit-identical off; A5 + share conservation (demand-
allocation change only); market share disperses (Gibrat); firm-size upper tail is a steep power law
(not the flat −0.33); wealth tail steepens (modestly). And the headline: the §4 re-validation reads
**8/8** — the model now reproduces every held-out macro regularity from the micro axioms alone, though
T8's tail is outlier-driven not yet a clean Pareto, and at an employment cost.

---

## 24. v8.2 — Adaptive portfolio rebalancing: a pre-registered experiment that was falsified

§23 left T8's wealth *tail* outlier-driven (upper-tail −0.42), diagnosed (§18) as **ownership
diversification**: the Zipf firms are broadly held, so wealth doesn't inherit the firm tail. The
proposed fix — *without* imposing concentration (which would violate §0-ii) — was to apply the **B2
adaptive-expectation discipline to the one decision that lacked it: portfolio rebalancing.** Households
move only a fraction λ (`portfolio_adjust`) toward their ideal equity target each tick (partial
adjustment) instead of instant full rebalancing, so founders delever slowly and concentrated ownership
of Gibrat winners should *emerge*. λ was set to λ_I (0.25) **independently**, and the outcome
**pre-registered**: the tail should steepen to ~−0.6…−0.8, but *not* to a clean −1 (the genesis-broad-
ownership + churn ceiling).

### 24.1 Finding (round 9): the mechanism works, the effect does not survive scale — falsified
- **The mechanism is sound and §0-ii-clean.** `portfolio_adjust=1.0` ⇒ v8.1 bit-identical; λ<1
  genuinely slows rebalancing (turnover ~halves) and conserves. It fixes a real inconsistency (every
  other decision used adaptive expectations; portfolio was instant).
- **But the goal failed at scale.** At 120 firms the smoke looked promising (ownership Gini
  0.54→0.62, wealth upper tail −0.41→−0.57). **It did not replicate at the 200C/4000-tick validation
  scale: wealth upper tail −0.42→−0.40 — no steepening at all.** The 120C effect was a small-N
  artifact; the founder-concentration channel is too weak against **genesis firms being structurally
  broadly held** and **entrant churn wiping would-be-concentrated founders** before they compound.
- **And it has a real macro cost — bigger than the scorecard suggested.** A 3-seed side-by-side
  (150C, `investigate`) shows the *robust* changes are not the wealth tail (noisy) but: turnover −45%
  (the mechanism), **firms MORE concentrated** (firm-size slope −0.86→−1.40, Gini 0.85→0.92, robust),
  and — the headline — **the economy is markedly more depressed: unemployment 0.14→0.40 (+176%),
  output −28%, both robust.** (An earlier 120C smoke had u *falling* — that was a seed artifact; the
  robust sign is a large *rise*.) The scorecard slip (T3 +0.27→+0.11, T6 −1.46) is the noisy tip of
  this. So v8.2 does not *earn* the default — it depresses output for no robust distributional gain.
  The surprising channel (wealth effect is off, yet slow *equity* trading hits the *real* economy):
  it must run through the equity→investment links (q-driven investment §18 / equity finance §19) —
  slower trading reshapes the q distribution, concentrating investment onto fewer firms and stranding
  labour at the rest. That "trading speed → q → real concentration/employment" feedback is a genuine
  (unplanned) observation worth its own check.

### 24.2 What it teaches (the falsification is the value)
The pre-registration paid off: I predicted "improves but not clean," chose λ on independent grounds,
did not tune to −1, and the model **honestly said no** — even more negatively than predicted (no
robust improvement at scale). The clean lesson: **a clean wealth Pareto tail is not reachable by
making rebalancing sticky.** It requires attacking the two structural ceilings directly — **genesis
firms owned by few founders (not split among watchers)** and **lower churn / more persistent winners**
— so that the Gibrat firm tail (which v8.1 *does* produce) can actually flow to concentrated holders.
That is the real v8.3/v9 target; v8.2 rules out the cheaper route.

### 24.3 Status
`portfolio_adjust` is kept as a legitimate, more-realistic dial (`Config.v82()`), but **the canonical
frontier stays v8.1 (8/8)** — v8.2 is off by default (`portfolio_adjust=1.0`). Acceptance
(`test_v82_portfolio`, 4/4): regression bit-identical at λ=1; conservation; partial adjustment slows
rebalancing. The downstream tail effect is a §24 finding (weak, scale-fragile, falsified at scale),
deliberately not a unit threshold.

---

## 25. v8.3 — Weakening the Tobin's-q → investment channel (realism + stability), and v8.2 ruled out

The v8.2 investigation (§24) was muddied by a **spurious macro volatility**: the same config gave
u=0.14 with one seed subset and 0.40 with another. The culprit: our **Tobin's-q → investment**
channel was **over-strong and too fast** — `lambda_q=0.3` applied to the *instant, bubble-laden*
market q every tick, whereas empirically q has a **weak, sluggish** effect on investment (accelerator
+ cash flow dominate; firms ignore transient mispricing). So stock-market noise was being pumped
straight into real investment. v8.3 fixes this in two disciplined steps.

### 25.1 Step 1 — weaken + smooth q→investment (realism-justified, pre-registered)
Lower `lambda_q` (0.3→0.1) and drive investment off a **smoothed** q (`q_invest_smooth`; investment
follows `tobin_q_ema`, not the instant price). Calibrated on the empirical low q-elasticity, **not**
tuned to any target (§0-ii); `q_invest_smooth=1` ⇒ v8.1 bit-identical. **Pre-registered:** the economy
should get calmer with no regularity broken. **Confirmed (5 seeds, 150C):** seed spread of unemployment
fell **0.138→0.093 (−33%)** and of output **216→157 (−27%)**; it even ran *healthier* (u 0.35→0.27,
output +14%); and the **§4 re-validation held 8/8** (T3 credit comovement recovered to +0.32, T8 skew
*strengthened* +2.11→+3.57). A clean **realism + stability** win at no cost — over-strong q-investment
was a genuine (unplanned) volatility bug, now fixed.

### 25.2 Step 2 — with the economy calm, re-test v8.2 (slow rebalancing): ruled out
The point of step 1 was to make v8.2's effect *measurable* (the shaky scale steadied). Re-tested in
the calm v8.3 economy (5 seeds, tight spreads): **v8.2 does nothing for the wealth tail** — upper-tail
slope −0.52→−0.51 (identical), and ownership concentration does **not** rise (0.653→0.644). The
earlier "v8.2 helped / hurt" signals were all q-driven volatility noise. **Verdict: slow rebalancing is
definitively ruled out as a wealth-tail fix; `portfolio_adjust` stays off by default.** (This also
retro-corrects §24: v8.2 does *not* robustly depress the economy — that was the same q-volatility
artifact.)

### 25.3 Where this leaves T8
The wealth tail is still ≈ −0.52 (heavy but not a clean Pareto −1). Two candidate fixes are now both
**ruled out** — Gibrat propagation (§23, gives the *body* not a clean tail) and sticky rebalancing
(§24/§25). The remaining lever is the **structural** one §24.2 named: **genesis firms owned by few
founders (not split among watchers) + lower churn**, so the Gibrat firm tail can flow to concentrated,
persistent holders. That is the real v8.4/v9 target.

### 25.4 Status & acceptance
`Config.v83()` = v8.1 + weakened/smoothed q — the **new recommended frontier** (more realistic, calmer,
8/8). Mechanism defaults unchanged (`lambda_q=0.3`, `q_invest_smooth=1.0`) so v8.1 and all prior layers
stay bit-identical baselines. `test_v83_q_channel` (regression + smoother-q + conservation). The
two-step design paid off: step 1 fixed a real bug and enabled clean measurement; step 2 then cleanly
falsified v8.2 — neither result was available while the economy was shaking.

---

## §26 v8.4 — dividends pro-rata to shareholders (a correctness fix that, alone, destabilizes)

**Config:** `pro_rata_dividends` (default False ⇒ bit-identical). `Config.v84()` = v8.3 + on. Needs `per_firm_equity`.

### 26.1 The inconsistency it fixes
Since v6.1 we track *who owns what* (`h.holdings[f.id]`), yet dividends were split EQUALLY per capita
([economy.py] Phase-4 (ii)) — a "choice 甲 homogeneity" leftover from the v6 aggregate-index era. So a
100%-owner and a zero-share household received identical dividend income. Pro-rata routes each firm's
payout to ITS holders in proportion to holdings; a non-owner earns zero dividend income. The K-sector
(un-equitized) dividends have no household holders, so they stay on the equal-split path as a residual
(the homogeneity fallback for unowned equity). Money (A5) and share floats still conserve exactly.

By Miller–Modigliani the capital-gains channel was *already* pro-rata (hold more → gain more on a price
rise); only the **dividend cash** channel was broken. So this is a consistency fix, pre-registered to
**barely move T8** while genesis ownership is still diffuse.

### 26.2 Finding — in ISOLATION it is a net macro negative
- Pre-registered mechanism **confirmed**: pro-rata raises cross-household **income Gini** (dividend income
  is now concentrated). `test_v84_dividends` asserts this.
- But §4 drops **8/8 → 7/8**: **T3 credit comovement** falls below the 0.2 bar. Same-seed 5-seed: credit
  comovement **+0.31 → +0.13**; 6-seed per-seed pass-rate 5/6 → 2/6 — a systematic DOWNWARD shift with
  *smaller* variance (0.15→0.07), i.e. a real effect, **not** T3's usual seed-noise.
- Macro levels (same seeds): mean **u 0.259 → 0.295**, seed spread **×3** (0.026→0.084), output cyclical
  CV 0.22→0.35. The whole economy got **more volatile**, not just T3.

### 26.3 Mechanism — equal-split dividends were an accidental automatic stabilizer
Profit (hence dividends) is procyclical. Equal-split spread that procyclical cash to *all* households —
a "follow-the-cycle universal dividend" that propped up demand and synchronized balance sheets. Pro-rata
sends it to a few low-MPC owners instead, removing the stabilizer. Credit-component decomposition: the
procyclicality of **every** credit type falls (firm +0.16→+0.10, household consumption +0.07→**0.00**,
margin +0.07→+0.02) — concentrated dividend income **desynchronizes household borrowing** from the cycle.

### 26.4 The insight (why this matters beyond T3)
Wealth concentration (T8) and macro stability (T3, u) **trade off in a model with no stabilizers**. Real
economies get both only via the machinery we lack: fiscal transfers, progressive tax, unemployment
insurance, a central bank. Our chronic high-u, the T3 break, and the hard-to-sharpen T8 tail may be
**three faces of one gap: no stabilizer.**

### 26.5 Status
Kept, off by default. We do **not** roll back a more-correct mechanism to protect a score (§0-ii). It is
step 1 of a structural change; §27 completes it. `test_v84_dividends` (3).

---

## §27 v8.5 — founder-owned genesis (the surprise: it FIXES stability, and the reason isn't concentration)

**Config:** `founder_owned_genesis` (default False ⇒ bit-identical) + `genesis_founder_pool=0.1`
(fraction of households that may found; anchored to the ~10% real business-ownership rate, NOT tuned).
`Config.v85()` = v8.4 + on. Needs `per_firm_equity`.

### 27.1 What changed
At t=0, v6.1 split each firm's float equally among its (many) watchers — diffuse ownership. v8.5 vests
the genesis float in a minority founder class (each firm 100% to one random founder), mirroring the
run-time "funder owns 100%" rule. Pre-registered **risk**: instant rebalancing (`portfolio_adjust=1`)
may dissolve the blocks — founders sell down toward their θ_equity target.

### 27.2 Result — §4 **8/8**, and it was the OPPOSITE of my prediction
Same 5 seeds, head-to-head: **v8.4 diffuse 7/8** (T3 credit +0.13, mean u 0.274, u-range 0–**1.00**) vs
**v8.5 founder 8/8** (T3 credit **+0.29**, mean u **0.175**, u-range 0–0.85, T8 tail slope −0.87). Founder
genesis **restored T3, cut unemployment 36%, removed the total-collapse (u=1) crises, kept the clean T8
tail.** My pre-registered worry (more concentration → less stable) is **falsified**. `test_v85_founder` (3).

### 27.3 Mechanism — three cheaper hypotheses refuted, one survives
The puzzle: founder concentration **erodes** (ownership Gini converges to v8.4's ~0.82 by mid-run), so the
benefit is *not* persistent concentration. Ruling out, with data:
1. **Concentration persists** — NO. Ownership Gini early 0.33→ mid 0.78 → late 0.81, same as diffuse.
2. **Lower aggregate leverage** — NO. Steady-state margin debt ~8500 and total credit ~9000 are identical.
3. **Fire-sale cascade drives the collapse** — NO. Fire-sale volume identical (~40 mean), and
   `corr(fire-saleₜ, uₜ₊₁) = −0.13` in **both** — fire sales slightly *precede lower* u; they are normal
   plumbing, not the trigger.

**Surviving mechanism — household insolvency → demand destruction (a self-reinforcing loop).** The one
hard discriminator is **wipeouts**: diffuse genesis ends with **173/2000 (8.7%) households insolvent**
(net worth ≤ 0) and max individual leverage **52×**; founder genesis **36 (1.8%)** and **14×**. Chain:
diffuse genesis makes every household a small, **homogeneous, levered** holder → a crash wipes out many at
once → wiped-out households are **demand-dead** (B1 wealth term ≤ 0) → aggregate demand collapses →
**deeper/longer recessions** (time with u>0.5: **21% vs 5%**; u>0.9: **2% vs 0%**) → prices crash more →
more wipeouts. Founder genesis endows equity in *unlevered* founders and leaves most households
equity-light, so far fewer are exposed enough to ignite the loop.

*Honest caveat:* the softest link is *why* diffuse over-levers — attributed to homogeneous synchronized
exposure; the OUTCOME (5× more wipeouts → demand destruction) is directly in the data, the ignition detail
is not fully isolated.

### 27.4 Status
`Config.v85()` = **new recommended frontier**: §4 **8/8**, and strictly healthier than the prior v8.3 8/8
(fixed the pro-rata T3 regression, u ~0.27→~0.18, cleaner T8 tail −0.87). Nothing tuned to a target — the
founder pool is externally anchored and the 8/8 *emerged*.

### 27.5 Open items
- **Full-NW-Gini metric artifact:** `hh_full_networth_gini` collapses to ~0.05 after t≈2500 (both v8.4 and
  v8.5) while `hh_wealth_gini_incl_equity` stays ~0.70 — leverage compresses *net* worth even as *gross*
  wealth stays concentrated. Present in both modes; the min-shift normalization likely degenerates under
  negative net worth. Decide which wealth measure T8 should use.
- **Tobin-q dispersion outlier:** a single tiny-book firm can spike `tobin_q_dispersion` to ~10³ for one
  tick; harmless but a valuation floor would clean it.
- **Does founder+lower-churn persist concentration?** v8.5 alone doesn't hold the blocks. v8.6 candidate:
  founder genesis + slow rebalancing (`portfolio_adjust`<1) — would test whether persistent concentration
  sharpens T8 *beyond* −0.87. (v8.2's slow-rebalance was falsified WITHOUT founder genesis; the combination
  is untested.)

