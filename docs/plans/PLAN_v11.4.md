# PLAN v11.4 — deposit partitioning + a reserve/funding tier + INTERBANK LENDING (拆借)

The 枢纽 (the pivotal layer). Everything downstream the user named — 拆借 (interbank), 挤兑 (runs),
存款竞争 (deposit-side competition) — is blocked by ONE simplification we've carried since v3: **deposits are a
single global pool** (a household's money isn't "at" a specific bank). v11.4 partitions deposits, adds the
reserve/funding dimension that partitioning creates, and builds the **interbank market** on top. Runs and
deposit competition then become cheap follow-ons (v11.5 / v11.6) on this same foundation.

Scope discipline (as always): opt-in master switch ⇒ prior versions **bit-identical**; **A5 is a hard gate**;
params anchored to reality; emergent results **reported, not tuned** (§0-ii); parallelize all sweeps.

---

## 1. Why partitioning changes everything (the mechanism we're adding)

Today a bank faces only a **solvency** constraint (capital ≥ 0; lending capped at κ·capital). It never faces a
**funding / liquidity** constraint, because loans create deposits from nothing into a global pool — any bank can
lend regardless of where the money ends up. That's the unrealistic part: real banks fund loans with **deposits**,
and when a loan's deposit flows to *another* bank, the lender must settle in **reserves** — borrowing them if
short. v11.4 adds exactly that **funding-liquidity dimension**, and interbank lending is how reserve-surplus
banks fund reserve-deficit banks.

New realistic features this unlocks:
- a **money-market (interbank) rate** = the funding cost of a reserve gap;
- **funding-liquidity risk** — an aggressive lender whose deposits leak out pays to fund the gap (thins profit);
- **interbank contagion** — a failed borrower bank stiffs its interbank creditors (a *direct* bank-to-bank
  failure linkage, on top of v11's real-economy contagion);
- the **foundation** for bank runs (deposit flight → funding gap → liquidity crisis) and deposit competition
  (banks bid a deposit rate to shrink their funding gap) — v11.5 / v11.6.

---

## DECISIONS (from discussion) + one important caveat surfaced while designing

You chose: **(A) full RTGS reserve rebuild**, **scope = foundation + interbank + deposit-side competition**
(runs → v11.5), **endogenous tightness-driven interbank rate**.

**Caveat I have to surface before building A (the balance-sheet identity revealed it).** A and B do NOT differ in
the reserve positions they produce. If reserves are settled on every flow (A), then at the end of *every* tick a
bank's reserves satisfy **R_k = C_k + D_k − L_k exactly** — which is precisely what B *reconstructs* from the
identity. I checked every flow (loan draw, customer↔customer payment, interest, equity trade, tax/benefit): each
preserves `R_k − (C_k + D_k − L_k) = 0`. So **A and B give identical tick-level reserve positions.** The *only*
thing full RTGS (A) adds is **intra-tick** granularity: a bank can be transiently reserve-short *mid-tick* (before
a later inflow), which matters *only if we impose payment-blocking / a hard intraday settlement constraint* —
i.e. **payment-system gridlock**. That is a **bank-run** phenomenon (v11.5), needs per-payment interception of
*every* transfer site (goods, wages, taxes, dividends, equity, interest — high blast radius + A5 risk), and buys
nothing at tick granularity until runs exist.

**Crucially, none of your chosen FEATURES depend on A vs B.** Interbank lending, the endogenous rate, interbank
contagion, and deposit-side competition all run on the tick-level reserve position `R_k = C_k + D_k − L_k` — which
A and B share. So I can build **all of them now** via the identity (a genuine, explicit reserve tier at tick
granularity), and add **intra-tick RTGS settlement + payment-blocking only when v11.5 runs actually need it** —
paying the big invasive rewrite exactly when it buys something. My recommendation: **build the reserve tier by the
identity now (all your features), defer intra-tick RTGS to v11.5-runs.** Confirm, or insist on full intra-tick
RTGS up front.

## 2. THE settlement model (context for the caveat above)

### Option A — full RTGS reserve rebuild (the "correct" heavyweight)
Every deposit becomes a specific bank's liability; **every payment** (goods, wages, taxes, dividends, interest)
moves **reserves** between the payer's and payee's banks in real time; banks hold explicit reserve accounts;
a reserve-short bank borrows intraday. **Cost:** invasive — must intercept *every* `transfer` in the code
(goods market, wages, fiscal, dividends…), and each interception is an A5 risk. High blast radius.

### Option B — net funding-gap (RECOMMENDED: minimal, A5-safe, no payment rewrite)
Keep payments as global ledger transfers (unchanged, cheap, A5-safe). Once per tick, **reconstruct** each bank's
reserve position from the balance-sheet identity and price the imbalance:

> Bank *k*'s reserve position **ρ_k = C_k + D_k − L_k**
> where C_k = bank capital (its own ledger balance), D_k = customer deposits banked at *k*, L_k = its loan book.

- **ρ_k < 0** ⇒ *k* lent more than its deposits+capital fund ⇒ a **funding deficit** it borrows in the interbank
  market. **ρ_k > 0** ⇒ a **surplus** it lends.
- **The market always clears internally:** Σρ_k = C+D−L summed = **M₀ − GOV > 0** (the bank system holds base
  money + the outside money the deficit injected), so aggregate surplus ≥ aggregate deficit, always. Deficit banks
  draw from the surplus pool **pro-rata**.
- **Interbank interest** = the *only* money that moves for interbank: deficit banks pay the interbank rate on
  their gap to surplus banks (a plain `transfer` ⇒ **A5-safe**). It's a bank **expense** slotted before the
  capital-ratio payout.
- **Interbank contagion on failure:** when a deficit bank fails, its funders eat the loss — we reassign the
  failed bank's negative balance to its interbank creditors pro-rata (an A5-safe transfer; the *total* loss is
  unchanged, only *who* holds it), which can push a creditor into failure → a **cascade**.

