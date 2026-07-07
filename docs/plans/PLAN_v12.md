# PLAN v12 — the SECURITIES arc: un-consolidate the CB, issue BONDS, sterilise reserves, a traded bond market

v12 opens a new tier (the **v12.x securities arc**). It un-consolidates the central bank from the Treasury,
finances the deficit with **bonds** that **sterilise reserves** (⇒ reserves turn SCARCE ⇒ the funding-side
machinery built-but-LATENT in §37/§38 finally fires), and adds a **traded bond market** with **duration risk**
(the 2023-SVB channel). Confirmed scope: un-consolidated CB **now** + household/bank bonds + traded market +
duration. **Deferred to a later v12.x:** OMO/QE + LoLR (their foundation — the CB balance sheet — is built now).

This plan was **revised after a review** that (correctly) flagged that *government bonds are not a stock-market
overlay* — a bond is simultaneously a Treasury liability, a CB asset, a bank asset, a household asset, and a
reserve-management tool, and the four must be booked differently. The load-bearing principle:

> **The FOUR bookings that must stay distinct** (reserves always flow via the **TGA** = the Treasury's account at
> the CB, a CB-liability transit node — NEVER a vague "→CB"):
> 1. **Household buys a bond** = an asset swap on the household: **deposits ↓, bonds ↑** (a `transfer` hh→TSY;
>    RTGS settles reserves **hh-bank ↓, TGA ↑**, so the banking system's reserves drain).
> 2. **Bank buys a bond** = an asset swap on the bank's ASSET side: **reserves ↓, bonds ↑, equity UNCHANGED**
>    (it pays with RESERVES **bank ↓, TGA ↑**, NOT a deposit transfer — buying HQLA must not thin capital).
> 3. **Treasury issues a bond** = a TSY **liability ↑** (bonds outstanding), proceeds land in the **TGA**, spent next.
> 4. **The CB creates base money by EXPANDING its balance sheet** — its new asset is a **claim on the TSY**
>    (money-financing) OR **CB-held bonds** (OMO, deferred). (Money-financing AND OMO both create reserves — bond
>    purchase by the CB is not the *only* base-money op.)
>
> **A bond has THREE values — each used in exactly one place (the round-3 fix):**
> **face** → the **bond identity** (`Σ holdings@face = bonds_outstanding`); **book / carrying value** → the
> **bank-money invariant** (`ΣD − ΣL − Σ bank-bonds@book = M₀`, since a bank creates deposits = the BOOK price it
> paid); **market value** → **wealth / welfare / bank `economic_capital`** (duration/SVB) only. **The master NFA
> invariant uses nominal/book, NEVER market** (else a rate move makes NFA jump on revaluation, which is not a flow).
> **v12.1/v12.2 use ONE-PERIOD PAR bonds ⇒ face = book = market = x** (they coincide; no `p/x` confusion); the
> three values only diverge at **v12.3** when multi-period bonds give `market = f(rate) ≠ book` (duration).

---

## The account + instrument structure

Split the consolidated `GOV` into two agents; add two overlays alongside the existing deposit ledger:

- **TSY (Treasury)** — a deposit-ledger account (replaces `GOV`; may go negative, like GOV did). Taxes in, spends
  out, pays coupons. Issues bonds (a liability tracked outside ΣD).
- **CB (Central Bank)** — holds the **reserve** liability (banks' reserves) and the **bond/claim** assets. Its
  settlement node already exists (v11.4 routed `GOV`→`CB`). CB equity = assets − reserve liability.
- **⚠ `D_TSY` vs `TGA` are the SAME cash, seen from two sides — NOT two Treasury assets** (the round-4 note): the
  Treasury's spendable cash is ONE quantity; `D_TSY` is its **deposit-ledger** face and `TGA` is its **mirror on
  the reserve-settlement side** (the CB's liability to the TSY). A bond sale credits it once; do not add it to both
  a "TSY cash" and a "TGA" as if they were separate — the tables move `D_TSY` (deposit side) and `TGA` (reserve
  side) as the two legs of the SAME event, never as two independent balances to sum into government net worth.
- **Deposits** (ΣD) — the existing A5 ledger, unchanged in structure.
- **Reserves** — the v11.4 overlay, but now **issuable/retirable** by the CB (no longer a conserved constant).
- **Bonds** — a NEW overlay: `bond_holdings[holder] → face`, plus a price and cohorts (Stage v12.3).

### The CORRECTED identities (after review round 2 — the key realisation)

**A bank buying a government bond CREATES money, exactly like a bank loan** (the govt spends the proceeds ⇒ the
recipient's deposit is created, offset by the bank's new bond asset). So the deposit invariant EXTENDS to include
bank-held bonds; household bonds are asset swaps (deposit↔bond, money-neutral). The gates:

1. **Deposit invariant.**
   - **v12.1 (households only): `ΣD − ΣL = M₀` — UNCHANGED.** A household bill purchase is a deposit↔bond swap
     (D_buyer −p, D_TSY +p; then TSY spends), no money created ⇒ the original A5 holds exactly.
   - **v12.2+ (banks hold bonds): `ΣD − ΣL − Σ(bank bonds @BOOK) = M₀`** — i.e. `ΣD = M₀ + ΣL + Σ bank-bonds@book`
     (banks create deposits by lending AND by buying govt debt, at the BOOK price paid). Bank bonds join loans as
     money-creating. (@book, not face, not market — the round-3 fix.)
2. **CB balance sheet (reserves are a CB LIABILITY, now variable; needs the TGA):**
   `CB assets (cb_bonds + cb_claim_on_TSY) = Σ bank reserves + TGA + CB_equity`, where **TGA** = the Treasury's
   account at the CB (a reserve-side transit account: a bond buyer's reserves flow bank→TGA, then TSY spending
   flows TGA→recipient bank). New paired primitives `issue_reserves`/`retire_reserves` move total reserves AND a
   matching CB asset (`cb_claim_on_tsy` on money-financing; `cb_bonds` on OMO, deferred).
3. **Bond identity:** `Σ bond_holdings (households + banks + CB) = TSY bonds_outstanding`.
4. **MASTER invariant (always holds, mix-independent) — at NOMINAL/BOOK, never market:** `private-sector NFA
   (ΣD_priv − ΣL_priv + private bond holdings @book) = genesis M₀ + cumulative deficit = government total net
   liability`. The single-number M₀ is a special case (v12.1); a **monetising redemption** (printing reserves to
   redeem a bank bond) correctly *raises* base money (moves debt bond→money) — so the master gate is this NFA
   identity, not "M₀ = const". (Market-value revaluations move WEALTH, not NFA — they must not enter this gate.)

### The six bookings (double-entry table — the review's requested deliverable)
Signs are Δ. `D_x` = deposit-ledger balance; `R_x` = a bank's reserves; `TGA` = Treasury's account at the CB;
`cb_claim` = CB claim on TSY; `Bd_x` = bond holdings; `Bout` = TSY bonds outstanding. **One-period PAR bond:
face = book = market = x**, coupon `c = r·x` paid at maturity (financed into the deficit). No `p`/`x` split until
v12.3. Every reserve movement is shown (nothing is `—` where RTGS must settle).

| # | operation | deposits | reserves / TGA / cb-claim | bonds@face | Bout | invariant |
|---|---|---|---|---|---|---|
| a | TSY **money-financed** spend x | D_TSY −x, D_recip +x | cb_claim +x, TGA +x→0, R_recip-bank +x | — | — | ΣD 0 ✓ |
| b | **household** buys new bond (v12.1) | D_Hb −x, D_TSY +x | R_Hb-bank −x, TGA +x | Bd_H +x | +x | ΣD 0, no bank bond ✓ |
| c | **bank** buys new bond (v12.2) | D_recip +x *(created when TSY spends)* | R_bank −x, TGA +x→0, R_recip-bank +x | Bd_bank +x | +x | ΣD +x = Σbank-bond@book +x ✓ |
| d | coupon c to a holder | D_holder +c, D_TSY −c | TGA −c, R_holder-bank +c | — | — | ΣD 0 ✓ (c adds to the deficit → refinanced) |
| e | redemption x, **household**-held | D_H +x, D_TSY −x | TGA −x, R_H-bank +x | Bd_H −x | −x | ΣD 0 ✓ |
| f | redemption x, **bank**-held (money-fin.) | — | cb_claim +x, R_bank +x | Bd_bank −x | −x | Σbank-bond −x ⇒ base money +x (monetised — correct) |
| g | **bank buys bond from a HH** (v12.3+; **restrict to own depositor first**) | D_Hseller +x *(created)* | — *(intra-bank; cross-bank ⇒ settle)* | Bd_bank +x, Bd_H −x | — | ΣD +x = Σbank-bond@book +x ✓ (needs `bank_buy_security`) |

**Sterilisation is already visible in v12.1:** bill-financing (row b+spend) leaves **net bank reserves flat**
(drained from the buyer's bank, added to the recipient's), whereas money-financing (row a) **grows** them ⇒ high
`bond_finance_frac` ⇒ reserves stay ~M₀ ⇒ scarce ⇒ the interbank keystone is **testable in v12.1**, before the
bank balance sheet.

### Bank ECONOMIC capital (the review's #3/#4)
A bank's loss-absorbing equity used by the leverage cap, the failure test, AND the run health signal becomes:

> `economic_capital(bank) = ledger.balance(bank) + Σ (bond_MTM − bond_cost)`  (unrealised bond P&L)

- Buying a bond leaves `ledger.balance` (equity) untouched (it was paid with reserves) — correct: HQLA doesn't
  thin capital.
- **At par / no-duration (v12.2): MTM = cost ⇒ economic_capital = ledger.balance ⇒ constraint behaviour
  unchanged** — bonds merely park excess reserves.
- **With duration (v12.3): a rate HIKE ⇒ MTM < cost ⇒ economic_capital thins ⇒ the SVB channel is actually read**
  by leverage/failure/runs (not just drawn on the plot).

---

## The sterilisation mechanism — precise, and PRE-REGISTERED (the review's #5)

Per tick, deficit `D` = spending − taxes **+ coupon bill** (coupons are a fiscal expense — the review's #7). A
fraction `bond_finance_frac = f` is bond-financed (private buys bonds → reserves drain to CB), `(1−f)` money-
financed (CB issues reserves to TSY → `cb_claim_on_tsy` ↑). Over time:

> `Σ bank reserves ≈ M₀ + (1 − f)·(cumulative deficit)`

So higher `f` **lowers the reserve LEVEL** (not just its growth). **Pre-registered (verify, don't assume):** only
`f` near 1 (or an explicit **stock operation** — issuing bonds to retire the CB's accumulated claim / soak the
existing reserve stock) drives reserves **scarce** enough that peak intraday overdraft, interbank volume, and run
liquidity-suspension go from ~0 to **positive**. Swept + reported honestly; if `f<1` never reaches scarcity, that
is itself the finding (⇒ a stock-drain lever, or OMO in v12.4).

---

## Build stages (rigorous re-staging, per the review; each gated + bit-identical when off)

- **v12.0 — account SEPARATION, no bonds.** Add `TSY`, `CB`; abstract every hard-coded `"GOV"` into a
  `fiscal_account` helper. `bonds=False` ⇒ TSY behaves exactly as GOV ⇒ **bit-identical to v11.5**. (Pure refactor
  + the CB balance-sheet scaffolding; validates the three-identity gates as no-ops.)
- **v12.1 — HOUSEHOLDS hold one-period PAR T-BILLS (`coupon = 0` first).** Only households buy short PAR bills:
  **issue price = redemption face = `x`, face = book = market = `x`** — NO discount, NO `p`/`x` split, NO duration
  (coupon and discount/duration arrive in v12.2/v12.3). Validates issuance, redemption, the bond identity, private
  NFA, and (bonus) **the sterilisation keystone itself** — bill-finance leaves bank reserves flat vs money-finance
  growing them, so raising `f` should make reserves scarce and the interbank market activate, testable HERE without
  the bank balance sheet. Deposit-A5 holds exactly (household bills are money-neutral swaps).
- **v12.2 — BANK balance-sheet expansion (money creation).** Banks buy bonds with **reserves** (asset swap, equity
  unchanged); this CREATES deposits ⇒ the invariant extends to `ΣD − ΣL − Σ bank-bonds = M₀`; add the TGA + the CB
  balance-sheet gate; `economic_capital = ledger.balance + bond-P&L` wired into the leverage cap + failure. Coupon
  bonds (financed into the deficit) can arrive here.
- **v12.3 — traded bond MARKET + DURATION.** Medium/long cohorts, price = f(policy rate), MTM + unrealised P&L
  feeding `economic_capital`; households + banks trade (extend the v6 portfolio machinery: deposits ↔ equity ↔
  bank-equity ↔ bonds). The SVB channel + its interaction with v11.5 runs.
- **v12.4 (deferred) — CB OMO / QE / LoLR.** `issue_reserves`/`retire_reserves` against `cb_bonds`; QE re-floods
  reserves ⇒ **re-latents** interbank (the post-2008 story); LoLR funds a bank being run ⇒ fully activates the
  run-suspension.

---

## New ledger primitives, config, metrics, tests
- Ledger: bond tokens (`bond_holdings`, face/price/cohort), a **TGA** node, `issue_reserves`/`retire_reserves`
  (variable total + CB-asset sync), a `bank_buy_security` primitive (v12.3, money-creating), a `fiscal_account`
  indirection, and asserts for the master NFA invariant + CB balance sheet + bond identity.
- Config (default-off ⇒ bit-identical): `bonds`, `bond_finance_frac`, `bond_coupon` (~policy rate),
  `bond_maturity`/cohorts, `bond_theta` (hh target bond share), duration/pricing params.
- Metrics (the review's #5 — RE-DEFINE the fiscal ones for the split): `gov_debt = |TSY deposit-debt| + bonds_out +
  cb_claim_on_tsy − TGA` (⚠ subtract `TGA`, the TSY's cash — it's a Treasury ASSET, so it must NOT inflate net
  debt; and `D_TSY` and `TGA` are the same cash from two sides — do not add both); `private_nfa = ΣD_priv −
  ΣL_priv + private bond holdings@book` (the master invariant's LHS); plus `bonds_outstanding`, `gov_interest_bill`,
  `bank/hh/cb_bond_holdings`, `cb_equity`, `TGA`, `bank_reserves_total` (watch FALL), `bank_bond_mtm_loss`,
  `bank_economic_capital`, + re-surface `interbank_volume` / `peak_intraday_overdraft` (watch turn POSITIVE).
- `test_v12_bonds.py`: off ⇒ v11.5 bit-identical; **the master NFA invariant** + the CB balance-sheet identity +
  the bond identity hold through issuance/coupon/redemption/trading/duration (incl. a monetising redemption
  correctly raising base money); **a single bond issuance's proceeds do NOT increase two forms of government net
  asset at once** (the `D_TSY`/`TGA` double-count guard); the **sterilisation activation** (interbank turns positive
  as `f`→1, testable from v12.1); duration losses thin `economic_capital` on a rate hike. `plot_v12.py`.

## Note carried from v11.5
Sims are ~5–10× slower (RTGS + bank-stock market); bonds add a portfolio/market pass. Keep test horizons short.
