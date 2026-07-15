## §35 v11 — MULTI-BANK: a realistic "loan-book banks" system (stable; a latent failure machinery)

The financial-sector arc: a single unfailable bank becomes a **system of banks** with realistic complexity —
each with its own capital, loan book, and leverage limit. **Framing (a corrected one, see 35.4):** the goal is
a *realistic banking system*, NOT a crisis demo. Real banks are well-capitalized and rarely fail; ours should
too. The failure machinery is built and correct, but **LATENT** under normal conditions — it awaits a genuine
(future, exogenous) shock. Converged scope: the cheap half (deposits stay global, no reserve/settlement tier).

### 35.1 The design — "loan-book banks" (deposits stay global)
Deposits remain a **single global pool** (payments unchanged, no interbank settlement, no reserve tier — A5
barely touched). Only the **loan book** is partitioned among `n_banks` accounts. The key trick: **a bank's
capital IS its own deposit balance** — the existing `write_off(borrower, BANK, amt)` already makes bad debt
shrink the bank's deposits; with ONE bank that buffer is the whole money supply (never fails), with N accounts
each is **finite**. `n_banks=1` ⇒ one "BANK" ⇒ **bit-identical to v10.2** (the whole v2–v10.2 chain is the
one-bank special case; 26/26 regression). Interest and write-offs route to the borrower's own bank (`bank_of`);
the redistribution total is unchanged.

### 35.2 A realistic, stable banking system
- **Well-capitalized banks:** a bank **retains ρ of its interest income** (pays out the rest as dividends, like
  a firm) → it builds an **adequate capital buffer** and is **STABLE under normal conditions** — it does NOT
  fail from ordinary idiosyncratic defaults (write-offs ≪ retained earnings). This is the realistic behaviour.
- **Heterogeneous leverage limits:** each bank draws a cap `κ_bank` (mean ± dispersion) — risk-appetite
  heterogeneity, so under stress the aggressive/thin banks fail first (selective, not uniform).
- **The leverage cap (`bank_capital_constraint`):** a bank lends only while `loan_book ≤ κ_bank·capital`. On the
  stable frontier banks are well-capitalized so it **rarely binds** (realistic — banks usually have adequate
  capital); it activates only when capital is impaired.
- **The LATENT failure machinery:** if a loss WAVE overruns a bank's capital its balance goes negative ⇒
  insolvent. **Resolution:** marked dead (stops lending), borrowers migrate (`bank_migrate_on_failure`), its
  account **keeps the negative balance = the realized loss** ⇒ A5 untouched (no money created/destroyed).
  Contagion would run through the **real economy**. All correct and conserving — but dormant absent a shock.

### 35.3 Verification — realistic, stable, frontier-preserving
- **Stable (realistic):** `Config.v11()` (n_banks=8) runs **0 bank failures** under normal conditions; banks
  are well-capitalized; output/employment/money-distribution are healthy (~v10.2).
