# PLAN v11 — MULTI-BANK: "loan-book banks", endogenous bank failure & credit crunch

Status: **design draft for approval.** Cumulative on v10.2. `n_banks=1` ⇒ bit-identical to v10.2 (the whole
v2–v10.2 chain is preserved as the one-bank special case).

---

## 0. Converged scope (from discussion)

**Goal = financial fragility / endogenous crises**, NOT monetary policy (which is DEFANGED here — fiscal
dominance + the JG absorb the rate; §33). So we build the CHEAP half and skip the reserve/settlement machinery:
- **Deposits stay a single global pool** — payments unchanged, NO interbank settlement, conservation barely
  touched. Only the **loan book** is partitioned among banks.
- **Banks are loan portfolios with a capital buffer.** A bank's capital *is its own deposit balance* (retained
  interest grows it, write-offs shrink it). Capital exhausted ⇒ **failure**.
- **Contagion runs through the REAL economy** (a failed/crunched bank's borrowers lose credit → default →
  drag others), not through interbank exposures. Interbank lending has no object without a reserve tier — deferred.
- **Heterogeneity is the crisis spark**: banks differ in **risk appetite** (leverage), so failure is *selective*.

## 1. What already exists (audited) vs what's new
**Exists (reused):** the single `BANK` account absorbs all write-offs (`write_off(borrower, BANK, amt)`,
A5-conserving); interest income collected + redistributed to households by deposits (v10.1); per-borrower credit
limits (firm κ·NW, household DTI). **The bank never fails** because one account holds the whole retained buffer.
**New (the last link):** partition into **N bank accounts**, each with a **finite** capital buffer, a
**risk-appetite** parameter, a **lending capacity constraint**, a **failure + resolution** rule, and
**borrower migration** when a bank can't lend.

## 2. The design — N loan-book banks

- **N bank accounts** `BANK_0..BANK_{n-1}` in the ledger; each has a **deposit balance = its capital** (equity).
  `n_banks` config. `n_banks=1` ⇒ one BANK ⇒ current model exactly.
- **`bank_of[borrower_id]`** — each firm/household borrower is assigned to one bank (genesis + on entry).
  Assignment: random, or by-size (by-size makes "too big to fail" emerge). Config `bank_assignment`.
- **Interest & write-offs go to the borrower's OWN bank:** borrower pays `r·debt` to `BANK_k`; its defaults are
  written off against `BANK_k` (existing `write_off`, now targeting the right bank). So each bank's capital =
  genesis capital + its retained interest − its write-offs. **Redistribution to households is unchanged** (Σ over
  banks of `ρ·interest` by deposits = exactly v10.1 at any n).
- **Capital / leverage constraint (the crunch, opt-in):** a bank lends only while `loan_book_k ≤ κ_bank ·
  capital_k`. When write-offs erode `capital_k`, the bank hits its limit and **cannot make new loans** →
  its borrowers are credit-crunched. `bank_capital_constraint=False` ⇒ banks lend freely ⇒ pure partitioning
  (a clean intermediate: multi-bank, no crunch, still bit-identical-ish in aggregate).
- **Heterogeneity:** `κ_bank` drawn per-bank from a distribution (`bank_leverage_mean` ± `bank_leverage_disp`).
  Aggressive (high κ) banks grow fast in booms, fail first in busts — selective failure.
- **Failure:** `capital_k < 0` (write-offs would overrun the buffer) ⇒ insolvent ⇒ **resolution** (§5).
- **Borrower migration (competition, ~free):** a borrower whose bank is crunched/failed seeks credit from a bank
  with capacity; if none has room ⇒ genuine credit crunch (no loan → real effects). This IS bank competition on
  the lending side + the crunch mechanism, emergent from the capital constraint.
- **Contagion (real-economy):** crunch → borrower can't pay wages/roll debt → bankruptcy → its write-offs hit
  its bank → that bank's capital drops → more crunch. The crisis spiral, no interbank needed.

## 3. Bit-identicalness & conservation
- `n_banks=1` ⇒ a single BANK account, no migration, no cross-bank anything ⇒ **bit-identical to v10.2**.
- **A5 is barely touched:** write-offs use the existing conserving primitive; N bank accounts are just part of
  ΣD; `ΣD − ΣL = M₀` holds unchanged. Bank capital is not a new money tier — it is a bank's own deposit balance.
- **Genesis capital (a design detail):** carve a small `bank_capital_pool` from M₀, split among banks (like the
  founder pool) — conservation-clean initial allocation. (Alt: banks start ~0 and accumulate before the
  constraint is enabled.) Proposed: a modest pool so banks start solvent but *finitely* buffered.

