# Implementation plan — v3 (banks + endogenous money)

Implements DESIGNDOC §12 (v1.3). Companion engineering plan, not part of the axiom set.
Scope inherits v2 except where §12 extends it. Status: **ready to build, pending sign-off.**

---

## 0. Architecture decision — extend in place (as v2), flag-gated

Same discipline that worked for v2: one codebase, v3 opt-in behind a config flag
(`bank_enabled` / `Config.v3()`). v1, v2, and v2.5 remain **regression guards** — bit-identical
when banks are off. The single most important lever making this safe:

> **A5 reduces to M0 when there is no credit.** The ledger's conservation gate becomes
> `sum(deposits) − sum(loans) = M`. With no loans (v1/v2/v2.5), `sum(loans)=0`, so it is exactly
> `sum(deposits)=M` — the old gate, unchanged. Turning the gate into its A5 form therefore breaks
> nothing and needs no v1/v2 branching.

Rejected: a separate `BankEconomy`/`v3` module (two loops drift — the §0 parsimony argument).

---

## 1. The accounting core — A5 made structural (the heart of v3)

v3's correctness rests on one thing: **money creation must be as unbreakable-by-construction as
money movement was.** In v1/v2, `transfer` was the *only* mutator and A1/M0 held by construction.
v3 adds exactly one more mutator: `create_loan` (and its inverse `repay`).

**Ledger extended to two inside instruments.**
- `deposits[id]` — as today (the current `_bal`), the only thing `transfer` touches.
- `loans[id]` — new: debt owed by a borrower (≥ 0). The bank's loan *assets* = Σ borrower debt.
- Gate (A5): `assert sum(deposits) − sum(loans) == M` every tick. (Reduces to M0 for v1/v2.)

**The two new primitives (money creation is structural, §7.6 discipline):**
```
create_loan(borrower, Λ):   deposits[borrower] += Λ ;  loans[borrower] += Λ
repay(borrower, Λ):         deposits[borrower] -= Λ ;  loans[borrower] -= Λ   (Λ ≤ debt, ≤ cash)
```
Both move `sum(deposits)` and `sum(loans)` **together**, so `sum(D) − sum(L)` is invariant *by
construction* — A5 can't be violated without bypassing them. `create_loan` has **no source
account** (that is the point — money is created); it is the only path that grows the money stock.
Agents get no direct write access to deposits *or* loans (as before).