- **Frontier-preserving:** §4 = **6/8** (same as v10.2 — T7 recovers; the multi-bank structure with stable
  banks doesn't distort credit dynamics). `n_banks=1` OR `bank_capital_constraint=False` ⇒ bit-identical.
- **The failure path is CORRECT (not just untested):** under a deliberately EXTREME stress config (many very
  thin, aggressive banks — capital frac 0.005, κ 15 — on a volatile base) banks **do** fail (~26 of 40) and A5
  holds through every failure. So the machinery is exercised and conserving; it simply isn't triggered by a
  healthy economy — exactly as a real banking system behaves.

### 35.4 A corrected course, status & deferred
**Corrected framing (kept honestly):** the first build optimised for *producing crises* — a "thin-bank" payout
(banks pay out to the bare-minimum capital = loan_book/κ) that left every bank one bad tick from insolvency, so
`Config.v11()` **chronically collapsed** (3–8 of 8 banks failing, §4 dropping to 5/8 via a broken T7). That was
**anti-realistic** — real banks don't fail that easily. Corrected to the ρ-retention payout above: banks build
capital and are stable. Lesson (general): **model the mechanism realistically; don't tune a module to manufacture
a phenomenon** — let phenomena (here, bank failures) emerge from genuine shocks, not from a fragile calibration.

`Config.v11()` = v10.2 + `n_banks=8`, `bank_capital_constraint=True` (latent), heterogeneous κ. New levers:
`n_banks`, `bank_leverage_mean/disp`, `bank_assignment`, `bank_capital_constraint`, `bank_migrate_on_failure`
(Config). `test_v11_banks` (5/5); `n_banks=1` ⇒ v10.2 bit-identical; A5 holds through failures; §4 = 6/8; full
26-suite regression green. **Deferred** (PLAN_v11 §8): an **exogenous-shock lever** (to actually stress the
banks); by-size assignment → too-big-to-fail; rate competition; deposit insurance (fiscal); and — needing the
reserve tier, a separate arc of doubtful value here (§33) — **deposit partitioning → interbank / bank runs**,
and **reserves → reserve requirements / LoLR / OMO / QE**.

### 35.5 v11.2 — realistic bank capital (Basel), and a natural-rate insight
**The realism gap in v11.** ρ-retention keeps banks stable but makes them **hoard capital without bound** — by
tick 4000 the banks hold **~2× broad money** in idle deposits (a diagnosed un-realism; real banks hold ~10% of
loans as capital, not an ever-growing cash pile).

**v11.2 — two real institutions replace the hoard** (`Config.v112()` = v11 + these, off ⇒ v11 bit-identical):
- **A Basel CAPITAL RATIO** (`bank_target_capital_ratio=0.1`): banks pay out earnings ABOVE target capital =
  0.1·loan_book (~the real bank leverage ratio) ⇒ capital is **bounded & thin** (leverage ~10, ~3% of money).
- **A LARGE-EXPOSURE limit** (`bank_exposure_limit=0.25`): a single borrower ≤ 0.25·(bank capital), Basel-style
  ⇒ banks are **DIVERSIFIED**, so a thin bank survives any single default; only a loss WAVE breaks it.
Params anchored to reality (§0-ii); the resulting failure rate is **reported, not tuned**: ~1.7/8 banks fail
(emergent), in waves, and the failures **amplify recessions through the real economy** (corr(u, banks-alive)
≈ −0.26 — a bank-crisis → credit-crunch → recession feedback; u spikes to ~0.6 in episodes).

**Two findings this exposed:**
1. **The bank hoard was propping up "realistic" unemployment.** Isolating the two levers: it is the **payout**
   (banks stop hoarding) — NOT the exposure limit, NOT the JG — that drops mean u from ~0.05 to ~0.01. v11's
   idle hoard **drained demand** (household money share 0.22, consumption 24.7k); v11.2's payout **recirculates**
   it (share 0.28, consumption +38% → 34k) ⇒ fuller employment. So v11's "healthy 5% u" was partly an artefact
   of an *unrealistic* bank money-sink.
2. **The model has no NATURAL RATE — the labour market is FRICTIONLESS.** `_phase2_labor` matches instantly, so
   whenever aggregate demand ≥ supply, u → 0. The model has genuine **cyclical / demand-deficient** unemployment
   (involuntary, from the §9 drain + DNWR) but NOT **frictional / structural** unemployment (which needs search
   frictions + worker/job heterogeneity — Mortensen-Pissarides). So **u≈0 at full demand is CORRECT for a
   frictionless economy**; the gap vs reality (~4–5% natural rate) is the missing search-friction layer. This is
   why v11.2 fails **T4** (mean u too low once the hoard-drain is gone) — an honest structural gap, not a bug.

**§4 = 4/8** on `Config.v112()` (T7 breaks — capital-constrained credit changes the cycle; T4 breaks — the
frictionless labour market has no natural-rate floor). Honest (§0-ii: a judge, not a target — Basel params not
tuned to it). `test_v11_banks` 7/7 (adds `test_v112_realistic_capital`, `test_v112_off_bit_identical`); off ⇒
v11 bit-identical; full regression green. **The realistic-banking frontier is `Config.v112()`** (thin,
diversified, bounded); v11 (ρ-hoard, §4 6/8) is kept as its predecessor. **Deferred: a search-and-matching
LABOUR layer (v12)** — an endogenous natural rate would also make the CB's NAIRU real and the JG buffer cleaner.

## §36 v11.3 — loan-rate COMPETITION: market share won on price, and emergent too-big-to-fail

The banking-layer realism arc continues (the user's "拆借、竞争" list, §35.4 deferred). v11.2 banks are realistic
in *capital* but **static in market structure**: a borrower is assigned to a bank at genesis and stays there,
and every bank charges the same rate. Real banks **compete on price** and borrowers **shop** — so market share
is *won*, not handed out. v11.3 adds that, staying inside the cheap "loan-book banks" architecture (deposits
still global — no reserve tier; deposit-side competition / interbank / runs remain for the deposit-partitioning
arc, §35.4).

### 36.1 The design — heterogeneous spreads + borrower shopping
- **A per-bank loan-rate spread** over the policy rate (`bank_spread_disp` = the cross-bank SD): each bank draws
  a spread once (dedicated RNG). It is **mean-preserving** (de-meaned to sum exactly 0) — some banks undercut,
  some charge more (efficiency / market-power heterogeneity), but the **average cost of credit is unchanged**,
  so the layer isolates the *sorting/competition* mechanism rather than shifting the rate level (§0-ii).
- **The rate a borrower pays** = `max(0, policy_rate + spread_of_its_bank)` (`_loan_rate_for`), wired into firm
  and household debt service. Competition off ⇒ the plain policy rate ⇒ **bit-identical**.
- **Borrower shopping** (`shop_bank`, in `grant_loan`): a **debt-free** borrower seeking its first
  origination samples `bank_search_m` rivals (search friction — imperfect information) and chooses the cheapest
  bank with capacity; the assigned incumbent remains eligible. Once ordinary debt or a mortgage balance exists,
  every top-up remains with that creditor. The earlier implementation moved the borrower's entire relationship
  map and existing debt between loan books without a payoff, refinance, loan sale, or reserve/cash consideration;
  the v23 integration patch removes that false asset transfer. Cheap, well-capitalized banks can still win new
  borrowers, but existing credit stocks are sticky until a real refinancing/secondary-loan rail is modeled.

`Config.v113()` = v11.2 + `bank_rate_competition=True`, `bank_spread_disp=0.003` (~⅓ of the policy rate, anchored
to real cross-bank loan-rate dispersion), `bank_search_m=2`. Off (or `n_banks=1`) ⇒ v11.2 bit-identical.

### 36.2 The result — competition concentrates the sector and raises failures (real economy insulated)
8-seed head-to-head (NC100/NK50/NH1000, 2000 ticks, `Config.v112` vs `Config.v113`), tail-mean:

| metric | v11.2 | v11.3 | reading |
|---|---|---|---|
| loan-book Gini | 0.33 | **0.50** | competition **concentrates** the banking sector (+50%) |
| loan-book HHI | 0.19 | **0.27** | well above the even-split floor 0.125 — share is **won on price** |
| loan-rate dispersion (SD) | 0.000 | **0.0025** | a real cross-borrower rate spread emerges |
| bank failures (of 8) | 1.5 | **3.1** | concentration → **too-big-to-fail fragility** (roughly doubles) |
| unemployment | 0.00 | 0.00 | **real economy untouched** |
| real output | 1298 | 1304 | flat (+0.5%) |

**The finding (emergent, reported not tuned):** price competition → winners take share → the loan book
**concentrates** → bigger banks carry bigger books → when one fails it takes **more** with it, so failures
roughly **double** (1.5→3.1 of 8). This is the classic **competition → concentration → too-big-to-fail** channel,
emerging from a price mechanism + a capital constraint, not imposed. Yet the **real economy is insulated**
(u stays 0, output flat): the fiscal deficit + JG hold demand at full employment, so bank failures here
*reallocate* credit among survivors rather than *drain* aggregate demand (the §35.5 hoard-drain channel is
already gone). A genuine exogenous shock (deferred) is what would turn this latent fragility into a real
recession — exactly the realistic ordering (build the fragile structure honestly; let crises come from shocks).

### 36.3 Verification & status
`test_v113_competition` **6/6**: competition off ⇒ v11.2 bit-identical; `n_banks=1` ⇒ v10.2 bit-identical; A5
conserves with competition on; the spreads are exactly mean-preserving; a rate dispersion emerges (≈0 off); the
loan-book HHI rises above the 1/n floor. New metrics `bank_loanbook_hhi`, `bank_rate_spread_sd`. New Config
levers `bank_rate_competition`, `bank_spread_disp`, `bank_search_m`. Full **27-suite regression green**; A5 holds.
**Deferred (still, §35.4):** the deposit-partitioning + reserve tier that unlocks **interbank lending (拆借),
bank runs, and deposit-side competition** — the next big banking-realism step.

**v23 correction.** The historical concentration estimates above were produced by the earlier
whole-relationship-switch implementation. They remain historical evidence, not a calibrated result for the
first-origination-only rule. The current rule has separate regression coverage for debt-free shopping and for
the invariant that an indebted borrower cannot change creditor through a top-up.

## §37 v11.4 — the RESERVE tier + intra-tick RTGS + interbank market: correct, and a diagnosis of why it's latent

The 枢纽. Since v3 deposits were a **single global pool** — a household's money wasn't "at" a bank — which blocks
everything on the funding side (interbank 拆借, runs, deposit competition). v11.4 **partitions deposits**, adds a
**reserve tier** with **full intra-tick RTGS settlement** (the user's explicit choice over a net-settlement
shortcut), an **interbank money market**, and **deposit-side competition**. The build is correct and conserving;
the headline result is a **structural diagnosis** of when a reserve/interbank tier can matter in this economy.

### 37.1 The architecture — a reserve OVERLAY at the one settlement choke point
The deposit ledger stays **exactly as before** (every v2–v11.3 behaviour + the deposit-A5 gate are untouched).
Reserves are a **second accounting layer**: since **every** payment funnels through `Ledger.transfer`, reserve
settlement is hooked **there** (one method, zero call-site edits) — on a payment `src→dst`, reserves move between
`settlement_bank(src)` and `settlement_bank(dst)` (customer→its bank; a bank→itself; CLEARING→a pass-through node;
**GOV→the CB**, the base-money source/sink). `create_loan`/`repay`/`write_off` need no settlement — they preserve
`R_k = capital_k + deposits_k − loans_k` by construction. **Two hard-gated conservation laws:** deposit-A5
(unchanged) **and** reserve conservation (Σ reserves = M₀). Genesis reserves = each bank's capital + its customers'
deposits (all base money; no loans yet). `interbank=False` (or `n_banks=1`) ⇒ **v11.3 bit-identical**.

**A key identity, proven and verified:** at the end of every tick the RTGS-settled reserves equal the balance-
sheet identity `R_k = capital+deposits−loans` **exactly** (drift ~7e-8). This means net-settlement and full RTGS
give the *same* tick-level reserve positions — RTGS only adds *intra-tick* granularity (a bank transiently short
mid-tick), which is the only reason to pay for it (and it needs deposit/loan/reserve backing to **follow** every
relationship switch — shopping, deposit migration, failure migration — via `move_reserves`, else the identity drifts).

### 37.2 The build (all A5-safe; `interbank=True` on the v11.3 stack ⇒ `Config.v114()`)
- **Intra-tick RTGS settlement** + per-tick **intraday-overdraft tracking** (`reserve_min`): the lowest reserve a
  bank touches mid-tick — the peak intraday funding need.
- **Interbank money market:** a reserve-deficit bank borrows from surplus banks; the **rate is endogenous to
  market tightness** (`policy + interbank_tightness·(deficit/surplus)`); interest is a plain transfer; a failed
  debtor bank's residual loss reassigns to its interbank creditors pro-rata (**contagion cascade**, a while-loop).
- **Gridlock instrumentation** (Stage 3): a would-block counter vs the intraday-credit limit
  (`−reserve_floor_frac·capital`) — no invasive payment-blocking built (see the finding: it can never fire here).
- **Deposit-side competition** (opt-in via `deposit_rate_disp>0`; ships OFF — see §37.3): banks post mean-preserving
  **deposit-rate spreads** and pure depositors **shop** (`deposit_search_m`) and migrate toward the higher rate;
  deposits being partitioned, a bank pays its OWN depositors. Absent a funding motive it degenerates (see below).

### 37.3 THE FINDING — the reserve/interbank tier is CORRECT but LATENT (a diagnosis, not a bug)
**No bank ever runs reserve-short — peak intraday overdraft is EXACTLY 0 in every regime** (default, low-, and
zero-deficit), so the interbank market, intraday funding, and gridlock **never activate**. Why (measured): total
credit is only **3.4% of broad money** (money multiplier D/M₀ = **1.03** vs a real 5–10), so nearly all money is
**base money** held as reserves; each bank sits on a reserve buffer **~20× its own per-tick payment flow**; and the
**unsterilised deficit** floods still more reserves in (Σ reserves = M₀ − GOV, ever-growing). Reserves are
hyper-abundant relative to payment flows ⇒ nothing can stress the funding side. This is the **ample-reserves
regime** (post-2008), pushed to an extreme by **thin credit + no bond sterilisation**. The whole funding-liquidity
complex (interbank, gridlock, and the *funding motive* for deposit competition) is **latent** — like v11's failure
machinery — and activates only in a **scarce-reserves** regime: a future **bond/securities layer** that sterilises
the deficit's reserve injections (its true purpose, revealed here), or much thicker credit. Reported, not tuned.

**Deposit-side competition ALSO lacks a genuine driver here — and DEGENERATES** (a third face of the same root):
with reserves hyper-abundant, banks don't need deposits to fund loans, so there is no equilibrating force behind
an imposed exogenous deposit-rate spread. Forced on, depositors all pile into the top-rate bank — **deposit-market
HHI → ~1.0 (monopoly)** and the sector **collapses** (7–8/8 banks fail over a long horizon), regardless of a
congestion damping term. So it ships **OFF** (`deposit_rate_disp=0`): the machinery exists and conserves, but it
cannot produce a realistic result absent a real funding motive. Deposit competition, like interbank lending, needs
a **scarce-reserves** regime (a bond layer) where deposits genuinely fund lending. **The clean v11.4 deliverable is
the correct, conserving reserve/RTGS/interbank INFRASTRUCTURE** — not an active funding-side phenomenon, which this
economy's structure cannot yet support.

### 37.4 Verification & status
`test_v114_interbank` **7/7**: `interbank=False` ⇒ v11.3 bit-identical; `n_banks=1` ⇒ v10.2 bit-identical;
deposit-A5 conserves with the overlay on AND through interbank contagion; reserves conserve (Σ=M₀) AND the RTGS
settlement matches the `R_k=cap+dep−loans` identity each tick; the interbank market is latent (peak overdraft ≈0,
no gridlock); and deposit competition degenerates when forced on (so the shipped default stays near the even-split
floor — it's off). New Ledger primitives (`enable_reserves`,
`_settle_reserves`, `move_reserves`, `reset_intraday`, `assert_reserves_conserved`); new metrics (`bank_reserves_total`,
`cb_reserves`, `interbank_rate/volume`, `interbank_contagion_loss`, `peak_intraday_overdraft`, `payments_gridlocked`,
`bank_deposit_hhi`); new Config levers `interbank`, `interbank_rate_base`, `interbank_tightness`, `reserve_floor_frac`,
`deposit_rate_disp`, `deposit_search_m`. Full **28-suite regression green**; both conservation laws hold.
**Deferred (now well-motivated): a BOND/securities layer** — sterilises the deficit's reserve flood ⇒ scarce
reserves ⇒ the interbank market + gridlock activate ⇒ and it hands the CB OMO/QE. Also **bank runs** (need a
depositor-flight rule on the same partitioning).

## §38 v11.5 — bank DEMOGRAPHICS & OWNERSHIP: entry, equity + a bank-stock market, and runs

The gap a user spotted: banks only ever **died** (insolvency → dead → borrowers migrate to survivors), never
**born** — so the count decayed monotonically toward oligopoly. v11.5 gives banks the firm-style **entry/exit +
ownership** structure: banks are **founded by owners** (de novo), **owned** (profit → shareholder dividends via a
tradeable **bank-stock market**), and can die from a **run** as well as write-offs. It completes the firm↔bank
symmetry. Four opt-in sub-flags, each off ⇒ bit-identical; A5 + reserve conservation + bank-**share** conservation
all hard-gated.

### 38.1 A — equity-ification + a full secondary bank-stock market
- **Ownership:** each bank has `shares_outstanding` + `owners`; genesis banks vest in a **founder class** (v8.5).
  **Bank profit → OWNERS** as dividends (was: to depositors). **Bank equity enters household wealth** (metrics +
  the wealth-tax base); on **failure** price → 0, owners wiped (first-loss).
- **A flagged distributional shift (a finding, not plumbing):** redirecting bank interest income from **depositors**
  (broad) to **owners** (a concentrated founder class) makes bank profit a **wealth-concentration channel** and,
  by draining broad demand, *raises* failures (≈2→4) — a real, reported effect.
- **The market (full v6-style, per bank):** households target `bank_theta_equity` of wealth in bank stock
  (fundamentalist + chartist demand), each bank's price **gropes** on its own excess demand, trades are pro-rata
  rationed and settled via CLEARING so **shares AND money conserve** (drift ~1e-14; reserves settle buyer's
  bank→seller's). The chartist term bubbles/crashes prices away from the fundamental — the **run trigger**.
  Result: prices trade at 0.7–1.0× their own peak (live distress signals), and founder ownership **deconcentrates**
  to the whole population via trading.

### 38.2 B — de-novo bank ENTRY (profit-driven), calibrated for REALISTIC LOW churn
When the banking sector's **ROE beats the policy-rate hurdle**, a household with ≥ `bank_min_capital` **founds** a
bank (A5-safe transfer; the reserve backing follows to the new node) and **owns it 100%**; the entrant **undercuts**
on the loan rate to break in and win borrowers via v11.3 shopping. A **congestion** term makes chartering rare +
self-limiting. **A CALIBRATION lesson (a user caught it):** the first cut used a low capital gate
(`bank_min_capital=200`) → **thin entrants that failed fast** → an unrealistic **near-total turnover** (116 births
/ 108 deaths over 4000 ticks — 87% of all banks ever created had died; banks churned like *firms*, whereas real
banks are long-lived and both failures + de-novo entry are RARE). **Fix (a sweep, `min_capital`×`entry_beta`):**
`bank_min_capital` is the dominant lever (it's founder-wealth-gated) — anchoring it **HIGH (1500, ~2× a genesis
bank's capital)** makes entrants **well-capitalised ⇒ they SURVIVE**, cutting churn **~12×** to a realistic
regime: at the diagnostic scale (200C/100K/2000H, 4000 ticks) **~9 births / ~11 deaths, count stable ~6** — banks
long-lived, entry rare, failures few. Entry OFF ⇒ the count only decays. (`bank_min_capital` is founder-wealth-
constrained, so smaller economies sustain fewer banks — realistic consolidation.)

### 38.3 C — bank RUNS (queued withdrawals; flight active, liquidity-suspension latent)
Depositors flee banks of low **HEALTH** — a blend of the **market** signal (share price / recent peak, the
2008-style stock crash) and the **book** signal (capital / loan book) — amplified by a system-wide **FEAR** level
(panic contagion). A run executes as a **QUEUE** (like `_phase2_labor`): fleeing depositors are served sequentially
from the bank's **OWN reserves** (loans are illiquid; **interbank FROZEN** — no one funds a bank being run); when
reserves are exhausted the bank **SUSPENDS** and fails from **illiquidity**. **Honest scope (the recurring fact):**
with credit thin, banks are nearly fully reserved (reserves ≈ deposits), so the queue rarely exhausts reserves ⇒
**liquidity-suspension is LATENT**; the **active** halves are the **flight** (weak banks bleed deposits — ~17k
cumulative over ~90 episodes at NH1000) + the **fear/acceleration** of already-weak banks toward failure (alive 3
vs 6 with runs off). Full liquidity crises await scarce reserves (the bond layer).

### 38.4 Verification & status
`Config.v115()` = v11.4 + all four sub-flags. `test_v115_bank_demographics` **6/6**: each
sub-flag off ⇒ prior bit-identical; A5 + reserve + **share** conservation hold through dividends, trading, entry,
and runs; entry founds banks + sustains the count (off only decays); dividends reach owners (bank-ownership Gini
> 0); runs produce deposit flight. New Bank fields + Ledger reuse; new metrics (`bank_births/deaths`,
`bank_equity_total/gini`, `bank_deposit_flight`, `bank_fear`, `bank_min_price_peak`, `bank_stock_turnover`); new
Config levers `bank_equity(_lambda/_trading)`, `bank_theta_equity`, `bank_dynamics`, `bank_min_capital`,
`bank_entry_beta/_max`, `bank_runs`, `run_sensitivity/_health_ref/_market_weight/_fear_persistence`. Full
**29-suite regression green**. **Deferred: the BOND layer** (activates the interbank market, gridlock, AND runs'
liquidity-suspension) + deposit insurance / resolution funds (temper the now-realistic contagion).

## §39 v12 — the SECURITIES arc: un-consolidate the CB, issue BONDS, sterilise reserves

The keystone tier (PLAN_v12, **hardened over 4 accounting-review rounds**). It un-consolidates the central bank
from the Treasury and finances the deficit with **bonds**, whose purpose is to **sterilise reserves** ⇒ turn them
scarce ⇒ activate the funding-side machinery left LATENT in §37/§38. Built in small stages; v12.0 + v12.1 landed.

### 39.1 The accounting (the review's core corrections)
*Government bonds are NOT a stock-market overlay* — a bond is at once a Treasury liability, a CB asset, a bank
asset, a household asset, and a reserve tool, and the bookings must differ. The load-bearing rules:
- **A bond has THREE values, each used in exactly one identity: FACE** (the bond identity `Σ holdings@face =
  outstanding`), **BOOK/carrying** (the bank-money invariant), **MARKET** (wealth / bank `economic_capital` only).
- **A bank buying a govt bond CREATES money** (like a loan) ⇒ `ΣD − ΣL − Σ(bank-bonds@book) = M₀`; a **household**
  buying is a deposit↔bond swap (money-neutral). *(bank bonds arrive at v12.2.)*
- **MASTER conservation (mix-independent, at book/nominal):** `private NFA (ΣD_priv − ΣL_priv + private bonds) =
  M₀ + cumulative deficit = government total net liability`. The single-number M₀ is a special case.
- **Un-consolidated structure:** `TSY` (fiscal deposit account, replaces GOV) + `CB` (reserves = liability;
  bonds + claim-on-TSY = assets); the **TGA** = the Treasury's account at the CB (the same cash as `D_TSY` seen
  from the reserve side — *not* a second asset). `bonds=False` ⇒ TSY≡GOV ⇒ bit-identical to v11.5.

### 39.2 v12.0 — un-consolidate (a bit-identical refactor)
`GOV` splits into `TSY`+`CB` behind a `_fiscal` account id; the CB balance-sheet scaffolding (TGA, cb_claim, bond
overlay) + the three securities-identity gates run as **no-ops** when there is no issuance. `Config.v12(bond_
finance_frac=0)` is **bit-identical to v11.5** (the fiscal account merely renamed TSY). (No diagnostic — a
bit-identical version's plot carries no new information.)

### 39.3 v12.1 — households hold PAR bills; the corrected finding (an artifact caught via the diagnostic)
The Treasury targets holding `bond_finance_frac` of its debt as **one-period PAR bills** (`face=book=market`,
coupon 0 — no `p/x`/duration yet), issued to / redeemed from households (deposit↔bill swaps whose RTGS leg drains
bank reserves to the CB). All four gates hold every tick (deposit-A5, reserve conservation, bond identity, master
NFA). **A first cut allocated bills pro-rata to ALL household deposits — and the diagnostic caught an ARTIFACT:**
it drained households' *transaction* balances (money share 0.19→0.03), and since B1 consumption is cash-capped on
deposits (bills aren't spendable here), **demand collapsed — u 0.007 → 0.35** as f 0→0.9. That is not economics,
it is the minimal mechanism starving transactions. **FIX:** bills are bought only from households' **IDLE SAVINGS**
(deposits above a transaction buffer ≈ expected income), so transaction balances are preserved ⇒ **no artifact**
(u stays ~0.001–0.02 across all f). **The honest consequence:** household idle savings are a **small pool** (~10%
of the debt), so **household bond-financing — and its sterilisation — is MODEST** (bonds barely rise with f; they
are savings-capped, not f-capped). **The strong reserve drain must come from BANKS** (v12.2): banks hold the
excess reserves (§37) to absorb the *bulk* of the government debt into bonds. So the interbank keystone awaits
**v12.2** (banks buy bonds with reserves ⇒ real drain) **+ v12.4** (OMO drains below M₀). *(The earlier "reserves →
M₀ floor" reading was the artifact version — draining transaction deposits, not real sterilisation.)*
`Config.v12()` = frac 0.9 (a policy target, savings-capped in v12.1); off (or frac=0) ⇒ bit-identical.

**A SECOND artifact caught by the standing diagnostic (→ v12.1-fix, bill ROLLOVER).** Over a *long* run the
idle-savings version still bled: by 4000 ticks u climbed to **~0.25 at f=0.9** (vs ~0.02 at f=0). A f=0-vs-0.9
time-series decomposition pinned the cause — and it was **NOT** bank crowding-out (my first guess): `banks_alive`
dips mid-run but **RECOVERS to ~4.5**, *higher* than f=0's, so the sector is not the late driver. The real cause is
a **freeze RATCHET**: the old single `_phase_debt_management` targeted a STOCK (`0.9·gov_debt`) and only netted the
gap, so once bought, bills **never matured back to deposits**. Idle savings were locked into non-spendable,
zero-coupon bills *permanently*; the `α2·D` wealth term of B1 consumption withered; and — because the sweep buffer
`max(y_expected,·)` shrinks as income falls — a **downward spiral** (bond stock ratcheted to **3.06M**; crucially
`gov_debt` stayed IDENTICAL to f=0, proving the damage was pure private-liquidity *composition*, not any fiscal
difference). **FIX = honour "one-period bill" literally.** Split the phase in two: `_phase_bill_maturity` redeems
EVERY bill to deposits at the **top** of the tick (before planning), so for the whole tick the holder carries pure
deposits — bills now feed consumption, the goods-market live-deposit cap, equity/bank-stock buys, and start-up /
founding capital **with no change to the deposit-only behavioural code**; `_phase_bill_issuance` re-sweeps only the
genuine *end-of-tick* idle, now over a **thicker buffer** `max(2·y_expected, d_household0·price)`. **Result: f=0.9
is bit-identical to f=0 in u, banks_alive, AND gov_debt across all four 1000-tick windows** (the pre-registered
prediction, confirmed) — the "stone" became "cash". This made the once-planned haircut / `_make_cash` liquidity
bridge **unnecessary** (dropped). **New honest consequence:** once bills are intra-tick liquid *and* pay no coupon,
households have no reason to hold them OVERNIGHT, so the bill stock collapses to a thin **residual (~33k, ~0.5% of
debt, vs the frozen 3.06M)** — sterilisation is now minimal. A *meaningful* bond stock (a genuine safe asset + a
real sterilisation lever) needs the **demand** side — coupon income + portfolio choice (`bond_theta`) — which is
**v12.3**; and it will now grow the stock **without re-freezing**, precisely because bills are liquid. *(This
supersedes the earlier "bank-deposit crowding-out" reading of the late-u dip — that channel is real but secondary
and mid-run; the dominant driver was the freeze ratchet, now removed.)*

### 39.4 Verification & status
`test_v12_bonds` 3/3 (bit-identical at frac=0; all four identities hold with bills active; **no demand artifact** —
raising f keeps u low). Bill ROLLOVER phases `_phase_bill_maturity` (top of tick) + `_phase_bill_issuance` (end),
both no-ops at frac=0 (bit-identical preserved). New Config levers `bonds`, `bond_finance_frac`, `bond_coupon`,
`bond_theta`; new ledger scaffolding
(`_fiscal`, TGA, `cb_claim_on_tsy`, `_bond_holdings`, `_bonds_outstanding`) + the securities gate; new metrics
(`bonds_outstanding`, `hh_bond_wealth`, redefined `gov_debt`, corrected `bank_reserves_total`=BANK-side). Full
**regression green (all 30 test scripts)**; pre-registered f=0-vs-0.9 time-series check confirmed (post-rollover u
tracks f=0 bit-for-bit across four windows).

### 39.5 v12.3 — bonds become a REAL asset: maturity + coupon + a household portfolio + the bank balance sheet (SVB)
v12.3 folds in what was v12.2+v12.3 of the plan (PLAN_v12.3.md). Bonds gain **maturity, a coupon, and a market
price**, so the **three values finally diverge**: `_bonds` is now a list of LOTS `{holder, face, cost, matures_at}`;
`price(face,n,r,c) = c·face·Σ(1+r)^−k + face·(1+r)^−n` (a rate HIKE with `n>1` ⇒ `market < face`). Built in gated
sub-steps, every new lever off ⇒ the v12.1-fix economy (`test_v123_off_bit_identical`), `bonds=False` ⇒ v11.5.

**A+B (households, SHIPPED ON).** A per-period **coupon** (`bond_coupon`, a fiscal expense that adds to the
deficit) gives bonds a reason to be held; households target `bond_theta` of wealth in bonds, funded from
post-consumption surplus over a thinner buffer (justified because bonds now pay a coupon, enter the B1 wealth term,
and mature/roll ⇒ **liquid**). **Pre-registered #2 confirmed:** making bonds a real held asset does NOT re-freeze
demand — late u stays at the frac=0 baseline (`test_v123_coupon_theta_conserve_no_refreeze`). Honest scope: the
household stock is inherently surplus-limited (a deliberate ~θ share, not a runaway), so a bond has three tracked
values but households alone can't build a large book — that is intrinsically a BANK phenomenon.

**C — the LEDGER REFACTOR (the hardest accounting in the arc).** A bank cannot buy bonds "with reserves" as a
deposit transfer: its own deposit-capital is ~0 (v11.5 pays profits out as dividends) and reserves are a DERIVED
overlay of the deposit ledger (`R_k = capital+deposits−loans`). So reserves/securities are promoted to first-class:
a new `bank_buy_bond_with_reserves` primitive (reserves drain bank→CB ⇒ **sterilisation**; the Treasury is credited
spendable funds ⇒ **money creation**; `_bank_securities += amount` offsets), the core **A5 gate is redefined to
`ΣD − ΣL − _bank_securities = M`** (=old gate when `_bank_securities=0` ⇒ every existing config bit-identical), the
master-NFA gate subtracts `_bank_securities`, and `bank_redeem_bond` unwinds it at maturity. **All four gates hold
through banks buying/redeeming bonds via money creation (identΔ ≈ 3e-13).** `economic_capital = ledger.balance +
Σ(market − cost)` (unrealised P&L only — the bond is deposit-funded) is wired into the leverage cap, the exposure
limit, and the insolvency trigger.

**D — SVB duration channel (wired + proven; live activation DEFERRED to v12.4).** A rate hike marks a bank's
multi-period bonds below cost ⇒ `economic_capital` thins ⇒ crunch/insolvency — proven in a controlled test
(`test_svb_duration_channel_and_bank_securities_conserve`). **Honest finding (the reason `bank_bond_appetite=0` by
default):** turning the live bank drain ON collapses the sector at ANY positive appetite — banks are **thinly
capitalised in equity** (~tens) but a bond book is thousands, and the CB's Taylor rule swings the policy rate to
5–7% vs a 1% coupon ⇒ enormous MTM losses instantly wipe the tiny equity buffer (**exactly the 2023-SVB structure**),
while draining reserves to scarcity cascades the §37/§38 run/gridlock machinery with no Lender of Last Resort. So
the bank balance sheet + strong drain + SVB are **BUILT and conservation-verified but gated OFF**; their stable
activation needs a **capital floor + LoLR + OMO = v12.4** — precisely the plan's staging. New levers `bond_coupon`,
`bond_theta`, `bond_maturity`, `bank_bond_appetite`; `Config.v123()`. New metrics (`bond_book_total`,
`bond_market_total`, `bond_mtm_pnl`, `bank_bond_face`, `bank_economic_capital_min`, `gov_interest_bill`).
`test_v12_bonds` **6/6**; full **30-suite green**; `diagnostic_v123.png`. **Next: v12.4** — LoLR + a bank capital
floor + OMO/QE, which together let the strong bank drain + SVB run LIVE (and re-latent the interbank market post-QE).

### 39.6 v12.4 — the CB's quantity tools: OMO / QE / LoLR (the interbank keystone finally BINDS; arc closed)
v12.4 (PLAN_v12.4.md) closes the securities arc. The one architectural change: the **reserve total becomes
VARIABLE** — the un-consolidated CB is the source/sink of base money. Two ledger primitives, `issue_reserves(node,x)`
/ `retire_reserves(node,x)`, move `_reserves[node]` AND `_reserve_M` together, so the gate `Σ reserves = _reserve_M`
**stays exact by construction** (=the fixed-total v11.4 gate when nothing is issued ⇒ every prior config
bit-identical); the deposit ledger `ΣD−ΣL−_bank_securities=M` is untouched (reserves are a separate overlay).

**OMO — the headline, CONFIRMED.** `_phase_omo` steers Σ bank reserves toward `omo_reserve_target`·(genesis) by
absorbing them into the CB's own instrument (reverse repo / CB bills — the modern drain, e.g. the Fed's ON RRP),
`retire_reserves` + `_cb_absorbed↑`; QE is the mirror. **Draining reserves scarce makes the §37 interbank market —
latent since v11.4 — finally BIND**: at `target=0.3` the pre-registered signal fired (peak intraday overdraft ≈11k,
`interbank_volume`>0, up from EXACTLY 0), `_reserve_M` correctly fell as base money was destroyed, all four
conservation gates held. QE re-floods ⇒ it re-latents (the post-2008 story). This is the keystone the whole arc was
built to reach.

**LoLR + the SVB floor.** In `_phase_bank_runs`, an illiquid-but-**solvent** bank (economic_capital > 0) is funded
by the CB (`issue_reserves`, `_lolr_advances`) instead of suspending — liquidity ≠ solvency, so an INSOLVENT bank
(SVB MTM wipe-out) still fails, but **alone**, not by dragging the sector into a liquidity cascade. A duration limit
caps each bank's bond book at `k·economic_capital` so a rate hike can't wipe it.

**THE BANK BLEED and its fix (user-driven).** A user flagged that the diagnostic showed `banks_alive→0`. Diagnosis
(ablation + a founder-pool trace): NOT the coupon/theta/OMO levers per se (at NH1000/2500t all configs keep 5–8
banks) but a **scale × horizon** failure of the v11.5 demographics — de-novo ENTRY was structurally DEAD (roe/r ≈
10× so the profit hurdle was fine, but `eligible_founders = 0`: at NH2000, with `bond_theta` draining deposits,
**no household clears `bank_min_capital=1500` in ANY wealth form** — deposits, +bonds, or full NW). With births ≈ 0
and a steady death rate, the count bleeds to 0 over 4000 ticks. **The fix is BOTH sides:** thicker capital
(`bank_target_capital_ratio` 0.1→**0.18**, `bank_exposure_limit` 0.25→**0.15** ⇒ fewer deaths) **and** a founder
gate the wealth distribution can clear (`bank_min_capital` 1500→**400** ⇒ births resume; 800 was still too high,
150 over-churns — the 116/108 problem). At NH2000/4000t this holds the count at **~11 (births≈deaths, low churn)**,
not 0. (A reserve-tolerance bug OMO exposed was also fixed: `assert_reserves_conserved` keyed its tolerance off the
*current* `_reserve_M`, which OMO drains small, tripping on normal float error — now keyed off the stable deposit
base money.) **Deferred (the deeper structural gap the user identified):** de-novo entry is still too
single-household-cash — it should allow **joint founding / bank IPO / bridge banks on resolution / recapitalisation
/ an indexed `bank_min_capital`**; the founder-liquidity path (`_redeem_hh_bonds`, count bonds@market toward
eligibility) is in place but insufficient alone.

`Config.v124()` is now the **HEALTHY** default (gentle OMO `target=1.0`/`drain=0.03` + a light short bank book
`appetite=0.03`/`duration_limit=0.5`/`maturity=4`); `Config.v124_stress()` is the interbank-activation STRESS test
(`target=0.3`, heavy long book — deliberately exhibits overdrafts + SVB failures). **Honest scope:** the clean
verified win is **OMO→interbank activation** + the conservation-safe CB balance sheet; the real economy is
fiscally insulated throughout (JG + deficit hold u≈0.01–0.05 across all bank outcomes). New levers `omo`/
`omo_reserve_target`/`omo_drain_frac`/`lolr`/`bank_bond_duration_limit`; new metrics (`cb_absorbed`, `omo_flow`,
`lolr_advances`, `reserve_M`); `test_v12_bonds` **9/9** (reserve create/destroy conservation, LoLR funds-a-solvent-
bank, off⇒bit-identical); full **30-suite green**; `diagnostic_v123/v124.png`. **The securities arc (v12.0–v12.4)
is CLOSED.** Next major direction (§0-ii health lever, not more plumbing): **v13 — a search-and-matching LABOUR
layer** (an endogenous natural rate ⇒ T4).

---

## §40 v23 integration patches — creditor ownership, common RWA, and external settlement

The v23 review found several places where an aggregate scalar was correct in isolation but
attached to the wrong institution when subsystems met. The patch set keeps historical paths
default-off where behavior changes, while making the diagnostic frontier exercise the corrected
composition.

### 40.1 A loan stock cannot change owner through a relationship-map write

With `bank_relationship_lock_in=True`, loan-rate competition still lets a debt-free borrower
compare the assigned incumbent with a search sample before the **first** origination. Once ledger debt or a mortgage balance exists,
the relationship is sticky: a top-up is funded by the current creditor. This is a deliberate
contract boundary. Moving the whole outstanding scalar between `_loan_book` entries without a
payoff, refinance, loan sale, or consideration/reserve leg was not competition; it was an
unbooked asset transfer. A future refinancing layer must create the new creditor's asset, settle
the old claim, preserve borrower contract terms, and route the cash/reserve legs explicitly.

Mortgage principal remains a shadow composition inside the borrower's aggregate ledger debt.
Ordinary principal repayment now reduces that shadow pro rata in the normal path so secured and
unsecured RWA do not drift merely because a later consumer loan reused the same scalar. This is a
bridge, not a substitute for typed contracts.

### 40.2 One bank risk budget and a realized income statement

With `unified_bank_rwa`, ordinary firm/consumer exposure receives a 100% risk weight and mortgage
exposure receives `mortgage_risk_weight`; both consume one capital-based RWA limit. Gross leverage
and large-exposure caps remain additional constraints. Bank profit closes realized loan interest,
bond coupons, interbank interest income and expense, and realized credit losses before dividends.
These corrections stop the mortgage book and credit-loss journal from living outside the bank
whose capital they consume.

This is still not a complete bank funding model. `interest_by_deposits` distributes payable
profits according to deposit holdings; it is not contractual deposit interest posted by account
and bank. There is therefore no deposit funding-cost curve, and the reported bank result must not
be read as a fully specified net interest margin.

### 40.3 The external sector is not the first commercial bank

Cross-border factor-income service now uses the Treasury/central-bank account when government is
present and an explicit, negative-capable `EXTISSUER` account otherwise. The aggregate NFA
liability no longer lands on the first live commercial bank or its P&L. Separately, `FXDEALER`
always resolves to the neutral `CLEARING` reserve node. A cached resolver therefore stays valid
through bank failure, and changing bank list order cannot change the dealer's settlement
counterparty.

These two accounts are intentionally aggregate. They identify a conserving issuer and settlement
node but do not say which households, firms, banks, or sovereign entities own each external asset
or owe each liability. External principal still lacks instrument type, maturity, seniority,
default, restructuring, and owner-level income allocation; the current World diagnostics should
report that as an aggregate-external-ownership scope limit.

### 40.4 Boundaries carried forward

The banking/finance stack is materially more coherent, but four related layers remain future
work: typed loan contracts and vintages (including fixed/floating repricing and refinancing),
contractual deposit funding cost, collateral priority/liquidation/recovery, and inventory-cost
lots that match COGS to sales. The priced inventory and borrowing-base proxy are decision and
valuation inputs only; they do not yet create a recovery claim or turn current production cash
cost into accrual inventory accounting.

---