## 4. The two rules we flagged — proposed defaults
- **R1 — risk appetite acts on the LEVERAGE limit** `κ_bank` (capital-adequacy / Basel-like): `loan_book ≤
  κ_bank·capital`. Cleanest, standard, and directly drives boom-over-leverage → bust-failure. (Reuses the firm
  `κ` idea.) Alternatives (borrower-risk screening, pricing) are refinements.
- **R2 — resolution = "migrate the performing, write off the bad".** On failure: `BANK_k`'s still-solvent
  borrowers are reassigned to banks with capacity (merger-like); if none, they're crunched (liquidation-like);
  its bad debt is written off (existing machinery); the failed bank is removed. No depositor loss (deposits
  global). Simple, conserving, and the migration/crunch split tunes how violent the crisis is.

## 5. Levers (Config + Policy; `n_banks=1` ⇒ bit-identical)
- **`n_banks`** (Config) — number of banks. 1 ⇒ current.
- **`bank_capital_constraint`** (Policy — a macroprudential dial) — enable the leverage limit / crunch. Off ⇒
  banks lend freely (partition only).
- **`bank_leverage_mean`, `bank_leverage_disp`** (Config) — the risk-appetite distribution (heterogeneity).
- **`bank_capital_pool`** (Config) — genesis bank equity carved from M₀.
- **`bank_assignment`** (Config) — random / by-size.
- **`bank_capital_ratio`** (Policy) — a *system* capital-adequacy floor the government/regulator can set (a real
  macroprudential lever — connects banks to the existing Policy control surface).
- `Config.v11()` = v10.2 + `n_banks≈5`, `bank_capital_constraint=True`, anchored leverage mean/disp.

## 6. Pre-registered hypotheses (§0-ii)
| # | Hypothesis | Expected | Falsifier |
|---|---|---|---|
| H1 | Partitioning the loan book (constraint off) ≈ aggregate-neutral | macro ≈ v10.2 | large drift with n_banks alone |
| H2 | Finite per-bank capital + heterogeneity ⇒ **endogenous bank failures** | some banks fail in downturns | none ever fail |
| H3 | Failure ⇒ **credit crunch** ⇒ amplified recessions (real-economy contagion) | deeper/longer downturns vs v10.2 | no amplification |
| H4 | Aggressive (high-κ) banks fail SELECTIVELY | failures concentrated in high-κ banks | random/uniform failure |
| H5 | Richer credit cycles / fatter tails | T7 stronger, T5 fatter (crises) | unchanged |
| H6 | A `bank_capital_ratio` floor (macropru) trades fewer crises for less credit/output | fewer failures, lower mean output | no tradeoff |

## 7. Build order
1. `config`: `n_banks`, `bank_capital_constraint`, leverage dist, `bank_capital_pool`, `bank_assignment`; `Config.v11()`.
2. `economy/agents`: N `BANK_k` accounts + genesis capital; `bank_of` assignment (genesis + on firm entry).
3. Route interest + `write_off` to each borrower's `BANK_k`; confirm redistribution total unchanged.
4. The capital/leverage constraint at loan origination + borrower migration when crunched (opt-in).
5. Failure detection + resolution (migrate performing / write off bad / remove bank).
6. `metrics`: per-bank capital, leverage, `n_bank_failures`, credit-crunch measure, bank-size distribution.
7. `tests/test_v11_banks.py`: n_banks=1 ⇒ bit-identical; A5 (write-offs across N banks still conserve);
   constraint-off multi-bank ≈ aggregate; a forced downturn ⇒ a high-κ bank fails; failure ⇒ measurable crunch.
8. Validate: n_banks=1 regression → constraint-off neutrality (H1) → failure/crunch battery (H2–H4) → §4 (T7/T5) → diagnostic.
9. DESIGNDOC §35.

## 8. Optimizable / deferred modules (the menu, roughly by cost)
**Cheap refinements (same architecture):**
- **By-size assignment ⇒ "too big to fail"**, bank-sector concentration (a T6-for-banks / Gibrat dynamic).
- **Rate competition** — banks post different loan rates (heterogeneous credit pricing).
- **Borrower-risk screening** — risk appetite acts on *who* a bank lends to, not just leverage.
- **Deposit insurance (fiscal)** — government covers a failed bank's hole; a real fiscal-cost lever.
- **Bank dividends to shareholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (need the reserve tier — a separate v12 arc; value here is questionable, §33):**
- **Deposit partitioning** (deposits become bank-specific liabilities) → enables:
  - **Interbank market / 拆借** (liquidity management + a fast contagion channel);
  - **Bank runs** (depositors flee a weak bank);
  - **Deposit-side competition** (savers chase better banks).
- **Reserves + central-bank money tier** → **reserve requirements, LoLR, OMO, QE** — real monetary quantity
  tools. (Deferred: fiscal dominance makes their value here doubtful — revisit only if a non-dominated regime
  is of interest.)