**Interest is NOT a loan operation.** Interest is an ordinary `transfer(borrower, bank, r·L)` —
it redistributes existing deposits (bank's income), changing no one's net worth in aggregate and
leaving `sum(D) − sum(L)` untouched. Keep the two strictly separate: principal ↔ `create_loan`/
`repay` (changes money stock); interest ↔ `transfer` (redistributes). Mixing them is the classic
credit-accounting bug.

**Reserves are conceptual in minimal v3.** The bank "holds M in reserves" so its balance sheet is
consistent (§A5), but with a single bank and no cash/interbank settlement, reserves never move and
never enter the gate. Track `bank.reserves = M` as a documented constant; do **not** build a
reserve-transfer machinery (parsimony). The gate `sum(D) − sum(L) = M` is complete on its own.

**Worked example (A5 holds throughout).** Firm borrows Λ, pays wages w·N from it, sells, pays
interest rΛ, amortizes aΛ:
```
create_loan:   D_f += Λ, L_f += Λ        ->  ΣD−ΣL unchanged
wages:         transfer(f → households)   ->  ΣD−ΣL unchanged (deposits move)
interest:      transfer(f → bank, rL)     ->  ΣD−ΣL unchanged
amortize:      repay(f, aΛ): D_f−=aΛ,L_f−=aΛ -> ΣD−ΣL unchanged
```

---

## 2. Module-by-module changes

| module | change |
|---|---|
| `ledger.py` | Add `loans` dict + `create_loan`/`repay` primitives + `debt(id)`. Change `assert_conserved` to the A5 form `sum(deposits) − sum(loans) == M` (bit-identical for v1/v2). Overdraft/negative guards extended to loans (can't repay more than owed or more than cash). |
| `config.py` | Add `bank_enabled` + `Config.v3()`; params `kappa`, `r` (interest/tick), `amort`, `d_bank0` (bank genesis deposits, 0), bank ownership. v1/v2 configs unchanged. |
| `agents.py` | New `Bank` dataclass (id, rho, reserves=M, per-tick interest income scratch). Firms need no new field — debt is read from `ledger.debt(f.id)` (single source of truth). Bank owned equally by households (dividends). |
| `behavior.py` | New `plan_credit(firm, ledger, p_k_est)` (B6: gap = max(0, wage-bill + investment outlay − deposits)); `grant_credit(firm, requested, ledger, kappa)` (B7: NW=D−L, cap κ·NW−L); `service_debt(firm, ledger, r, amort)` (interest transfer + amortize repay, defer shortfall). |
| `economy.py` | Add **Phase 1.5 (credit)** before markets and **Phase 4.5 (debt service + bank distribution)**; A5 gate in Phase 5; bank agent wired into settlement (its profit = interest income; pays dividends to close the interest loop). |
| `metrics.py` | New series: **broad money `sum(deposits)`** (the headline — must be *alive*), total credit `sum(loans)`, net worth (=M check), aggregate leverage, credit split by purpose (investment vs wage), interest paid, new loans, repayments, bank deposits. |
| `diagnostics.py` | v3 dashboard: broad money & credit over time, leverage, credit-by-purpose, net worth (flat at M), plus the v2 panels. |
| `runlog.py` | Add v3 summary keys (broad money, credit, leverage). Works as-is otherwise. |
| `run_v3.py` | v3 entrypoint: run, log, plot, sweep κ (the credit-cycle knob), acceptance readout. |

---

## 3. The v3 tick (economy.py)

- **Phase 1 (plan).** As v2 + each firm has its wage-bill target (`w_f·N^d_f`) and desired
  investment `I*` (B5) ready.
- **Phase 1.5 — NEW (credit).** For each firm: `plan_credit` → requested = cash gap over planned
  spending (wages + investment); `grant_credit` (B7 cap); `ledger.create_loan(f, Λ)`. Record the
  loan's split by purpose (allocate Λ pro-rata to the wage vs investment needs). Placed **before
  markets** so credit funds *this* tick's wage bill — this is what relaxes v1/v2 cash-capped hiring.
- **Phase 2 (labor).** Unchanged code — the cash cap `D_f/w_f` now reads deposits *including*
  credit, so hiring capacity rises automatically.
- **Phase 3 / 3.5 (goods / capital).** Unchanged; investment now fundable by credit.
- **Phase 4 (settlement).** Firm profits + dividends + capital commit (as v2).
- **Phase 4.5 — NEW (debt service + bank).** Each firm: interest `transfer(f, bank, r·L)` then
  amortize `repay(f, min(amort·L, cash))`; shortfalls defer (no default). Bank profit = interest
  received this tick; bank distributes `ρ·profit` to households (closes the interest loop — else
  the bank becomes a new sink), retains the rest.
- **Phase 5 (check + record).** Assert **A5** (`sum D − sum L = M`); record broad money, credit,
  leverage, credit-by-purpose, etc.

---

## 4. Key subtleties & guards (explicit, never silent)

1. **A5 ≡ M0 without credit** — the regression safety. Verify v1/v2/v2.5 bit-identical after the
   ledger change (residuals must stay 7.28e-12 on the drain test).
2. **`create_loan` is the only money-creation path.** No agent creates deposits directly. Interest
   ≠ principal (transfer vs create_loan/repay).
3. **No default (v3).** Debt service pays from cash to the extent available; any shortfall
   **defers** (carried, unpenalized). Never force a negative deposit; never auto-liquidate.
4. **Close the interest loop.** The bank *must* distribute (most of) its interest income as
   dividends, or interest becomes a fresh money sink (the fractal drain again). Bank is
   household-owned; dividends flow bank → households.
5. **`p^K` estimate for the investment gap.** At Phase 1.5 the firm doesn't yet know the realized
   capital price, so it estimates the investment cash need with the last observed capital price.
   Over/under-borrowing washes out (excess deposits are held / repaid). Document the estimate.
6. **Credit drawn on *planned* spending.** If hiring or investment is then rationed, the firm
   holds unused borrowed deposits — harmless, repaid via amortization.
7. **κ is the taming knob.** Credit is positive feedback; the first run may be **more volatile or
   divergent than v2**. κ damps it (as λ_I did the accelerator). Divergence with A5 intact is
   calibration, not plumbing.
8. **Bank net worth is not load-bearing in v3.** B7 uses *borrower* net worth (D−L), not bank
   capital. A bank-capital constraint is deferred (v3.1/§12.2). So we don't need the bank's full
   balance-sheet consistency for the mechanics — only the A5 gate.

---

## 5. Build order (each layer green before the next)

1. **`ledger.py`**: add loans + `create_loan`/`repay` + A5 gate → **run v1/v2/v2.5 suites; confirm
   bit-identical** (the regression guard). Unit-test the primitives (create/repay conserve A5;
   guards reject over-repay / negative).
2. **`config.py` + `agents.py`**: `bank_enabled`, `Config.v3()`, `Bank` agent, firm debt access.
3. **`behavior.py`**: `plan_credit` (B6), `grant_credit` (B7), `service_debt` — unit-test B7 cap
   and the debt-service arithmetic.
4. **`economy.py`**: Phase 1.5 + Phase 4.5 + bank distribution + A5 gate. Smoke-test conservation
   (A5) on a short v3 run.
5. **`metrics.py` + `diagnostics.py`**: broad-money / credit / leverage series + v3 dashboard.
6. **`run_v3.py` + acceptance tests + seed-invariance** (large N).

---

## 6. Acceptance (§12.8) + tests

- **Regression:** v1/v2/v2.5 suites bit-identical after the ledger change.
- **A5 conservation:** `sum D − sum L = M` every tick to machine precision (`test_a5_conservation`).
- **Loan primitives:** `create_loan`/`repay` conserve A5; can't repay > owed or > cash
  (`test_credit_primitives`).
- **Broad money is endogenous:** `sum D` is **not** constant over a v3 run (it moves) while
  `sum D − sum L = M` holds — the headline (§12.8): the flat line comes alive.
- **Credit relaxes the cash constraint:** exists a tick where a firm's realized wages/investment
  exceed its pre-credit deposits (read the credit-by-purpose log) — A4's credit term does work.
- **Leverage cap respected:** no firm's debt exceeds `κ·NW` (+tol) (`test_leverage_cap`).
- **Bounded & active:** no divergence; doesn't collapse to permanent depression.
- **Seed-invariance (large N).** A credit cycle, if it appears, is a §4 *observation*, not a gate.

---

## 7. Parameter starting points (tentative; retune after first run)

`κ ≈ 3` (leverage), `r ≈ 0.01`/tick (interest), `amort ≈ 0.1` (principal/tick), bank `ρ` = firm ρ.
Free dials 7 → ~9 (add κ; r/amort if treated free). Per §0-iv, κ pays its way (procyclical
leverage → the §4 credit-cycle target); r is the price of debt.

---

## 8. Open items (confirm before / during build)

- **Bank dividend timing:** distribute interest income in Phase 4.5 (same tick) vs a lag — I lean
  same-tick (simplest, closes the loop immediately).
- **Does the bank hire labor?** No in minimal v3 (no bank wage bill; profit = net interest). Flag
  if we want bank operating costs later.
- **`p^K` estimate source** for the investment gap (last observed capital price) — confirm.
