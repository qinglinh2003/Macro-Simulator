# PLAN v12.3 — traded bond MARKET + DURATION + coupon + bank balance sheet (the SVB stage)

Builds on v12.1-fix (bill rollover). Scope chosen by the user: **do the FULL v12.3 in one shot**, folding in
v12.2's bank-bond-holding + `economic_capital`. This is the heaviest-accounting stage; it is built in **gated
sub-steps A→D**, each with the conservation gate green before the next. `bonds=False` (and every new lever at its
off-default) ⇒ **bit-identical to v11.5**; `Config.v12()` with the new levers off ⇒ bit-identical to the v12.1-fix
economy (the rollover bills still work).

---

## 0. What changes vs v12.1 (one-period PAR bill, face=book=market)

v12.1 bonds are a `{holder → face}` scalar. v12.3 gives bonds **maturity + coupon + a market price**, so the
**three values finally diverge**:

- **face** `f` — redemption principal. The **bond identity**: `Σ_holders face = bonds_outstanding` (invariant under
  trading/coupon; changes only on issue/redeem).
- **book** `b` — the amortised **cost** at which a holding is carried. For the **bank-money invariant** only bank
  holdings matter: `ΣD − ΣL − Σ(bank bonds)@book = M₀`. A bank creates a deposit = the price it pays ⇒ book = that
  price. Household book is irrelevant to money (their bonds are pure asset swaps).
- **market** `m = price(remaining_maturity, policy_rate, coupon)` — used ONLY for **wealth / welfare / bank
  `economic_capital`** (the duration/SVB channel). Never in a conservation identity.

**Master NFA stays at BOOK/nominal, never MTM:** `private_NFA = ΣD_priv − ΣL_priv + Σ(private bonds)@face =
M₀ + cumulative_deficit = govt total net liability`. (MTM P&L is a private wealth *revaluation*, not a change in
net financial claims — it nets to zero against the issuer, so it must NOT enter the master identity.)

### Bond data model
`self._bonds: list[Bond]` where `Bond = {holder_id, face, cost, matures_at}` (cohort = a lot). `bonds_outstanding
= Σ face`. `_bond_holdings[holder] = Σ face` kept as a fast index (back-compat with v12.1 metrics/consumption).
One-period bills are just `matures_at = t+1`. Multi-period arrive with `bond_maturity > 1`.

### Pricing (flat-yield PV, the minimal duration engine)
`price(face, n, r, c) = c·face·Σ_{k=1..n}(1+r)^-k + face·(1+r)^-n`, `n = matures_at − t` (periods left), `r` =
current policy rate, `c` = coupon rate. At `n=1, c=r` ⇒ price=face (PAR bill, v12.1 bit-identical path). A rate
**hike** (`r↑`) with `n>1` ⇒ `price < face` ⇒ **MTM loss** (the duration/SVB channel); longer `n` ⇒ bigger loss.

---

## 1. Operation → ledger deltas (each row states the identity it preserves)

Notation: `D_x` deposit of x, `Bk` = a bank, `H` = a household, `TSY`/`CB` fiscal/reserve nodes. RTGS reserve leg
shown where a deposit crosses banks. `f` face, `P` price paid, `b` book.

| # | event | deposits (A5) | reserves (RTGS) | bond tokens | invariant preserved |
|---|-------|---------------|-----------------|-------------|---------------------|
| a | **issue** bill to H (primary, at par) | `D_H −f`, `D_TSY +f` | R: H-bank → CB | H bond +f (cost f) | ΣD 0; face identity +f = outstanding +f |
| b | **redeem** matured bond of H | `D_H +f`, `D_TSY −f` | R: CB → H-bank | H bond −f | ΣD 0; face −f |
| c | **coupon** c·f to holder | `D_holder +cf`, `D_TSY −cf` | R: CB → holder-bank | — | ΣD 0; coupon adds to deficit (refinanced) |
| d | **H buys bond from H′** (secondary) | `D_H −P`, `D_H′ +P` | R: buyer-bank → seller-bank | face f moves H′→H (cost P for H) | ΣD 0; face identity unchanged (moved) |
| e | **Bank buys bond from H** (money-creating) | `D_H +P` *(created)* | — (bank credits its own depositor; cross-bank ⇒ settle) | face f moves H→Bk, bank book +P | `ΣD +P` **=** `Σ(bank bonds)@book +P` ⇒ `ΣD−ΣL−Σbankbonds` = M₀ ✓ |
| f | **Bank sells bond to H** (money-destroying) | `D_H −P` *(destroyed)* | — | face f moves Bk→H, bank book −(its cost) | ΣD −P = Σ(bank bonds)@book −P ✓ |
| g | **bank's bond matures** | `D_TSY −f`, bank money +f *(destroyed on redemption: −book, +f cash… see note)* | R: CB → bank | bank bond −f | face −f; bank swaps bond asset for reserves |

**Note on (e)/(g) and the ledger:** the ledger's A5 is `ΣD − ΣL = M` **by construction** (3 mutators). Bank
money-creation-against-a-bond would break that unless the ledger KNOWS the bond asset. So add a ledger-level
`_bank_securities` total + primitives `bank_buy_security(seller, amount)` (credits `D_seller += amount`,
`_bank_securities += amount`) and `bank_release_security(amount)` (the reverse on sale/maturity). The gate becomes
`ΣD − ΣL − _bank_securities = M`, still exact by construction. Household bond trades are ordinary `transfer`s
(A5 already holds) — households are NOT in `_bank_securities`.

