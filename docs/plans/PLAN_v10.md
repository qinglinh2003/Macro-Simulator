# PLAN v10 — The CENTRAL BANK: an endogenous policy interest rate (a Taylor rule)

Status: **design draft for approval.** Cumulative on v9.3. New lever default-off ⇒ bit-identical to v9.3.

> **Scope warning (read §9 first).** This is a deliberately THIN central bank: it builds exactly ONE of the
> ~20 real central-bank functions — the **policy interest rate**. That is the highest-value, zero-structural-
> cost one (§0 below), and it is enough to test the inflation-anchor and T3 hypotheses. But it means v10 is
> **known-incomplete**: the entire *quantity*-tool side of central banking (bonds, OMO, reserves, QE) is
> deferred and **will require a structural refactor** (a securities layer + un-consolidating CB from Treasury).
> §9 lists every deferred function so the debt is explicit, not hidden.

---

## 0. Why this, why now, why only the rate

Three reasons converge on the policy rate as the next layer:
1. **The one unaddressed pathology is nominal inflation.** §30 isolated the real cost of inflation as
   **sticky-price misallocation** and named it *"the v10 central bank's job — not fiscal."* The v9.3 diagnostic
   shows an unanchored price level (index → ~35 over 4000 ticks). There is no monetary anchor in the model.
2. **The rate is plausibly the structural fix for T3.** T3 fails on the **investment** component (−0.13,
   countercyclical) because the countercyclical *deficit* substitutes for credit cyclicality (§28). A
   countercyclical *rate* (ease in slumps) restores procyclical investment via monetary transmission — the
   clean fix, without distorting fiscal (forcing procyclical government investment would be bad economics AND
   §0-ii tuning). Pre-registered as H2, allowed to be refuted.
3. **Sequencing (settled in discussion):** the rate needs NO new structure; the quantity tools (OMO/QE/reserves)
   are *implementation machinery for rate control in a decentralized banking system* — a problem our single-
   consolidated-bank model does not have. Building that machinery first = plumbing for a non-problem (§9).

## 1. What already exists (audited) vs what's new

**The entire monetary-transmission surface is ALREADY wired to `cfg.r_interest`** (audited in code) — v10 only
makes that scalar *move*:

| channel | site | current behaviour |
|---|---|---|
| **Investment / entry hurdle** | [economy.py:791] | firm entry ∝ `(median return − r)`; higher r ⇒ less investment. **The T3 channel.** |
| **Asset-price / valuation** | [economy.py:926], [economy.py:107] | equity value `= book + ema(π − r·book)/r`; higher r ⇒ lower valuations, Tobin's q. |
| **Cash-flow (firm)** | [economy.py:684] | firm interest `= r · debt` (A5-safe transfer, redistributed). |
| **Cash-flow (household)** | [economy.py:706] | household + margin interest `= r · debt`. |

**New (only the last link):**
- (a) `r_interest` becomes a **per-tick policy state** the central bank sets, not a frozen constant;
- (b) a **Taylor rule** that updates it from last tick's inflation (and an unemployment gap);
- (c) the read-sites read the **live** rate; when the bank is off, the live rate ≡ `cfg.r_interest` ⇒ identical.

## 2. Ontology
- **Policy rate `r_t`** — one economy-wide per-tick nominal rate, held on the `Economy`/`Policy`, updated each
  tick by the rule. It IS `r_interest`, promoted from constant to state.
- **The central bank** — in v10 it is *only* the rate-setting authority. It stays **consolidated with the
  Treasury** (the GOV account still issues outside money directly; the deficit is still monetary-financed).
  The CB's independent tool is the **price of credit**; the Treasury's is the deficit. This consolidation is a
  simplification to be revisited when bonds arrive (§9).

## 3. The mechanism — a Taylor rule with inertia and a ZLB

At the **start of each tick**, before any borrowing/valuation, set the rate from LAST tick's state (current-tick
inflation/u aren't computed yet — same pattern as the deficit rule's `_prev_u`):
```
π̄_t   = EMA(per-tick inflation, smoothing λ)          # smooth the noisy per-tick inflation
r*_t   = r_neutral + φ_π·(π̄_t − π_target) − φ_u·(u_{t-1} − u_natural)
r_t    = clip( ρ·r_{t-1} + (1−ρ)·r*_t , 0, r_max )     # inertia + zero lower bound
```
- **Taylor principle:** `φ_π > 1` (nominal rate rises MORE than inflation ⇒ real rate rises ⇒ stabilizing).
- **Countercyclical / T3 term:** `−φ_u·(u − u_natural)` — when u is high (slack), cut the rate ⇒ easier entry
  hurdle ⇒ investment recovers procyclically. `φ_u=0` gives a pure inflation-targeter.