**Honest framing:** Option B is a *net-settlement abstraction* — it prices the net reserve imbalance rather than
simulating tick-by-tick reserve flows from individual payments. It faithfully delivers the funding-liquidity
dimension, the interbank rate, contagion, and the run/competition foundation, at a fraction of A's blast radius.
A is a possible future "full RTGS" upgrade. **My recommendation: build B now.**

---

## KEY EMPIRICAL FINDING (Stage 2) → the reserve/interbank tier is LATENT here

Built Stages 1–2 (reserve overlay + RTGS + interbank market); all accounting sound (A5 2e-8, reserves conserve
1e-7, RTGS = identity exactly). **But the interbank market is structurally DORMANT: peak intraday overdraft is
EXACTLY 0 in every regime** — no bank ever runs reserve-short, not even mid-tick. Why (measured): total credit is
only **3.4% of broad money** (money multiplier D/M₀ = **1.03** vs a real 5–10), so almost all money is BASE money
held as reserves; each bank sits on a reserve buffer ~**20× its own per-tick payment flow**; and the unsterilized
deficit floods yet more reserves in (Σ reserves = M₀ − GOV, ever-growing). Reserves are hyper-abundant relative to
payment flows ⇒ the interbank market, intraday funding, and gridlock **cannot activate**. This is the ample-reserves
regime (post-2008), extreme here from thin credit + no bond sterilization.

**DECISION (from discussion): ship the honest dormant infrastructure + the ACTIVE deposit-side competition.**
- Keep Stages 1–2 (reserve tier + RTGS + interbank + contagion) — correct, conserving, and **latent** (documented
  like v11's latent failure machinery; activates in a scarce-reserves regime → a future **bond/securities layer**
  that sterilizes reserves, or much thicker credit).
- Stage 3 (intra-tick gridlock): keep the intraday-overdraft **instrumentation** + a gridlock-events counter (which
  reads 0), but do NOT build the invasive payment-blocking rewrite — it can never fire here. Honest, non-invasive.
- **Stage 4 (deposit-side competition) is the active headline** — it does NOT need reserve scarcity: banks post
  heterogeneous deposit-rate spreads, depositors migrate toward higher rates (deposit-market concentration), and
  the bank routes its payout to its OWN depositors (correct now deposits are partitioned). Mirror of v11.3.

## CONFIRMED: full intra-tick RTGS (your call). Architecture + build stages.

**Architecture that makes RTGS tractable + A5-safe:** a **reserve OVERLAY**, settled at the ONE choke point.
- The deposit ledger stays **exactly as now** — every v2–v11.3 behaviour and the deposit-A5 gate are **untouched**
  (reserves are a *second* accounting layer, not a rewrite of money). Deposit-A5 literally cannot break.
- **Every** money movement already funnels through `Ledger.transfer` (verified: `create_loan`/`repay`/`write_off`
  need no settlement — they preserve `R_k = C_k+D_k−L_k` by construction, since loan/deposit move together at the
  same bank). So I add reserve settlement **inside `transfer`**: on a payment `src→dst`, move reserves between
  `settlement_bank(src)` and `settlement_bank(dst)`; same node ⇒ no-op. **One method, zero call-site edits.**
- **Settlement nodes:** each customer → its bank (`_bank_for`, already universal over all firms+households); a
  bank's own capital account → itself; **CLEARING** → its own pass-through reserve node (dividends credit it
  before debiting, so it never goes short); **GOV** → the **CB** (base-money source/sink: taxes drain reserves
  from the banking system, spending/benefits inject them — matching Σ reserves = M₀ − GOV).
- **Two conservation invariants:** deposit-A5 (unchanged) **and** reserve conservation (Σ bank reserves + CB = M₀,
  const). Both hard-gated.

**Build stages (A5 + reserve-conservation gated at each; `interbank=False` ⇒ v11.3 bit-identical throughout):**
1. **Foundation** — deposit partitioning + reserve overlay + RTGS settlement in `transfer`, reserves free to go
   negative (unlimited intraday credit, no cost yet). Pure instrumentation ⇒ observationally bit-identical even
   ON; validate the reserve identity `R_k = C_k+D_k−L_k` and reserve conservation each tick.