---

## 2. Behaviour (decision rules, all opt-in)

- **Coupon** (`bond_coupon > 0`): paid at maturity per row (c). Financed into the deficit (a fiscal expense — so
  higher `bond_coupon` raises `gov_debt` and thus next-tick issuance; the review's #7). Gives bonds a REASON to be
  held overnight (fixes the v12.1-fix "thin residual" — a *meaningful* stock can now form).
- **Household portfolio** (`bond_theta > 0`): each H targets `bond_theta` of wealth in bonds (extend the v6
  deposits↔equity machinery to deposits↔equity↔bank-equity↔**bonds**). Buys from idle deposits, sells when
  over-weight or cash-short. Bonds enter the B1 wealth term at **market** (they are liquid — sellable — so the
  freeze cannot return; this is the v12.1-fix guard restated).
- **Bank portfolio** (`bank_bond_theta > 0` or reuse a share): banks buy bonds with **reserves / money creation**
  when they have excess reserves and the bond yield beats the reserve rate ⇒ the **STRONG sterilisation drain**
  (v12.2's point). This is where `Σ bank reserves` finally FALLS materially.
- **Secondary market**: a simple groping/priced market — households + banks trade at `market` price; face moves,
  money settles (rows d/e/f). Reuse the v6 CLEARING pattern (pro-rata rationing so money+face conserve).

## 3. `economic_capital` + the SVB channel (v12.2 hook, activated by v12.3 duration)

`economic_capital(bank) = ledger.balance(bank) + Σ_lots(market(lot) − cost(lot))` (unrealised bond P&L). Wire it
into **exactly** the two places bank capital is read:
- `_bank_capacity` / exposure limit (leverage cap uses economic capital);
- the insolvency trigger in `_resolve_bank_failures` (`economic_capital < −EPS`, not `ledger.balance`).
- (optionally the run-health `book_h`.)

When no bank bonds ⇒ `economic_capital = ledger.balance` ⇒ **bit-identical**. With duration, a rate hike thins it
⇒ crunch / failure / feeds v11.5 runs — **the 2023-SVB channel, emergent**.

---

## 4. Gates (run after EACH sub-step; the hard ones are pre-registered)

- **Off ⇒ bit-identical**: `bonds=False` ⇒ v11.5; `Config.v12()` + new levers off ⇒ the v12.1-fix economy.
- **A5 / money**: `ΣD − ΣL − _bank_securities = M₀` every tick (~1e-6 rel).
- **Bond identity**: `Σ face = bonds_outstanding` through issue/coupon/redeem/**trade**/maturity.
- **Master NFA (at book/face, NOT MTM)**: `private_NFA = M₀ + cumulative_deficit`. Explicitly assert MTM swings do
  NOT move it.
- **No double-count**: a single issuance's proceeds don't raise two govt net-asset forms (`D_TSY`/`TGA`).
- **CB balance sheet** (once the CB holds anything): `cb_bonds + cb_claim_on_tsy = Σ bank reserves + TGA + cb_equity`.
- **PRE-REGISTERED #1 (duration/SVB)**: with `bond_maturity>1`, a **policy-rate hike** ⇒ `bank_bond_mtm_loss > 0`
  and `bank_economic_capital` falls below `ledger.balance`; a big enough hike ⇒ ≥1 extra failure vs no-duration.
  Refute: if MTM loss stays 0 under a hike, the pricing/`economic_capital` wiring is dead.
- **PRE-REGISTERED #2 (no re-freeze)**: with coupon + `bond_theta` ON at `frac=0.9`, the bond **stock grows
  materially** (≫ the 33k thin residual) **AND** late-sample `u` stays ≈ `frac=0` (≲0.02). This is the guard the
  v12.1-fix teed up: bonds become a real asset WITHOUT re-freezing the economy (because they are liquid).

## 5. Config levers (all off-default ⇒ bit-identical)
`bond_coupon` (≈ policy rate), `bond_maturity` (periods; 1 ⇒ v12.1 bill), `bond_theta` (hh target bond share),
`bank_bond_appetite` (bank excess-reserve → bond share), `bond_price_sensitivity` (duration knob, or derive from
maturity). `Config.v12()` keeps frac 0.9; a `Config.v123()` (or v12 overrides) turns coupon+maturity+theta on.

## 6. Metrics
`bond_face_total` (=outstanding), `bond_book_total`, `bond_market_total`, `bank/hh/cb_bond_face`,
`bank_bond_mtm_loss`, `bank_economic_capital` (min/mean), `gov_interest_bill`, re-surface `interbank_volume` /
`peak_intraday_overdraft` (watch them turn materially positive as the bank drain bites).

## 7. Build order (each gated)
A. data model + pricing + coupon (household one-period first, then `bond_maturity>1`) → gate.
B. household portfolio (`bond_theta`) + secondary market → gate + pre-registered #2.
C. bank balance sheet (`bank_buy_security`, money creation, `_bank_securities`, economic_capital → leverage/
   failure) → extended-invariant gate.
D. SVB: duration → `economic_capital` → failure/runs → pre-registered #1.
Then metrics, tests, diagnostic (`diagnostic_v123.png`), DESIGNDOC §39.5, changelog, memory, full regression.