- **Inertia `ρ`** — real central banks move gradually; also damps the noisy per-tick signal.
- **ZLB** `r ≥ 0` (the existing `r_interest ≥ 0` assert); `r_max` a sanity cap.
- **Valuation guard:** equity value divides by `r` (line 926). Use `r_val = max(r_t, ε)` there so a near-ZLB
  rate can't blow up valuations. (Implementation care point, not a new mechanism.)

`r_neutral` defaults to today's `r_interest` (0.01/tick), so the rule *deviates around the current world*.

## 4. Accounting (A5-safe, trivially)
v10 adds **no new stock and no new money**. It only changes the *value* of an existing flow (interest), which
is already an A5-safe `transfer` (firm/household → bank → redistributed to households). Changing a rate cannot
break conservation. No GOV involvement (the CB is consolidated; it issues no money in v10). A5 gate untouched.

## 5. Levers (Config + Policy; `central_bank=False` ⇒ bit-identical)
Policy (the CB's live control surface — a government/CB can move these in-run, per the interactive-sim goal):
- **`central_bank`** (bool) — master switch. Off ⇒ `r_t ≡ cfg.r_interest` ⇒ **bit-identical to v9.3**.
- **`inflation_target`** (π_target) — per-tick target, anchored to a small positive value.
- **`taylor_phi_pi`** (φ_π) — inflation response, anchored > 1 (Taylor principle).
- **`taylor_phi_u`** (φ_u) — unemployment-gap response; 0 ⇒ pure inflation-targeter.
- **`rate_inertia`** (ρ) — smoothing, anchored ~0.7–0.9.
Config (structural constants, not run-time dials):
- **`r_neutral`** (= current `r_interest` default), **`u_natural`** (reference u), **`infl_ema_lambda`** (λ), **`r_max`**.
- `Config.v10()` = v9.3 + `central_bank=True`, anchored `φ_π≈1.5`, `φ_u≈0.5`, `ρ≈0.8`, modest `π_target`.

## 6. Tick placement
- **Tick start (new, before Phase 1):** `_cb_set_rate()` updates `self._rate` from `_prev_inflation_ema`,
  `_prev_u`. When `central_bank=False`, `self._rate = cfg.r_interest` (constant) — the identical path.
- **All read-sites** (791 entry, 926/107 valuation, 684/706 debt service) read `self._rate` instead of
  `cfg.r_interest`. This threading is the bulk of the diff.
- **Metrics:** record `policy_rate`, `real_rate` (`r − π̄`), `inflation_ema`, so the rule is observable.

## 7. §0 discipline
- **§0-ii:** φ_π, φ_u, ρ, π_target all anchored to real monetary-policy magnitudes (Taylor 1993). **Pre-register
  T3 (H2) as a hypothesis to be tested, NOT a target — never tune CB params to move a §4 score.**
- **§0-iv parsimony:** promotes ONE existing constant to a state + one rule; zero new stocks, zero new money,
  zero new primitives. The transmission is entirely reused.
- **Cumulative:** `central_bank=False` ⇒ bit-identical to v9.3 ⇒ the whole chain (incl. v8.5 8/8) preserved off.

## 8. Pre-registered hypotheses

| # | Hypothesis | Expected | Falsifier |
|---|---|---|---|
| H1 | An active Taylor rule (φ_π>1) **anchors inflation** | v9.3's runaway price index tamed / bounded | inflation unchanged or worse |
| H2 | A countercyclical rate **restores procyclical investment ⇒ T3** | T3 investment comovement −0.13 → >0 | investment stays countercyclical |
| H3 | **Monetary transmission has the right sign** | a rate HIKE is contractionary (output/entry ↓), a cut expansionary | no real response (super-neutral) |
| H4 | Leaning against the cycle **reduces output/u volatility** | lower σ(u), σ(output) vs fixed-rate | volatility unchanged/higher |
| H5 | Aggressive disinflation carries a **sacrifice ratio** | higher φ_π ⇒ lower inflation but higher mean u | no tradeoff (free disinflation) |

Overarching: v10 should give the model a **working nominal anchor** and, ideally, close T3. If the rate proves
**super-neutral** here (no real traction), that is itself a clean, reportable result about this economy.

## 9. What this round does NOT do — known incompleteness & the coming refactor  ⚠️

**v10 is a rate-only central bank. It builds 1 of ~20 real CB functions. This section makes the debt explicit
so the future refactor is planned, not a surprise.** Each deferred function, why, and its build-trigger:

**Quantity / balance-sheet tools — all blocked on a SECURITIES LAYER we have not built:**
- **Government bonds / a risk-free asset** — the deficit is still *direct monetary financing* (GOV issues
  outside money). No bond market exists. *Trigger:* wanting realistic debt financing, a risk-free asset that
  reshapes portfolio/saving (may bear on T8/T3), or any tool below. **This is the big one — a v11-sized layer.**
- **Open market operations (OMO)** — needs bonds to buy/sell. Without them the rate is set *directly* (fine for
  a single bank). *Trigger:* modelling a decentralized rate that must be *implemented*, not decreed.
- **Reserve requirements / interest on reserves / a floor system** — needs a two-tier money stock (reserves ≠
  deposits). We have a single consolidated bank; `reserves` is only an accounting label today. *Trigger:*
  building multiple banks or a reserve-constrained credit multiplier.
- **Quantitative easing / balance-sheet policy** — needs assets to buy + a zero-lower-bound bind. *Trigger:*
  hitting the ZLB and wanting an unconventional tool.
- **Yield-curve control, negative rates, term structure** — need a bond term structure. *Trigger:* modelling
  maturities.

**Structural simplifications baked into v10 (each a future refactor):**
- **CB and Treasury are CONSOLIDATED** — one GOV account, monetary-financed deficit. A real refactor would
  *split* them: Treasury issues bonds, CB buys/sells them, and monetary-fiscal coordination becomes a modelled
  interaction (incl. central-bank independence). *Trigger:* studying fiscal-monetary interaction or QE.
- **One uniform rate on all credit** — firm, household, and margin debt all pay the same `r`. No spreads, no
  risk premia, no term structure, no separate deposit rate. *Trigger:* a corridor system or credit-risk pricing.
- **No deposit rate (corridor)** — deposits stay zero-interest, so there is no saving-side monetary channel.
  This is the *cheapest* future add (a deposit-interest transfer, no new structure) if a saving/§9-drain channel
  is wanted. *Candidate for v10.1.*

**Functions that are genuinely N/A to the current structure (not deferred — absent by design):**
- **Lender of last resort, bank supervision, deposit insurance** — single unfailable bank, no interbank, no
  runs. No object to act on. *Trigger:* a multi-bank financial sector.
- **Currency issuance / cash** — no cash-vs-deposit distinction. *Trigger:* modelling physical currency.
- **FX / foreign reserves / capital-flow management** — closed economy. *Trigger:* an open-economy layer.

**Already elsewhere (do NOT rebuild in the CB):**
- **Macroprudential (LTV/DTI/κ)** already lives in government `Policy`; **clearing/payments** already exist
  (CLEARING account). Whether macropru "belongs" to the CB is a control-surface question for the refactor, not
  new mechanism.

**Bottom line:** v10 = the *price of credit*, endogenized. The *quantity of money/credit* side of central
banking is a coherent, deferred second module gated on a securities layer. When that lands, v10's rate rule
slots into it largely unchanged (the rule is the same; only its *implementation* — decreed vs OMO — changes).

## 10. Build order
1. `config`/`policy`: add the levers (§5); `self._rate` state on `Economy`; `Config.v10()`.
2. `economy._cb_set_rate()` (tick start): the Taylor rule from `_prev_inflation_ema` + `_prev_u`; off ⇒
   `self._rate = cfg.r_interest`. Maintain the inflation EMA.
3. Thread `self._rate` into the 5 read-sites (791, 926, 107, 684, 706), replacing `cfg.r_interest`; add the
   `r_val = max(r, ε)` guard in valuation. Confirm off-path reads the constant ⇒ bit-identical.
4. `metrics`: `policy_rate`, `real_rate`, `inflation_ema`.
5. `tests/test_v10_central_bank.py`: off ⇒ bit-identical (regression); A5 (rate change can't break it); the
   Taylor principle holds (φ_π>1 ⇒ higher inflation ⇒ higher real rate); ZLB respected; **transmission sign**
   (an exogenous rate hike lowers investment/output — H3 as a unit test).
6. Validate: rate-path sanity (bounded, not oscillating wildly) → H1 inflation-anchor (v10 vs v9.3 price path)
   → H2 the **§4 T3 re-score** (the headline experiment) → H4 volatility → a v10 diagnostic (add a rate panel).
7. DESIGNDOC §33 (+ changelog, header). Pre-register H1–H5 in the doc BEFORE running the battery.