2. **Interbank market + endogenous rate + contagion** — a bank with a reserve deficit borrows from surplus banks;
   the **interbank rate is endogenous to market tightness** (rises with aggregate deficit/surplus); interbank
   interest is a deposit transfer (A5-safe) slotted as a bank expense before the capital-ratio payout; a failed
   debtor bank's loss reassigns to its interbank creditors pro-rata (cascade). This feeds back ⇒ the new mechanism.
3. **Intra-tick gridlock** — a reserve floor / intraday-credit limit: a payment **blocks** when the payer's bank
   cannot source enough reserves (own + willing interbank). This is the genuinely intra-tick-dependent phenomenon
   (payment-system gridlock; the seed of liquidity crises) — the reason you chose full RTGS.
4. **Deposit-side competition** — per-bank **deposit rate**; depositors migrate toward higher rates; banks bid the
   rate to shrink their funding gap (the mirror of v11.3's loan-rate competition).
5. **Metrics + tests + diagnostic (`plot_v114.py`) + docs (§37).**

## 3. What v11.4 builds — detail

**Deposit partitioning (the foundation, used by everything after):**
- `_deposit_bank_of[agent]`: the home bank for **every** household + firm's deposits (a superset of `_bank_of`,
  which only covers borrowers). Assigned at genesis via a dedicated RNG (no main-stream perturbation), default
  aligned with the loan bank. Per-bank deposit base `D_k = Σ balance(a)` over its depositors.

**Reserve/funding tier + interbank market (the headline, 拆借):**
- Compute ρ_k each tick (a new settlement phase, after debt service / write-offs are known).
- Deficit banks borrow their gap from the surplus pool pro-rata; **interbank rate = the policy rate** (the CB's
  rate *is* the money-market rate in reality — a clean tie-in, and a NEW CB transmission channel: the policy rate
  now directly prices bank funding).
- Interbank interest flows deficit→surplus (expense/income), feeding the existing capital-ratio payout net of it.
- On a deficit-bank failure, reassign its loss to interbank creditors pro-rata (contagion cascade).

**Deliberately NOT in v11.4** (kept for the follow-ons, same foundation):
- **v11.5 — bank runs:** a depositor-flight rule (deposits move off a weak bank → its gap widens → liquidity
  distress); needs only a `_deposit_bank_of` mutation rule.
- **v11.6 — deposit-side competition:** a per-bank **deposit rate**; depositors migrate toward higher rates;
  banks bid the rate to shrink their funding gap. The mirror image of v11.3's loan-rate competition.
- A hard **reserve-requirement** funding constraint (a CB macroprudential lever) — v11.4 adds funding *cost* +
  contagion; a hard *limit* on lending beyond the deposit base is a natural later CB knob.

---

## 4. Config levers (all default-off ⇒ bit-identical)

- `interbank: bool = False` — master switch (deposit partitioning + reserve tier + interbank market).
- `interbank_rate_spread: float = 0.0` — spread over the policy rate for interbank funding (0 ⇒ money-market =
  policy rate; a small penalty could be added for stressed banks later). Anchored ~0 (money market ≈ policy).
- (deposit-bank assignment reuses `bank_assignment` = random | by_size.)

`Config.v114()` = `Config.v113()` + `interbank=True`. Off ⇒ v11.3 bit-identical.

---

## 5. Metrics (pure observation, bit-identical)

`interbank_volume` (Σ funded deficits), `interbank_rate`, `n_deficit_banks`, `max_funding_gap`,
`interbank_exposure_gini` (concentration of interbank claims), and a contagion tag (failures with interbank
losses). Keep the v11.3 concentration/dispersion metrics.

---

## 6. Tests (`tests/test_v114_interbank.py`)

- `interbank=False` ⇒ v11.3 **bit-identical**; `n_banks=1` ⇒ v10.2 bit-identical.
- **A5 holds** with interbank on, AND **through interbank-driven failures / cascades** (the loss-reassignment
  is a conserving transfer — the whole point).
- Σρ_k = M₀ − GOV (the reserve-identity invariant) holds each tick.
- The interbank market **clears** (funded deficit = drawn surplus).
- Contagion is real: under stress, a borrower-bank failure imposes losses on its funders (exercise the cascade,
  like v11's extreme-stress failure test).

## 7. Report + diagnostic (per the new standing rule)
Characterize v11.4 vs v11.3 across 8 seeds (interbank volume, money-market rate, funding-gap dispersion, failures
/ cascades, and whether the real economy stays insulated), **reported not tuned**. Ship `plot_v114.py` →
`diagnostic_v114.png` with an interbank-market row.

---

## 8. Open questions for you
1. **Settlement model: Option B (net funding-gap, recommended) or A (full RTGS)?** This is the architectural call.
2. **Interbank rate = policy rate** (money-market ≈ policy), or do you want an endogenous tightness-driven rate /
   a stress penalty spread from the start?
3. **v11.4 = foundation + interbank only** (runs → v11.5, deposit competition → v11.6), or fold one of those in now?
4. Include a hard **reserve-requirement** funding limit in v11.4, or keep it to funding-cost + contagion first?
